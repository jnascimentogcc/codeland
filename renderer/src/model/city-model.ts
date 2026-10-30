/* Generated from schema/city-model.schema.json by npm run gen:types. Do not edit. */

/**
 * Contract between analyzers and clients. Raw metrics plus a persisted layout; clients decide visual mappings (see docs/architecture_and_mvp.md, section 2.2).
 */
export interface CodelandCityModel {
  schemaVersion: "0.2.0";
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
