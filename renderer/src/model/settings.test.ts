import { describe, expect, it } from "vitest";
import {
  DEFAULT_SETTINGS,
  isDefault,
  loadSettings,
  matchingPreset,
  parseSettings,
  PRESETS,
  presetSettings,
  RANGES,
  saveSettings,
} from "./settings";

function memory(initial?: string) {
  let value = initial;
  return {
    getItem: () => value ?? null,
    setItem: (_key: string, next: string) => {
      value = next;
    },
    read: () => value,
  };
}

describe("parseSettings", () => {
  it("falls back to the defaults for anything missing or unknown", () => {
    expect(parseSettings(undefined)).toEqual(DEFAULT_SETTINGS);
    expect(parseSettings("nonsense")).toEqual(DEFAULT_SETTINGS);
    expect(parseSettings({ height: "volume", arcs: 3, grid: "yes", listLimit: 7 })).toEqual(
      DEFAULT_SETTINGS,
    );
  });

  it("keeps valid values and clamps numbers into their range", () => {
    const settings = parseSettings({
      height: "problems",
      heightScale: "sqrt",
      heightFactor: 99,
      glow: -4,
      weights: { hotspot: 3.5, testFiles: 7, churn: Number.NaN },
      arcs: "off",
      idleOrbit: false,
      listLimit: 100,
    });
    expect(settings.height).toBe("problems");
    expect(settings.heightScale).toBe("sqrt");
    expect(settings.heightFactor).toBe(RANGES.heightFactor.max);
    expect(settings.glow).toBe(RANGES.glow.min);
    expect(settings.weights.hotspot).toBe(3.5);
    expect(settings.weights.testFiles).toBe(RANGES.testFiles.max);
    expect(settings.weights.churn).toBe(DEFAULT_SETTINGS.weights.churn);
    expect(settings.arcs).toBe("off");
    expect(settings.idleOrbit).toBe(false);
    expect(settings.listLimit).toBe(100);
  });
});

describe("severity weights and the extra parameters", () => {
  it("validates each severity weight and the scene parameters on their own", () => {
    const settings = parseSettings({
      weights: { severity: { critical: 99, high: -3, medium: "x", low: 2 } },
      minHeight: 1.5,
      towerWidth: 0.1,
      orbitSpeed: 9,
      arcOpacity: 0.3,
      fog: false,
      districts: false,
    });
    expect(settings.weights.severity).toEqual({
      critical: RANGES.severity.max,
      high: RANGES.severity.min,
      medium: DEFAULT_SETTINGS.weights.severity.medium,
      low: 2,
      info: DEFAULT_SETTINGS.weights.severity.info,
    });
    expect(settings.minHeight).toBe(1.5);
    expect(settings.towerWidth).toBe(RANGES.towerWidth.min);
    expect(settings.orbitSpeed).toBe(RANGES.orbitSpeed.max);
    expect(settings.arcOpacity).toBe(0.3);
    expect([settings.fog, settings.districts]).toEqual([false, false]);
  });
});

describe("presets", () => {
  it("are complete valid settings, the first one being the defaults", () => {
    expect(presetSettings(PRESETS[0]!)).toEqual(DEFAULT_SETTINGS);
    for (const preset of PRESETS) {
      expect(parseSettings(presetSettings(preset))).toEqual(presetSettings(preset));
    }
    const ids = PRESETS.map((p) => p.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("change what they promise and keep the rest at the defaults", () => {
    const security = presetSettings(PRESETS.find((p) => p.id === "security")!);
    expect(security.height).toBe("problems");
    expect(security.weights.severity.critical).toBe(15);
    expect(security.weights.hotspot).toBe(0.5);
    expect(security.glow).toBe(DEFAULT_SETTINGS.glow);
    const focus = presetSettings(PRESETS.find((p) => p.id === "focus")!);
    expect([focus.idleOrbit, focus.grid, focus.fog]).toEqual([false, false, false]);
  });

  it("are recognised only while the settings still equal them", () => {
    const debt = PRESETS.find((p) => p.id === "debt")!;
    expect(matchingPreset(presetSettings(debt))?.id).toBe("debt");
    expect(matchingPreset(DEFAULT_SETTINGS)?.id).toBe("default");
    expect(matchingPreset({ ...presetSettings(debt), glow: 0.1 })).toBeUndefined();
  });
});

describe("persistence", () => {
  it("round-trips through storage", () => {
    const storage = memory();
    const changed = parseSettings({ height: "churn", glow: 0.5 });
    saveSettings(changed, storage);
    expect(loadSettings(storage)).toEqual(changed);
  });

  it("survives corrupt, missing or blocked storage", () => {
    expect(loadSettings(memory("{not json"))).toEqual(DEFAULT_SETTINGS);
    expect(loadSettings(undefined)).toEqual(DEFAULT_SETTINGS);
    const blocked = {
      getItem: () => {
        throw new Error("denied");
      },
      setItem: () => {
        throw new Error("denied");
      },
    };
    expect(loadSettings(blocked)).toEqual(DEFAULT_SETTINGS);
    expect(() => saveSettings(DEFAULT_SETTINGS, blocked)).not.toThrow();
  });

  it("knows when the settings are the defaults", () => {
    expect(isDefault(DEFAULT_SETTINGS)).toBe(true);
    expect(isDefault({ ...DEFAULT_SETTINGS, glow: 2 })).toBe(false);
  });
});
