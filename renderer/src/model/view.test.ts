import { describe, expect, it } from "vitest";
import type { Building, CodelandCityModel } from "./city-model";
import { parseModel } from "./load";
import { buildCityView, hotspotRanking, MIN_HEIGHT, PLATE_THICKNESS, topModule } from "./view";

function building(path: string, loc: number, hotspot: number, role: Building["role"]): Building {
  const folder = path.includes("/") ? path.slice(0, path.lastIndexOf("/")) : ".";
  return {
    id: path,
    path,
    district: folder,
    role,
    metrics: {
      loc,
      complexity: 0,
      decisions: 0,
      maxFunctionComplexity: 0,
      functions: 0,
      imports: 0,
      externalImports: 0,
      churnCommits: 0,
      churnLines: 0,
      coverage: null,
      hotspot,
    },
    layout: { x: 2, z: 2, width: 2, depth: 2 },
  };
}

const MODEL: CodelandCityModel = {
  schemaVersion: "0.5.0",
  generatedAt: "2026-10-30T00:00:00+00:00",
  repository: { name: "sample", commit: null, branch: "main" },
  analysis: { language: "typescript", churnWindowDays: 180, coverageSource: null, findingSources: [], triageSource: null, trend: null },
  districts: [
    { id: ".", path: "", parent: null, depth: 0, layout: { x: 0, z: 0, width: 20, depth: 10 } },
    { id: "src", path: "src", parent: ".", depth: 1, layout: { x: 1, z: 1, width: 8, depth: 8 } },
  ],
  buildings: [
    building("src/a.ts", 100, 0.9, "source"),
    building("src/a.test.ts", 50, 0, "test"),
    building("index.ts", 0, 0.2, "source"),
  ],
  edges: [],
  findings: [],
};

describe("buildCityView", () => {
  it("centers the city on the origin", () => {
    const view = buildCityView(MODEL);
    const root = view.districts.find((d) => d.district.id === ".")!;
    expect([root.x, root.z]).toEqual([0, 0]);
    expect(view.buildings[0]).toMatchObject({ x: -7, z: -2, radius: 1 });
    expect(view.size).toBe(20);
  });

  it("scales height linearly with LOC and stacks buildings on their district", () => {
    const view = buildCityView(MODEL);
    const [a, test, index] = view.buildings;
    expect(a!.height).toBeCloseTo(MIN_HEIGHT + view.maxHeight);
    expect(test!.height).toBeCloseTo(MIN_HEIGHT + view.maxHeight / 2);
    expect(index!.height).toBe(MIN_HEIGHT);
    expect(a!.base).toBeCloseTo(2 * PLATE_THICKNESS); // depth-1 plate on top of the root plate
  });

  it("hides tests without rescaling the rest of the city", () => {
    const all = buildCityView(MODEL);
    const sources = buildCityView(MODEL, { includeTests: false });
    expect(sources.buildings.map((b) => b.building.id)).toEqual(["src/a.ts", "index.ts"]);
    expect(sources.buildings[0]!.height).toBe(all.buildings[0]!.height);
    expect(sources.indexById.get("index.ts")).toBe(1);
  });

  it("gives each top-level module a stable hue", () => {
    const view = buildCityView(MODEL);
    expect(view.modules.map((m) => m.name)).toEqual([".", "src"]);
    expect(view.buildings[0]!.moduleHue).toBe(view.buildings[1]!.moduleHue);
    expect(view.buildings[0]!.moduleHue).not.toBe(view.buildings[2]!.moduleHue);
    expect(topModule("index.ts")).toBe(".");
  });
});

describe("hotspotRanking", () => {
  it("ranks source files with a positive score", () => {
    expect(hotspotRanking(MODEL, 10).map((b) => b.id)).toEqual(["src/a.ts", "index.ts"]);
  });
});

describe("parseModel", () => {
  it("rejects other schema versions", () => {
    expect(() => parseModel({ schemaVersion: "0.1.0" })).toThrow(/0\.5\.0/);
    expect(parseModel(MODEL)).toBe(MODEL);
  });
});
