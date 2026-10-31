// How the person wants to see the city: pure data with validation (no React, no three.js).
// Applied live, never part of the city model, and kept in the browser between visits.
import type { Finding } from "./city-model";

export type HeightMetric = "loc" | "decisions" | "churn" | "problems";
export type HeightScale = "linear" | "sqrt";
export type ArcMode = "auto" | "selection" | "off";
type Severity = Finding["severity"];

/** How findings are ranked (see findings.ts `priorityOf`). */
export interface PriorityWeights {
  /** Base weight of each severity. */
  severity: Record<Severity, number>;
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
  /** Height of a tower whose metric is zero: how visible an empty lot stays. */
  minHeight: number;
  /** Share of the footprint a tower fills (1 = the whole lot). */
  towerWidth: number;
  weights: PriorityWeights;
  arcs: ArcMode;
  arcOpacity: number;
  /** Bloom intensity: 0 turns the glow off. */
  glow: number;
  idleOrbit: boolean;
  /** Speed of the idle orbit. */
  orbitSpeed: number;
  grid: boolean;
  fog: boolean;
  /** Folder plates and their outlines. */
  districts: boolean;
  /** Findings listed in the panel. */
  listLimit: number;
}

export const DEFAULT_WEIGHTS: PriorityWeights = {
  severity: { critical: 10, high: 6, medium: 3, low: 1.5, info: 0.5 },
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
  minHeight: 0.4,
  towerWidth: 1,
  weights: DEFAULT_WEIGHTS,
  arcs: "auto",
  arcOpacity: 0.16,
  glow: 1.1,
  idleOrbit: true,
  orbitSpeed: 0.05,
  grid: true,
  fog: true,
  districts: true,
  listLimit: 40,
};

export const HEIGHT_METRICS: HeightMetric[] = ["loc", "decisions", "churn", "problems"];
export const LIST_LIMITS = [10, 20, 40, 100];
const SEVERITY_KEYS: Severity[] = ["critical", "high", "medium", "low", "info"];

/** Allowed range of every number, shared by the validation and the sliders. */
export const RANGES = {
  heightFactor: { min: 0.3, max: 2, step: 0.05 },
  minHeight: { min: 0, max: 3, step: 0.1 },
  towerWidth: { min: 0.3, max: 1, step: 0.05 },
  arcOpacity: { min: 0.05, max: 0.6, step: 0.01 },
  glow: { min: 0, max: 2.5, step: 0.05 },
  orbitSpeed: { min: 0.01, max: 0.4, step: 0.01 },
  severity: { min: 0, max: 20, step: 0.5 },
  hotspot: { min: 0, max: 5, step: 0.1 },
  churn: { min: 0, max: 5, step: 0.1 },
  uncovered: { min: 0, max: 3, step: 0.1 },
  testFiles: { min: 0, max: 1, step: 0.05 },
  corroboration: { min: 0, max: 1, step: 0.05 },
} as const;

/** Ready-made profiles: the defaults plus the listed changes. */
export interface Preset {
  id: string;
  label: string;
  hint: string;
  /** Raw patch; `presetSettings` completes and validates it. */
  patch: Record<string, unknown>;
}

export const PRESETS: Preset[] = [
  { id: "default", label: "Padrão", hint: "Os valores iniciais", patch: {} },
  {
    id: "debt",
    label: "Dívida técnica",
    hint: "Altura pela complexidade; pesa o que é complexo, muda muito e não tem teste",
    patch: {
      height: "decisions",
      heightScale: "sqrt",
      arcs: "selection",
      weights: { hotspot: 3, churn: 2, uncovered: 1, testFiles: 0.3 },
    },
  },
  {
    id: "security",
    label: "Segurança",
    hint: "Altura pelo nº de problemas; severidade manda, churn e cobertura quase não contam",
    patch: {
      height: "problems",
      heightScale: "sqrt",
      minHeight: 0.2,
      arcs: "selection",
      weights: {
        severity: { critical: 15, high: 8, medium: 2, low: 0.5, info: 0.2 },
        hotspot: 0.5,
        churn: 0.5,
        uncovered: 0,
        corroboration: 0.5,
      },
    },
  },
  {
    id: "present",
    label: "Apresentação",
    hint: "Mais brilho, torres mais altas, órbita mais viva",
    patch: { heightFactor: 1.3, glow: 1.6, orbitSpeed: 0.12, arcOpacity: 0.25 },
  },
  {
    id: "focus",
    label: "Foco",
    hint: "Cena calma: pouco brilho, sem órbita, grade nem névoa; imports só da seleção",
    patch: { glow: 0.4, idleOrbit: false, arcs: "selection", grid: false, fog: false },
  },
];

const STORAGE_KEY = "codeland.settings.v1";

function pick<T extends string>(value: unknown, allowed: readonly T[], fallback: T): T {
  return allowed.includes(value as T) ? (value as T) : fallback;
}

function number(value: unknown, range: { min: number; max: number }, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value)
    ? Math.min(range.max, Math.max(range.min, value))
    : fallback;
}

function flag(value: unknown, fallback: boolean): boolean {
  return typeof value === "boolean" ? value : fallback;
}

function record(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
}

/** Anything stored or passed in becomes valid settings: unknown or out-of-range values fall back. */
export function parseSettings(raw: unknown): Settings {
  const input = record(raw);
  const w = record(input.weights);
  const sev = record(w.severity);
  const d = DEFAULT_SETTINGS;
  const dw = DEFAULT_WEIGHTS;
  return {
    height: pick(input.height, HEIGHT_METRICS, d.height),
    heightScale: pick(input.heightScale, ["linear", "sqrt"], d.heightScale),
    heightFactor: number(input.heightFactor, RANGES.heightFactor, d.heightFactor),
    minHeight: number(input.minHeight, RANGES.minHeight, d.minHeight),
    towerWidth: number(input.towerWidth, RANGES.towerWidth, d.towerWidth),
    weights: {
      severity: Object.fromEntries(
        SEVERITY_KEYS.map((key) => [key, number(sev[key], RANGES.severity, dw.severity[key])]),
      ) as Record<Severity, number>,
      hotspot: number(w.hotspot, RANGES.hotspot, dw.hotspot),
      churn: number(w.churn, RANGES.churn, dw.churn),
      uncovered: number(w.uncovered, RANGES.uncovered, dw.uncovered),
      testFiles: number(w.testFiles, RANGES.testFiles, dw.testFiles),
      corroboration: number(w.corroboration, RANGES.corroboration, dw.corroboration),
    },
    arcs: pick(input.arcs, ["auto", "selection", "off"], d.arcs),
    arcOpacity: number(input.arcOpacity, RANGES.arcOpacity, d.arcOpacity),
    glow: number(input.glow, RANGES.glow, d.glow),
    idleOrbit: flag(input.idleOrbit, d.idleOrbit),
    orbitSpeed: number(input.orbitSpeed, RANGES.orbitSpeed, d.orbitSpeed),
    grid: flag(input.grid, d.grid),
    fog: flag(input.fog, d.fog),
    districts: flag(input.districts, d.districts),
    listLimit: LIST_LIMITS.includes(input.listLimit as number)
      ? (input.listLimit as number)
      : d.listLimit,
  };
}

/** The full settings of a preset (the defaults plus its patch). */
export function presetSettings(preset: Preset): Settings {
  return parseSettings(preset.patch);
}

/** The preset the settings equal exactly, if any (so the panel can highlight it). */
export function matchingPreset(settings: Settings): Preset | undefined {
  const text = JSON.stringify(settings);
  return PRESETS.find((preset) => JSON.stringify(presetSettings(preset)) === text);
}

/** Storage can be missing, full or blocked (private windows): settings just do not persist then. */
export function loadSettings(
  storage: Pick<Storage, "getItem"> | undefined = safeStorage(),
): Settings {
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
