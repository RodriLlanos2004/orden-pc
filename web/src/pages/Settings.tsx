import { useState } from "react";
import { Link } from "react-router";
import { DatabaseBackup, FolderSearch, Lock, Plus, RotateCcw, ShieldPlus, X } from "lucide-react";
import { api } from "../api";
import { Bajada } from "../components/motion";
import { Alerta, Seccion, useAccion } from "../components/ui";
import { fmtDateTime, formatBytes } from "../format";
import { rutaPanel } from "../paneles";
import { useApi } from "../useApi";

type Root = { path: string; mode: "completo" | "carpetas" };
type Settings = {
  protected_default: string[];
  protected_rules: string[];
  protected_extra: string[];
  roots: Root[];
  roots_custom: boolean;
  db: { path: string; size: number; backups: string; last_backups: { name: string; size: number; mtime: number }[] };
};

const MODE_LABEL = { completo: "Todo: carpetas y archivos", carpetas: "Solo carpetas, 3 niveles" };
const soloRuta = (rs: Root[]) => rs.map(({ path, mode }) => ({ path, mode }));

/** Campo de ruta con su botón, en una fila. */
function AgregarRuta({ label, placeholder, boton, icono, onAgregar }: { label: string; placeholder: string; boton: string; icono: React.ReactNode; onAgregar: (path: string) => void }) {
  const [path, setPath] = useState("");
  return (
    <form
      className="mt-4 flex flex-wrap gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (path.trim()) onAgregar(path.trim());
        setPath("");
      }}
    >
      <label className="min-w-0 flex-1">
        <span className="sr-only">{label}</span>
        <input value={path} onChange={(e) => setPath(e.target.value)} placeholder={placeholder} className="campo font-mono text-xs placeholder:font-sans" />
      </label>
      <button type="submit" disabled={!path.trim()} className="boton">
        {icono}
        {boton}
      </button>
    </form>
  );
}

function Protected({ s, onChange }: { s: Settings; onChange: (extra: string[]) => void }) {
  const [pendiente, setPendiente] = useState("");
  const { error, correr } = useAccion();
  const add = () =>
    correr(async () => {
      onChange((await api<{ protected_extra: string[] }>("/api/settings/protected", { method: "POST", body: JSON.stringify({ path: pendiente }) })).protected_extra);
    }).finally(() => setPendiente(""));

  const lista = (rutas: string[], color: string, mono = false) => (
    <ul className="mt-2 space-y-1.5 text-sm">
      {rutas.map((p) => (
        <li key={p} className="flex items-start gap-2">
          <Lock size={13} aria-hidden="true" className={`mt-1 shrink-0 ${color}`} />
          <span className={`break-all ${mono ? "font-mono text-xs" : ""}`}>{p}</span>
        </li>
      ))}
    </ul>
  );

  return (
    <div className="grid gap-6 md:grid-cols-2">
      <div>
        <h3 className="text-sm text-tenue">Siempre protegidas</h3>
        {lista([...s.protected_default, ...s.protected_rules], "text-tenue")}
      </div>
      <div>
        <h3 className="text-sm text-tenue">Agregadas por ti</h3>
        {s.protected_extra.length ? lista(s.protected_extra, "text-acento", true) : <p className="mt-2 text-sm text-tenue">Ninguna todavía.</p>}
        <AgregarRuta label="Ruta para proteger" placeholder="Por ejemplo: C:\Users\rodri\Privado" boton="Proteger ruta" icono={<ShieldPlus size={14} aria-hidden="true" />} onAgregar={setPendiente} />
        {pendiente && (
          <div role="alertdialog" aria-labelledby="confirmar-proteger" className="mt-3 rounded-md border border-cambios/60 px-4 py-3 text-sm">
            <p id="confirmar-proteger">
              Orden PC nunca podrá crear, mover, renombrar ni enviar a la Papelera nada dentro de <span className="break-all font-mono text-xs">{pendiente}</span>. La lista solo crece: no se puede quitar desde la app.
            </p>
            <div className="mt-3 flex gap-2">
              <button type="button" autoFocus onClick={add} className="boton-primario">
                Proteger para siempre
              </button>
              <button type="button" onClick={() => setPendiente("")} className="boton">
                Cancelar
              </button>
            </div>
          </div>
        )}
        <Alerta className="mt-3">{error}</Alerta>
      </div>
    </div>
  );
}

function Roots({ s, onSaved }: { s: Settings; onSaved: () => void }) {
  const [roots, setRoots] = useState<Root[]>(() => soloRuta(s.roots));
  const [saved, setSaved] = useState("");
  const { error, correr } = useAccion();
  const dirty = JSON.stringify(roots) !== JSON.stringify(soloRuta(s.roots));

  const save = (body: Root[] | null) =>
    correr(async () => {
      setSaved("");
      const r = await api<{ roots: Root[] }>("/api/settings/roots", { method: "PUT", body: JSON.stringify({ roots: body }) });
      setRoots(soloRuta(r.roots));
      setSaved("Guardado. Se usa desde el próximo escaneo.");
      onSaved();
    });

  return (
    <div>
      <ul className="divide-y divide-linea rounded-md border border-linea">
        {roots.map((r, i) => (
          <li key={r.path} className="flex flex-wrap items-center gap-3 px-4 py-2.5 text-sm">
            <span className="min-w-0 flex-1 break-all font-mono text-xs">{r.path}</span>
            <label>
              <span className="sr-only">Qué escanear en {r.path}</span>
              <select
                value={r.mode}
                onChange={(e) => setRoots(roots.map((x, j) => (j === i ? { ...x, mode: e.target.value as Root["mode"] } : x)))}
                className="rounded-md border border-linea bg-superficie px-2 py-1 text-xs"
              >
                {Object.entries(MODE_LABEL).map(([v, l]) => (
                  <option key={v} value={v}>
                    {l}
                  </option>
                ))}
              </select>
            </label>
            <button type="button" onClick={() => setRoots(roots.filter((_, j) => j !== i))} aria-label={`Dejar de escanear ${r.path}`} data-tip-izq className="boton-icono">
              <X size={15} aria-hidden="true" />
            </button>
          </li>
        ))}
      </ul>
      <AgregarRuta label="Carpeta para escanear" placeholder="Por ejemplo: D:\" boton="Agregar carpeta" icono={<Plus size={14} aria-hidden="true" />} onAgregar={(path) => setRoots([...roots, { path, mode: "completo" }])} />
      <div className="mt-5 flex flex-wrap items-center gap-3">
        <button type="button" disabled={!dirty || !roots.length} onClick={() => save(roots)} className="boton-primario">
          Guardar carpetas
        </button>
        {s.roots_custom && (
          <button type="button" onClick={() => save(null)} className="boton">
            <RotateCcw size={14} aria-hidden="true" />
            Volver a las de siempre
          </button>
        )}
        <p aria-live="polite" className="text-sm text-tenue">
          {saved}
        </p>
      </div>
      <Alerta className="mt-3">{error}</Alerta>
    </div>
  );
}

function Database({ s, onDone }: { s: Settings; onDone: () => void }) {
  const [result, setResult] = useState("");
  const { ocupado, error, correr } = useAccion();
  const backup = () =>
    correr(async () => {
      const r = await api<{ path: string; size: number }>("/api/settings/backup", { method: "POST" });
      setResult(`Copia creada: ${r.path} (${formatBytes(r.size)}).`);
      onDone();
    });
  return (
    <div className="grid gap-6 md:grid-cols-2">
      <dl className="grid grid-cols-[7rem_1fr] gap-x-4 gap-y-2 text-sm">
        <dt className="text-tenue">Archivo</dt>
        <dd className="break-all font-mono text-xs">{s.db.path}</dd>
        <dt className="text-tenue">Tamaño</dt>
        <dd className="tabular-nums">{formatBytes(s.db.size)}</dd>
        <dt className="text-tenue">Copias en</dt>
        <dd className="break-all font-mono text-xs">{s.db.backups}</dd>
      </dl>
      <div>
        <button type="button" disabled={ocupado} onClick={backup} className="boton-primario">
          <DatabaseBackup size={15} aria-hidden="true" />
          {ocupado ? "Copiando" : "Crear copia ahora"}
        </button>
        <p aria-live="polite" className="mt-3 break-all text-sm text-texto">
          {result}
        </p>
        <Alerta className="mt-3">{error}</Alerta>
        {s.db.last_backups.length > 0 && (
          <>
            <h3 className="mt-5 text-sm text-tenue">Últimas copias</h3>
            <ul className="mt-2 space-y-1 text-sm">
              {s.db.last_backups.map((b) => (
                <li key={b.name} className="flex justify-between gap-4">
                  <span>{fmtDateTime(b.mtime)}</span>
                  <span className="tabular-nums text-tenue">{formatBytes(b.size)}</span>
                </li>
              ))}
            </ul>
          </>
        )}
        <p className="mt-5 text-xs text-tenue">Para restaurar: cierra Orden PC y reemplaza el archivo de arriba por una copia (renómbrala a orden.db).</p>
      </div>
    </div>
  );
}

const TARJETA = "rounded-lg border border-linea bg-superficie px-6 py-6";

export default function Settings() {
  const { data, error, setData, recargar } = useApi<Settings>("/api/settings");
  return (
    <div>
      <Bajada>
        Rutas que la app nunca toca, qué carpetas escanea y la copia de tu base de datos. La estructura de carpetas y sus reglas están en{" "}
        <Link to={rutaPanel("ordenar", { ver: "organizar" })} className="enlace">
          Ordenar
        </Link>
        .
      </Bajada>
      <Alerta className="mt-8">{error}</Alerta>
      {data && (
        <div className="mt-10 flex flex-col gap-6">
          <Seccion
            className={TARJETA}
            titulo={<><Lock size={18} aria-hidden="true" className="text-acento" />Rutas protegidas</>}
            descripcion="Orden PC nunca crea, mueve, renombra ni envía a la Papelera nada dentro de estas rutas, aunque se lo pidas. Puedes agregar más; ninguna se puede quitar."
          >
            <Protected s={data} onChange={(extra) => setData({ ...data, protected_extra: extra })} />
          </Seccion>
          <Seccion className={TARJETA} titulo={<><FolderSearch size={18} aria-hidden="true" className="text-acento" />Carpetas a escanear</>} descripcion="Escanear solo lee. Además, Orden PC solo puede cambiar cosas dentro de estas carpetas.">
            <Roots s={data} onSaved={recargar} />
          </Seccion>
          <Seccion className={TARJETA} titulo={<><DatabaseBackup size={18} aria-hidden="true" className="text-acento" />Base de datos</>} descripcion="El índice, tus etiquetas, notas, reglas e historial viven en un solo archivo. La copia se puede hacer con la app abierta.">
            <Database s={data} onDone={recargar} />
          </Seccion>
        </div>
      )}
    </div>
  );
}
