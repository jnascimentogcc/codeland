import { describe, expect, it } from "vitest";
import type { Building, CodelandCityModel, Finding } from "./city-model";
import {
  DEFAULT_FILTER,
  facets,
  formatLocation,
  priorityOf,
  problemsByBuilding,
  rankFindings,
} from "./findings";

function building(path: string, hotspot: number, churnCommits: number, coverage: number | null): Building {
  return {
    id: path,
    path,
    district: ".",
    role: "source",
    metrics: {
      loc: 10,
      complexity: 1,
      decisions: 1,
      maxFunctionComplexity: 1,
      functions: 1,
      imports: 0,
      externalImports: 0,
      churnCommits,
      churnLines: 0,
      coverage,
      hotspot,
    },
    layout: { x: 0, z: 0, width: 1, depth: 1 },
  };
}

function finding(id: string, path: string, severity: Finding["severity"], extra: Partial<Finding> = {}): Finding {
  return {
    id,
    ruleId: `rule/${id}`,
    title: null,
    category: "security",
    severity,
    message: `message ${id}`,
    location: { path, startLine: 3, endLine: 3 },
    source: { tool: "t", version: null, kind: "scanner" },
    status: "open",
    ...extra,
  };
}

const MODEL = {
  buildings: [building("calm.ts", 0, 0, 1), building("hot.ts", 1, 10, 0.2)],
  findings: [
    finding("a", "calm.ts", "high"),
    finding("b", "hot.ts", "medium", { category: "maintainability" }),
    finding("c", "package-lock.json", "critical", { category: "dependencies" }),
    finding("d", "hot.ts", "low", { status: "suppressed" }),
  ],
} as unknown as CodelandCityModel;

describe("priority", () => {
  it("raises a problem in code that changes often and is poorly covered", () => {
    const [calm, hot] = MODEL.buildings as [Building, Building];
    const same = finding("x", "any.ts", "medium");
    expect(priorityOf(same, null, 10)).toBe(3);
    expect(priorityOf(same, hot, 10)).toBeGreaterThan(priorityOf(same, calm, 10) * 3);
  });

  it("ranks by priority, so a medium in a hotspot can beat a high in calm code", () => {
    const ranked = rankFindings(MODEL, DEFAULT_FILTER);
    expect(ranked.map((r) => r.finding.id)).toEqual(["b", "c", "a"]);
    expect(ranked[1]!.building).toBeNull(); // lock file: not a building, plain severity weight
  });
});

describe("filters", () => {
  it("hides suppressed findings unless asked", () => {
    expect(rankFindings(MODEL, DEFAULT_FILTER).map((r) => r.finding.id)).not.toContain("d");
    const all = rankFindings(MODEL, { ...DEFAULT_FILTER, showSuppressed: true });
    expect(all.map((r) => r.finding.id)).toContain("d");
  });

  it("filters by category, minimum severity and text", () => {
    const rank = (patch: object) =>
      rankFindings(MODEL, { ...DEFAULT_FILTER, ...patch }).map((r) => r.finding.id);
    expect(rank({ categories: new Set(["security"]) })).toEqual(["a"]);
    expect(rank({ minSeverity: "high" })).toEqual(["c", "a"]);
    expect(rank({ query: "HOT" })).toEqual(["b"]);
    expect(rank({ query: "rule/c" })).toEqual(["c"]);
  });

  it("counts facets ignoring their own filter", () => {
    const filter = { ...DEFAULT_FILTER, categories: new Set(["security" as const]), minSeverity: "high" as const };
    const counts = facets(MODEL, filter);
    // Categories are counted among findings that pass the severity filter only.
    expect(counts.categories.security).toBe(1);
    expect(counts.categories.dependencies).toBe(1);
    expect(counts.categories.maintainability).toBe(0);
    // Severities are counted among findings that pass the category filter only.
    expect(counts.severities.high).toBe(1);
    expect(counts.severities.critical).toBe(0);
  });
});

describe("problemsByBuilding", () => {
  it("keeps the worst severity and the count per building", () => {
    const ranked = rankFindings(MODEL, { ...DEFAULT_FILTER, showSuppressed: true });
    const problems = problemsByBuilding(ranked);
    expect(problems.get("hot.ts")).toEqual({ heat: 0.55, count: 2 });
    expect(problems.get("calm.ts")).toEqual({ heat: 0.8, count: 1 });
    expect(problems.has("package-lock.json")).toBe(false);
  });
});

describe("formatLocation", () => {
  it("shows lines when known", () => {
    expect(formatLocation(finding("a", "x.ts", "low"))).toBe("x.ts:3");
    const range = finding("a", "x.ts", "low", { location: { path: "x.ts", startLine: 3, endLine: 9 } });
    expect(formatLocation(range)).toBe("x.ts:3-9");
    const none = finding("a", "x.ts", "low", { location: { path: "x.ts", startLine: null, endLine: null } });
    expect(formatLocation(none)).toBe("x.ts");
  });
});
