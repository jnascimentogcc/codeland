// Pure mapping from the city model to world-space values for the scene (no three.js here).
import type { Building, CodelandCityModel, District } from "./city-model";
import type { HeightMetric, HeightScale } from "./settings";

export type Layer = "structure" | "debt" | "agents" | "problems";
export type BuildingShape = "rings" | "prism";

export const PLATE_THICKNESS = 0.12;
export const MIN_HEIGHT = 0.4;

export interface BuildingView {
  building: Building;
  /** Center of the footprint, city centered on the origin. */
  x: number;
  z: number;
  /** Elevation of the building base (top of its district plate). */
  base: number;
  /** Circumradius of the prism; fits inside the square footprint from the layout. */
  radius: number;
  height: number;
  /** Hue in [0, 1) of the building's top-level module, shared by the shader and the legend. */
  moduleHue: number;
}

export interface DistrictView {
  district: District;
  x: number;
  z: number;
  width: number;
  depth: number;
  /** Elevation of the plate bottom; nested districts stack on their parents. */
  elevation: number;
}

export interface CityView {
  /** Largest ground dimension of the city. */
  size: number;
  maxHeight: number;
  buildings: BuildingView[];
  districts: DistrictView[];
  modules: { name: string; hue: number }[];
  indexById: Map<string, number>;
}

export function topModule(path: string): string {
  const slash = path.indexOf("/");
  return slash < 0 ? "." : path.slice(0, slash);
}

export function moduleHue(index: number): number {
  // Golden-ratio steps keep neighbouring modules far apart on the color wheel.
  return (index * 0.618034 + 0.52) % 1;
}

export interface ViewOptions {
  includeTests?: boolean;
  /** What the tower height shows (default: lines of code). */
  height?: HeightMetric;
  heightScale?: HeightScale;
  /** Multiplies the tallest tower (default 1). */
  heightFactor?: number;
  /** Findings per building id, for the "problems" height; buildings without an entry have 0. */
  problemCounts?: ReadonlyMap<string, number>;
}

/** The raw value a height metric reads from a building. */
export function heightValue(
  building: Building,
  metric: HeightMetric,
  problemCounts?: ReadonlyMap<string, number>,
): number {
  switch (metric) {
    case "decisions":
      return building.metrics.decisions;
    case "churn":
      return building.metrics.churnCommits;
    case "problems":
      return problemCounts?.get(building.id) ?? 0;
    default:
      return building.metrics.loc;
  }
}

export function buildCityView(
  model: CodelandCityModel,
  {
    includeTests = true,
    height = "loc",
    heightScale = "linear",
    heightFactor = 1,
    problemCounts,
  }: ViewOptions = {},
): CityView {
  const root = model.districts.find((d) => d.parent === null)?.layout ?? {
    x: 0,
    z: 0,
    width: 1,
    depth: 1,
  };
  const centerX = root.x + root.width / 2;
  const centerZ = root.z + root.depth / 2;
  const size = Math.max(root.width, root.depth);
  const maxHeight = Math.min(Math.max(size * 0.35, 6), 60) * heightFactor;
  // Normalize over all buildings so hiding tests does not rescale the city.
  const maxValue = model.buildings.reduce(
    (max, b) => Math.max(max, heightValue(b, height, problemCounts)),
    1,
  );
  const share = (building: Building): number => {
    const ratio = heightValue(building, height, problemCounts) / maxValue;
    return heightScale === "sqrt" ? Math.sqrt(ratio) : ratio;
  };

  const moduleNames = [...new Set(model.buildings.map((b) => topModule(b.path)))].sort();
  const hueByModule = new Map(moduleNames.map((name, i) => [name, moduleHue(i)]));

  const districts = model.districts.map((district) => ({
    district,
    x: district.layout.x + district.layout.width / 2 - centerX,
    z: district.layout.z + district.layout.depth / 2 - centerZ,
    width: district.layout.width,
    depth: district.layout.depth,
    elevation: district.depth * PLATE_THICKNESS,
  }));
  const elevationById = new Map(districts.map((d) => [d.district.id, d.elevation]));

  const buildings = model.buildings
    .filter((b) => includeTests || b.role === "source")
    .map((building) => {
      const { layout } = building;
      return {
        building,
        x: layout.x + layout.width / 2 - centerX,
        z: layout.z + layout.depth / 2 - centerZ,
        base: (elevationById.get(building.district) ?? 0) + PLATE_THICKNESS,
        radius: Math.min(layout.width, layout.depth) / 2,
        height: MIN_HEIGHT + share(building) * maxHeight,
        moduleHue: hueByModule.get(topModule(building.path)) ?? 0,
      };
    });

  return {
    size,
    maxHeight,
    buildings,
    districts,
    modules: moduleNames.map((name) => ({ name, hue: hueByModule.get(name) ?? 0 })),
    indexById: new Map(buildings.map((b, i) => [b.building.id, i])),
  };
}

export function hotspotRanking(model: CodelandCityModel, limit: number): Building[] {
  return model.buildings
    .filter((b) => b.role === "source" && b.metrics.hotspot > 0)
    .sort((a, b) => b.metrics.hotspot - a.metrics.hotspot)
    .slice(0, limit);
}
