import { useMemo, useState } from "react";
import { Link } from "react-router";
import { AnimatePresence, motion } from "motion/react";
import { ChevronDown, FolderOpen, SignalHigh, SignalLow, SignalMedium, SlidersHorizontal, Trash2, type LucideIcon } from "lucide-react";
import { api } from "../api";
import { useOps } from "../ops";
import { CountUp, EASE } from "../components/motion";
import { Alerta, BarraAccion, Casilla, Dialogo, MasFilas, useAccion, Vacio } from "../components/ui";
import { fmtDate, formatBytes, fmtInt, toGB } from "../format";
import { rutaPanel } from "../paneles";
import { useApi } from "../useApi";

type Confidence = "alta" | "media" | "baja";
type Rule = { id: string; label: string; description: string; enabled: boolean; confianza: Confidence; dias?: number; mb?: number; coincidencia?: number };
type Rec = {
  path: string;
  name: string;
  parent: string;
  size: number;
  reason: string;
  rule: string;
  confidence: Confidence;
  marked: boolean;
  detail: {
    keep?: { path: string; name: string; size: number; mtime: number };
    original?: { path: string; name: string; size: number; mtime: number };
    copy?: { size: number; mtime: number };
    app?: string;
  };
};
type Result = {
  rules: Rule[];
  items: Rec[];
  summary: { count: number; total: number; by_confidence: Record<Confidence, number>; marked: { count: number; bytes: number } };
};

const CONF: Record<Confidence, { icon: LucideIcon; label: string }> = {
  alta: { icon: SignalHigh, label: "Confianza alta" },
  media: { icon: SignalMedium, label: "Confianza media" },
  baja: { icon: SignalLow, label: "Confianza baja" },
};
const NIVELES: Confidence[] = ["alta", "media", "baja"];
const PAGE = 100; // filas por sección antes de "Mostrar más"
const PARAMS: Record<string, { label: string; unit: string; min: number; max: number }> = {
  dias: { label: "Antigüedad", unit: "días", min: 1, max: 3650 },
  mb: { label: "Tamaño mínimo", unit: "MB", min: 10, max: 100000 },
  coincidencia: { label: "Coincidencia mínima", unit: "%", min: 50, max: 100 },
};

function ConfidenceTag({ c }: { c: Confidence }) {
  const { icon: Icon, label } = CONF[c];
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-tenue">
      <Icon size={14} aria-hidden="true" className="text-texto" />
      {label}
    </span>
  );
}

function Compare({ rec }: { rec: Rec }) {
  const o = rec.detail.original;
  const c = rec.detail.copy;
  if (!o || !c) return null;
  const cell = (title: string, name: string, size: number, mtime: number) => (
    <div className="rounded-md border border-linea px-3 py-2">
      <p className="text-xs text-tenue">{title}</p>
      <p className="truncate text-texto" title={name}>
        {name}
      </p>
      <p className="mt-1 text-xs tabular-nums text-tenue">
        {formatBytes(size)}, modificado el {fmtDate(mtime)}
      </p>
    </div>
  );
  return (
    <div className="mt-3 grid gap-2 sm:grid-cols-2">
      {cell("Posible copia", rec.name, c.size, c.mtime)}
      {cell("Original", o.name, o.size, o.mtime)}
    </div>
  );
}

function RecRow({ rec, onMark }: { rec: Rec; onMark: (paths: string[], v: boolean) => void }) {
  return (
    <li className="grid grid-cols-[auto_1fr_auto] gap-x-4 gap-y-1 border-t border-linea py-4">
      <div className="pt-0.5">
        <Casilla checked={rec.marked} onChange={(v) => onMark([rec.path], v)} label={`Aceptar: eliminar ${rec.name}`} />
      </div>
      <div className="min-w-0">
        <p className="truncate font-medium text-texto" title={rec.name}>
          {rec.name}
        </p>
        <p className="truncate font-mono text-[11px] text-tenue" title={rec.parent}>
          {rec.parent}
        </p>
        <p className="mt-2 max-w-[72ch] text-sm leading-relaxed text-texto/85">{rec.reason}</p>
        {rec.detail.keep && (
          <p className="mt-1 truncate font-mono text-[11px] text-tenue" title={rec.detail.keep.path}>
            Se conserva: {rec.detail.keep.path}
          </p>
        )}
        <Compare rec={rec} />
      </div>
      <div className="flex flex-col items-end gap-2 text-right">
        <span className="tabular-nums text-texto">{formatBytes(rec.size)}</span>
        <Link to={rutaPanel("archivos", { ruta: rec.parent })} className="flex min-h-6 items-center gap-1 text-xs text-tenue hover:text-texto">
          <FolderOpen size={12} aria-hidden="true" />
          Ver carpeta
        </Link>
      </div>
    </li>
  );
}

function RuleSection({ rule, items, onMark, index }: { rule: Rule; items: Rec[]; onMark: (paths: string[], v: boolean) => void; index: number }) {
  const [open, setOpen] = useState(index < 2);
  const [shown, setShown] = useState(PAGE);
  const total = items.reduce((s, i) => s + i.size, 0);
  const marked = items.filter((i) => i.marked).length;
  const id = `regla-${rule.id}`;
  return (
    <motion.section
      aria-labelledby={id}
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.1 + index * 0.06, ease: EASE }}
      className="rounded-lg border border-linea bg-superficie"
    >
      <div className="flex flex-wrap items-center gap-4 px-5 py-4">
        <Casilla checked={marked === items.length} mixed={marked > 0 && marked < items.length} onChange={(v) => onMark(items.map((i) => i.path), v)} label={`Aceptar todas: ${rule.label}`} />
        <button type="button" aria-expanded={open} aria-controls={`${id}-lista`} onClick={() => setOpen(!open)} className="flex min-w-0 flex-1 items-center gap-3 text-left">
          <span className="min-w-0 flex-1">
            <span id={id} className="block font-mono text-base text-display">
              {rule.label}
            </span>
            <span className="mt-0.5 block text-sm text-tenue">{rule.description}</span>
          </span>
          <span className="shrink-0 text-right">
            <span className="block tabular-nums text-texto">{formatBytes(total)}</span>
            <span className="block text-xs text-tenue">
              {fmtInt(items.length)} {items.length === 1 ? "elemento" : "elementos"}
            </span>
          </span>
          <ChevronDown size={18} aria-hidden="true" className={`shrink-0 text-tenue transition-transform ${open ? "rotate-180" : ""}`} />
        </button>
        <span className="w-full pl-9 sm:w-auto sm:pl-0">
          <ConfidenceTag c={rule.confianza} />
        </span>
      </div>
      <AnimatePresence initial={false}>
        {open && (
          <motion.ul
            id={`${id}-lista`}
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.35, ease: EASE }}
            className="overflow-hidden px-5"
          >
            {items.slice(0, shown).map((r) => (
              <RecRow key={r.path} rec={r} onMark={onMark} />
            ))}
            <MasFilas restantes={items.length - shown} pagina={PAGE} onMas={() => setShown(shown + PAGE)} />
            <li className="h-2" aria-hidden="true" />
          </motion.ul>
        )}
      </AnimatePresence>
    </motion.section>
  );
}

function RulesDialog({ rules, onClose, onSaved }: { rules: Rule[]; onClose: () => void; onSaved: () => void }) {
  const [draft, setDraft] = useState<Rule[]>(rules);
  const set = (id: string, patch: Partial<Rule>) => setDraft((ds) => ds.map((r) => (r.id === id ? { ...r, ...patch } : r)));

  async function save() {
    const body: Record<string, Record<string, unknown>> = {};
    for (const r of draft) {
      body[r.id] = { enabled: r.enabled, confianza: r.confianza };
      for (const p of Object.keys(PARAMS)) if (r[p as keyof Rule] !== undefined) body[r.id][p] = Number(r[p as keyof Rule]);
    }
    await api("/api/recommendations/rules", { method: "PUT", body: JSON.stringify({ rules: body }) });
    onSaved();
  }

  return (
    <Dialogo
      titulo="Ajustar reglas"
      descripcion="Elige qué reglas se aplican, con qué confianza y desde qué umbral. Ninguna regla borra nada por sí sola."
      ancho="w-[min(44rem,calc(100vw-2rem))]"
      onClose={onClose}
      onSubmit={save}
      confirmar="Guardar reglas"
    >
      {draft.map((r) => (
        <fieldset key={r.id} className="border-t border-linea py-4 first:border-t-0 first:pt-0">
          <legend className="sr-only">{r.label}</legend>
          <label className="flex items-center gap-3">
            <Casilla checked={r.enabled} onChange={(v) => set(r.id, { enabled: v })} />
            <span className={r.enabled ? "text-texto" : "text-tenue"}>{r.label}</span>
          </label>
          <div className="mt-3 flex flex-wrap gap-4 pl-9">
            <label className="flex items-center gap-2">
              <span className="text-tenue">Confianza</span>
              <select value={r.confianza} disabled={!r.enabled} onChange={(e) => set(r.id, { confianza: e.target.value as Confidence })} className="campo w-auto px-2 py-1">
                <option value="alta">Alta</option>
                <option value="media">Media</option>
                <option value="baja">Baja</option>
              </select>
            </label>
            {Object.entries(PARAMS).map(([p, meta]) =>
              r[p as keyof Rule] !== undefined ? (
                <label key={p} className="flex items-center gap-2">
                  <span className="text-tenue">{meta.label}</span>
                  <input
                    type="number"
                    min={meta.min}
                    max={meta.max}
                    required
                    disabled={!r.enabled}
                    value={String(r[p as keyof Rule])}
                    onChange={(e) => set(r.id, { [p]: e.target.value === "" ? "" : Number(e.target.value) } as Partial<Rule>)}
                    className="campo w-24 px-2 py-1 tabular-nums"
                  />
                  <span className="text-tenue">{meta.unit}</span>
                </label>
              ) : null,
            )}
          </div>
        </fieldset>
      ))}
    </Dialogo>
  );
}

export default function Recommendations() {
  const { editMode, openPlan, cambios } = useOps();
  const { data, error, loading, setData, recargar } = useApi<Result>(`/api/recommendations?v=${cambios}`);
  const summary = useApi<{ scanned: boolean }>("/api/summary");
  const [filter, setFilter] = useState<Set<Confidence>>(new Set(NIVELES));
  const [dialog, setDialog] = useState(false);
  const marcar = useAccion();

  const groups = useMemo(() => {
    if (!data) return [];
    return data.rules
      .filter((r) => r.enabled && filter.has(r.confianza))
      .map((r) => ({ rule: r, items: data.items.filter((i) => i.rule === r.id) }))
      .filter((g) => g.items.length > 0);
  }, [data, filter]);

  async function mark(paths: string[], marked: boolean) {
    if (!data) return;
    const set = new Set(paths);
    const items = data.items.map((i) => (set.has(i.path) ? { ...i, marked } : i));
    const m = items.filter((i) => i.marked);
    setData({ ...data, items, summary: { ...data.summary, marked: { count: m.length, bytes: m.reduce((s, i) => s + i.size, 0) } } });
    const rule = data.items.find((i) => set.has(i.path))?.rule ?? "";
    if (!(await marcar.correr(() => api("/api/recommendations/marks", { method: "POST", body: JSON.stringify({ paths, marked, rule }) })))) setData(data);
  }

  if (summary.data && !summary.data.scanned) {
    return <p className="text-tenue">Las recomendaciones salen de tu índice. Escanea tu equipo desde el árbol y vuelve aquí.</p>;
  }

  const s = data?.summary;
  return (
    <div>
      <p className="max-w-2xl text-tenue">Lo que podrías eliminar y por qué. Nada se borra solo: tú marcas lo que aceptas.</p>
      <Alerta className="mt-8">{error}</Alerta>

      {s && (
        <div className={`mt-10 transition-opacity ${loading ? "opacity-50" : ""}`}>
          <div className="flex flex-wrap items-end gap-x-14 gap-y-8">
            <div>
              <p className="cifra text-[clamp(3rem,7vw,5rem)] text-acento">
                <CountUp value={toGB(s.total)} format={(n) => `${n.toLocaleString("es-MX", { maximumFractionDigits: 1 })} GB`} />
              </p>
              <p className="mt-3 text-sm text-tenue">
                recuperables en {fmtInt(s.count)} {s.count === 1 ? "elemento" : "elementos"}
              </p>
            </div>
            <dl className="flex flex-wrap gap-x-10 gap-y-4">
              {NIVELES.map((c) => (
                <div key={c}>
                  <dt>
                    <ConfidenceTag c={c} />
                  </dt>
                  <dd className="cifra mt-1 text-2xl text-texto">{formatBytes(s.by_confidence[c])}</dd>
                </div>
              ))}
            </dl>
          </div>

          <div className="mt-12 flex flex-wrap items-center gap-2">
            <span className="mr-1 text-sm text-tenue">Mostrar</span>
            {NIVELES.map((c) => {
              const on = filter.has(c);
              const Icon = CONF[c].icon;
              return (
                <button
                  key={c}
                  type="button"
                  aria-pressed={on}
                  onClick={() => {
                    const n = new Set(filter);
                    if (on) n.delete(c);
                    else n.add(c);
                    setFilter(n);
                  }}
                  className={`boton ${on ? "border-acento" : "text-tenue"}`}
                >
                  <Icon size={14} aria-hidden="true" />
                  {CONF[c].label}
                </button>
              );
            })}
            <button type="button" onClick={() => setDialog(true)} className="boton ml-auto">
              <SlidersHorizontal size={14} aria-hidden="true" />
              Ajustar reglas
            </button>
          </div>

          <div className="mt-6 flex flex-col gap-4">
            {groups.map((g, i) => (
              <RuleSection key={g.rule.id} rule={g.rule} items={g.items} onMark={mark} index={i} />
            ))}
            {groups.length === 0 && <Vacio>{s.count === 0 ? "Todo en orden: ninguna regla encontró algo que eliminar." : "Ninguna recomendación con la confianza elegida. Activa otro nivel arriba."}</Vacio>}
          </div>
        </div>
      )}

      <Alerta className="mt-4">{marcar.error}</Alerta>
      <BarraAccion
        visible={!!s && s.marked.count > 0}
        texto={
          s && (
            <>
              Aceptaste {fmtInt(s.marked.count)} {s.marked.count === 1 ? "recomendación" : "recomendaciones"}: <span className="cifra text-acento">{formatBytes(s.marked.bytes)}</span>
            </>
          )
        }
        detalle={editMode ? "Antes de enviar verás la lista exacta. Todo se puede restaurar desde el Historial." : "Activa el Modo edición arriba para enviarlas a la Papelera."}
      >
        <button type="button" disabled={!editMode} onClick={() => openPlan({ kind: "papelera", paths: data!.items.filter((i) => i.marked).map((i) => i.path) })} className="boton-peligro">
          <Trash2 size={15} aria-hidden="true" />
          Enviar a la Papelera
        </button>
      </BarraAccion>

      {dialog && data && <RulesDialog rules={data.rules} onClose={() => setDialog(false)} onSaved={recargar} />}
    </div>
  );
}
