import { CameraControls, Grid } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { Bloom, EffectComposer, Noise, Vignette } from "@react-three/postprocessing";
import { type ComponentRef, useEffect, useRef } from "react";
import type { Conflict, LiveState } from "../model/agents";
import { visibleAgents } from "../model/agents";
import type { Edge } from "../model/city-model";
import type { BuildingProblems } from "../model/findings";
import type { Settings } from "../model/settings";
import type { BuildingShape, BuildingView, CityView, Layer } from "../model/view";
import { AgentOrbs, ConflictMarkers } from "./Agents";
import { Buildings } from "./Buildings";
import { Districts } from "./Districts";
import { ImportArcs } from "./ImportArcs";

const BACKGROUND = "#03060c";

interface Props {
  view: CityView;
  edges: Edge[];
  layer: Layer;
  shape: BuildingShape;
  live: LiveState;
  problems: ReadonlyMap<string, BuildingProblems>;
  settings: Settings;
  conflicts: Conflict[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}

export function CityCanvas(props: Props) {
  const { view, edges, layer, shape, live, problems, settings, conflicts } = props;
  const { selectedId, onSelect } = props;
  const selectedIndex = selectedId === null ? null : (view.indexById.get(selectedId) ?? null);
  const focus = selectedIndex === null ? null : (view.buildings[selectedIndex] ?? null);
  const size = Math.max(view.size, 10);

  return (
    <Canvas
      camera={{ fov: 45, near: 0.1, far: size * 30, position: [size, size * 0.8, size * 1.2] }}
      dpr={[1, 2]}
      gl={{ antialias: false }}
      onPointerMissed={() => onSelect(null)}
    >
      <color attach="background" args={[BACKGROUND]} />
      <fog attach="fog" args={[BACKGROUND, size * 1.2, size * 4]} />
      {settings.grid && (
      <Grid
        infiniteGrid
        position={[0, -0.01, 0]}
        cellSize={1}
        sectionSize={5}
        cellThickness={0.6}
        sectionThickness={1}
        cellColor="#0a2533"
        sectionColor="#0f5470"
        fadeDistance={size * 3}
        fadeStrength={1.5}
      />
      )}
      <Districts view={view} />
      <Buildings
        view={view}
        layer={layer}
        shape={shape}
        live={live}
        problems={problems}
        selectedIndex={selectedIndex}
        onSelect={(i) => onSelect(view.buildings[i]?.building.id ?? null)}
      />
      <ImportArcs view={view} edges={edges} selectedId={selectedId} mode={settings.arcs} />
      <AgentOrbs view={view} agents={visibleAgents(live)} />
      <ConflictMarkers view={view} conflicts={conflicts} />
      <CameraRig size={size} focus={focus} orbit={settings.idleOrbit} />
      <EffectComposer multisampling={4}>
        <Bloom mipmapBlur intensity={settings.glow} luminanceThreshold={0.3} luminanceSmoothing={0.25} />
        <Noise opacity={0.025} />
        <Vignette offset={0.3} darkness={0.75} />
      </EffectComposer>
    </Canvas>
  );
}

/** Slow orbit while idle; flies to the selected tower. */
function CameraRig(props: { size: number; focus: BuildingView | null; orbit: boolean }) {
  const { size, focus, orbit } = props;
  const ref = useRef<ComponentRef<typeof CameraControls>>(null);
  const idle = useRef(true);

  useEffect(() => {
    ref.current?.setLookAt(size * 0.75, size * 0.6, size * 0.9, 0, 0, 0, false);
  }, [size]);

  useEffect(() => {
    if (!ref.current) return;
    if (!focus) {
      ref.current.setFocalOffset(0, 0, 0, true);
      return;
    }
    idle.current = false;
    const top = focus.base + focus.height;
    const distance = Math.max(8, focus.height * 1.8);
    // Shift the framing left so the tower is not hidden behind the side panels.
    ref.current.setFocalOffset(distance * 0.35, 0, 0, true);
    ref.current.setLookAt(
      focus.x + distance,
      top + distance * 0.6,
      focus.z + distance,
      focus.x,
      focus.base + focus.height * 0.5,
      focus.z,
      true,
    );
  }, [focus]);

  useFrame((_, delta) => {
    if (idle.current && orbit) ref.current?.rotate(delta * 0.05, 0, false);
  });

  return (
    <CameraControls
      ref={ref}
      makeDefault
      minDistance={2}
      maxDistance={size * 5}
      maxPolarAngle={Math.PI * 0.47}
      onStart={() => {
        idle.current = false;
      }}
    />
  );
}
