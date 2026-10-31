import { useState } from "react";
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
import type { Building, CodelandCityModel, Finding } from "../model/city-model";
import {
  CATEGORIES,
  type Category,
  duplicatesByPrimary,
  facets,
  type FindingFilter,
  formatLocation,
  isNew,
  isSetAside,
  type RankedFinding,
  SEVERITIES,
  type Severity,
  trendSummary,
} from "../model/findings";
import { type BuildingShape, type CityView, hotspotRanking, type Layer } from "../model/view";

const STATUS_LABEL: Record<LiveStatus, string> = {
  off: "desligado",
  connecting: "conectando",
  live: "ao vivo",
  offline: "sem servidor",
};

const CATEGORY_LABEL: Record<Category, string> = {
  security: "segurança",
  reliability: "confiabilidade",
  maintainability: "manutenibilidade",
  testing: "testes",
  dependencies: "dependências",
  performance: "desempenho",
  other: "outros",
};

const SEVERITY_LABEL: Record<Severity, string> = {
  critical: "crítica",
  high: "alta",
  medium: "média",
  low: "baixa",
  info: "info",
};

const LIST_LIMIT = 40;

interface Props {
  ranked: RankedFinding[];
  filter: FindingFilter;
  onFilter: (filter: FindingFilter) => void;
  selectedFindingId: string | null;
  onSelectFinding: (id: string | null) => void;
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
  const selectedFinding = model.findings.find((f) => f.id === props.selectedFindingId);
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
              ["problems", "Problemas"],
              ["debt", "Dívida"],
              ["structure", "Estrutura"],
              ...(props.liveStatus === "off" ? [] : [["agents", "Agentes"] as [Layer, string]]),
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
        <FindingsPanel
          model={model}
          ranked={props.ranked}
          filter={props.filter}
          onFilter={props.onFilter}
          selectedId={props.selectedFindingId}
          onSelect={props.onSelectFinding}
        />
        {selectedFinding && (
          <FindingDetails
            finding={selectedFinding}
            alsoReportedBy={duplicatesByPrimary(model.findings).get(selectedFinding.id) ?? []}
            since={model.analysis.trend?.since ?? null}
            triageFile={model.analysis.triageSource ?? "codeland-triage.json"}
            onClose={() => props.onSelectFinding(null)}
          />
        )}
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
        {layer === "problems" ? (
          <>
            <div className="gradient" />
            <div className="legend-scale">
              <span>nenhum / info</span>
              <span>crítica</span>
            </div>
            <div className="muted">
              Cor = problema mais grave do arquivo (após os filtros) · torre apagada = sem problemas
              · a lista ao lado ordena por prioridade
            </div>
          </>
        ) : layer === "agents" ? (
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

function FindingsPanel(props: {
  model: CodelandCityModel;
  ranked: RankedFinding[];
  filter: FindingFilter;
  onFilter: (filter: FindingFilter) => void;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}) {
  const { model, ranked, filter, onFilter } = props;
  const counts = facets(model, filter);
  const suppressed = model.findings.filter(isSetAside).length;
  const trend = trendSummary(model);
  const since = trend?.since ?? null;
  const toggleCategory = (category: Category) => {
    const next = new Set(filter.categories);
    if (!next.delete(category)) next.add(category);
    onFilter({ ...filter, categories: next });
  };

  if (model.findings.length === 0) {
    return (
      <section className="panel">
        <h2>Problemas</h2>
        <p className="muted">
          Nenhum problema no modelo. Importe relatórios com <code>--sarif</code> ao gerar a cidade.
        </p>
      </section>
    );
  }

  return (
    <section className="panel findings">
      <h2>
        Problemas <span className="live-status">{ranked.length}</span>
      </h2>
      <input
        className="search"
        type="search"
        placeholder="Buscar arquivo, regra ou mensagem"
        value={filter.query}
        onChange={(e) => onFilter({ ...filter, query: e.target.value })}
      />
      <div className="chips">
        {CATEGORIES.filter((c) => counts.categories[c] > 0 || filter.categories.has(c)).map((c) => (
          <button
            key={c}
            className={`chip ${filter.categories.has(c) ? "active" : ""}`}
            onClick={() => toggleCategory(c)}
          >
            {CATEGORY_LABEL[c]} {counts.categories[c]}
          </button>
        ))}
      </div>
      <div className="chips">
        {SEVERITIES.filter((s) => counts.severities[s] > 0 || filter.minSeverity === s).map((s) => (
          <button
            key={s}
            className={`chip sev-${s} ${filter.minSeverity === s && s !== "info" ? "active" : ""}`}
            title="Mostrar só esta severidade e as mais graves (clique de novo para limpar)"
            onClick={() =>
              onFilter({ ...filter, minSeverity: filter.minSeverity === s ? "info" : s })
            }
          >
            {SEVERITY_LABEL[s]} {counts.severities[s]}
          </button>
        ))}
      </div>
      {trend && (
        <div className="trend">
          <button
            className={`chip ${filter.onlyNew ? "active" : ""}`}
            title="Mostrar só os problemas que apareceram desde a análise anterior"
            onClick={() => onFilter({ ...filter, onlyNew: !filter.onlyNew })}
          >
            novos {trend.added}
          </button>
          <span className="muted">
            desde {formatDate(trend.since)} · {trend.fixed.length} corrigidos
          </span>
          {trend.fixed.length > 0 && (
            <details>
              <summary>ver corrigidos</summary>
              <ul className="fixed-list">
                {trend.fixed.map((f) => (
                  <li key={f.id}>
                    <i className={`sev-dot sev-${f.severity}`} /> {f.title ?? f.ruleId}
                    <span className="finding-where">{f.path}</span>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
      {suppressed > 0 && (
        <label className="toggle">
          <input
            type="checkbox"
            checked={filter.showSuppressed}
            onChange={(e) => onFilter({ ...filter, showSuppressed: e.target.checked })}
          />
          Mostrar suprimidos e triados ({suppressed})
        </label>
      )}
      {ranked.length === 0 && <p className="muted">Nenhum problema com esses filtros.</p>}
      <ol className="finding-list">
        {ranked.slice(0, LIST_LIMIT).map(({ finding, building, priority, alsoReportedBy }) => (
          <li key={finding.id}>
            <button
              className={finding.id === props.selectedId ? "active" : ""}
              onClick={() => props.onSelect(finding.id)}
              title={formatLocation(finding)}
            >
              <i className={`sev-dot sev-${finding.severity}`} />
              <span className="finding-title">
                {finding.title ?? finding.ruleId}
                {isNew(finding, since) && <b className="badge-new">novo</b>}
                {alsoReportedBy.length > 0 && (
                  <b className="badge-also" title={alsoReportedBy.map((f) => f.source.tool).join(", ")}>
                    +{alsoReportedBy.length}
                  </b>
                )}
              </span>
              <span className="finding-score">{priority.toFixed(1)}</span>
              <span className="finding-where">
                {formatLocation(finding)}
                {!building && " · fora da cidade"}
              </span>
            </button>
          </li>
        ))}
      </ol>
      {ranked.length > LIST_LIMIT && (
        <p className="muted">
          +{ranked.length - LIST_LIMIT} abaixo na prioridade; refine os filtros.
        </p>
      )}
    </section>
  );
}

const TRIAGE_LABEL = { accepted: "aceito", "false-positive": "falso positivo" } as const;

function formatDate(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleDateString("pt-BR");
}

function FindingDetails(props: {
  finding: Finding;
  alsoReportedBy: Finding[];
  since: string | null;
  triageFile: string;
  onClose: () => void;
}) {
  const { finding, source } = { finding: props.finding, source: props.finding.source };
  const [copied, setCopied] = useState<string | null>(null);
  const copy = (state: string) => {
    const command = `codeland-triage ${props.triageFile} ${state} ${finding.id} --note ""`;
    navigator.clipboard?.writeText(command).then(
      () => setCopied(state),
      () => setCopied(null),
    );
  };
  return (
    <section className="panel details">
      <button className="close" onClick={props.onClose} aria-label="Fechar">
        ×
      </button>
      <h2>
        <i className={`sev-dot sev-${finding.severity}`} /> {SEVERITY_LABEL[finding.severity]} ·{" "}
        {CATEGORY_LABEL[finding.category]}
        {finding.status === "suppressed" && " · suprimido"}
        {finding.triage && ` · ${TRIAGE_LABEL[finding.triage.state]}`}
      </h2>
      <div className="details-path">{finding.title ?? finding.ruleId}</div>
      <p className="finding-message">{finding.message}</p>
      <dl>
        <div>
          <dt>Regra</dt>
          <dd>{finding.ruleId}</dd>
        </div>
        <div>
          <dt>Local</dt>
          <dd>{formatLocation(finding)}</dd>
        </div>
        <div>
          <dt>Fonte</dt>
          <dd>
            {source.tool}
            {source.version && ` ${source.version}`}
            {source.kind === "agent" && " · agente"}
          </dd>
        </div>
        {props.alsoReportedBy.length > 0 && (
          <div>
            <dt>Também em</dt>
            <dd>
              {props.alsoReportedBy
                .map((f) => `${f.source.tool}${f.source.kind === "agent" ? " (agente)" : ""}: ${f.title ?? f.ruleId}`)
                .join("; ")}
            </dd>
          </div>
        )}
        <div>
          <dt>Visto desde</dt>
          <dd>
            {formatDate(finding.firstSeen)}
            {isNew(finding, props.since) && " · novo"}
          </dd>
        </div>
        {finding.triage && (
          <div>
            <dt>Decisão</dt>
            <dd>
              {TRIAGE_LABEL[finding.triage.state]}
              {finding.triage.at && ` em ${formatDate(finding.triage.at)}`}
              {finding.triage.note && `: ${finding.triage.note}`}
            </dd>
          </div>
        )}
      </dl>
      <div className="triage-actions">
        {finding.triage ? (
          <button className="chip" onClick={() => copy("reopen")}>
            {copied === "reopen" ? "comando copiado" : "reabrir"}
          </button>
        ) : (
          <>
            <button className="chip" onClick={() => copy("accepted")}>
              {copied === "accepted" ? "comando copiado" : "aceitar"}
            </button>
            <button className="chip" onClick={() => copy("false-positive")}>
              {copied === "false-positive" ? "comando copiado" : "falso positivo"}
            </button>
          </>
        )}
        <span className="muted">copia o comando para o terminal</span>
      </div>
      <div className="muted finding-id">id {finding.id}</div>
    </section>
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
