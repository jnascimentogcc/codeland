import { QuadraticBezierLine } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { type ComponentRef, useMemo, useRef } from "react";
import * as THREE from "three";
import type { Edge } from "../model/city-model";
import type { CityView } from "../model/view";

const OUTGOING = new THREE.Color(0.2, 0.95, 1).multiplyScalar(2.2);
const INCOMING = new THREE.Color(1, 0.3, 0.85).multiplyScalar(2.2);
const IDLE = new THREE.Color(0.25, 0.6, 1).multiplyScalar(1.3);

interface Arc {
  key: string;
  edge: Edge;
  start: THREE.Vector3;
  end: THREE.Vector3;
  mid: THREE.Vector3;
}

/**
 * Imports as arcs of light between rooftops. With a selection, only its imports are shown
 * (outgoing in cyan, incoming in magenta) with particles flowing along the dependency.
 */
export function ImportArcs({
  view,
  edges,
  selectedId,
}: {
  view: CityView;
  edges: Edge[];
  selectedId: string | null;
}) {
  const arcs = useMemo(() => {
    const result: Arc[] = [];
    for (const edge of edges) {
      const from = view.buildings[view.indexById.get(edge.from) ?? -1];
      const to = view.buildings[view.indexById.get(edge.to) ?? -1];
      if (!from || !to) continue;
      const start = new THREE.Vector3(from.x, from.base + from.height, from.z);
      const end = new THREE.Vector3(to.x, to.base + to.height, to.z);
      const lift = Math.max(start.y, end.y) + start.distanceTo(end) * 0.35 + 1;
      const mid = start.clone().lerp(end, 0.5).setY(lift);
      result.push({ key: `${edge.from}>${edge.to}>${edge.kind}`, edge, start, end, mid });
    }
    return result;
  }, [view, edges]);

  const shown = selectedId
    ? arcs.filter((a) => a.edge.from === selectedId || a.edge.to === selectedId)
    : arcs;

  return (
    <group>
      {shown.map((arc) => (
        <ArcLine
          key={arc.key}
          arc={arc}
          color={!selectedId ? IDLE : arc.edge.from === selectedId ? OUTGOING : INCOMING}
          active={selectedId !== null}
        />
      ))}
    </group>
  );
}

function ArcLine({ arc, color, active }: { arc: Arc; color: THREE.Color; active: boolean }) {
  const ref = useRef<ComponentRef<typeof QuadraticBezierLine>>(null);
  useFrame((_, delta) => {
    if (active && ref.current) ref.current.material.dashOffset -= delta * 1.5;
  });
  return (
    <QuadraticBezierLine
      ref={ref}
      start={arc.start}
      end={arc.end}
      mid={arc.mid}
      color={color}
      lineWidth={active ? 2.2 : 1}
      dashed={active}
      dashSize={0.5}
      gapSize={0.35}
      transparent
      opacity={active ? 0.95 : 0.16}
      toneMapped={false}
    />
  );
}
