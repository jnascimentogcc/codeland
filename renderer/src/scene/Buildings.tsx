import { Html } from "@react-three/drei";
import { type ThreeEvent, useFrame } from "@react-three/fiber";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import type { CityView, Layer } from "../model/view";
import { createBuildingMaterial } from "./buildingMaterial";

interface Props {
  view: CityView;
  layer: Layer;
  selectedIndex: number | null;
  onSelect: (index: number) => void;
}

/** All towers in one instanced draw call. */
export function Buildings({ view, layer, selectedIndex, onSelect }: Props) {
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const [hovered, setHovered] = useState<number | null>(null);
  const material = useMemo(createBuildingMaterial, []);

  const geometry = useMemo(() => {
    // Hexagonal prism with a slight taper; unit height with its base at y = 0.
    const geo = new THREE.CylinderGeometry(0.84, 1, 1, 6, 1);
    geo.translate(0, 0.5, 0);
    const attribute = (read: (i: number) => number) =>
      new THREE.InstancedBufferAttribute(Float32Array.from(view.buildings, (_, i) => read(i)), 1);
    const metrics = (i: number) => view.buildings[i]!.building.metrics;
    geo.setAttribute("aHeat", attribute((i) => metrics(i).hotspot));
    geo.setAttribute("aCoverage", attribute((i) => metrics(i).coverage ?? -1));
    geo.setAttribute("aTest", attribute((i) => (view.buildings[i]!.building.role === "test" ? 1 : 0)));
    geo.setAttribute("aHue", attribute((i) => view.buildings[i]!.moduleHue));
    return geo;
  }, [view]);

  useEffect(() => () => geometry.dispose(), [geometry]);
  useEffect(() => () => material.dispose(), [material]);

  useLayoutEffect(() => {
    const mesh = meshRef.current;
    if (!mesh) return;
    const matrix = new THREE.Matrix4();
    view.buildings.forEach((b, i) => {
      const r = b.radius * 0.92;
      matrix.makeScale(r, b.height, r).setPosition(b.x, b.base, b.z);
      mesh.setMatrixAt(i, matrix);
    });
    mesh.instanceMatrix.needsUpdate = true;
    mesh.computeBoundingSphere();
  }, [view, geometry]);

  useEffect(() => {
    material.uniforms.uLayer!.value = layer === "debt" ? 1 : 0;
    material.uniforms.uSelected!.value = selectedIndex ?? -1;
    material.uniforms.uHovered!.value = hovered ?? -1;
  }, [material, layer, selectedIndex, hovered]);

  useEffect(() => {
    document.body.style.cursor = hovered === null ? "" : "pointer";
  }, [hovered]);

  useFrame(({ clock }) => {
    material.uniforms.uTime!.value = clock.elapsedTime;
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
