import { Html } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { type AgentState, type Conflict, describeAction } from "../model/agents";
import { type CityView, PLATE_THICKNESS } from "../model/view";

const HOVER_ABOVE_ROOF = 1.8;

/** Live agents as glowing orbs that fly to whatever they are working on. */
export function AgentOrbs({ view, agents }: { view: CityView; agents: AgentState[] }) {
  return (
    <group>
      {agents.map((agent, order) => (
        <AgentOrb
          key={agent.id}
          agent={agent}
          target={targetPosition(view, agent, order, agents.length)}
        />
      ))}
    </group>
  );
}

function targetPosition(
  view: CityView,
  agent: AgentState,
  order: number,
  count: number,
): THREE.Vector3 {
  const angle = (order / Math.max(count, 1)) * Math.PI * 2;
  if (agent.status === "idle") {
    // Parked in a ring around the city.
    const radius = view.size * 0.62;
    return new THREE.Vector3(Math.cos(angle) * radius, 2.5, Math.sin(angle) * radius);
  }
  if (agent.target !== null && agent.action !== "command") {
    const index = view.indexById.get(agent.target);
    const building = index === undefined ? undefined : view.buildings[index];
    if (building) {
      // Agents on the same file sit side by side instead of overlapping.
      const offset = (order % 3) - 1;
      return new THREE.Vector3(
        building.x + offset * 0.9,
        building.base + building.height + HOVER_ABOVE_ROOF,
        building.z,
      );
    }
    const district = view.districts.find((d) => d.district.path === agent.target);
    if (district) {
      return new THREE.Vector3(district.x, district.elevation + PLATE_THICKNESS + 3, district.z);
    }
  }
  // Commands and anything without a place in the city: hover over the centre.
  const radius = Math.max(view.size * 0.12, 2);
  return new THREE.Vector3(
    Math.cos(angle) * radius,
    view.maxHeight * 0.7 + 4,
    Math.sin(angle) * radius,
  );
}

function AgentOrb({ agent, target }: { agent: AgentState; target: THREE.Vector3 }) {
  const group = useRef<THREE.Group>(null);
  const core = useMemo(
    () => new THREE.Color().setHSL(agent.hue, 0.85, 0.6).multiplyScalar(3),
    [agent.hue],
  );
  const halo = useMemo(() => new THREE.Color().setHSL(agent.hue, 0.9, 0.55), [agent.hue]);
  // Spawn at the first target; later targets are reached by the lerp below.
  const [initial] = useState(() => target.clone());

  useFrame(({ clock }, delta) => {
    const g = group.current;
    if (!g) return;
    const bob = Math.sin(clock.elapsedTime * 2 + agent.hue * 10) * 0.15;
    const goal = target.clone().setY(target.y + bob);
    g.position.lerp(goal, 1 - Math.exp(-delta * 3));
  });

  const idle = agent.status === "idle";
  return (
    <group ref={group} position={initial}>
      <mesh>
        <sphereGeometry args={[0.35, 24, 16]} />
        <meshBasicMaterial color={core} toneMapped={false} transparent opacity={idle ? 0.5 : 1} />
      </mesh>
      <mesh>
        <sphereGeometry args={[0.85, 24, 16]} />
        <meshBasicMaterial
          color={halo}
          transparent
          opacity={idle ? 0.06 : 0.16}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </mesh>
      <Html position={[0, 0.9, 0]} center style={{ pointerEvents: "none" }}>
        <div className="agent-label" style={{ borderColor: `hsl(${agent.hue * 360} 85% 60%)` }}>
          <b>{agent.name}</b>
          <span>{describeAction(agent)}</span>
        </div>
      </Html>
    </group>
  );
}

/** Spinning red rings over files that two agents are editing at the same time. */
export function ConflictMarkers({ view, conflicts }: { view: CityView; conflicts: Conflict[] }) {
  const color = useMemo(() => new THREE.Color(1, 0.12, 0.2).multiplyScalar(3), []);
  return (
    <group>
      {conflicts.map((conflict) => {
        const index = view.indexById.get(conflict.path);
        const building = index === undefined ? undefined : view.buildings[index];
        if (!building) return null;
        return (
          <ConflictRing
            key={conflict.path}
            position={[building.x, building.base + building.height + 0.5, building.z]}
            radius={building.radius * 1.4}
            color={color}
          />
        );
      })}
    </group>
  );
}

function ConflictRing(props: {
  position: [number, number, number];
  radius: number;
  color: THREE.Color;
}) {
  const ref = useRef<THREE.Mesh>(null);
  useFrame(({ clock }) => {
    const ring = ref.current;
    if (!ring) return;
    ring.rotation.z = clock.elapsedTime * 1.5;
    const pulse = 1 + Math.sin(clock.elapsedTime * 6) * 0.12;
    ring.scale.setScalar(pulse);
  });
  return (
    <mesh ref={ref} position={props.position} rotation={[-Math.PI / 2, 0, 0]}>
      <torusGeometry args={[props.radius, 0.08, 8, 6]} />
      <meshBasicMaterial color={props.color} toneMapped={false} />
    </mesh>
  );
}
