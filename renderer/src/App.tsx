import { useEffect, useMemo, useState } from "react";
import { useLive, useNow } from "./live/useLive";
import { conflicts as findConflicts } from "./model/agents";
import type { CodelandCityModel } from "./model/city-model";
import { DEFAULT_FILTER, type FindingFilter, problemsByBuilding, rankFindings } from "./model/findings";
import { loadDefaultModel, parseModel } from "./model/load";
import { type BuildingShape, buildCityView, type Layer } from "./model/view";
import { CityCanvas } from "./scene/CityCanvas";
import { Hud } from "./ui/Hud";

export function App() {
  const [model, setModel] = useState<CodelandCityModel | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [layer, setLayer] = useState<Layer>("problems");
  const [shape, setShape] = useState<BuildingShape>("rings");
  const [showTests, setShowTests] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedFindingId, setSelectedFindingId] = useState<string | null>(null);
  const [filter, setFilter] = useState<FindingFilter>(DEFAULT_FILTER);
  const live = useLive();
  const now = useNow();
  const conflicts = useMemo(() => findConflicts(live.state, now), [live.state, now]);
  const ranked = useMemo(() => (model ? rankFindings(model, filter) : []), [model, filter]);
  const problems = useMemo(() => problemsByBuilding(ranked), [ranked]);

  useEffect(() => {
    loadDefaultModel().then((loaded) => {
      setModel(loaded);
      if (loaded.findings.length === 0) setLayer("debt"); // nothing to show on the problems layer
    }, (e: Error) => setError(e.message));
  }, []);

  const selectBuilding = (id: string | null) => {
    setSelectedId(id);
    setSelectedFindingId(null);
  };
  const selectFinding = (id: string | null) => {
    setSelectedFindingId(id);
    const finding = model?.findings.find((f) => f.id === id);
    const building = model?.buildings.find((b) => b.path === finding?.location.path);
    setSelectedId(building?.id ?? null);
  };

  useEffect(() => {
    // Drop a city.json anywhere on the page to open another repository.
    const onDragOver = (e: DragEvent) => e.preventDefault();
    const onDrop = async (e: DragEvent) => {
      e.preventDefault();
      const file = e.dataTransfer?.files[0];
      if (!file) return;
      try {
        setModel(parseModel(JSON.parse(await file.text())));
        setSelectedId(null);
        setSelectedFindingId(null);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    };
    window.addEventListener("dragover", onDragOver);
    window.addEventListener("drop", onDrop);
    return () => {
      window.removeEventListener("dragover", onDragOver);
      window.removeEventListener("drop", onDrop);
    };
  }, []);

  const view = useMemo(
    () => (model ? buildCityView(model, { includeTests: showTests }) : null),
    [model, showTests],
  );

  if (!model || !view) {
    return <div className="splash">{error ?? "Carregando cidade…"}</div>;
  }

  return (
    <>
      <CityCanvas
        view={view}
        edges={model.edges}
        layer={layer}
        shape={shape}
        live={live.state}
        problems={problems}
        conflicts={conflicts}
        selectedId={selectedId}
        onSelect={selectBuilding}
      />
      <Hud
        ranked={ranked}
        filter={filter}
        onFilter={setFilter}
        selectedFindingId={selectedFindingId}
        onSelectFinding={selectFinding}
        live={live.state}
        liveStatus={live.status}
        conflicts={conflicts}
        model={model}
        view={view}
        layer={layer}
        onLayer={setLayer}
        shape={shape}
        onShape={setShape}
        showTests={showTests}
        onShowTests={setShowTests}
        selectedId={selectedId}
        onSelect={selectBuilding}
        error={error}
      />
    </>
  );
}
