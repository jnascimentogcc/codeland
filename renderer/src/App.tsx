import { useEffect, useMemo, useState } from "react";
import type { CodelandCityModel } from "./model/city-model";
import { loadDefaultModel, parseModel } from "./model/load";
import { type BuildingShape, buildCityView, type Layer } from "./model/view";
import { CityCanvas } from "./scene/CityCanvas";
import { Hud } from "./ui/Hud";

export function App() {
  const [model, setModel] = useState<CodelandCityModel | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [layer, setLayer] = useState<Layer>("debt");
  const [shape, setShape] = useState<BuildingShape>("rings");
  const [showTests, setShowTests] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    loadDefaultModel().then(setModel, (e: Error) => setError(e.message));
  }, []);

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
        selectedId={selectedId}
        onSelect={setSelectedId}
      />
      <Hud
        model={model}
        view={view}
        layer={layer}
        onLayer={setLayer}
        shape={shape}
        onShape={setShape}
        showTests={showTests}
        onShowTests={setShowTests}
        selectedId={selectedId}
        onSelect={setSelectedId}
        error={error}
      />
    </>
  );
}
