import type { ReactNode } from "react";
import {
  type ArcMode,
  DEFAULT_SETTINGS,
  type HeightMetric,
  type HeightScale,
  isDefault,
  LIST_LIMITS,
  matchingPreset,
  PRESETS,
  type PriorityWeights,
  presetSettings,
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

const SEVERITY_ROWS = [
  ["critical", "Crítica"],
  ["high", "Alta"],
  ["medium", "Média"],
  ["low", "Baixa"],
  ["info", "Info"],
] as const;

interface Props {
  settings: Settings;
  onChange: (settings: Settings) => void;
  onClose: () => void;
}

/** Everything that changes how the city looks or how problems are ranked; applies instantly. */
export function SettingsPanel({ settings, onChange, onClose }: Props) {
  const set = (patch: Partial<Settings>) => onChange({ ...settings, ...patch });
  const weight = (key: Exclude<keyof PriorityWeights, "severity">) => (value: number) =>
    set({ weights: { ...settings.weights, [key]: value } });
  const severity = (key: (typeof SEVERITY_ROWS)[number][0]) => (value: number) =>
    set({
      weights: { ...settings.weights, severity: { ...settings.weights.severity, [key]: value } },
    });
  const active = matchingPreset(settings);

  return (
    <section className="panel settings-panel" aria-label="Ajustes da visualização">
      <header className="settings-head">
        <h2>Ajustes</h2>
        <button className="close" onClick={onClose} aria-label="Fechar ajustes">
          ×
        </button>
      </header>

      <div className="presets" role="group" aria-label="Perfis">
        {PRESETS.map((preset) => (
          <button
            key={preset.id}
            className={`chip ${active?.id === preset.id ? "active" : ""}`}
            title={preset.hint}
            onClick={() => onChange(presetSettings(preset))}
          >
            {preset.label}
          </button>
        ))}
        {!active && <span className="muted">personalizado</span>}
      </div>

      <div className="settings-body">
        <Section title="Altura das torres" open>
          <Select
            label="Mede"
            value={settings.height}
            onChange={(height) => set({ height: height as HeightMetric })}
            options={(Object.keys(HEIGHT_LABEL) as HeightMetric[]).map((m) => [m, HEIGHT_LABEL[m]])}
          />
          <Select
            label="Escala"
            title="Raiz quadrada achata as torres muito altas e destaca as pequenas"
            value={settings.heightScale}
            onChange={(heightScale) => set({ heightScale: heightScale as HeightScale })}
            options={[
              ["linear", "linear"],
              ["sqrt", "raiz quadrada"],
            ]}
          />
          <Slider
            label="Exagero"
            value={settings.heightFactor}
            range={RANGES.heightFactor}
            format={(v) => `${v.toFixed(2)}×`}
            onChange={(heightFactor) => set({ heightFactor })}
          />
          <Slider
            label="Altura mínima"
            title="Altura de uma torre sem nada a mostrar: o quanto um lote vazio continua visível"
            value={settings.minHeight}
            range={RANGES.minHeight}
            onChange={(minHeight) => set({ minHeight })}
          />
          <Slider
            label="Largura"
            title="Quanto do lote cada torre ocupa"
            value={settings.towerWidth}
            range={RANGES.towerWidth}
            format={(v) => `${Math.round(v * 100)}%`}
            onChange={(towerWidth) => set({ towerWidth })}
          />
        </Section>

        <Section title="Prioridade dos problemas">
          <Slider
            label="Peso do hotspot"
            title="Quanto um arquivo crítico (complexo e que muda muito) pesa no ranking"
            value={settings.weights.hotspot}
            range={RANGES.hotspot}
            onChange={weight("hotspot")}
          />
          <Slider
            label="Peso das mudanças"
            title="Quanto um arquivo que muda com frequência pesa no ranking"
            value={settings.weights.churn}
            range={RANGES.churn}
            onChange={weight("churn")}
          />
          <Slider
            label="Falta de teste"
            title="Quanto a falta de cobertura de testes pesa no ranking"
            value={settings.weights.uncovered}
            range={RANGES.uncovered}
            onChange={weight("uncovered")}
          />
          <Slider
            label="Arquivos de teste"
            title="Importância dos problemas em arquivos de teste, em relação ao código"
            value={settings.weights.testFiles}
            range={RANGES.testFiles}
            format={(v) => `${Math.round(v * 100)}%`}
            onChange={weight("testFiles")}
          />
          <Slider
            label="Várias fontes"
            title="Bônus por cada outra ferramenta que reporta o mesmo problema (até duas)"
            value={settings.weights.corroboration}
            range={RANGES.corroboration}
            format={(v) => `+${Math.round(v * 100)}%`}
            onChange={weight("corroboration")}
          />
          <h3>Peso base por severidade</h3>
          {SEVERITY_ROWS.map(([key, label]) => (
            <Slider
              key={key}
              label={label}
              value={settings.weights.severity[key]}
              range={RANGES.severity}
              format={(v) => v.toFixed(1)}
              onChange={severity(key)}
            />
          ))}
          <Select
            label="Itens na lista"
            value={String(settings.listLimit)}
            onChange={(n) => set({ listLimit: Number(n) })}
            options={LIST_LIMITS.map((n) => [String(n), String(n)])}
          />
        </Section>

        <Section title="Cena">
          <Select
            label="Imports"
            value={settings.arcs}
            onChange={(arcs) => set({ arcs: arcs as ArcMode })}
            options={(Object.keys(ARC_LABEL) as ArcMode[]).map((m) => [m, ARC_LABEL[m]])}
          />
          <Slider
            label="Opacidade dos imports"
            value={settings.arcOpacity}
            range={RANGES.arcOpacity}
            format={(v) => `${Math.round(v * 100)}%`}
            onChange={(arcOpacity) => set({ arcOpacity })}
          />
          <Slider
            label="Brilho"
            value={settings.glow}
            range={RANGES.glow}
            onChange={(glow) => set({ glow })}
          />
          <Slider
            label="Velocidade da órbita"
            value={settings.orbitSpeed}
            range={RANGES.orbitSpeed}
            onChange={(orbitSpeed) => set({ orbitSpeed })}
          />
          <div className="field-row">
            <Check label="Órbita lenta" checked={settings.idleOrbit} onChange={(idleOrbit) => set({ idleOrbit })} />
            <Check label="Grade" checked={settings.grid} onChange={(grid) => set({ grid })} />
            <Check label="Névoa" checked={settings.fog} onChange={(fog) => set({ fog })} />
            <Check label="Distritos" checked={settings.districts} onChange={(districts) => set({ districts })} />
          </div>
        </Section>
      </div>

      <button
        className="chip reset"
        disabled={isDefault(settings)}
        onClick={() => onChange(DEFAULT_SETTINGS)}
      >
        restaurar padrões
      </button>
    </section>
  );
}

function Section(props: { title: string; open?: boolean; children: ReactNode }) {
  return (
    <details className="settings-section" open={props.open}>
      <summary>{props.title}</summary>
      {props.children}
    </details>
  );
}

function Select(props: {
  label: string;
  value: string;
  options: (readonly [string, string])[];
  onChange: (value: string) => void;
  title?: string;
}) {
  return (
    <label className="field" title={props.title}>
      <span>{props.label}</span>
      <select value={props.value} onChange={(e) => props.onChange(e.target.value)}>
        {props.options.map(([value, label]) => (
          <option key={value} value={value}>
            {label}
          </option>
        ))}
      </select>
    </label>
  );
}

function Check(props: { label: string; checked: boolean; onChange: (value: boolean) => void }) {
  return (
    <label className="toggle">
      <input
        type="checkbox"
        checked={props.checked}
        onChange={(e) => props.onChange(e.target.checked)}
      />
      {props.label}
    </label>
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
