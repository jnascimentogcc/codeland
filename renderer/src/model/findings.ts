// Pure findings logic: priority, filters, summaries (no three.js). See docs section 6.
import type { Building, CodelandCityModel, Finding, Trend } from "./city-model";
import { DEFAULT_WEIGHTS, type PriorityWeights } from "./settings";

export type Severity = Finding["severity"];
export type Category = Finding["category"];

/** Most severe first. */
export const SEVERITIES: Severity[] = ["critical", "high", "medium", "low", "info"];
export const CATEGORIES: Category[] = [
  "security",
  "reliability",
  "maintainability",
  "testing",
  "dependencies",
  "performance",
  "other",
];

export const SEVERITY_WEIGHT: Record<Severity, number> = {
  critical: 10,
  high: 6,
  medium: 3,
  low: 1.5,
  info: 0.5,
};

/** Colour-ramp position of a severity in the problems layer (same ramp as the debt heat). */
export const SEVERITY_HEAT: Record<Severity, number> = {
  critical: 1,
  high: 0.8,
  medium: 0.55,
  low: 0.3,
  info: 0.15,
};

export interface FindingFilter {
  /** Empty = every category. */
  categories: ReadonlySet<Category>;
  /** Findings at least this severe. */
  minSeverity: Severity;
  /** Also show findings suppressed in the scanner or triaged (accepted / false positive). */
  showSuppressed: boolean;
  /** Only findings first seen after the previous model (needs a trend). */
  onlyNew: boolean;
  /** Case-insensitive match on path, rule, title and message. */
  query: string;
}

export const DEFAULT_FILTER: FindingFilter = {
  categories: new Set(),
  minSeverity: "info",
  showSuppressed: false,
  onlyNew: false,
  query: "",
};

export interface RankedFinding {
  finding: Finding;
  /** The finding's file when it is a building of the city, else null. */
  building: Building | null;
  /** Other findings that repeat this one (different tools, same place), most severe first. */
  alsoReportedBy: Finding[];
  priority: number;
}

/**
 * How much a finding deserves attention: severity, times how much its file matters (hotspot and
 * churn: a problem in code that changes every week costs more), times how little a test covers it.
 * Computed here and never stored, so the weights can change without re-analysis.
 */
export function priorityOf(
  finding: Finding,
  building: Building | null,
  maxChurn: number,
  weights: PriorityWeights = DEFAULT_WEIGHTS,
): number {
  const weight = SEVERITY_WEIGHT[finding.severity];
  if (!building) return weight;
  const m = building.metrics;
  const churn = maxChurn > 0 ? m.churnCommits / maxChurn : 0;
  const uncovered = m.coverage === null ? 0 : 1 - m.coverage;
  const importance = 1 + weights.hotspot * m.hotspot + weights.churn * churn;
  const testFactor = building.role === "test" ? weights.testFiles : 1;
  return weight * importance * (1 + weights.uncovered * uncovered) * testFactor;
}

/** Extra tools that report the same problem count up to this many times. */
const CORROBORATION_MAX = 2;

/** Set aside by the scanner or by a human decision. */
export function isSetAside(finding: Finding): boolean {
  return finding.status === "suppressed" || finding.triage !== undefined;
}

/** First seen after the previous model; false when there is no previous model. */
export function isNew(finding: Finding, since: string | null): boolean {
  return since !== null && finding.firstSeen > since;
}

export function matches(
  finding: Finding,
  filter: FindingFilter,
  since: string | null,
  skip?: "category" | "severity",
): boolean {
  if (finding.duplicateOf !== null) return false; // shown under its primary finding
  if (isSetAside(finding) && !filter.showSuppressed) return false;
  if (filter.onlyNew && !isNew(finding, since)) return false;
  if (
    skip !== "severity" &&
    SEVERITIES.indexOf(finding.severity) > SEVERITIES.indexOf(filter.minSeverity)
  ) {
    return false;
  }
  if (
    skip !== "category" &&
    filter.categories.size > 0 &&
    !filter.categories.has(finding.category)
  ) {
    return false;
  }
  const query = filter.query.trim().toLowerCase();
  if (!query) return true;
  return [finding.location.path, finding.ruleId, finding.title ?? "", finding.message].some((s) =>
    s.toLowerCase().includes(query),
  );
}

/** Findings that pass the filter, highest priority first (ties: severity, then path and line). */
export function rankFindings(
  model: CodelandCityModel,
  filter: FindingFilter,
  weights: PriorityWeights = DEFAULT_WEIGHTS,
): RankedFinding[] {
  const byPath = new Map(model.buildings.map((b) => [b.path, b]));
  const maxChurn = model.buildings.reduce((max, b) => Math.max(max, b.metrics.churnCommits), 0);
  const since = model.analysis.trend?.since ?? null;
  const repeats = duplicatesByPrimary(model.findings);
  return model.findings
    .filter((f) => matches(f, filter, since))
    .map((finding) => {
      const building = byPath.get(finding.location.path) ?? null;
      const alsoReportedBy = repeats.get(finding.id) ?? [];
      const extra = Math.min(alsoReportedBy.length, CORROBORATION_MAX);
      const corroboration = 1 + weights.corroboration * extra;
      return {
        finding,
        building,
        alsoReportedBy,
        priority: priorityOf(finding, building, maxChurn, weights) * corroboration,
      };
    })
    .sort(
      (a, b) =>
        b.priority - a.priority ||
        SEVERITIES.indexOf(a.finding.severity) - SEVERITIES.indexOf(b.finding.severity) ||
        a.finding.location.path.localeCompare(b.finding.location.path) ||
        (a.finding.location.startLine ?? 0) - (b.finding.location.startLine ?? 0),
    );
}

/** Primary finding id -> the findings that repeat it, most severe first. */
export function duplicatesByPrimary(findings: Finding[]): Map<string, Finding[]> {
  const result = new Map<string, Finding[]>();
  for (const finding of findings) {
    if (finding.duplicateOf === null) continue;
    result.set(finding.duplicateOf, [...(result.get(finding.duplicateOf) ?? []), finding]);
  }
  for (const list of result.values()) {
    list.sort((a, b) => SEVERITIES.indexOf(a.severity) - SEVERITIES.indexOf(b.severity));
  }
  return result;
}

export interface Facets {
  categories: Record<Category, number>;
  severities: Record<Severity, number>;
}

/** Counts for the filter chips; each facet ignores its own filter so it shows what a click adds. */
export function facets(model: CodelandCityModel, filter: FindingFilter): Facets {
  const result: Facets = {
    categories: Object.fromEntries(CATEGORIES.map((c) => [c, 0])) as Facets["categories"],
    severities: Object.fromEntries(SEVERITIES.map((s) => [s, 0])) as Facets["severities"],
  };
  const since = model.analysis.trend?.since ?? null;
  for (const finding of model.findings) {
    if (matches(finding, filter, since, "category")) result.categories[finding.category] += 1;
    if (matches(finding, filter, since, "severity")) result.severities[finding.severity] += 1;
  }
  return result;
}

export interface BuildingProblems {
  /** Colour-ramp position of the most severe finding of the file (0..1). */
  heat: number;
  count: number;
}

/** Per building id: its most severe visible finding and how many there are. */
export function problemsByBuilding(ranked: RankedFinding[]): Map<string, BuildingProblems> {
  const result = new Map<string, BuildingProblems>();
  for (const { finding, building } of ranked) {
    if (!building) continue;
    const heat = SEVERITY_HEAT[finding.severity];
    const known = result.get(building.id);
    result.set(building.id, {
      heat: Math.max(known?.heat ?? 0, heat),
      count: (known?.count ?? 0) + 1,
    });
  }
  return result;
}

export function formatLocation(finding: Finding): string {
  const { path, startLine, endLine } = finding.location;
  if (startLine === null) return path;
  return endLine !== null && endLine !== startLine
    ? `${path}:${startLine}-${endLine}`
    : `${path}:${startLine}`;
}

export interface TrendSummary {
  since: string;
  /** Open findings that appeared since the previous model. */
  added: number;
  fixed: Trend["fixed"];
}

/** What changed since the previous model, or null when the model has no trend. */
export function trendSummary(model: CodelandCityModel): TrendSummary | null {
  const trend = model.analysis.trend;
  if (!trend) return null;
  const added = model.findings.filter((f) => !isSetAside(f) && f.duplicateOf === null && isNew(f, trend.since)).length;
  return { since: trend.since, added, fixed: trend.fixed };
}
