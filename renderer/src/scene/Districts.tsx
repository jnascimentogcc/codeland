import { Text } from "@react-three/drei";
import { useLayoutEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { type CityView, PLATE_THICKNESS } from "../model/view";

const LABEL_MAX_DEPTH = 2;
// Served from public/: without an explicit font, troika fetches one from a CDN at runtime.
const LABEL_FONT = `${import.meta.env.BASE_URL}fonts/inter-latin-600.woff`;

/** District plates (one instanced mesh) with neon outlines (one line segments geometry). */
export function Districts({ view }: { view: CityView }) {
  const platesRef = useRef<THREE.InstancedMesh>(null);

  const outline = useMemo(() => {
    const points: number[] = [];
    for (const d of view.districts) {
      const y = d.elevation + PLATE_THICKNESS + 0.005;
      const [x0, x1] = [d.x - d.width / 2, d.x + d.width / 2];
      const [z0, z1] = [d.z - d.depth / 2, d.z + d.depth / 2];
      points.push(x0, y, z0, x1, y, z0, x1, y, z0, x1, y, z1);
      points.push(x1, y, z1, x0, y, z1, x0, y, z1, x0, y, z0);
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.Float32BufferAttribute(points, 3));
    return geo;
  }, [view]);

  useLayoutEffect(() => {
    const mesh = platesRef.current;
    if (!mesh) return;
    const matrix = new THREE.Matrix4();
    const color = new THREE.Color();
    view.districts.forEach((d, i) => {
      matrix
        .makeScale(d.width, PLATE_THICKNESS, d.depth)
        .setPosition(d.x, d.elevation + PLATE_THICKNESS / 2, d.z);
      mesh.setMatrixAt(i, matrix);
      // Deeper districts are slightly lighter, so nesting stays readable from above.
      mesh.setColorAt(i, color.setHSL(0.58, 0.55, 0.035 + d.district.depth * 0.018));
    });
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  }, [view]);

  return (
    <group>
      <instancedMesh
        key={view.districts.length}
        ref={platesRef}
        args={[undefined, undefined, view.districts.length]}
      >
        <boxGeometry />
        <meshBasicMaterial />
      </instancedMesh>
      <lineSegments geometry={outline}>
        <lineBasicMaterial
          color={new THREE.Color(0.15, 0.75, 1).multiplyScalar(1.6)}
          transparent
          opacity={0.55}
          toneMapped={false}
        />
      </lineSegments>
      {view.districts
        .filter((d) => d.district.depth > 0 && d.district.depth <= LABEL_MAX_DEPTH)
        .map((d) => (
          <Text
            key={d.district.id}
            font={LABEL_FONT}
            position={[
              d.x - d.width / 2 + 0.4,
              d.elevation + PLATE_THICKNESS + 0.02,
              d.z + d.depth / 2 - 0.4,
            ]}
            rotation={[-Math.PI / 2, 0, 0]}
            fontSize={Math.min(Math.max(d.width * 0.045, 0.3), 1.6)}
            anchorX="left"
            anchorY="bottom"
            letterSpacing={0.12}
            color="#5fe3ff"
            fillOpacity={0.75}
          >
            {d.district.path.split("/").pop()!.toUpperCase()}
          </Text>
        ))}
    </group>
  );
}
