import { Html } from "@react-three/drei";
import { type ThreeEvent, useFrame } from "@react-three/fiber";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import type { BuildingShape, CityView, Layer } from "../model/view";
import { createBeamMaterial } from "./beamMaterial";
import { createBuildingMaterial } from "./buildingMaterial";

interface Props {
  view: CityView;
  layer: Layer;
  shape: BuildingShape;
  selectedIndex: number | null;
  onSelect: (index: number) => void;
}

const BEAM_RADIUS = 0.24; // relative to the tower radius
const BEAM_OVERSHOOT = 0.8; // world units the beam rises above the roof

/**
 * All towers in one instanced draw call, plus (ring shape) one instanced draw call for the
 * light beams through their cores. Instance i of both meshes is building i.
 */
export function Buildings({ view, layer, shape, selectedIndex, onSelect }: Props) {
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

    // Hexagonal prism with a slight taper; unit height with its base at y = 0.
    const tower = new THREE.CylinderGeometry(0.84, 1, 1, 6, 1);
    tower.translate(0, 0.5, 0);
    tower.setAttribute("aHeat", heat);
    tower.setAttribute("aCoverage", attribute((i) => metrics(i).coverage ?? -1));
    tower.setAttribute("aTest", test);
    tower.setAttribute("aHue", hue);

    const beam = new THREE.CylinderGeometry(1, 1, 1, 10, 1, true);
    beam.translate(0, 0.5, 0);
    beam.setAttribute("aHeat", heat);
    beam.setAttribute("aTest", test);
    beam.setAttribute("aHue", hue);
    return [tower, beam];
  }, [view]);

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
      m.uniforms.uLayer!.value = layer === "debt" ? 1 : 0;
      m.uniforms.uSelected!.value = selectedIndex ?? -1;
      m.uniforms.uHovered!.value = hovered ?? -1;
    }
    material.uniforms.uRings!.value = shape === "rings" ? 1 : 0;
  }, [material, beamMaterial, layer, shape, selectedIndex, hovered]);

  useEffect(() => {
    document.body.style.cursor = hovered === null ? "" : "pointer";
  }, [hovered]);

  useFrame(({ clock }) => {
    material.uniforms.uTime!.value = clock.elapsedTime;
    beamMaterial.uniforms.uTime!.value = clock.elapsedTime;
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
            </div>
          </div>
        </Html>
      )}
    </>
  );
}
