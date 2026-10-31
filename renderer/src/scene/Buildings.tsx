import { Html } from "@react-three/drei";
import { type ThreeEvent, useFrame } from "@react-three/fiber";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import type { LiveState } from "../model/agents";
import type { BuildingProblems } from "../model/findings";
import type { BuildingShape, CityView, Layer } from "../model/view";
import { createBeamMaterial } from "./beamMaterial";
import { createBuildingMaterial, LIVE_EPOCH, NO_ACTIVITY } from "./buildingMaterial";

interface Props {
  view: CityView;
  layer: Layer;
  shape: BuildingShape;
  live: LiveState;
  /** Visible findings per building id, for the problems layer. */
  problems: ReadonlyMap<string, BuildingProblems>;
  selectedIndex: number | null;
  onSelect: (index: number) => void;
}

const LAYER_UNIFORM: Record<Layer, number> = { structure: 0, debt: 1, agents: 2, problems: 3 };

const BEAM_RADIUS = 0.24; // relative to the tower radius
const BEAM_OVERSHOOT = 0.8; // world units the beam rises above the roof

/**
 * All towers in one instanced draw call, plus (ring shape) one instanced draw call for the
 * light beams through their cores. Instance i of both meshes is building i.
 */
export function Buildings({
  view,
  layer,
  shape,
  live,
  problems,
  selectedIndex,
  onSelect,
}: Props) {
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const beamsRef = useRef<THREE.InstancedMesh>(null);
  const [hovered, setHovered] = useState<number | null>(null);
  const material = useMemo(createBuildingMaterial, []);
  const beamMaterial = useMemo(createBeamMaterial, []);

  const [geometry, beamGeometry] = useMemo(() => {
    const attribute = (read: (i: number) => number) =>
      new THREE.InstancedBufferAttribute(Float32Array.from(view.buildings, (_, i) => read(i)), 1);
    const metrics = (i: number) => view.buildings[i]!.building.metrics;
    const heat = attribute((i) => metrics(i).hotspot);
    const test = attribute((i) => (view.buildings[i]!.building.role === "test" ? 1 : 0));
    const hue = attribute((i) => view.buildings[i]!.moduleHue);
    // Live agent activity, rewritten in place whenever an event arrives.
    const agentHue = attribute(() => -1);
    const activityAt = attribute(() => NO_ACTIVITY);
    const activityKind = attribute(() => 0);
    // Heat-ramp position of the file's worst visible finding, 0 = none.
    const problem = attribute(() => 0);

    // Hexagonal prism with a slight taper; unit height with its base at y = 0.
    const tower = new THREE.CylinderGeometry(0.84, 1, 1, 6, 1);
    tower.translate(0, 0.5, 0);
    tower.setAttribute("aCoverage", attribute((i) => metrics(i).coverage ?? -1));
    const beam = new THREE.CylinderGeometry(1, 1, 1, 10, 1, true);
    beam.translate(0, 0.5, 0);
    for (const geo of [tower, beam]) {
      geo.setAttribute("aHeat", heat);
      geo.setAttribute("aTest", test);
      geo.setAttribute("aHue", hue);
      geo.setAttribute("aAgentHue", agentHue);
      geo.setAttribute("aActivityAt", activityAt);
      geo.setAttribute("aActivityKind", activityKind);
      geo.setAttribute("aProblem", problem);
    }
    return [tower, beam];
  }, [view]);

  useEffect(() => {
    const hues = geometry.getAttribute("aAgentHue") as THREE.InstancedBufferAttribute;
    const at = geometry.getAttribute("aActivityAt") as THREE.InstancedBufferAttribute;
    const kind = geometry.getAttribute("aActivityKind") as THREE.InstancedBufferAttribute;
    view.buildings.forEach((b, i) => {
      const activity = live.activity[b.building.path];
      const agent = activity && live.agents[activity.agent];
      hues.setX(i, agent ? agent.hue : -1);
      at.setX(i, activity ? activity.ts - LIVE_EPOCH : NO_ACTIVITY);
      kind.setX(i, activity?.kind === "edit" ? 1 : 0);
    });
    for (const attribute of [hues, at, kind]) attribute.needsUpdate = true;
  }, [view, geometry, live.activity, live.agents]);

  useEffect(() => {
    const attribute = geometry.getAttribute("aProblem") as THREE.InstancedBufferAttribute;
    view.buildings.forEach((b, i) => attribute.setX(i, problems.get(b.building.id)?.heat ?? 0));
    attribute.needsUpdate = true;
  }, [view, geometry, problems]);

  useEffect(
    () => () => {
      geometry.dispose();
      beamGeometry.dispose();
    },
    [geometry, beamGeometry],
  );
  useEffect(
    () => () => {
      material.dispose();
      beamMaterial.dispose();
    },
    [material, beamMaterial],
  );

  useLayoutEffect(() => {
    const mesh = meshRef.current;
    const beams = beamsRef.current;
    const matrix = new THREE.Matrix4();
    view.buildings.forEach((b, i) => {
      const r = b.radius * 0.92;
      mesh?.setMatrixAt(i, matrix.makeScale(r, b.height, r).setPosition(b.x, b.base, b.z));
      const beamR = r * BEAM_RADIUS;
      beams?.setMatrixAt(
        i,
        matrix.makeScale(beamR, b.height + BEAM_OVERSHOOT, beamR).setPosition(b.x, b.base, b.z),
      );
    });
    for (const m of [mesh, beams]) {
      if (!m) continue;
      m.instanceMatrix.needsUpdate = true;
      m.computeBoundingSphere();
    }
  }, [view, geometry, shape]);

  useEffect(() => {
    for (const m of [material, beamMaterial]) {
      m.uniforms.uLayer!.value = LAYER_UNIFORM[layer];
      m.uniforms.uSelected!.value = selectedIndex ?? -1;
      m.uniforms.uHovered!.value = hovered ?? -1;
    }
    material.uniforms.uRings!.value = shape === "rings" ? 1 : 0;
  }, [material, beamMaterial, layer, shape, selectedIndex, hovered]);

  useEffect(() => {
    document.body.style.cursor = hovered === null ? "" : "pointer";
  }, [hovered]);

  useFrame(({ clock }) => {
    const now = Date.now() / 1000 - LIVE_EPOCH;
    for (const m of [material, beamMaterial]) {
      m.uniforms.uTime!.value = clock.elapsedTime;
      m.uniforms.uNow!.value = now;
    }
  });

  const hoveredView = hovered === null ? undefined : view.buildings[hovered];

  return (
    <>
      <instancedMesh
        key={view.buildings.length}
        ref={meshRef}
        args={[geometry, material, view.buildings.length]}
        onPointerMove={(e: ThreeEvent<PointerEvent>) => {
          e.stopPropagation();
          setHovered(e.instanceId ?? null);
        }}
        onPointerOut={() => setHovered(null)}
        onClick={(e: ThreeEvent<MouseEvent>) => {
          e.stopPropagation();
          if (e.instanceId !== undefined) onSelect(e.instanceId);
        }}
      />
      {shape === "rings" && (
        <instancedMesh
          key={`beams-${view.buildings.length}`}
          ref={beamsRef}
          args={[beamGeometry, beamMaterial, view.buildings.length]}
          raycast={() => null}
        />
      )}
      {hoveredView && hovered !== selectedIndex && (
        <Html
          position={[hoveredView.x, hoveredView.base + hoveredView.height + 0.6, hoveredView.z]}
          center
          style={{ pointerEvents: "none" }}
        >
          <div className="tooltip">
            <div className="tooltip-path">{hoveredView.building.path}</div>
            <div className="tooltip-meta">
              hotspot {hoveredView.building.metrics.hotspot.toFixed(2)} ·{" "}
              {hoveredView.building.metrics.loc} linhas
              {problems.has(hoveredView.building.id) &&
                ` · ${problems.get(hoveredView.building.id)!.count} problemas`}
            </div>
          </div>
        </Html>
      )}
    </>
  );
}
