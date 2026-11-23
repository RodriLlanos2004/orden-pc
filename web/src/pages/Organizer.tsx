import { useEffect, useMemo, useState } from "react";
import { motion } from "motion/react";
import { AlertTriangle, ArrowDown, ArrowRight, ArrowUp, CheckCircle2, CircleDashed, Cloud, File, Folder, FolderPlus, Pencil, Plus, Sparkles, Square, Trash2, Wand2 } from "lucide-react";
import { api } from "../api";
import { EASE } from "../components/motion";
import { Alerta, BarraAccion, Casilla, Cifras, Dialogo, MasFilas, Seccion, useAccion, Vacio } from "../components/ui";
import { formatBytes, fmtInt } from "../format";
import { useOps } from "../ops";
import { usePanel } from "../paneles";
import { useApi } from "../useApi";

type Item = { path: string; name: string; is_dir: boolean; size: number | null; mtime: number; cloud: string | null };
type Proposal = Item & { rule: string; rule_name: string; dest: string; new_name: string; conflict: string | null };
type Rule = {
  id?: string;
  nombre: string;
  activa: boolean;
  tipo: "archivos" | "carpetas" | "ambos";
  extensiones: string[];
  empieza: string[];
  palabras: string[];
  origen: string[];
  destino: string;
  renombrar: "no" | "entrega" | "minusculas";
};
type Folder = { template: string; path: string; exists: boolean };
type Structure = { materias: string[]; carpetas: string[]; origenes: string[] };
type Sugerencia = { path: string; nombre: string; destino: string; nuevo_nombre: string; razon: string; origen: "modelo" | "palabras" | "antigüedad" };
type Sugerencias = { estado: string; total: number; hechos: number; actual: string; error: string | null; aviso: string | null; sugerencias: Sugerencia[]; materias_nuevas: { nombre: string; carpeta: string; documentos: number }[] };
type View = {
  estructura: Structure;
  reglas: Rule[];
  variables: Record<string, string>;
  carpetas: Folder[];
  propuestas: Proposal[];
  por_clasificar: Item[];
};

const RENAME_LABEL: Record<Rule["renombrar"], string> = {
  no: "Conserva el nombre",
  entrega: "Regla de entregas: AAAA-MM-DD_Materia_Tema_v1",
  minusculas: "Minúsculas con guiones",
};
const TIPO_LABEL: Record<Rule["tipo"], string> = { archivos: "Archivos", carpetas: "Carpetas", ambos: "Archivos y carpetas" };
const PAGE = 30;

const inside = (p: string, base?: string) => !!base && (p.toLowerCase() === base.toLowerCase() || p.toLowerCase().startsWith(base.toLowerCase() + "\\"));
const carpetaDe = (p: string) => p.slice(0, p.lastIndexOf("\\"));

/** Rutas legibles: "OneDrive\20_Carrera" en vez de "C:\Users\rodri\OneDrive\20_Carrera". */
function prettyPath(p: string, vars: Record<string, string>) {
  for (const key of ["OneDrive", "Descargas", "Escritorio"]) {
    if (inside(p, vars[key])) return key + p.slice(vars[key].length);
  }
  return inside(p, vars.Usuario) ? p.slice(vars.Usuario.length + 1) || "Tu carpeta de usuario" : p;
}
const prettyTemplate = (t: string) => t.replace(/^\{Usuario\}\\?/, "").replace(/\{(\w+)\}/g, "$1") || "tu carpeta de usuario";

function joinOr(xs: string[]) {
  const q = xs.map((x) => `«${x}»`);
  return q.length > 1 ? `${q.slice(0, -1).join(", ")} o ${q[q.length - 1]}` : q[0];
}

function describe(r: Rule) {
  const parts = [TIPO_LABEL[r.tipo]];
  if (r.extensiones.length) parts.push(r.extensiones.map((e) => `.${e}`).join(", "));
  if (r.empieza.length) parts.push(`que empiezan con ${joinOr(r.empieza)}`);
  if (r.palabras.length) parts.push(`${r.empieza.length ? "y contienen" : "que contienen"} ${joinOr(r.palabras)}`);
  if (r.origen.length) parts.push(`dentro de ${r.origen.map(prettyTemplate).join(", ")}`);
  return parts.join(" ");
}

/** Nombre, carpeta de origen e iconos de un elemento suelto. */
function ItemName({ item, vars }: { item: Item; vars: Record<string, string> }) {
  const Icon = item.is_dir ? Folder : File;
  return (
    <span className="flex min-w-0 items-center gap-2">
      <span className="flex shrink-0 items-center gap-1 text-tenue">
        <Icon size={15} aria-hidden="true" />
        {item.cloud === "solo_nube" && <Cloud size={13} role="img" aria-label="Solo en la nube" className="text-nube" />}
      </span>
      <span className="min-w-0">
        <span className="block truncate text-texto" title={item.name}>
          {item.name}
        </span>
        <span className="block truncate text-xs text-tenue">{prettyPath(carpetaDe(item.path), vars)}</span>
      </span>
    </span>
  );
}

// ---------------------------------------------------------------------- plan propuesto

function Group({ dest, items, vars, isOn, names, onToggle, onName, index }: {
  dest: string;
  items: Proposal[];
  vars: Record<string, string>;
  isOn: (p: Proposal) => boolean;
  names: Record<string, string>;
  onToggle: (paths: string[], on: boolean) => void;
  onName: (path: string, name: string) => void;
  index: number;
}) {
  const on = items.filter(isOn).length;
  const rules = [...new Set(items.map((i) => i.rule_name))];
  const size = items.reduce((s, i) => s + (i.size ?? 0), 0);
  const label = prettyPath(dest, vars);
  return (
    <motion.section
      aria-label={`Destino ${label}`}
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, delay: Math.min(index, 8) * 0.05, ease: EASE }}
      className="rounded-lg border border-linea bg-superficie"
    >
      <header className="flex items-start gap-4 px-5 py-4">
        <Casilla checked={on === items.length} mixed={on > 0 && on < items.length} onChange={(v) => onToggle(items.map((i) => i.path), v)} label={`Incluir todo lo que va a ${label}`} />
        <div className="min-w-0 flex-1">
          <h3 className="break-words font-mono text-base text-display">{label}</h3>
          <p className="mt-0.5 text-sm text-tenue">{rules.join(", ")}</p>
        </div>
        <p className="shrink-0 text-right text-sm">
          <span className="block tabular-nums text-texto">{size ? formatBytes(size) : ""}</span>
          <span className="block text-xs text-tenue">
            {fmtInt(items.length)} {items.length === 1 ? "elemento" : "elementos"}
          </span>
        </p>
      </header>
      <ul className="px-5 pb-2">
        {items.map((i) => {
          const name = names[i.path] ?? i.new_name;
          const off = !isOn(i);
          return (
            <li key={i.path} className={`grid grid-cols-[auto_minmax(0,1fr)] items-center gap-x-4 gap-y-1 border-t border-linea py-2.5 text-sm md:grid-cols-[auto_minmax(0,0.8fr)_auto_minmax(0,1.2fr)] ${off && !i.conflict ? "opacity-50" : ""}`}>
              <Casilla checked={!off} onChange={(v) => onToggle([i.path], v)} label={`Incluir ${i.name}`} />
              <ItemName item={i} vars={vars} />
              <ArrowRight size={14} aria-hidden="true" className="hidden text-tenue md:block" />
              <label className="col-start-2 md:col-start-auto">
                <span className="sr-only">Nombre en el destino para {i.name}</span>
                <input
                  value={name}
                  title={name}
                  disabled={off}
                  onChange={(e) => onName(i.path, e.target.value)}
                  className={`w-full rounded-md border border-transparent bg-transparent px-2 py-1 font-mono text-xs hover:border-linea focus:border-acento ${name !== i.name ? "text-acento" : "text-texto/80"}`}
                />
              </label>
              {i.conflict && (
                <p className="col-start-2 flex gap-2 text-xs text-cambios md:col-span-3">
                  <AlertTriangle size={13} aria-hidden="true" className="mt-0.5 shrink-0" />
                  <span className="break-all">{i.conflict}</span>
                </p>
              )}
            </li>
          );
        })}
      </ul>
    </motion.section>
  );
}

// ---------------------------------------------------------------------- reglas

const EMPTY_RULE: Rule = { nombre: "", activa: true, tipo: "archivos", extensiones: [], empieza: [], palabras: [], origen: [], destino: "", renombrar: "no" };
const csv = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);
const lines = (s: string) => s.split("\n").map((x) => x.trim()).filter(Boolean);

/** Un campo con su etiqueta encima. */
function Campo({ label, children }: { label: React.ReactNode; children: React.ReactNode }) {
  return (
    <label className="grid gap-1.5">
      <span className="text-tenue">{label}</span>
      {children}
    </label>
  );
}

function RuleDialog({ rule, folders, onClose, onSave }: { rule: Rule; folders: Folder[]; onClose: () => void; onSave: (r: Rule) => Promise<void> }) {
  const [r, setR] = useState(rule);
  const [text, setText] = useState({ ext: rule.extensiones.join(", "), emp: rule.empieza.join(", "), pal: rule.palabras.join(", "), ori: rule.origen.join("\n") });
  const opciones = (o: Record<string, string>) =>
    Object.entries(o).map(([v, l]) => (
      <option key={v} value={v}>
        {l}
      </option>
    ));
  return (
    <Dialogo
      titulo={rule.id ? "Editar regla" : "Nueva regla"}
      descripcion="Una regla solo propone. Nada se mueve hasta que revisas la vista previa y la confirmas."
      onClose={onClose}
      confirmar="Guardar regla"
      onSubmit={() => onSave({ ...r, extensiones: csv(text.ext), empieza: csv(text.emp), palabras: csv(text.pal), origen: lines(text.ori) })}
    >
      <div className="grid gap-4">
        <Campo label="Nombre de la regla">
          <input required maxLength={120} value={r.nombre} onChange={(e) => setR({ ...r, nombre: e.target.value })} className="campo" />
        </Campo>
        <Campo label="Se aplica a">
          <select value={r.tipo} onChange={(e) => setR({ ...r, tipo: e.target.value as Rule["tipo"] })} className="campo">
            {opciones(TIPO_LABEL)}
          </select>
        </Campo>
        <fieldset className="grid gap-3 rounded-md border border-linea px-4 py-3">
          <legend className="px-1 text-tenue">Coincide si cumple todo lo que llenes (al menos uno)</legend>
          <Campo label="Extensiones, separadas por comas">
            <input value={text.ext} onChange={(e) => setText({ ...text, ext: e.target.value })} placeholder="pdf, docx" className="campo" />
          </Campo>
          <Campo label="El nombre empieza con">
            <input value={text.emp} onChange={(e) => setText({ ...text, emp: e.target.value })} placeholder="M02" className="campo" />
          </Campo>
          <Campo label="El nombre contiene alguna de estas palabras">
            <input value={text.pal} onChange={(e) => setText({ ...text, pal: e.target.value })} placeholder="chixi, hw07" className="campo" />
          </Campo>
          <p className="text-xs text-tenue">No distingue mayúsculas ni acentos, y trata igual espacios, guiones y guiones bajos.</p>
        </fieldset>
        <Campo label="Carpeta destino">
          <input required list="carpetas-estructura" value={r.destino} onChange={(e) => setR({ ...r, destino: e.target.value })} placeholder="{OneDrive}\20_Carrera\CV_y_Perfil" className="campo font-mono text-xs" />
          <datalist id="carpetas-estructura">
            {folders.map((f) => (
              <option key={f.template} value={f.template} />
            ))}
          </datalist>
          <span className="text-xs text-tenue">Elige una carpeta de tu estructura o escribe una ruta. Variables: {"{Usuario}"}, {"{OneDrive}"}, {"{Descargas}"}, {"{Escritorio}"}.</span>
        </Campo>
        <Campo label="Nombre en el destino">
          <select value={r.renombrar} onChange={(e) => setR({ ...r, renombrar: e.target.value as Rule["renombrar"] })} className="campo">
            {opciones(RENAME_LABEL)}
          </select>
        </Campo>
        <Campo label="Buscar solo en estas carpetas (opcional, una por línea)">
          <textarea rows={2} value={text.ori} onChange={(e) => setText({ ...text, ori: e.target.value })} placeholder="Vacío: tus carpetas de origen" className="campo font-mono text-xs" />
        </Campo>
      </div>
    </Dialogo>
  );
}

function RuleList({ rules, onChange, onEdit }: { rules: Rule[]; onChange: (rules: Rule[]) => void; onEdit: (i: number) => void }) {
  const move = (i: number, d: number) => {
    const next = [...rules];
    [next[i], next[i + d]] = [next[i + d], next[i]];
    onChange(next);
  };
  return (
    <ol className="divide-y divide-linea rounded-lg border border-linea bg-superficie">
      {rules.map((r, i) => (
        <li key={r.id ?? i} className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2 px-5 py-4 md:grid-cols-[auto_minmax(0,1fr)_auto]">
          <Casilla checked={r.activa} onChange={(v) => onChange(rules.map((x, j) => (j === i ? { ...x, activa: v } : x)))} label={`Regla activa: ${r.nombre}`} />
          <div className={`min-w-0 ${r.activa ? "" : "opacity-50"}`}>
            <p className="font-medium text-texto">
              <span className="mr-2 tabular-nums text-tenue">{i + 1}.</span>
              {r.nombre}
            </p>
            <p className="mt-1 text-sm text-texto/85">{describe(r)}</p>
            <p className="mt-1 break-words font-mono text-xs text-tenue">
              a {prettyTemplate(r.destino)}. {RENAME_LABEL[r.renombrar]}.
            </p>
          </div>
          <div className="col-start-2 flex gap-1 md:col-start-auto">
            <button type="button" disabled={i === 0} onClick={() => move(i, -1)} aria-label={`Subir ${r.nombre}`} className="boton-icono">
              <ArrowUp size={15} aria-hidden="true" />
            </button>
            <button type="button" disabled={i === rules.length - 1} onClick={() => move(i, 1)} aria-label={`Bajar ${r.nombre}`} className="boton-icono">
              <ArrowDown size={15} aria-hidden="true" />
            </button>
            <button type="button" onClick={() => onEdit(i)} aria-label={`Editar ${r.nombre}`} className="boton-icono">
              <Pencil size={15} aria-hidden="true" />
            </button>
            <button type="button" onClick={() => onChange(rules.filter((_, j) => j !== i))} aria-label={`Quitar ${r.nombre}`} className="boton-icono hover:bg-error/10 hover:text-error">
              <Trash2 size={15} aria-hidden="true" />
            </button>
          </div>
        </li>
      ))}
    </ol>
  );
}

// ---------------------------------------------------------------------- estructura

type Node = { name: string; children: Map<string, Node>; folder?: Folder };

function buildTree(folders: Folder[]) {
  const root: Node = { name: "", children: new Map() };
  for (const f of folders) {
    let n = root;
    for (const part of prettyTemplate(f.template).split("\\")) {
      if (!n.children.has(part)) n.children.set(part, { name: part, children: new Map() });
      n = n.children.get(part)!;
    }
    n.folder = f;
  }
  return root;
}

function Tree({ node }: { node: Node }) {
  return (
    <ul className="border-l border-linea pl-4">
      {[...node.children.values()].map((c) => (
        <li key={c.name} className="py-0.5">
          <span className="flex items-center gap-2 font-mono text-xs">
            {c.folder ? (
              c.folder.exists ? (
                <CheckCircle2 size={13} role="img" aria-label="Ya existe" className="text-exito" />
              ) : (
                <CircleDashed size={13} role="img" aria-label="Falta crearla" className="text-cambios" />
              )
            ) : (
              <Folder size={13} aria-hidden="true" className="text-tenue" />
            )}
            <span className={c.folder && !c.folder.exists ? "text-tenue" : "text-texto"}>{c.name}</span>
          </span>
          {c.children.size > 0 && <Tree node={c} />}
        </li>
      ))}
    </ul>
  );
}

function StructureDialog({ st, onClose, onSave }: { st: Structure; onClose: () => void; onSave: (s: Structure) => Promise<void> }) {
  const [text, setText] = useState({ materias: st.materias.join("\n"), carpetas: st.carpetas.join("\n"), origenes: st.origenes.join("\n") });
  const area = (key: keyof typeof text, rows: number) => (
    <textarea rows={rows} value={text[key]} onChange={(e) => setText({ ...text, [key]: e.target.value })} className="campo font-mono text-xs leading-relaxed" />
  );
  return (
    <Dialogo
      titulo="Editar estructura"
      descripcion="Guardar solo cambia la configuración. Crear las carpetas es otra acción, con vista previa."
      ancho="w-[min(48rem,calc(100vw-2rem))]"
      onClose={onClose}
      confirmar="Guardar estructura"
      onSubmit={() => onSave({ materias: lines(text.materias), carpetas: lines(text.carpetas), origenes: lines(text.origenes) })}
    >
      <div className="grid gap-4">
        <Campo label={<>Carpetas, una por línea. {"{Materia}"} se repite por cada materia.</>}>{area("carpetas", 10)}</Campo>
        <Campo label="Materias, una por línea">{area("materias", 6)}</Campo>
        <Campo label="Carpetas de origen: aquí se buscan elementos sueltos, una por línea">{area("origenes", 4)}</Campo>
      </div>
    </Dialogo>
  );
}

// ---------------------------------------------------------------------- sugerencias del asistente

const ORIGEN: Record<Sugerencia["origen"], string> = { modelo: "leyó el documento", palabras: "por palabras clave", "antigüedad": "por antigüedad" };

/** El asistente lee cada documento por clasificar y propone su carpeta. Solo propone: aplicar pasa por la vista previa. */
function useSugerencias() {
  const { params } = usePanel();
  const sug = useApi<Sugerencias>("/api/organizer/sugerencias");
  const accion = useAccion();
  const pensando = sug.data?.estado === "pensando";
  useEffect(() => {
    if (!pensando) return;
    const t = setInterval(sug.recargar, 1500);
    return () => clearInterval(t);
  }, [pensando, sug.recargar]);
  const pedir = () => accion.correr(() => api("/api/organizer/sugerir", { method: "POST" })).then(sug.recargar);
  const detener = () => api("/api/organizer/sugerir/detener", { method: "POST" }).then(sug.recargar);
  // Desde el asistente ("Sugiere cómo ordenar mis documentos") se llega aquí con ?sugerir=1.
  const pedido = params.get("sugerir") === "1";
  useEffect(() => {
    if (pedido && sug.data && !pensando) pedir();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pedido, !!sug.data]);
  const porRuta = new Map((sug.data?.sugerencias ?? []).map((x) => [x.path, x]));
  return { datos: sug.data, pensando, pedir, detener, porRuta, error: accion.error || sug.error };
}

function PanelSugerencias({ sug, manual, onUsar, onMaterias }: { sug: ReturnType<typeof useSugerencias>; manual: Record<string, string>; onUsar: (l: Sugerencia[]) => void; onMaterias: (m: string[]) => void }) {
  const d = sug.datos;
  const pendientes = (d?.sugerencias ?? []).filter((x) => manual[x.path] !== x.destino);
  return (
    <div className="mb-4 space-y-2 text-sm">
      {!d || d.estado === "inactivo" ? (
        <p className="max-w-3xl text-tenue">
          Cómo decide: lee el contenido y clasifica por materia o proyecto, no por tipo de archivo; lo entregado va a Entregas con nombre AAAA-MM-DD_Materia_Tema_v1, los apuntes a
          Material, lo que lleva más de un año sin cambios al Archivo, y si no hay evidencia clara lo deja donde está. Solo elige carpetas de tu estructura.
        </p>
      ) : sug.pensando ? (
        <div aria-live="polite">
          <div className="h-1.5 max-w-md overflow-hidden rounded-full bg-superficie-2">
            <div className="bg-amarillo-fuerte h-full rounded-full transition-[width]" style={{ width: `${(d.hechos / Math.max(d.total, 1)) * 100}%` }} />
          </div>
          <p className="mt-2 text-xs text-tenue">
            Leyendo {fmtInt(d.hechos)} de {fmtInt(d.total)} documentos. {d.actual}
          </p>
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-3">
          <p aria-live="polite" className="text-texto">
            {d.sugerencias.length
              ? `${fmtInt(d.sugerencias.length)} de ${fmtInt(d.total)} documentos con sugerencia. El resto se queda donde está: no había evidencia clara.`
              : d.total
                ? "Ningún documento dio evidencia clara de su carpeta: todo se queda donde está."
                : "No hay documentos leídos por clasificar. Abre el asistente y pulsa Preparar para que lea tus documentos."}
          </p>
          {pendientes.length > 0 && (
            <button type="button" onClick={() => onUsar(pendientes)} className="boton-primario">
              <Sparkles size={14} aria-hidden="true" />
              Usar las {fmtInt(pendientes.length)} sugerencias
            </button>
          )}
        </div>
      )}
      {!!d?.materias_nuevas.length && !sug.pensando && (
        <div className="max-w-3xl rounded-md border border-acento/40 px-4 py-3">
          <p className="text-texto">
            {d.materias_nuevas.length === 1 ? "Tus documentos mencionan una materia que no está en tu estructura:" : "Tus documentos mencionan materias que no están en tu estructura:"}
          </p>
          <ul className="mt-1 list-disc pl-5 text-tenue">
            {d.materias_nuevas.map((m) => (
              <li key={m.carpeta}>
                {m.nombre} ({fmtInt(m.documentos)} {m.documentos === 1 ? "documento" : "documentos"}): carpeta <span className="font-mono text-xs">{m.carpeta}</span>
              </li>
            ))}
          </ul>
          <p className="mt-1 text-xs text-tenue">El asistente no los manda a otra materia. Agrégala a tu estructura y vuelve a sugerir.</p>
          <button type="button" onClick={() => onMaterias(d.materias_nuevas.map((m) => m.carpeta))} className="boton mt-2">
            <FolderPlus size={14} aria-hidden="true" />
            Agregar a mi estructura
          </button>
        </div>
      )}
      {d?.aviso && <p className="text-xs text-cambios">{d.aviso}</p>}
      <Alerta>{sug.error || d?.error}</Alerta>
    </div>
  );
}

// ---------------------------------------------------------------------- página

export default function Organizer() {
  const { editMode, openPlan, cambios } = useOps();
  const { data, error, loading, setData } = useApi<View>(`/api/organizer?v=${cambios}`);
  // Lo que eliges a mano; sin elección, todo va incluido salvo los conflictos (Orden PC no elige por ti).
  const [pick, setPick] = useState<Record<string, boolean>>({});
  const isOn = (p: Proposal) => pick[p.path] ?? !p.conflict;
  const [names, setNames] = useState<Record<string, string>>({});
  const [manual, setManual] = useState<Record<string, string>>({});
  const [shown, setShown] = useState(PAGE);
  const [editing, setEditing] = useState<{ index: number | null; rule: Rule } | null>(null);
  const [estructura, setEstructura] = useState<Structure | null>(null);
  const guardar = useAccion();
  const sug = useSugerencias();
  const usar = (lista: Sugerencia[]) => {
    setManual((m) => ({ ...m, ...Object.fromEntries(lista.map((x) => [x.path, x.destino])) }));
    setNames((n) => ({ ...n, ...Object.fromEntries(lista.map((x) => [x.path, x.nuevo_nombre])) }));
  };
  // Después de aplicar, la propuesta se vuelve a leer (por `cambios`) y lo elegido a mano se olvida.
  const reset = () => {
    setManual({});
    setNames({});
    setPick({});
  };

  const groups = useMemo(() => {
    const m = new Map<string, Proposal[]>();
    for (const p of data?.propuestas ?? []) m.set(p.dest, [...(m.get(p.dest) ?? []), p]);
    return [...m.entries()];
  }, [data]);

  const moves = useMemo(() => {
    if (!data) return [];
    const auto = data.propuestas.filter((p) => pick[p.path] ?? !p.conflict).map((p) => ({ src: p.path, dest: p.dest, name: (names[p.path] ?? p.new_name).trim(), size: p.size ?? 0 }));
    const byHand = data.por_clasificar
      .filter((i) => manual[i.path])
      .map((i) => ({ src: i.path, dest: data.carpetas.find((f) => f.template === manual[i.path])!.path, name: (names[i.path] ?? i.name).trim(), size: i.size ?? 0 }));
    return [...auto, ...byHand];
  }, [data, pick, names, manual]);
  const missing = data?.carpetas.filter((f) => !f.exists) ?? [];

  const toggle = (paths: string[], on: boolean) => setPick((x) => ({ ...x, ...Object.fromEntries(paths.map((p) => [p, on])) }));
  const put = async (url: string, body: unknown) => setData(await api<View>(url, { method: "PUT", body: JSON.stringify(body) }));
  const saveRules = (rules: Rule[]) => put("/api/organizer/rules", { rules });

  function ruleFromItem(i: Item): Rule {
    const ext = i.is_dir ? "" : (i.name.split(".").pop() ?? "").toLowerCase();
    const word = i.name.replace(/\.[^.]+$/, "").split(/[\s_\-.()]+/).find((w) => w.length >= 3) ?? "";
    return {
      ...EMPTY_RULE,
      nombre: word ? `Archivos con «${word}»` : `Regla para ${i.name}`,
      tipo: i.is_dir ? "carpetas" : "archivos",
      extensiones: ext && !word ? [ext] : [],
      palabras: word ? [word] : [],
      destino: manual[i.path] ?? "",
    };
  }

  const total = moves.reduce((s, m) => s + m.size, 0);
  const dests = new Set(moves.map((m) => m.dest)).size;

  return (
    <div>
      <p className="max-w-2xl text-tenue">Tus reglas proponen dónde va cada elemento suelto. Revisas, ajustas nombres y confirmas; todo se puede deshacer desde el Historial.</p>
      <Alerta className="mt-8">{error}</Alerta>

      {data && (
        <div className={`transition-opacity ${loading ? "opacity-50" : ""}`}>
          <div className="mt-10">
            <Cifras
              items={[
                { label: "con destino propuesto", value: data.propuestas.length },
                { label: "por clasificar", value: data.por_clasificar.length },
                { label: "carpetas por crear", value: missing.length },
              ]}
            />
          </div>

          <Seccion titulo="Plan propuesto" descripcion="Agrupado por carpeta destino. Quita lo que no quieras mover y corrige cualquier nombre antes de revisar." className="mt-16">
            <div className="flex flex-col gap-4">
              {groups.map(([dest, items], i) => (
                <Group key={dest} dest={dest} items={items} vars={data.variables} isOn={isOn} names={names} onToggle={toggle} onName={(p, n) => setNames((x) => ({ ...x, [p]: n }))} index={i} />
              ))}
              {groups.length === 0 && <Vacio>Ninguna regla encontró algo que mover. Tus carpetas de origen están en orden o necesitan reglas nuevas.</Vacio>}
            </div>
          </Seccion>

          <Seccion
            titulo="Por clasificar"
            descripcion="Ninguna regla los reconoce. Elige un destino a mano o pide al asistente que lea los documentos y sugiera; si algo se repite, conviértelo en regla."
            acciones={
              sug.pensando ? (
                <button type="button" onClick={sug.detener} className="boton">
                  <Square size={14} aria-hidden="true" />
                  Detener
                </button>
              ) : (
                <button type="button" onClick={sug.pedir} disabled={data.por_clasificar.length === 0} className="boton">
                  <Sparkles size={14} aria-hidden="true" className="text-acento" />
                  {sug.datos?.estado === "listo" ? "Volver a sugerir" : "Que el asistente sugiera"}
                </button>
              )
            }
            className="mt-16"
          >
            <PanelSugerencias sug={sug} manual={manual} onUsar={usar} onMaterias={(ms) => setEstructura({ ...data.estructura, materias: [...data.estructura.materias, ...ms] })} />
            {data.por_clasificar.length === 0 ? (
              <Vacio>Nada por clasificar: tus reglas cubren todo lo suelto.</Vacio>
            ) : (
              <ul className="rounded-lg border border-linea bg-superficie px-5">
                {[...data.por_clasificar].sort((a, b) => Number(sug.porRuta.has(b.path)) - Number(sug.porRuta.has(a.path))).slice(0, shown).map((i) => {
                  const s = sug.porRuta.get(i.path);
                  return (
                  <li key={i.path} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-2 border-t border-linea py-2.5 text-sm first:border-t-0 md:grid-cols-[minmax(0,1fr)_5.5rem_16rem_auto]">
                    <ItemName item={i} vars={data.variables} />
                    <span className="text-right tabular-nums text-tenue">{i.size != null ? formatBytes(i.size) : ""}</span>
                    <label className="col-span-2 md:col-span-1">
                      <span className="sr-only">Destino para {i.name}</span>
                      <select
                        value={manual[i.path] ?? ""}
                        onChange={(e) => {
                          setManual((m) => ({ ...m, [i.path]: e.target.value }));
                          setNames(({ [i.path]: _, ...n }) => n); // otro destino: vuelve el nombre original
                        }}
                        className={`w-full rounded-md border bg-superficie px-2 py-1 text-xs ${manual[i.path] ? "border-acento text-texto" : "border-linea text-tenue"}`}
                      >
                        <option value="">Dejar donde está</option>
                        {data.carpetas.map((f) => (
                          <option key={f.template} value={f.template}>
                            {prettyTemplate(f.template)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <button type="button" onClick={() => setEditing({ index: null, rule: ruleFromItem(i) })} aria-label={`Crear regla a partir de ${i.name}`} className="enlace col-span-2 justify-end text-xs md:col-span-1">
                      <Wand2 size={13} aria-hidden="true" />
                      Crear regla
                    </button>
                    {s && (
                      <p className="col-span-2 flex flex-wrap items-start gap-x-2 gap-y-1 rounded-md bg-amarillo-suave/60 px-3 py-2 text-xs md:col-span-4">
                        <Sparkles size={13} aria-hidden="true" className="mt-0.5 shrink-0 text-acento" />
                        <span className="min-w-0 flex-1">
                          <span className="text-texto">
                            A {prettyTemplate(s.destino)}
                            {s.nuevo_nombre !== s.nombre && (
                              <>
                                {" "}como <span className="font-mono">{s.nuevo_nombre}</span>
                              </>
                            )}
                            .
                          </span>{" "}
                          <span className="text-tenue">
                            {s.razon} ({ORIGEN[s.origen]})
                          </span>
                        </span>
                        {manual[i.path] === s.destino ? (
                          <span className="text-tenue">Elegida</span>
                        ) : (
                          <button type="button" onClick={() => usar([s])} className="enlace">
                            Usar
                          </button>
                        )}
                      </p>
                    )}
                  </li>
                  );
                })}
                <MasFilas restantes={data.por_clasificar.length - shown} pagina={PAGE} onMas={() => setShown(shown + PAGE)} />
              </ul>
            )}
          </Seccion>

          <Seccion
            titulo="Reglas"
            descripcion="Se prueban en orden: la primera que coincide decide el destino."
            acciones={
              <button type="button" onClick={() => setEditing({ index: null, rule: EMPTY_RULE })} className="boton">
                <Plus size={14} aria-hidden="true" />
                Nueva regla
              </button>
            }
            className="mt-16"
          >
            <Alerta className="mb-4">{guardar.error}</Alerta>
            <RuleList rules={data.reglas} onChange={(rs) => guardar.correr(() => saveRules(rs))} onEdit={(i) => setEditing({ index: i, rule: data.reglas[i] })} />
          </Seccion>

          <Seccion
            titulo="Estructura objetivo"
            descripcion="Documentos en OneDrive, código en Dev. Las carpetas que faltan se crean con vista previa, y solo al confirmarlas."
            acciones={
              <>
                <button type="button" onClick={() => setEstructura(data.estructura)} className="boton">
                  <Pencil size={14} aria-hidden="true" />
                  Editar estructura
                </button>
                <button type="button" disabled={missing.length === 0} onClick={() => openPlan({ kind: "organizar", moves: [], folders: missing.map((f) => f.path) }, reset)} className="boton">
                  <FolderPlus size={14} aria-hidden="true" />
                  Crear carpetas que faltan ({fmtInt(missing.length)})
                </button>
              </>
            }
            className="mt-16"
          >
            <div className="rounded-lg border border-linea bg-superficie px-5 py-4">
              <Tree node={buildTree(data.carpetas)} />
            </div>
          </Seccion>
        </div>
      )}

      <BarraAccion
        visible={moves.length > 0}
        texto={
          <>
            {fmtInt(moves.length)} {moves.length === 1 ? "elemento" : "elementos"} a {fmtInt(dests)} {dests === 1 ? "carpeta" : "carpetas"}
            {total > 0 && (
              <>
                : <span className="cifra text-acento">{formatBytes(total)}</span>
              </>
            )}
          </>
        }
        detalle={editMode ? "Verás la lista exacta antes de aplicar. Todo se puede deshacer desde el Historial." : "Puedes ver la vista previa; para aplicarla activa el Modo edición."}
      >
        <button type="button" onClick={() => openPlan({ kind: "organizar", moves: moves.map(({ src, dest, name }) => ({ src, dest, name })) }, reset)} className="boton-primario">
          <ArrowRight size={15} aria-hidden="true" />
          Revisar movimientos
        </button>
      </BarraAccion>

      {editing && data && (
        <RuleDialog
          rule={editing.rule}
          folders={data.carpetas}
          onClose={() => setEditing(null)}
          onSave={(r) => saveRules(editing.index === null ? [...data.reglas, r] : data.reglas.map((x, j) => (j === editing.index ? { ...r, id: x.id } : x)))}
        />
      )}
      {estructura && <StructureDialog st={estructura} onClose={() => setEstructura(null)} onSave={(st) => put("/api/organizer/structure", st)} />}
    </div>
  );
}
