/* Generated from schema/city-model.schema.json by npm run gen:types. Do not edit. */

export type SourceKind = "scanner" | "native" | "agent";

/**
 * Contract between analyzers and clients. Raw metrics plus a persisted layout; clients decide visual mappings (see docs/architecture_and_mvp.md, section 2.2).
 */
export interface CodelandCityModel {
  schemaVersion: "0.4.0";
  generatedAt: string;
  repository: {
    name: string;
    /**
     * HEAD commit SHA at analysis time.
     */
    commit: string | null;
    branch: string | null;
  };
  analysis: {
    language: "typescript";
    churnWindowDays: number;
    /**
     * Coverage report used, or null when coverage was not provided.
     */
    coverageSource: string | null;
    /**
     * Where the findings came from: one entry per imported SARIF file plus one for Codeland's own native findings.
     */
    findingSources: FindingSource[];
    /**
     * Triage file applied to the findings, or null.
     */
    triageSource: string | null;
    /**
     * Findings compared with the previous model (--previous); null when there was none.
     */
    trend: null | Trend;
  };
  /**
   * Folders (city blocks). The repository root is the district with path "".
   */
  districts: District[];
  /**
   * Source files.
   */
  buildings: Building[];
  /**
   * Imports between buildings of this repository. External packages are only counted in metrics.externalImports.
   */
  edges: Edge[];
  /**
   * Problems found in the code, from scanners (SARIF), native analysis or agents (docs/architecture_and_mvp.md, section 6). Ordered by path, then line.
   */
  findings: Finding[];
}
export interface FindingSource {
  tool: string;
  version: string | null;
  kind: SourceKind;
  /**
   * Imported report, or null for native findings.
   */
  file: string | null;
  /**
   * Findings kept from this source.
   */
  findings: number;
  /**
   * Results ignored: no location, a location outside the repository, or an id already seen.
   */
  dropped: number;
}
export interface Trend {
  /**
   * generatedAt of the previous model; a finding is new when its firstSeen is later.
   */
  since: string;
  /**
   * Findings of the previous model that are gone, counted only for tools that reported in both runs (a missing report is not a fix).
   */
  fixed: {
    id: string;
    ruleId: string;
    title: string | null;
    category: "security" | "reliability" | "maintainability" | "testing" | "dependencies" | "performance" | "other";
    severity: "critical" | "high" | "medium" | "low" | "info";
    path: string;
  }[];
}
export interface District {
  id: string;
  /**
   * Repository-relative folder path with forward slashes.
   */
  path: string;
  parent: string | null;
  depth: number;
  layout: Rect;
}
/**
 * Ground rectangle in world units; x/z is the corner with the smallest coordinates.
 */
export interface Rect {
  x: number;
  z: number;
  width: number;
  depth: number;
}
export interface Building {
  id: string;
  /**
   * Repository-relative file path with forward slashes.
   */
  path: string;
  district: string;
  /**
   * "test" for *.test.* / *.spec.* files and files under test, tests or __tests__ folders.
   */
  role: "source" | "test";
  metrics: {
    /**
     * Lines containing code (blank and comment-only lines excluded).
     */
    loc: number;
    /**
     * Sum of cyclomatic complexity of all functions plus top-level code.
     */
    complexity: number;
    /**
     * Branching points only: complexity minus the base 1 of each function, so many trivial functions (e.g. test callbacks) do not add up.
     */
    decisions: number;
    maxFunctionComplexity: number;
    functions: number;
    /**
     * Efferent coupling: distinct modules imported (internal + external).
     */
    imports: number;
    externalImports: number;
    /**
     * Commits touching the file within the churn window, following renames.
     */
    churnCommits: number;
    /**
     * Lines added + deleted within the churn window.
     */
    churnLines: number;
    /**
     * Line coverage ratio, or null when unknown.
     */
    coverage: number | null;
    /**
     * Normalized decisions x normalized churnCommits.
     */
    hotspot: number;
  };
  layout: Rect;
}
export interface Edge {
  from: string;
  to: string;
  kind: "import" | "reexport" | "dynamic-import" | "require";
}
export interface Finding {
  /**
   * Stable across scans (docs section 6.3): never derived from line numbers.
   */
  id: string;
  ruleId: string;
  /**
   * Short human name of the rule.
   */
  title: string | null;
  category: "security" | "reliability" | "maintainability" | "testing" | "dependencies" | "performance" | "other";
  severity: "critical" | "high" | "medium" | "low" | "info";
  message: string;
  location: {
    /**
     * Repository-relative file path with forward slashes; it may not be a building (e.g. package-lock.json).
     */
    path: string;
    startLine: number | null;
    endLine: number | null;
  };
  source: {
    tool: string;
    version: string | null;
    kind: SourceKind;
  };
  status: "open" | "suppressed";
  /**
   * generatedAt of the first model that contained this id, carried over through --previous; findings new in this model carry its own generatedAt.
   */
  firstSeen: string;
  /**
   * Human decision from the triage file (docs 6.7); absent when untriaged.
   */
  triage?: {
    state: "accepted" | "false-positive";
    note: string | null;
    /**
     * Date of the decision.
     */
    at: string | null;
  };
}
