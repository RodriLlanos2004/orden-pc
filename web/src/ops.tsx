import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import {
  AlertOctagon,
  AlertTriangle,
  AppWindow,
  ArrowRight,
  Check,
  ExternalLink,
  FolderPlus,
  Info,
  Minus,
  PencilLine,
  RotateCcw,
  Trash2,
  X,
  type LucideIcon,
} from "lucide-react";
import { api } from "./api";
import { EASE } from "./components/motion";
import { BotonCerrar, Dialogo } from "./components/ui";
import { formatBytes, fmtInt } from "./format";

export type PlanBody =
  | { kind: "crear"; path: string; name: string }
  | { kind: "renombrar"; path: string; name: string }
  | { kind: "mover"; paths: string[]; dest: string }
  | { kind: "papelera"; paths: string[] }
  | { kind: "deshacer"; ids: number[] }
  | { kind: "organizar"; moves: { src: string; dest: string; name: string }[]; folders?: string[] };

type Step = { op: string; src: string | null; dst: string | null; is_dir: boolean; size: number; files: number };
export type Aviso = { level: "info" | "aviso" | "peligro"; text: string };
type Plan = {
  id: string;
  kind: string;
  title: string;
  confirm: string;
  steps: Step[];
  blocked: { path: string; reason: string }[];
  warnings: Aviso[];
  needs_ack: boolean;
  total: number;
};
type Result = Step & { audit_id: number; result: "hecho" | "error" | "omitido"; message: string | null };
type Applied = { batch: string; title: string; results: Result[]; done: number; total: number };

type Ctx = {
  editMode: boolean | null;
  setEditMode: (on: boolean) => Promise<void>;
  editError: string;
  openPlan: (body: PlanBody, onDone?: () => void) => Promise<void>;
  /** Sube con cada cambio aplicado: lo que muestra el disco (árbol, listas) se vuelve a leer. */
  cambios: number;
};

const OpsContext = createContext<Ctx | null>(null);
export const useOps = () => useContext(OpsContext)!;

const OP_ICON: Record<string, LucideIcon> = {
  crear: FolderPlus,
  renombrar: PencilLine,
  mover: ArrowRight,
  papelera: Trash2,
  restaurar: RotateCcw,
};
const WARN: Record<Aviso["level"], { icon: LucideIcon; color: string }> = {
  info: { icon: Info, color: "text-tenue" },
  aviso: { icon: AlertTriangle, color: "text-cambios" },
  peligro: { icon: AlertOctagon, color: "text-error" },
};
export const RESULT: Record<string, { icon: LucideIcon; color: string; label: string }> = {
  hecho: { icon: Check, color: "text-exito", label: "Hecho" },
  error: { icon: X, color: "text-error", label: "Error" },
  omitido: { icon: Minus, color: "text-cambios", label: "No se hizo" },
  iniciado: { icon: ExternalLink, color: "text-tenue", label: "Iniciado" },
};
const APP_OPS: Record<string, string> = {
  app_desinstalar: "Se abrió el desinstalador de",
  app_actualizar: "Se abrió la actualización de",
  app_instalar: "Se abrió el instalador de",
};

const base = (p: string | null) => (p ? p.slice(p.lastIndexOf("\\") + 1) : "");
const folder = (p: string | null) => (p ? p.slice(0, p.lastIndexOf("\\")) : "");

/** Avisos de una vista previa o una confirmación, con su nivel. */
export function Avisos({ avisos }: { avisos: Aviso[] }) {
  if (!avisos.length) return null;
  return (
    <ul className="mb-4 space-y-2">
      {avisos.map((w, i) => {
        const { icon: Icon, color } = WARN[w.level];
        return (
          <li key={i} className="flex gap-2.5 rounded-md border border-linea px-3 py-2">
            <Icon size={16} aria-hidden="true" className={`mt-0.5 shrink-0 ${color}`} />
            <span>{w.text}</span>
          </li>
        );
      })}
    </ul>
  );
}

export function StepLine({ s }: { s: Step }) {
  const Icon = OP_ICON[s.op] ?? (s.op.startsWith("app_") ? AppWindow : ArrowRight);
  const b = (p: string | null) => <b className="font-medium">{base(p)}</b>;
  let text: React.ReactNode;
  if (APP_OPS[s.op])
    text = (
      <>
        {APP_OPS[s.op]} <b className="font-medium">{s.src}</b> <span className="block break-all font-mono text-[11px] text-tenue">{s.dst}</span>
      </>
    );
  else if (s.op === "crear") text = <>Nueva carpeta {b(s.dst)} en {folder(s.dst)}</>;
  else if (s.op === "papelera") text = <>{b(s.src)} a la Papelera <span className="text-tenue">desde {folder(s.src)}</span></>;
  else if (s.op === "restaurar") text = <>{b(s.dst)} vuelve a {folder(s.dst)}</>;
  else if (s.op === "renombrar") text = <>{b(s.src)} pasa a llamarse {b(s.dst)}</>;
  else
    text = (
      <>
        {b(s.src)} <span className="text-tenue">de {folder(s.src)}</span> a {folder(s.dst)}
        {base(s.src) !== base(s.dst) && <> como {b(s.dst)}</>}
      </>
    );
  return (
    <span className="flex min-w-0 items-start gap-2.5">
      <Icon size={15} aria-hidden="true" className="mt-0.5 shrink-0 text-tenue" />
      <span className="min-w-0 break-words">{text}</span>
    </span>
  );
}

function PlanDialog({ plan, editMode, onClose, onApplied, onUndo }: {
  plan: Plan;
  editMode: boolean;
  onClose: () => void;
  onApplied: () => void;
  onUndo: (ids: number[]) => void;
}) {
  const [ack, setAck] = useState(false);
  const [applied, setApplied] = useState<Applied | null>(null);
  const trashes = plan.steps.some((s) => s.op === "papelera");
  const undoable = applied?.results.filter((r) => r.result === "hecho" && plan.kind !== "deshacer").map((r) => r.audit_id) ?? [];

  async function confirm() {
    setApplied(await api<Applied>(`/api/ops/apply/${plan.id}`, { method: "POST", body: JSON.stringify({ ack }) }));
    onApplied();
    return false; // el diálogo sigue abierto para mostrar el resultado
  }

  const descripcion = applied ? (
    <p className="text-texto" aria-live="polite">
      Se {applied.done === 1 ? "hizo" : "hicieron"} {fmtInt(applied.done)} de {fmtInt(applied.total)} {applied.total === 1 ? "cambio" : "cambios"}. Todo quedó en el Historial.
    </p>
  ) : plan.total > 0 ? (
    `${formatBytes(plan.total)} en total`
  ) : undefined;

  return (
    <Dialogo
      titulo={plan.title}
      antetitulo={applied ? "Resultado" : "Vista previa: nada ha cambiado todavía"}
      descripcion={descripcion}
      ancho="w-[min(46rem,calc(100vw-2rem))]"
      onClose={onClose}
      onSubmit={confirm}
      confirmar={plan.steps.length ? plan.confirm : "Nada que hacer"}
      peligro={trashes}
      deshabilitado={!editMode || plan.steps.length === 0 || (plan.needs_ack && !ack)}
      enfoque={trashes || plan.needs_ack ? "cancelar" : plan.steps.length ? "confirmar" : undefined}
      pieIzq={
        applied ? undefined : !editMode ? (
          <span className="text-cambios">Activa el Modo edición para aplicar estos cambios.</span>
        ) : plan.needs_ack ? (
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} className="size-6 accent-[var(--acento)]" />
            Leí el aviso y quiero continuar
          </label>
        ) : undefined
      }
      pie={
        applied ? (
          <>
            {undoable.length > 0 && (
              <button type="button" onClick={() => onUndo(undoable)} className="boton">
                <RotateCcw size={14} aria-hidden="true" />
                Deshacer
              </button>
            )}
            <BotonCerrar primario autoFocus />
          </>
        ) : undefined
      }
    >
      {!applied ? (
        <>
          <Avisos avisos={plan.warnings} />
          {plan.steps.length > 0 && (
            <>
              <h3 className="text-xs text-tenue">Esto va a pasar ({fmtInt(plan.steps.length)})</h3>
              <ol className="mt-2 divide-y divide-linea">
                {plan.steps.map((s, i) => (
                  <motion.li
                    key={i}
                    initial={{ opacity: 0, x: -6 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.3, delay: Math.min(i, 12) * 0.03, ease: EASE }}
                    className="flex items-start justify-between gap-4 py-2"
                  >
                    <StepLine s={s} />
                    {s.size > 0 && <span className="shrink-0 tabular-nums text-tenue">{formatBytes(s.size)}</span>}
                  </motion.li>
                ))}
              </ol>
            </>
          )}
          {plan.blocked.length > 0 && (
            <>
              <h3 className="mt-5 text-xs text-tenue">No se incluye ({fmtInt(plan.blocked.length)})</h3>
              <ul className="mt-2 divide-y divide-linea">
                {plan.blocked.map((b, i) => (
                  <li key={i} className="py-2">
                    <p className="break-all font-mono text-[11px] text-tenue">{b.path}</p>
                    <p className="mt-0.5">{b.reason}</p>
                  </li>
                ))}
              </ul>
            </>
          )}
        </>
      ) : (
        <ol className="divide-y divide-linea">
          {applied.results.map((r, i) => {
            const { icon: Icon, color, label } = RESULT[r.result];
            return (
              <motion.li
                key={r.audit_id}
                initial={{ opacity: 0, scale: 0.98 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ duration: 0.3, delay: Math.min(i, 12) * 0.04, ease: EASE }}
                className="flex items-start gap-3 py-2"
              >
                <span className={`mt-0.5 flex shrink-0 items-center gap-1 text-xs ${color}`}>
                  <Icon size={15} aria-hidden="true" />
                  {label}
                </span>
                <span className="min-w-0">
                  <StepLine s={r} />
                  {r.message && <span className="mt-0.5 block text-tenue">{r.message}</span>}
                </span>
              </motion.li>
            );
          })}
        </ol>
      )}
    </Dialogo>
  );
}

export function OpsProvider({ children }: { children: React.ReactNode }) {
  const [editMode, setEdit] = useState<boolean | null>(null);
  const [editError, setEditError] = useState("");
  const [current, setCurrent] = useState<{ plan: Plan; onDone?: () => void } | null>(null);
  const [planError, setPlanError] = useState("");
  const [cambios, setCambios] = useState(0);

  useEffect(() => {
    api<{ edit_mode: boolean }>("/api/session")
      .then((s) => setEdit(s.edit_mode))
      .catch((e: Error) => setEditError(e.message));
  }, []);

  const setEditMode = useCallback(async (on: boolean) => {
    setEditError("");
    try {
      const s = await api<{ edit_mode: boolean }>("/api/session/edit-mode", { method: "POST", body: JSON.stringify({ enabled: on }) });
      setEdit(s.edit_mode);
    } catch (e) {
      setEditError((e as Error).message);
    }
  }, []);

  const openPlan = useCallback(async (body: PlanBody, onDone?: () => void) => {
    setPlanError("");
    try {
      const plan = await api<Plan>("/api/ops/plan", { method: "POST", body: JSON.stringify(body) });
      setCurrent({ plan, onDone });
    } catch (e) {
      setPlanError((e as Error).message);
    }
  }, []);

  return (
    <OpsContext.Provider value={{ editMode, setEditMode, editError, openPlan, cambios }}>
      {children}
      {current && (
        <PlanDialog
          key={current.plan.id}
          plan={current.plan}
          editMode={!!editMode}
          onClose={() => setCurrent(null)}
          onApplied={() => {
            setCambios((n) => n + 1);
            current.onDone?.();
          }}
          onUndo={(ids) => openPlan({ kind: "deshacer", ids }, current.onDone)}
        />
      )}
      <AnimatePresence>
        {planError && (
          <motion.div
            role="alert"
            initial={{ y: 40, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 40, opacity: 0 }}
            className="fixed inset-x-0 bottom-6 z-50 mx-auto flex w-[min(40rem,calc(100vw-2rem))] items-start gap-3 rounded-lg border border-error/50 bg-superficie px-4 py-3 text-sm shadow-2xl"
          >
            <AlertOctagon size={16} aria-hidden="true" className="mt-0.5 shrink-0 text-error" />
            <span className="flex-1">{planError}</span>
            <button type="button" onClick={() => setPlanError("")} aria-label="Cerrar aviso" data-tip-izq className="boton-icono size-6">
              <X size={14} aria-hidden="true" />
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </OpsContext.Provider>
  );
}
