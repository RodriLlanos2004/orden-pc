import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { AlertOctagon, ArrowUpCircle, BadgeCheck, ChevronDown, Download, Flag, FlagOff, RefreshCw, Trash2 } from "lucide-react";
import { api } from "../api";
import { Bajada, EASE, IconBox, TiltCard } from "../components/motion";
import { Alerta, BotonCerrar, Buscador, Cifras, Dialogo, Seccion, useAccion, Vacio } from "../components/ui";
import { formatBytes, fmtDate, fmtInt } from "../format";
import { Avisos, useOps, type Aviso } from "../ops";
import { qs, useApi } from "../useApi";

type App = {
  key: string;
  name: string;
  publisher: string | null;
  version: string | null;
  size: number | null;
  installed: string | null;
  location: string | null;
  sources: string[];
  winget_id: string | null;
  available: string | null;
  system: boolean;
  removable: boolean;
  uninstall: string | null;
  category: string;
  category_auto: string;
  review: string | null;
  review_auto: boolean;
  note: string;
};
type Inventory = { apps: App[]; categories: string[]; summary: { count: number; updates: number; review: number } };
type AppPlan = { id: string; action: string; title: string; confirm: string; command: string; warnings: Aviso[]; blocked: string | null; needs_ack: boolean };
type Found = { name: string; id: string; version: string; source: string };

const SOURCE_LABEL: Record<string, string> = { registro: "Registro", store: "Microsoft Store", winget: "winget" };

// El inventario no se relee al cerrar: el desinstalador sigue abierto. "Volver a leer" lo hace cuando terminas.
function AppPlanDialog({ plan, onClose }: { plan: AppPlan; onClose: () => void }) {
  const { editMode } = useOps();
  const [ack, setAck] = useState(false);
  const [launched, setLaunched] = useState(false);
  const danger = plan.action === "desinstalar";
  const listo = launched || !!plan.blocked;

  return (
    <Dialogo
      titulo={plan.title}
      antetitulo={launched ? "Listo" : "Confirmación: nada ha cambiado todavía"}
      onClose={onClose}
      confirmar={plan.confirm}
      peligro={danger}
      enfoque={danger ? "cancelar" : undefined}
      deshabilitado={!editMode || (plan.needs_ack && !ack)}
      onSubmit={async () => {
        await api(`/api/apps/run/${plan.id}`, { method: "POST", body: JSON.stringify({ ack }) });
        setLaunched(true);
        return false;
      }}
      pieIzq={
        listo ? undefined : !editMode ? (
          <span className="text-cambios">Activa el Modo edición para continuar.</span>
        ) : plan.needs_ack ? (
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} className="size-6 accent-[var(--acento)]" />
            Leí el aviso y quiero continuar
          </label>
        ) : undefined
      }
      pie={listo ? <BotonCerrar primario autoFocus /> : undefined}
    >
      {launched ? (
        <p aria-live="polite">Se abrió la ventana oficial. Termina el proceso ahí; cuando acabes, pulsa «Volver a leer» para ver el inventario al día. Quedó en el Historial.</p>
      ) : plan.blocked ? (
        <p className="flex gap-2.5 rounded-md border border-linea px-3 py-2">
          <AlertOctagon size={16} aria-hidden="true" className="mt-0.5 shrink-0 text-error" />
          {plan.blocked}
        </p>
      ) : (
        <>
          <Avisos avisos={plan.warnings} />
          <p className="text-xs text-tenue">Se va a abrir</p>
          <p className="mt-1 break-all rounded-md bg-fondo px-3 py-2 font-mono text-xs">{plan.command}</p>
        </>
      )}
    </Dialogo>
  );
}

function InstallDialog({ onPick, onClose }: { onPick: (f: Found) => void; onClose: () => void }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<Found[] | null>(null);
  return (
    <Dialogo
      titulo="Instalar con winget"
      descripcion={
        <>
          Busca en el catálogo de winget. Instalar abre el instalador oficial; tú decides ahí.
          <label className="mt-4 flex gap-2">
            <span className="sr-only">Nombre de la app</span>
            <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Por ejemplo: obsidian, 7zip, powertoys" className="campo flex-1" />
          </label>
        </>
      }
      ancho="w-[min(44rem,calc(100vw-2rem))]"
      onClose={onClose}
      confirmar="Buscar"
      deshabilitado={q.trim().length < 2}
      onSubmit={async () => {
        setResults((await api<{ results: Found[] }>(`/api/apps/search?${qs({ q })}`)).results);
        return false;
      }}
    >
      <ul className="-my-2 divide-y divide-linea" aria-live="polite">
        {results?.length === 0 && <li className="py-4 text-tenue">winget no encontró nada con ese nombre.</li>}
        {results?.map((r) => (
          <li key={r.id} className="flex items-center gap-4 py-3">
            <span className="min-w-0 flex-1">
              <span className="block truncate font-medium">{r.name}</span>
              <span className="block truncate font-mono text-[11px] text-tenue">
                {r.id}
                {r.version && `, versión ${r.version}`}
              </span>
            </span>
            <button type="button" onClick={() => onPick(r)} className="boton text-xs">
              <Download size={13} aria-hidden="true" />
              Instalar
            </button>
          </li>
        ))}
        {!results && <li className="py-2 text-tenue">Escribe al menos dos letras y pulsa Buscar.</li>}
      </ul>
    </Dialogo>
  );
}

function AppRow({ a, categories, onPlan, onMeta }: { a: App; categories: string[]; onPlan: (body: Record<string, string>) => void; onMeta: (body: Record<string, unknown>) => void }) {
  const { editMode } = useOps();
  const [open, setOpen] = useState(false);
  const fila = (label: string, valor: React.ReactNode, mono = false) => (
    <>
      <dt className="text-tenue">{label}</dt>
      <dd className={mono ? "break-all font-mono text-xs" : ""}>{valor ?? "Sin dato"}</dd>
    </>
  );
  return (
    <li className="border-t border-linea">
      <div className="grid grid-cols-[1fr_auto] items-center gap-x-4 gap-y-2 py-3 md:grid-cols-[minmax(0,1.6fr)_8rem_6rem_10rem_12rem]">
        <button type="button" aria-expanded={open} onClick={() => setOpen(!open)} className="flex min-w-0 items-center gap-2 text-left">
          <ChevronDown size={14} aria-hidden="true" className={`shrink-0 text-tenue transition-transform ${open ? "rotate-180" : ""}`} />
          <span className="min-w-0">
            <span className="flex items-center gap-2">
              <span className="truncate font-medium text-texto">{a.name}</span>
              {a.review && <Flag size={13} role="img" aria-label="Marcada para revisar" className="shrink-0 text-cambios" />}
            </span>
            <span className="block truncate text-xs text-tenue">{a.publisher ?? "Editor no declarado"}</span>
          </span>
        </button>
        <span className="text-right text-sm tabular-nums md:text-left">
          <span className="block truncate text-texto/90">{a.version ?? "Sin versión"}</span>
          {a.available && <span className="block truncate text-xs text-acento">Hay {a.available}</span>}
        </span>
        <span className="hidden text-sm tabular-nums text-tenue md:block">{a.size ? formatBytes(a.size) : "Sin dato"}</span>
        <label className="hidden md:block">
          <span className="sr-only">Categoría de {a.name}</span>
          <select
            value={a.category}
            onChange={(e) => onMeta({ key: a.key, category: e.target.value === a.category_auto ? null : e.target.value })}
            className="w-full rounded-md border border-linea bg-superficie px-2 py-1 text-xs text-texto"
          >
            {categories.map((c) => (
              <option key={c} value={c}>
                {c}
                {c === a.category_auto ? " (automática)" : ""}
              </option>
            ))}
          </select>
        </label>
        <span className="col-span-2 flex justify-end gap-1 md:col-span-1">
          {a.available && (
            <button type="button" onClick={() => onPlan({ action: "actualizar", key: a.key })} aria-label={`Actualizar ${a.name}`} className="flex min-h-7 items-center gap-1.5 rounded-md px-2 text-xs text-texto hover:bg-superficie-2">
              <ArrowUpCircle size={14} aria-hidden="true" className="text-acento" />
              Actualizar
            </button>
          )}
          <button
            type="button"
            onClick={() => onPlan({ action: "desinstalar", key: a.key })}
            aria-label={`Desinstalar ${a.name}`}
            title={editMode ? undefined : "Puedes revisar la confirmación; para continuar hace falta el Modo edición"}
            className="flex min-h-7 items-center gap-1.5 rounded-md px-2 text-xs text-error hover:bg-error/10"
          >
            <Trash2 size={14} aria-hidden="true" />
            Desinstalar
          </button>
        </span>
      </div>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.3, ease: EASE }} className="overflow-hidden">
            <dl className="grid gap-x-6 gap-y-2 pb-4 pl-6 text-sm sm:grid-cols-[9rem_1fr]">
              {fila("Origen", a.sources.map((s) => SOURCE_LABEL[s] ?? s).join(", ") || null)}
              {fila("Instalada", a.installed && fmtDate(new Date(`${a.installed}T00:00:00`).getTime() / 1000))}
              {fila("Tamaño", a.size ? formatBytes(a.size) : null)}
              {fila("Ubicación", a.location, true)}
              {fila("Desinstalador", a.uninstall ?? (a.winget_id ? `winget uninstall --id ${a.winget_id}` : "No registrado"), true)}
              {a.winget_id && fila("Id de winget", a.winget_id, true)}
              {a.system && fila("Componente", "Windows lo marca como componente del sistema.")}
              <dt className="text-tenue">Revisión</dt>
              <dd className="flex flex-wrap items-center gap-3">
                <span>{a.review ?? "Sin marca"}</span>
                <button type="button" onClick={() => onMeta(a.review ? { key: a.key, review: 0 } : { key: a.key, review: 1, note: "La marcaste para revisar." })} className="enlace text-xs">
                  {a.review ? <FlagOff size={13} aria-hidden="true" /> : <Flag size={13} aria-hidden="true" />}
                  {a.review ? "Quitar marca" : "Marcar para revisar"}
                </button>
              </dd>
            </dl>
          </motion.div>
        )}
      </AnimatePresence>
    </li>
  );
}

export default function Apps() {
  const [refresh, setRefresh] = useState(false);
  const { data, error, loading, setData, recargar } = useApi<Inventory>(`/api/apps?${qs({ refresh: refresh ? 1 : null })}`);
  const [cat, setCat] = useState("");
  const [q, setQ] = useState("");
  const [onlyUpdates, setOnlyUpdates] = useState(false);
  const [showSystem, setShowSystem] = useState(false);
  const [plan, setPlan] = useState<AppPlan | null>(null);
  const [installing, setInstalling] = useState(false);
  const accion = useAccion();

  const visible = useMemo(() => (data?.apps ?? []).filter((a) => showSystem || !a.system), [data, showSystem]);
  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return visible.filter(
      (a) => (!cat || a.category === cat) && (!onlyUpdates || a.available) && (!needle || a.name.toLowerCase().includes(needle) || (a.publisher ?? "").toLowerCase().includes(needle)),
    );
  }, [visible, cat, q, onlyUpdates]);
  const review = visible.filter((a) => a.review);

  const openPlan = (body: Record<string, string>) => accion.correr(async () => setPlan(await api<AppPlan>("/api/apps/plan", { method: "POST", body: JSON.stringify(body) })));
  async function saveMeta(body: Record<string, unknown>) {
    const ok = await accion.correr(() => api("/api/apps/meta", { method: "POST", body: JSON.stringify(body) }));
    if (ok) {
      setRefresh(false);
      recargar();
    } else if (data) setData({ ...data }); // devuelve los selectores a su valor
  }
  const reload = () => (refresh ? recargar() : setRefresh(true));

  return (
    <div>
      <Bajada>Lo que tienes instalado, de dónde vino y qué conviene revisar. Instalar y desinstalar siempre abre la ventana oficial: tú terminas el proceso ahí.</Bajada>
      <Alerta className="mt-8">{error}</Alerta>
      {!data && loading && (
        <p className="mt-10 flex items-center gap-3 text-sm text-tenue" aria-live="polite">
          <RefreshCw size={16} aria-hidden="true" className="animate-spin text-acento motion-reduce:animate-none" />
          Leyendo el registro, la Microsoft Store y winget. Tarda unos segundos.
        </p>
      )}

      {data && (
        <div className={`transition-opacity ${loading ? "opacity-50" : ""}`}>
          <div className="mt-10">
            <Cifras
              items={[
                { label: "apps instaladas", value: visible.length },
                { label: "con actualización", value: visible.filter((a) => a.available).length },
                { label: "para revisar", value: review.length },
              ]}
            />
          </div>

          {review.length > 0 && (
            <Seccion titulo="Para revisar" descripcion="Apps que duplican algo que ya tienes, envían datos o vinieron preinstaladas. La decisión es tuya." className="mt-14">
              <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-4">
                {review.map((a, i) => (
                  <TiltCard key={a.key} tilt={[-2, 1.5, -1, 2][i % 4]} delay={Math.min(i, 8) * 0.05}>
                    <IconBox>
                      <Flag size={18} aria-hidden="true" />
                    </IconBox>
                    <h3 className="mt-5 font-mono text-base">{a.name}</h3>
                    <p className="mt-1 text-xs text-texto/70">{a.category}</p>
                    <p className="mt-3 text-sm leading-relaxed text-texto/85">{a.review}</p>
                    <div className="mt-5 flex flex-wrap gap-3 text-xs">
                      <button type="button" onClick={() => openPlan({ action: "desinstalar", key: a.key })} aria-label={`Desinstalar ${a.name}`} className="enlace decoration-error">
                        <Trash2 size={13} aria-hidden="true" />
                        Desinstalar
                      </button>
                      <button type="button" onClick={() => saveMeta({ key: a.key, review: 0 })} aria-label={`Conservar ${a.name} y quitar la marca`} className="enlace decoration-linea">
                        <BadgeCheck size={13} aria-hidden="true" />
                        La conservo
                      </button>
                    </div>
                  </TiltCard>
                ))}
              </div>
            </Seccion>
          )}

          <Seccion
            titulo="Todas tus apps"
            className="mt-14"
            acciones={
              <>
                <button type="button" onClick={() => setInstalling(true)} className="boton-primario">
                  <Download size={14} aria-hidden="true" />
                  Instalar con winget
                </button>
                <button type="button" onClick={reload} className="boton">
                  <RefreshCw size={14} aria-hidden="true" className={loading ? "animate-spin motion-reduce:animate-none" : ""} />
                  Volver a leer
                </button>
              </>
            }
          >
            <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Filtrar por categoría">
              {["", ...data.categories].map((c) => {
                const n = c ? visible.filter((a) => a.category === c).length : visible.length;
                if (c && !n) return null;
                return (
                  <button key={c || "todas"} type="button" aria-pressed={cat === c} onClick={() => setCat(c)} className={`boton ${cat === c ? "border-acento" : "text-tenue"}`}>
                    {c || "Todas"} <span className="tabular-nums text-tenue">{n}</span>
                  </button>
                );
              })}
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-4 text-sm">
              <Buscador value={q} onChange={setQ} label="Buscar por nombre o editor" placeholder="Busca por nombre o editor" />
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={onlyUpdates} onChange={(e) => setOnlyUpdates(e.target.checked)} className="size-6 accent-[var(--acento)]" />
                Solo con actualización
              </label>
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={showSystem} onChange={(e) => setShowSystem(e.target.checked)} className="size-6 accent-[var(--acento)]" />
                Mostrar componentes del sistema ({fmtInt(data.apps.filter((a) => a.system).length)})
              </label>
            </div>
            <Alerta className="mt-4">{accion.error}</Alerta>

            <div className="mt-6 hidden grid-cols-[minmax(0,1.6fr)_8rem_6rem_10rem_12rem] gap-4 pb-2 text-xs text-tenue md:grid">
              <span className="pl-[22px]">Nombre</span>
              <span>Versión</span>
              <span>Tamaño</span>
              <span>Categoría</span>
              <span className="sr-only">Acciones</span>
            </div>
            <ul aria-label="Apps">
              {shown.map((a) => (
                <AppRow key={a.key} a={a} categories={data.categories} onPlan={openPlan} onMeta={saveMeta} />
              ))}
            </ul>
            {shown.length === 0 && <Vacio className="mt-4">Ninguna app coincide con los filtros.</Vacio>}
          </Seccion>
        </div>
      )}

      {plan && <AppPlanDialog key={plan.id} plan={plan} onClose={() => setPlan(null)} />}
      {installing && (
        <InstallDialog
          onClose={() => setInstalling(false)}
          onPick={(f) => {
            setInstalling(false);
            openPlan({ action: "instalar", winget_id: f.id, name: f.name });
          }}
        />
      )}
    </div>
  );
}
