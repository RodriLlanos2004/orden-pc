import { useEffect, useMemo, useState } from "react";
import { motion } from "motion/react";
import { Download, RotateCcw } from "lucide-react";
import { Bajada, EASE } from "../components/motion";
import { Alerta, Buscador, Selector, Vacio } from "../components/ui";
import { fmtDateTime, formatBytes, fmtInt, timeAgo } from "../format";
import { RESULT, StepLine, useOps } from "../ops";
import { qs, useApi } from "../useApi";

type Row = {
  id: number;
  ts: number;
  batch: string;
  title: string;
  op: string;
  src: string | null;
  dst: string | null;
  is_dir: number;
  size: number;
  files: number;
  result: "hecho" | "error" | "omitido" | "iniciado";
  message: string | null;
  undo_of: number | null;
  undone_by: number | null;
  can_undo: boolean;
};

const OPS = [
  ["", "Todas las acciones"],
  ["crear", "Crear carpeta"],
  ["renombrar", "Renombrar"],
  ["mover", "Mover"],
  ["papelera", "Enviar a la Papelera"],
  ["restaurar", "Restaurar"],
  ["app_instalar", "Instalar app"],
  ["app_actualizar", "Actualizar app"],
  ["app_desinstalar", "Desinstalar app"],
];
const RESULTS = [
  ["", "Todos los resultados"],
  ["hecho", "Hechos"],
  ["error", "Con error"],
  ["omitido", "No se hicieron"],
  ["iniciado", "Iniciados en otra ventana"],
];

/** Cada cambio que hace Orden PC, agrupado por lote, con la opción de deshacerlo. */
export default function History() {
  const { openPlan, editMode, cambios } = useOps();
  const [op, setOp] = useState("");
  const [result, setResult] = useState("");
  const [query, setQuery] = useState("");
  const [q, setQ] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setQ(query.trim()), 200);
    return () => clearTimeout(t);
  }, [query]);
  const { data, error, loading } = useApi<{ items: Row[] }>(`/api/history?${qs({ op, result, q, v: cambios })}`);

  const batches = useMemo(() => {
    const out: { batch: string; title: string; ts: number; rows: Row[] }[] = [];
    for (const r of data?.items ?? []) {
      const last = out[out.length - 1];
      if (last && last.batch === r.batch) last.rows.push(r);
      else out.push({ batch: r.batch, title: r.title, ts: r.ts, rows: [r] });
    }
    return out;
  }, [data]);

  const undo = (ids: number[]) => openPlan({ kind: "deshacer", ids });
  const sinEdicion = editMode ? undefined : "Activa el Modo edición para deshacer";

  return (
    <div>
      <Bajada>Cada cambio que hace Orden PC, con la opción de deshacerlo. Deshacer también pasa por una vista previa.</Bajada>

      <div className="mt-8 flex flex-wrap items-center gap-2">
        <Selector label="Acción" value={op} options={OPS} onChange={setOp} />
        <Selector label="Resultado" value={result} options={RESULTS} onChange={setResult} />
        <Buscador value={query} onChange={setQuery} label="Buscar en el historial" placeholder="Busca por nombre o ruta" />
        <a href="/api/history.csv" download className="boton ml-auto">
          <Download size={14} aria-hidden="true" />
          Exportar CSV
        </a>
      </div>

      <Alerta className="mt-6">{error}</Alerta>

      <div className={`mt-6 flex flex-col gap-4 transition-opacity ${loading ? "opacity-50" : ""}`}>
        {data && batches.length === 0 && <Vacio>{op || result || q ? "Ningún cambio coincide con los filtros." : "Sin cambios todavía. Orden PC solo lee tus archivos hasta que actives el Modo edición."}</Vacio>}
        {batches.map((b, i) => {
          const undoable = b.rows.filter((r) => r.can_undo).map((r) => r.id);
          const counts = (["hecho", "error", "omitido", "iniciado"] as const).map((k) => [k, b.rows.filter((r) => r.result === k).length] as const).filter(([, n]) => n);
          return (
            <motion.section
              key={b.batch}
              aria-label={b.title}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: Math.min(i, 8) * 0.04, ease: EASE }}
              className="rounded-lg border border-linea bg-superficie"
            >
              <header className="flex flex-wrap items-start gap-4 px-5 py-4">
                <div className="min-w-0 flex-1">
                  <h3 className="font-mono text-base text-display">{b.title}</h3>
                  <p className="mt-1 text-xs text-tenue">
                    {fmtDateTime(b.ts)}, {timeAgo(b.ts)}. {counts.map(([k, n]) => `${fmtInt(n)} ${RESULT[k].label.toLowerCase()}`).join(", ")}.
                  </p>
                </div>
                {undoable.length > 1 && (
                  <button type="button" disabled={!editMode} title={sinEdicion} onClick={() => undo(undoable)} className="boton">
                    <RotateCcw size={14} aria-hidden="true" />
                    Deshacer todo el lote
                  </button>
                )}
              </header>
              <ol className="divide-y divide-linea border-t border-linea px-5">
                {b.rows.map((r) => {
                  const { icon: Icon, color, label } = RESULT[r.result];
                  return (
                    <li key={r.id} className="grid grid-cols-[6.5rem_1fr_auto] items-start gap-4 py-3 text-sm">
                      <span className={`flex items-center gap-1.5 text-xs ${color}`}>
                        <Icon size={14} aria-hidden="true" />
                        {label}
                      </span>
                      <span className="min-w-0">
                        <StepLine s={{ op: r.op, src: r.src, dst: r.dst, is_dir: !!r.is_dir, size: r.size, files: r.files }} />
                        {r.message && <span className="mt-1 block text-tenue">{r.message}</span>}
                        {r.undone_by && <span className="mt-1 block text-xs text-tenue">Deshecho después (cambio n.º {r.undone_by}).</span>}
                        {r.undo_of && <span className="mt-1 block text-xs text-tenue">Deshace el cambio n.º {r.undo_of}.</span>}
                      </span>
                      <span className="flex items-center gap-3">
                        {r.size > 0 && <span className="tabular-nums text-tenue">{formatBytes(r.size)}</span>}
                        {r.can_undo && (
                          <button type="button" disabled={!editMode} title={sinEdicion} onClick={() => undo([r.id])} className="enlace text-xs disabled:opacity-40">
                            Deshacer
                          </button>
                        )}
                      </span>
                    </li>
                  );
                })}
              </ol>
            </motion.section>
          );
        })}
      </div>
    </div>
  );
}
