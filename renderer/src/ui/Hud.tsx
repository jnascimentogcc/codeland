import type { LiveStatus } from "../live/useLive";
import {
  type AgentState,
  type Conflict,
  describeAction,
  describeTests,
  type LiveState,
  summarizeChanges,
  visibleAgents,
} from "../model/agents";
import type { Building, CodelandCityModel } from "../model/city-model";
import { type BuildingShape, type CityView, hotspotRanking, type Layer } from "../model/view";

const STATUS_LABEL: Record<LiveStatus, string> = {
  off: "desligado",
  connecting: "conectando",
  live: "ao vivo",
  offline: "sem servidor",
};

interface Props {
  live: LiveState;
  liveStatus: LiveStatus;
  conflicts: Conflict[];
  model: CodelandCityModel;
  view: CityView;
  layer: Layer;
  onLayer: (layer: Layer) => void;
  shape: BuildingShape;
  onShape: (shape: BuildingShape) => void;
  showTests: boolean;
  onShowTests: (show: boolean) => void;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  error: string | null;
}

export function Hud(props: Props) {
  const { model, view, layer, onLayer, shape, onShape, showTests, onShowTests } = props;
  const { selectedId, onSelect } = props;
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
          <Segmented
            label="Camada"
            value={layer}
            onChange={onLayer}
            options={[
              ["structure", "Estrutura"],
              ["debt", "Dívida"],
              ["agents", "Agentes"],
            ]}
          />
          <Segmented
            label="Forma"
            value={shape}
            onChange={onShape}
            options={[
              ["rings", "Anéis"],
              ["prism", "Prisma"],
            ]}
          />
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
        <AgentsPanel
          live={props.live}
          status={props.liveStatus}
          conflicts={props.conflicts}
          onSelect={onSelect}
          known={(path) => model.buildings.some((b) => b.id === path)}
        />
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
        {layer === "agents" ? (
          <div className="muted">
            Prédio e feixe acendem na cor do agente que leu (fraco) ou editou (forte) o arquivo e
            apagam com o tempo · anel vermelho = dois agentes editando o mesmo arquivo
          </div>
        ) : layer === "debt" ? (
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

function AgentsPanel(props: {
  live: LiveState;
  status: LiveStatus;
  conflicts: Conflict[];
  onSelect: (id: string | null) => void;
  known: (path: string) => boolean;
}) {
  const { live, status, conflicts } = props;
  if (status === "off") return null;
  const agents = visibleAgents(live);
  const name = (id: string) => live.agents[id]?.name ?? id.slice(0, 4);

  return (
    <section className="panel agents">
      <h2>
        Agentes <span className={`live-status ${status}`}>{STATUS_LABEL[status]}</span>
      </h2>
      {conflicts.map((c) => (
        <button key={c.path} className="conflict" onClick={() => props.onSelect(c.path)}>
          <b>Conflito</b> {c.path}
          <span>{c.agents.map(name).join(" × ")}</span>
        </button>
      ))}
      {agents.length === 0 && (
        <p className="muted">
          {status === "live"
            ? "Nenhum agente ativo. Abra o Claude Code no repositório com os hooks instalados."
            : "Inicie: uv run codeland-live serve <repo>"}
        </p>
      )}
      <ul className="agent-list">
        {agents.map((agent) => {
          const target = agent.target && props.known(agent.target) ? agent.target : null;
          return (
            <li key={agent.id}>
              <button disabled={!target} onClick={() => target && props.onSelect(target)}>
                <i style={{ background: `hsl(${agent.hue * 360} 85% 60%)` }} />
                <span className="agent-name">{agent.name}</span>
                <span className="agent-action">{describeAction(agent)}</span>
                <span className="agent-counts">
                  {agent.reads} leituras · {agent.edits} edições · {agent.commands} comandos
                </span>
                {agent.tests && (
                  <span className={`agent-tests ${agent.tests.outcome}`}>
                    {agent.tests.outcome === "pass" ? "✓" : "✗"} {describeTests(agent.tests)}
                  </span>
                )}
              </button>
              <Changes agent={agent} onSelect={props.onSelect} known={props.known} />
            </li>
          );
        })}
      </ul>
    </section>
  );
}

const signed = (n: number) => (n > 0 ? `+${n}` : String(n));

/** What the agent changed: decisions are the debt signal (+ = more branching to maintain). */
function Changes(props: {
  agent: AgentState;
  onSelect: (id: string | null) => void;
  known: (path: string) => boolean;
}) {
  const { files, loc, decisions } = summarizeChanges(props.agent);
  if (files.length === 0) return null;
  return (
    <details className="changes">
      <summary>
        {files.length} {files.length === 1 ? "arquivo alterado" : "arquivos alterados"} ·{" "}
        {signed(loc)} linhas ·{" "}
        <span className={decisions > 0 ? "worse" : decisions < 0 ? "better" : ""}>
          {signed(decisions)} decisões
        </span>
      </summary>
      <ul>
        {files.map((f) => (
          <li key={f.path}>
            <button
              disabled={!props.known(f.path)}
              onClick={() => props.onSelect(f.path)}
              title={f.path}
            >
              <span className="path">{f.path}</span>
              <span className={f.decisions > 0 ? "worse" : f.decisions < 0 ? "better" : ""}>
                {f.created ? "novo · " : f.deleted ? "removido · " : ""}
                {signed(f.decisions)}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </details>
  );
}

function Segmented<T extends string>(props: {
  label: string;
  value: T;
  onChange: (value: T) => void;
  options: [T, string][];
}) {
  return (
    <div className="segmented" role="group" aria-label={props.label}>
      {props.options.map(([value, text]) => (
        <button
          key={value}
          className={props.value === value ? "active" : ""}
          onClick={() => props.onChange(value)}
        >
          {text}
        </button>
      ))}
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
