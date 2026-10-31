import {
  type ArcMode,
  DEFAULT_SETTINGS,
  type HeightMetric,
  type HeightScale,
  isDefault,
  LIST_LIMITS,
  type PriorityWeights,
  RANGES,
  type Settings,
} from "../model/settings";

const HEIGHT_LABEL: Record<HeightMetric, string> = {
  loc: "linhas de código",
  decisions: "complexidade (decisões)",
  churn: "mudanças (commits)",
  problems: "nº de problemas",
};

const ARC_LABEL: Record<ArcMode, string> = {
  auto: "todos, fracos",
  selection: "só da seleção",
  off: "ocultos",
};

interface Props {
  settings: Settings;
  onChange: (settings: Settings) => void;
}

/** Everything that changes how the city looks or how problems are ranked; applies instantly. */
export function SettingsPanel({ settings, onChange }: Props) {
  const set = (patch: Partial<Settings>) => onChange({ ...settings, ...patch });
  const weight = (key: keyof PriorityWeights) => (value: number) =>
    set({ weights: { ...settings.weights, [key]: value } });

  return (
    <div className="settings">
      <h2>Altura das torres</h2>
      <label className="field">
        <span>Mede</span>
        <select
          value={settings.height}
          onChange={(e) => set({ height: e.target.value as HeightMetric })}
        >
          {(Object.keys(HEIGHT_LABEL) as HeightMetric[]).map((metric) => (
            <option key={metric} value={metric}>
              {HEIGHT_LABEL[metric]}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>Escala</span>
        <select
          value={settings.heightScale}
          title="Raiz quadrada achata as torres muito altas e destaca as pequenas"
          onChange={(e) => set({ heightScale: e.target.value as HeightScale })}
        >
          <option value="linear">linear</option>
          <option value="sqrt">raiz quadrada</option>
        </select>
      </label>
      <Slider
        label="Exagero"
        value={settings.heightFactor}
        range={RANGES.heightFactor}
        format={(v) => `${v.toFixed(2)}×`}
        onChange={(heightFactor) => set({ heightFactor })}
      />

      <h2>Prioridade dos problemas</h2>
      <Slider
        label="Peso do hotspot"
        value={settings.weights.hotspot}
        range={RANGES.hotspot}
        onChange={weight("hotspot")}
        title="Quanto um arquivo crítico (complexo e que muda muito) pesa no ranking"
      />
      <Slider
        label="Peso das mudanças"
        value={settings.weights.churn}
        range={RANGES.churn}
        onChange={weight("churn")}
        title="Quanto um arquivo que muda com frequência pesa no ranking"
      />
      <Slider
        label="Peso da falta de teste"
        value={settings.weights.uncovered}
        range={RANGES.uncovered}
        onChange={weight("uncovered")}
        title="Quanto a falta de cobertura de testes pesa no ranking"
      />
      <Slider
        label="Arquivos de teste"
        value={settings.weights.testFiles}
        range={RANGES.testFiles}
        format={(v) => `${Math.round(v * 100)}%`}
        onChange={weight("testFiles")}
        title="Importância dos problemas em arquivos de teste, em relação ao código"
      />
      <Slider
        label="Várias fontes"
        value={settings.weights.corroboration}
        range={RANGES.corroboration}
        format={(v) => `+${Math.round(v * 100)}%`}
        onChange={weight("corroboration")}
        title="Bônus por cada outra ferramenta que reporta o mesmo problema (até duas)"
      />
      <label className="field">
        <span>Itens na lista</span>
        <select value={settings.listLimit} onChange={(e) => set({ listLimit: Number(e.target.value) })}>
          {LIST_LIMITS.map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
      </label>

      <h2>Cena</h2>
      <label className="field">
        <span>Imports</span>
        <select value={settings.arcs} onChange={(e) => set({ arcs: e.target.value as ArcMode })}>
          {(Object.keys(ARC_LABEL) as ArcMode[]).map((mode) => (
            <option key={mode} value={mode}>
              {ARC_LABEL[mode]}
            </option>
          ))}
        </select>
      </label>
      <Slider
        label="Brilho"
        value={settings.glow}
        range={RANGES.glow}
        onChange={(glow) => set({ glow })}
      />
      <div className="field-row">
        <label className="toggle">
          <input
            type="checkbox"
            checked={settings.idleOrbit}
            onChange={(e) => set({ idleOrbit: e.target.checked })}
          />
          Órbita lenta
        </label>
        <label className="toggle">
          <input
            type="checkbox"
            checked={settings.grid}
            onChange={(e) => set({ grid: e.target.checked })}
          />
          Grade
        </label>
      </div>
      <button
        className="chip reset"
        disabled={isDefault(settings)}
        onClick={() => onChange(DEFAULT_SETTINGS)}
      >
        restaurar padrões
      </button>
    </div>
  );
}

function Slider(props: {
  label: string;
  value: number;
  range: { min: number; max: number; step: number };
  onChange: (value: number) => void;
  format?: (value: number) => string;
  title?: string;
}) {
  const { label, value, range, onChange, format, title } = props;
  return (
    <label className="field" title={title}>
      <span>{label}</span>
      <input
        type="range"
        min={range.min}
        max={range.max}
        step={range.step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
      <output>{format ? format(value) : value.toFixed(2)}</output>
    </label>
  );
}
