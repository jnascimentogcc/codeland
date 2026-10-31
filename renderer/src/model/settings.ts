// How the person wants to see the city: pure data with validation (no React, no three.js).
// Applied live, never part of the city model, and kept in the browser between visits.

export type HeightMetric = "loc" | "decisions" | "churn" | "problems";
export type HeightScale = "linear" | "sqrt";
export type ArcMode = "auto" | "selection" | "off";

/** How findings are ranked (see findings.ts `priorityOf`). */
export interface PriorityWeights {
  /** Extra importance of a file per unit of hotspot score (0..1). */
  hotspot: number;
  /** Extra importance of a file per unit of normalized churn (0..1). */
  churn: number;
  /** Extra importance when the file is not covered by tests. */
  uncovered: number;
  /** Multiplier for findings in test files. */
  testFiles: number;
  /** Bonus per extra tool that reports the same problem (at most two count). */
  corroboration: number;
}

export interface Settings {
  height: HeightMetric;
  heightScale: HeightScale;
  /** Multiplies the tallest tower; below 1 flattens the skyline, above 1 exaggerates it. */
  heightFactor: number;
  weights: PriorityWeights;
  arcs: ArcMode;
  /** Bloom intensity: 0 turns the glow off. */
  glow: number;
  idleOrbit: boolean;
  grid: boolean;
  /** Findings listed in the panel. */
  listLimit: number;
}

export const DEFAULT_WEIGHTS: PriorityWeights = {
  hotspot: 2,
  churn: 1,
  uncovered: 0.5,
  testFiles: 0.5,
  corroboration: 0.25,
};

export const DEFAULT_SETTINGS: Settings = {
  height: "loc",
  heightScale: "linear",
  heightFactor: 1,
  weights: DEFAULT_WEIGHTS,
  arcs: "auto",
  glow: 1.1,
  idleOrbit: true,
  grid: true,
  listLimit: 40,
};

export const HEIGHT_METRICS: HeightMetric[] = ["loc", "decisions", "churn", "problems"];
export const LIST_LIMITS = [10, 20, 40, 100];

/** Allowed range of every number, shared by the validation and the sliders. */
export const RANGES = {
  heightFactor: { min: 0.3, max: 2, step: 0.05 },
  glow: { min: 0, max: 2.5, step: 0.05 },
  hotspot: { min: 0, max: 5, step: 0.1 },
  churn: { min: 0, max: 5, step: 0.1 },
  uncovered: { min: 0, max: 3, step: 0.1 },
  testFiles: { min: 0, max: 1, step: 0.05 },
  corroboration: { min: 0, max: 1, step: 0.05 },
} as const;

const STORAGE_KEY = "codeland.settings.v1";

function pick<T extends string>(value: unknown, allowed: readonly T[], fallback: T): T {
  return allowed.includes(value as T) ? (value as T) : fallback;
}

function number(value: unknown, range: { min: number; max: number }, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value)
    ? Math.min(range.max, Math.max(range.min, value))
    : fallback;
}

/** Anything stored or passed in becomes valid settings: unknown or out-of-range values fall back. */
export function parseSettings(raw: unknown): Settings {
  const input = (typeof raw === "object" && raw !== null ? raw : {}) as Record<string, unknown>;
  const w = (typeof input.weights === "object" && input.weights !== null ? input.weights : {}) as
    Record<string, unknown>;
  const d = DEFAULT_SETTINGS;
  return {
    height: pick(input.height, HEIGHT_METRICS, d.height),
    heightScale: pick(input.heightScale, ["linear", "sqrt"], d.heightScale),
    heightFactor: number(input.heightFactor, RANGES.heightFactor, d.heightFactor),
    weights: {
      hotspot: number(w.hotspot, RANGES.hotspot, DEFAULT_WEIGHTS.hotspot),
      churn: number(w.churn, RANGES.churn, DEFAULT_WEIGHTS.churn),
      uncovered: number(w.uncovered, RANGES.uncovered, DEFAULT_WEIGHTS.uncovered),
      testFiles: number(w.testFiles, RANGES.testFiles, DEFAULT_WEIGHTS.testFiles),
      corroboration: number(w.corroboration, RANGES.corroboration, DEFAULT_WEIGHTS.corroboration),
    },
    arcs: pick(input.arcs, ["auto", "selection", "off"], d.arcs),
    glow: number(input.glow, RANGES.glow, d.glow),
    idleOrbit: typeof input.idleOrbit === "boolean" ? input.idleOrbit : d.idleOrbit,
    grid: typeof input.grid === "boolean" ? input.grid : d.grid,
    listLimit: LIST_LIMITS.includes(input.listLimit as number)
      ? (input.listLimit as number)
      : d.listLimit,
  };
}

/** Storage can be missing, full or blocked (private windows): settings just do not persist then. */
export function loadSettings(storage: Pick<Storage, "getItem"> | undefined = safeStorage()): Settings {
  try {
    const text = storage?.getItem(STORAGE_KEY);
    return parseSettings(text ? JSON.parse(text) : undefined);
  } catch {
    return DEFAULT_SETTINGS;
  }
}

export function saveSettings(
  settings: Settings,
  storage: Pick<Storage, "setItem"> | undefined = safeStorage(),
): void {
  try {
    storage?.setItem(STORAGE_KEY, JSON.stringify(settings));
  } catch {
    // not persisted; the settings still apply for this visit
  }
}

function safeStorage(): Storage | undefined {
  try {
    return globalThis.localStorage;
  } catch {
    return undefined;
  }
}

export function isDefault(settings: Settings): boolean {
  return JSON.stringify(settings) === JSON.stringify(DEFAULT_SETTINGS);
}
