import { describe, expect, it } from "vitest";
import {
  DEFAULT_SETTINGS,
  isDefault,
  loadSettings,
  parseSettings,
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
