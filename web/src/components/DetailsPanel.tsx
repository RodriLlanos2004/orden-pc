import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Check, Copy, GitBranch, Lock, RefreshCw, Sparkles } from "lucide-react";
import { api } from "../api";
import { useAsistente } from "../asistente/Asistente";
import { EASE } from "./motion";
import { Alerta, useAccion } from "./ui";
import { fmtDateTime, formatBytes, fmtInt, timeAgo } from "../format";
import { qs, useApi } from "../useApi";
import { CLOUD_LABELS, StatusMarks, TYPE_LABELS, TypeIcon } from "./StatusMarks";
import type { EntryDetails } from "../types";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[7.5rem_1fr] gap-3 border-t border-linea py-2">
      <dt className="text-tenue">{label}</dt>
      <dd className="min-w-0 break-words text-texto">{children}</dd>
    </div>
  );
}

function CopyPath({ path }: { path: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      onClick={() => navigator.clipboard.writeText(path).then(() => (setDone(true), setTimeout(() => setDone(false), 1500)))}
      className="inline-flex min-h-6 items-center gap-1.5 rounded px-1.5 py-0.5 text-xs text-tenue hover:text-texto"
    >
      {done ? <Check size={12} aria-hidden="true" /> : <Copy size={12} aria-hidden="true" />}
      {done ? "Ruta copiada" : "Copiar ruta"}
    </button>
  );
}

function MetaEditor({ d, onSaved }: { d: EntryDetails; onSaved: (tags: string[], note: string) => void }) {
  const [tags, setTags] = useState(d.user_tags.join(", "));
  const [note, setNote] = useState(d.note);
  const [guardado, setGuardado] = useState(false);
  const { ocupado, error, correr } = useAccion();
  const dirty = tags !== d.user_tags.join(", ") || note !== d.note;

  async function save(ev: React.FormEvent) {
    ev.preventDefault();
    setGuardado(
      await correr(async () => {
        const r = await api<{ user_tags: string[]; note: string }>("/api/entry/meta", { method: "POST", body: JSON.stringify({ path: d.path, tags: tags.split(","), note }) });
        setTags(r.user_tags.join(", "));
        onSaved(r.user_tags, r.note);
      }),
    );
  }

  return (
    <form onSubmit={save} className="mt-6 border-t border-linea pt-5">
      <h3 className="font-mono text-sm text-display">Tus etiquetas y notas</h3>
      <p className="mt-1 text-xs text-tenue">Se guardan en Orden PC. El archivo no cambia.</p>
      <label className="mt-4 block text-xs text-tenue" htmlFor="etiquetas">
        Etiquetas, separadas por comas
      </label>
      <input id="etiquetas" value={tags} onChange={(e) => (setTags(e.target.value), setGuardado(false))} placeholder="Carrera, Entregado" className="campo mt-1" />
      <label className="mt-4 block text-xs text-tenue" htmlFor="nota">
        Nota
      </label>
      <textarea
        id="nota"
        value={note}
        onChange={(e) => (setNote(e.target.value), setGuardado(false))}
        rows={3}
        maxLength={5000}
        placeholder="Para qué es, a quién se lo enviaste..."
        className="campo mt-1 resize-y"
      />
      <div className="mt-3 flex items-center gap-3">
        <button type="submit" disabled={!dirty || ocupado} className="boton-primario">
          Guardar nota
        </button>
        <span aria-live="polite" className="text-xs text-tenue">
          {ocupado ? "Guardando" : guardado ? "Guardado" : ""}
        </span>
      </div>
      <Alerta className="mt-2">{error}</Alerta>
    </form>
  );
}

export default function DetailsPanel({ path, onNavigate, onMetaSaved }: {
  path: string | null;
  onNavigate: (path: string) => void;
  onMetaSaved: (path: string, tags: string[]) => void;
}) {
  const { data: d, error, setData } = useApi<EntryDetails>(path ? `/api/entry?${qs({ path })}` : null);
  const [shown, setShown] = useState<EntryDetails | null>(null);
  const { abrir } = useAsistente();
  useEffect(() => {
    if (d && d.path === path) setShown(d);
  }, [d, path]);

  if (!path) {
    return <p className="p-6 text-sm text-tenue">Elige un archivo o carpeta para ver todos sus datos.</p>;
  }

  return (
    <div className="relative h-full overflow-auto p-6 text-sm">
      <Alerta>{error}</Alerta>
      <AnimatePresence mode="wait">
        {shown && (
          <motion.div
            key={shown.path}
            initial={{ opacity: 0, filter: "blur(8px)", y: 6 }}
            animate={{ opacity: 1, filter: "blur(0px)", y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.35, ease: EASE }}
          >
            <div className="flex items-start gap-3">
              <span className="mt-1">
                <TypeIcon entry={shown} size={22} />
              </span>
              <div className="min-w-0">
                <h2 className="break-words text-base font-medium text-texto">{shown.name}</h2>
                <p className="mt-1 break-all font-mono text-[11px] leading-relaxed text-tenue">{shown.path}</p>
                <CopyPath path={shown.path} />
                {!shown.is_dir && (
                  <button
                    type="button"
                    onClick={() => abrir({ archivo: { path: shown.path, nombre: shown.name } })}
                    className="boton mt-2"
                  >
                    <Sparkles size={14} aria-hidden="true" className="text-acento" />
                    Explícame este archivo
                  </button>
                )}
              </div>
            </div>
            <div className="mt-3">
              <StatusMarks entry={shown} dirty={shown.project?.path === shown.path ? shown.project.git_dirty === 1 : null} />
            </div>

            {shown.protected_reason && (
              <p className="mt-4 flex gap-2 rounded-md border border-protegido/40 bg-protegido/10 px-3 py-2 text-texto">
                <Lock size={15} aria-hidden="true" className="mt-0.5 shrink-0 text-protegido" />
                <span>
                  Ruta protegida: Orden PC nunca la modifica. <span className="text-tenue">{shown.protected_reason}</span>
                </span>
              </p>
            )}
            {!!shown.collapsed && (
              <p className="mt-4 flex gap-2 rounded-md border border-linea px-3 py-2 text-tenue">
                <RefreshCw size={15} aria-hidden="true" className="mt-0.5 shrink-0 text-regenerable" />
                Orden PC suma esta carpeta sin listar su contenido.
                {shown.tags.includes("regenerable") && " Se puede regenerar desde su proyecto."}
              </p>
            )}

            <dl className="mt-5">
              <Row label="Tamaño">
                {formatBytes(shown.size)}
                {shown.is_dir ? <span className="text-tenue">, {fmtInt(shown.files)} archivos dentro</span> : null}
              </Row>
              <Row label="Tipo">{shown.type ? TYPE_LABELS[shown.type] : shown.ext ? `Archivo .${shown.ext}` : "Archivo"}</Row>
              <Row label="Creado">{fmtDateTime(shown.ctime)}</Row>
              <Row label="Modificado">
                {fmtDateTime(shown.mtime)} {shown.mtime && <span className="text-tenue">({timeAgo(shown.mtime)})</span>}
              </Row>
              <Row label="Último acceso">{fmtDateTime(shown.atime)}</Row>
              <Row label="Propietario">{shown.owner ?? <span className="text-tenue">Windows no lo informó</span>}</Row>
              <Row label="OneDrive">{shown.cloud ? CLOUD_LABELS[shown.cloud] : <span className="text-tenue">Fuera de OneDrive</span>}</Row>
              <Row label="Atributos">{shown.attrs.length ? shown.attrs.join(", ") : <span className="text-tenue">Ninguno</span>}</Row>
              {!shown.is_dir && (
                <Row label="Huella">
                  {shown.hash_full ? (
                    <span className="font-mono text-xs" title={shown.hash_full}>
                      {shown.hash_full.slice(0, 16)}…
                    </span>
                  ) : (
                    <span className="text-tenue">Se calcula solo si otro archivo pesa exactamente lo mismo</span>
                  )}
                </Row>
              )}
            </dl>

            {shown.project && (
              <div className="mt-5 rounded-md border border-linea px-3 py-3">
                <p className="flex items-center gap-2 text-texto">
                  <GitBranch size={14} aria-hidden="true" className={shown.project.git_dirty ? "text-cambios" : "text-tenue"} />
                  {shown.project.path === shown.path ? "Proyecto" : "Parte del proyecto"}{" "}
                  <button type="button" onClick={() => onNavigate(shown.project!.path)} className="truncate underline decoration-linea underline-offset-4 hover:text-acento">
                    {shown.project.path.split("\\").pop()}
                  </button>
                </p>
                <p className="mt-1 text-xs text-tenue">
                  {shown.project.kinds.split(",").join(", ")}
                  {shown.project.git_branch && `, rama ${shown.project.git_branch}`}
                  {shown.project.git_dirty === 1 && ", con cambios sin commit"}
                  {shown.project.last_activity && `. Última actividad ${timeAgo(shown.project.last_activity)}.`}
                </p>
              </div>
            )}

            {shown.duplicates.length > 0 && (
              <div className="mt-5">
                <h3 className="font-mono text-sm text-display">Copias exactas ({shown.duplicates.length})</h3>
                <ul className="mt-2 space-y-1">
                  {shown.duplicates.map((p) => (
                    <li key={p}>
                      <button
                        type="button"
                        onClick={() => onNavigate(p.slice(0, p.lastIndexOf("\\")))}
                        className="w-full truncate text-left font-mono text-[11px] text-tenue hover:text-acento"
                        title={p}
                      >
                        {p}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <MetaEditor
              key={shown.path}
              d={shown}
              onSaved={(tags, note) => {
                setData({ ...shown, user_tags: tags, note });
                onMetaSaved(shown.path, tags);
              }}
            />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
