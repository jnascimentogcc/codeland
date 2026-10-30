import type { Building, CodelandCityModel } from "../model/city-model";
import { type CityView, hotspotRanking, type Layer } from "../model/view";

interface Props {
  model: CodelandCityModel;
  view: CityView;
  layer: Layer;
  onLayer: (layer: Layer) => void;
  showTests: boolean;
  onShowTests: (show: boolean) => void;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  error: string | null;
}

export function Hud(props: Props) {
  const { model, view, layer, onLayer, showTests, onShowTests, selectedId, onSelect } = props;
  const selected = model.buildings.find((b) => b.id === selectedId);
  const hotspots = hotspotRanking(model, 10);
  const { repository } = model;

  return (
    <div className="hud">
      <header className="panel brand">
        <div className="logo">CODELAND</div>
        <div className="repo">{repository.name}</div>
        <div className="muted">
          {repository.branch ?? "detached"}
          {repository.commit && ` @ ${repository.commit.slice(0, 7)}`}
        </div>
        <div className="muted">
          {model.buildings.length} arquivos · {model.edges.length} imports ·{" "}
          {model.analysis.churnWindowDays} dias de histórico
        </div>
        <div className="controls">
          <div className="segmented" role="group" aria-label="Camada">
            {(
              [
                ["structure", "Estrutura"],
                ["debt", "Dívida"],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                className={layer === value ? "active" : ""}
                onClick={() => onLayer(value)}
              >
                {label}
              </button>
            ))}
          </div>
          <label className="toggle">
            <input
              type="checkbox"
              checked={showTests}
              onChange={(e) => onShowTests(e.target.checked)}
            />
            Testes
          </label>
        </div>
      </header>

      <aside className="side">
        {selected && <Details building={selected} onClose={() => onSelect(null)} />}
        <section className="panel">
          <h2>Pontos críticos</h2>
          {hotspots.length === 0 && <p className="muted">Nenhum arquivo com mudanças e decisões.</p>}
          <ol className="ranking">
            {hotspots.map((b) => (
              <li key={b.id}>
                <button
                  className={b.id === selectedId ? "active" : ""}
                  onClick={() => onSelect(b.id)}
                  title={b.path}
                >
                  <span className="bar" style={{ width: `${b.metrics.hotspot * 100}%` }} />
                  <span className="score">{b.metrics.hotspot.toFixed(2)}</span>
                  <span className="path">{b.path}</span>
                </button>
              </li>
            ))}
          </ol>
        </section>
      </aside>

      <footer className="panel legend">
        {layer === "debt" ? (
          <>
            <div className="gradient" />
            <div className="legend-scale">
              <span>estável</span>
              <span>ponto crítico</span>
            </div>
            <div className="muted">
              Altura = linhas · base = imports · pulso = decisões × mudanças
              {model.analysis.coverageSource
                ? " · arestas apagadas = cobertura < 50%"
                : " · sem relatório de cobertura"}
            </div>
          </>
        ) : (
          <div className="modules">
            {view.modules.map((m) => (
              <span key={m.name}>
                <i style={{ background: `hsl(${m.hue * 360} 80% 60%)` }} />
                {m.name}
              </span>
            ))}
          </div>
        )}
        <div className="muted hint">Arraste um city.json para abrir outro repositório</div>
      </footer>

      {props.error && <div className="panel error">{props.error}</div>}
    </div>
  );
}

function Details({ building, onClose }: { building: Building; onClose: () => void }) {
  const m = building.metrics;
  const rows: [string, string][] = [
    ["Pontuação", m.hotspot.toFixed(2)],
    ["Decisões", String(m.decisions)],
    ["Complexidade (máx. função)", `${m.complexity} (${m.maxFunctionComplexity})`],
    ["Linhas de código", String(m.loc)],
    ["Funções", String(m.functions)],
    ["Imports (externos)", `${m.imports} (${m.externalImports})`],
    ["Commits / linhas alteradas", `${m.churnCommits} / ${m.churnLines}`],
    ["Cobertura", m.coverage === null ? "—" : `${Math.round(m.coverage * 100)}%`],
  ];
  return (
    <section className="panel details">
      <button className="close" onClick={onClose} aria-label="Fechar">
        ×
      </button>
      <h2>{building.role === "test" ? "Teste" : "Arquivo"}</h2>
      <div className="details-path">{building.path}</div>
      <dl>
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
