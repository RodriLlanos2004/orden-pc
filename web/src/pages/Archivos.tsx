import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronRight, Code2, ExternalLink, FolderInput, FolderPlus, Info, Lock, PencilLine, Trash2, type LucideIcon } from "lucide-react";
import FolderTree from "../components/FolderTree";
import FileTable, { type Sort } from "../components/FileTable";
import DetailsPanel from "../components/DetailsPanel";
import { MoveDialog, NameDialog } from "../components/ActionDialogs";
import { Alerta, Buscador, Hoja, Selector, useAccion } from "../components/ui";
import { api } from "../api";
import { useOps } from "../ops";
import { usePanel } from "../paneles";
import { qs, useApi } from "../useApi";
import type { Entry, Listing } from "../types";

type Dialog = { type: "crear" } | { type: "renombrar"; entry: Entry } | { type: "mover"; paths: string[] } | null;

function ActionButton({ icon: Icon, label, onClick, disabled, danger }: { icon: LucideIcon; label: string; onClick: () => void; disabled?: boolean; danger?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={label}
      aria-label={label}
      className={`flex min-h-7 items-center gap-1.5 rounded-md px-2 py-1 text-xs disabled:opacity-35 ${danger ? "text-error hover:bg-error/10" : "text-texto hover:bg-superficie-2"}`}
    >
      <Icon size={14} aria-hidden="true" />
      <span aria-hidden="true" className="hidden 2xl:inline">
        {label}
      </span>
    </button>
  );
}

type Filters = { type: string; date: string; tag: string; cloud: string };
const NO_FILTERS: Filters = { type: "", date: "", tag: "", cloud: "" };

const TYPE_OPTIONS = [
  ["", "Todos los tipos"],
  ["carpeta", "Carpetas"],
  ["documentos", "Documentos"],
  ["imagenes", "Imágenes"],
  ["video", "Video"],
  ["audio", "Audio"],
  ["codigo", "Código"],
  ["comprimidos", "Comprimidos"],
  ["instaladores", "Instaladores"],
  ["otros", "Otros archivos"],
];
const DATE_OPTIONS = [
  ["", "Cualquier fecha"],
  ["since:7", "Modificados esta semana"],
  ["since:30", "Modificados este mes"],
  ["since:365", "Modificados este año"],
  ["older:180", "Sin cambios en 6 meses"],
  ["older:365", "Sin cambios en más de un año"],
];
const CLOUD_OPTIONS = [
  ["", "OneDrive: todos"],
  ["solo_nube", "Solo en la nube"],
  ["local", "En este equipo"],
  ["fuera", "Fuera de OneDrive"],
];
const TAG_LABELS: Record<string, string> = {
  git: "Repo de Git",
  node: "Proyecto Node",
  python: "Proyecto Python",
  flutter: "Proyecto Flutter",
  regenerable: "Regenerable",
  git_interno: "Interior de .git",
  sin_acceso: "Sin acceso",
};

/** Mismos filtros que aplica el servidor, para los resultados de búsqueda. */
function matches(e: Entry, f: Filters): boolean {
  if (f.type === "carpeta" && !e.is_dir) return false;
  if (f.type === "otros" && (e.is_dir || e.type)) return false;
  if (f.type && !["carpeta", "otros"].includes(f.type) && e.type !== f.type) return false;
  if (f.cloud === "solo_nube" && e.cloud !== "solo_nube") return false;
  if (f.cloud === "local" && !(e.cloud === "local" || e.cloud === "siempre_local")) return false;
  if (f.cloud === "fuera" && e.cloud) return false;
  if (f.tag && !e.tags.includes(f.tag) && !e.user_tags?.includes(f.tag)) return false;
  if (f.date) {
    const [k, n] = f.date.split(":");
    const limit = Date.now() / 1000 - Number(n) * 86400;
    if (k === "since" && !((e.mtime ?? 0) >= limit)) return false;
    if (k === "older" && !((e.mtime ?? 0) < limit)) return false;
  }
  return true;
}

function sortItems(items: Entry[], s: Sort): Entry[] {
  const dir = s.order === "asc" ? 1 : -1;
  const key = (e: Entry) => (s.key === "size" ? e.size : s.key === "mtime" ? e.mtime ?? 0 : s.key === "type" ? e.ext ?? "" : e.name.toLowerCase());
  return [...items].sort((a, b) => (key(a) < key(b) ? -dir : key(a) > key(b) ? dir : 0));
}

function Breadcrumb({ path, root, onOpen }: { path: string; root: Entry | undefined; onOpen: (p: string) => void }) {
  if (!root) return null;
  const base = root.path.replace(/\\$/, "");
  const parts = path.length > base.length ? path.slice(base.length + 1).split("\\") : [];
  const crumbs = [{ name: root.mode === "completo" ? "Mi carpeta" : root.path, path: root.path }];
  let acc = base;
  for (const p of parts) {
    acc = `${acc}\\${p}`;
    crumbs.push({ name: p, path: acc });
  }
  return (
    <nav aria-label="Ruta" className="flex min-w-0 flex-wrap items-center gap-0.5 text-sm">
      {crumbs.map((c, i) => (
        <span key={c.path} className="flex min-w-0 items-center gap-0.5">
          {i > 0 && <ChevronRight size={13} aria-hidden="true" className="shrink-0 text-tenue" />}
          {i === crumbs.length - 1 ? (
            <span aria-current="location" className="truncate font-medium text-texto">
              {c.name}
            </span>
          ) : (
            <button type="button" onClick={() => onOpen(c.path)} className="min-h-6 truncate rounded px-1 text-tenue hover:text-texto">
              {c.name}
            </button>
          )}
        </span>
      ))}
    </nav>
  );
}

/** Explorador de archivos: árbol de carpetas, tabla y detalles, con búsqueda en todo el índice y acciones con vista previa. */
export default function Archivos() {
  const { params, setParams } = usePanel();
  const { editMode, openPlan, cambios } = useOps();
  const [marked, setMarked] = useState<Set<string>>(new Set());
  const [dialog, setDialog] = useState<Dialog>(null);
  const accion = useAccion();
  const roots = useApi<{ roots: Entry[] }>(`/api/roots?v=${cambios}`);
  const home = roots.data?.roots.find((r) => r.mode === "completo") ?? roots.data?.roots[0];
  const current = params.get("ruta") ?? home?.path ?? "";
  const ir = (ruta: string) => setParams({ panel: "archivos", ruta });
  const refresh = async () => {
    setMarked(new Set());
    setSelected(null);
    // Si la carpeta que estabas viendo se movió, se renombró o fue a la Papelera, sube a la primera que siga ahí.
    let p = current;
    while (p.includes("\\") && !(await api("/api/entry?" + qs({ path: p })).then(() => true, () => false))) {
      p = p.slice(0, p.lastIndexOf("\\"));
    }
    if (p !== current) ir(p);
  };
  const [selected, setSelected] = useState<string | null>(null);
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [sort, setSort] = useState<Sort>({ key: "name", order: "asc" });
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [drawer, setDrawer] = useState(false);
  const [userTags, setUserTags] = useState<Map<string, string[]>>(new Map());
  const tags = useApi<{ detected: string[]; user: string[] }>(`/api/tags?v=${userTags.size}`);
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(query.trim()), 180);
    return () => clearTimeout(t);
  }, [query]);

  useEffect(() => {
    // Ctrl+K con la hoja ya abierta: vuelve al buscador.
    if (params.has("buscar")) searchRef.current?.focus();
  }, [params]);

  const [k, n] = filters.date.split(":");
  const listing = useApi<Listing>(
    current && !debounced
      ? `/api/list?${qs({ path: current, type: filters.type, tag: filters.tag, cloud: filters.cloud, sort: sort.key, order: sort.order, since: k === "since" ? n : null, older: k === "older" ? n : null, v: cambios })}`
      : null,
  );
  const search = useApi<{ results: Entry[] }>(debounced ? `/api/search?${qs({ q: debounced, limit: 500, v: cambios })}` : null);

  const searchMode = !!debounced;
  const items = useMemo(() => {
    const raw = searchMode ? sortItems((search.data?.results ?? []).filter((e) => matches(e, filters)), sort) : listing.data?.items ?? [];
    return raw.map((e) => (userTags.has(e.path) ? { ...e, user_tags: userTags.get(e.path) } : e));
  }, [searchMode, search.data, listing.data, filters, sort, userTags]);

  function open(path: string) {
    setQuery("");
    setDebounced("");
    setSelected(null);
    setMarked(new Set());
    ir(path);
  }

  // Sobre qué actúan las acciones: lo marcado, o si no hay nada marcado, la fila seleccionada.
  const targets = marked.size ? [...marked] : selected ? [selected] : [];

  const openIn = (app: "explorer" | "vscode") =>
    accion.correr(() => api("/api/open", { method: "POST", body: JSON.stringify({ path: targets.length === 1 ? targets[0] : current, app }) }));

  function openEntry(e: Entry) {
    if (e.is_dir && !e.collapsed) open(e.path);
    else {
      setSelected(e.path);
      setDrawer(true);
    }
  }

  function up() {
    const root = roots.data?.roots.find((r) => r.path.toLowerCase() === current.toLowerCase());
    if (root || !current.includes("\\")) return;
    const parent = current.slice(0, current.lastIndexOf("\\"));
    open(parent.endsWith(":") ? `${parent}\\` : parent);
  }

  const root = roots.data?.roots.filter((r) => current.toLowerCase().startsWith(r.path.toLowerCase().replace(/\\$/, ""))).sort((a, b) => b.path.length - a.path.length)[0];
  const filtering = filters.type || filters.date || filters.tag || filters.cloud;
  const tagOptions = [
    ["", "Etiqueta: todas"],
    ...(tags.data?.detected ?? []).map((t) => [t, TAG_LABELS[t] ?? t]),
    ...(tags.data?.user ?? []).map((t) => [t, `Tuya: ${t}`]),
  ];
  const detalles = (onNavigate: (p: string) => void) => (
    <DetailsPanel path={selected} onNavigate={onNavigate} onMetaSaved={(p, t) => setUserTags((m) => new Map(m).set(p, t))} />
  );

  const empty = searchMode ? (
    <p className="text-sm text-tenue">{search.loading ? "Buscando" : `Nada en el índice coincide con “${debounced}”${filtering ? " con estos filtros" : ""}.`}</p>
  ) : filtering ? (
    <p className="text-sm text-tenue">
      Nada en esta carpeta coincide con los filtros.{" "}
      <button type="button" onClick={() => setFilters(NO_FILTERS)} className="enlace">
        Quitar filtros
      </button>
    </p>
  ) : listing.data?.entry.collapsed ? (
    <p className="text-sm text-tenue">Orden PC suma esta carpeta sin listar su contenido.</p>
  ) : (
    <p className="text-sm text-tenue">{listing.loading ? "Cargando" : "Esta carpeta está vacía."}</p>
  );

  return (
    <>
      <div className="flex flex-wrap items-center gap-2 px-6 py-3 lg:px-10">
        <Buscador
          inputRef={searchRef}
          autoFocus={params.has("buscar")}
          value={query}
          onChange={setQuery}
          label="Buscar en todo el índice"
          placeholder="Busca por nombre o ruta en todo tu equipo"
          className="mr-2 w-full max-w-md"
        />
        <Selector label="Tipo" value={filters.type} options={TYPE_OPTIONS} onChange={(type) => setFilters({ ...filters, type })} />
        <Selector label="Fecha" value={filters.date} options={DATE_OPTIONS} onChange={(date) => setFilters({ ...filters, date })} />
        <Selector label="Etiqueta" value={filters.tag} options={tagOptions} onChange={(tag) => setFilters({ ...filters, tag })} />
        <Selector label="OneDrive" value={filters.cloud} options={CLOUD_OPTIONS} onChange={(cloud) => setFilters({ ...filters, cloud })} />
        {filtering && (
          <button type="button" onClick={() => setFilters(NO_FILTERS)} className="rounded-md px-2.5 py-1.5 text-sm text-tenue hover:text-texto">
            Quitar filtros
          </button>
        )}
        <span aria-live="polite" className="ml-auto text-xs text-tenue">
          {searchMode
            ? `${items.length.toLocaleString("es-MX")} resultados en todo el índice`
            : listing.data && `${items.length.toLocaleString("es-MX")} elementos${listing.data.truncated ? " (se muestran los primeros 10 000)" : ""}`}
        </span>
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-1 border-t border-linea md:grid-cols-[15rem_1fr] xl:grid-cols-[17rem_1fr_22rem]">
        <aside className="hidden min-h-0 border-r border-linea md:block">
          {roots.data && (
            <FolderTree
              roots={roots.data.roots}
              current={current}
              onOpen={open}
              version={cambios}
              onDropPaths={editMode ? (paths, dest) => openPlan({ kind: "mover", paths, dest }, refresh) : undefined}
            />
          )}
        </aside>

        <section aria-label="Contenido de la carpeta" className="flex min-h-0 flex-col">
          <div className="flex items-center gap-3 border-b border-linea px-4 py-2.5">
            {searchMode ? <p className="text-sm text-texto">Resultados para “{debounced}”</p> : <Breadcrumb path={current} root={root} onOpen={open} />}
            {selected && (
              <button type="button" onClick={() => setDrawer(true)} className="ml-auto flex shrink-0 items-center gap-1.5 rounded-md border border-linea px-2.5 py-1 text-xs text-tenue hover:text-texto xl:hidden">
                <Info size={13} aria-hidden="true" />
                Ver detalles
              </button>
            )}
          </div>
          {editMode ? (
            <div role="toolbar" aria-label="Acciones" className="flex flex-wrap items-center gap-1 border-b border-linea px-3 py-1.5">
              <ActionButton icon={FolderPlus} label="Nueva carpeta" disabled={searchMode} onClick={() => setDialog({ type: "crear" })} />
              <ActionButton
                icon={PencilLine}
                label="Renombrar"
                disabled={targets.length !== 1}
                onClick={() => {
                  const e = items.find((x) => x.path === targets[0]);
                  if (e) setDialog({ type: "renombrar", entry: e });
                }}
              />
              <ActionButton icon={FolderInput} label="Mover a" disabled={!targets.length} onClick={() => setDialog({ type: "mover", paths: targets })} />
              <ActionButton icon={Trash2} label="Enviar a la Papelera" danger disabled={!targets.length} onClick={() => openPlan({ kind: "papelera", paths: targets }, refresh)} />
              <span className="mx-1 h-4 w-px bg-linea" aria-hidden="true" />
              <ActionButton icon={ExternalLink} label="Abrir en el Explorador de Windows" onClick={() => openIn("explorer")} />
              <ActionButton icon={Code2} label="Abrir en VS Code" onClick={() => openIn("vscode")} />
              <span aria-live="polite" className="ml-auto pr-1 text-xs text-tenue">
                {marked.size > 0 && (
                  <>
                    {marked.size.toLocaleString("es-MX")} marcados.{" "}
                    <button type="button" onClick={() => setMarked(new Set())} className="underline underline-offset-2 hover:text-texto">
                      Quitar marcas
                    </button>
                  </>
                )}
              </span>
            </div>
          ) : (
            <p className="flex items-center gap-2 border-b border-linea px-4 py-2 text-xs text-tenue">
              <Lock size={12} aria-hidden="true" />
              Solo lectura. Activa el Modo edición arriba para crear, renombrar, mover o enviar a la Papelera.
            </p>
          )}
          <Alerta className="border-b border-linea px-4 py-2">{accion.error}</Alerta>
          {!searchMode && listing.data?.mode === "carpetas" && (
            <p className="flex items-center gap-2 border-b border-linea px-4 py-2 text-xs text-tenue">
              <Info size={13} aria-hidden="true" />
              En esta zona del disco Orden PC indexa carpetas, no archivos sueltos. Por eso solo ves carpetas.
            </p>
          )}
          <Alerta className="px-4 py-2">{listing.error || search.error}</Alerta>
          <div className="min-h-0 flex-1">
            <FileTable
              items={items}
              searchMode={searchMode}
              sort={sort}
              onSort={setSort}
              selected={selected}
              onSelect={(e) => setSelected(e.path)}
              onOpen={openEntry}
              onUp={up}
              empty={empty}
              dim={listing.loading || search.loading}
              editMode={!!editMode}
              marked={marked}
              onMarked={setMarked}
            />
          </div>
        </section>

        <aside aria-label="Detalles" className="hidden min-h-0 border-l border-linea xl:block">
          {detalles(open)}
        </aside>
      </div>

      {/* En pantallas angostas los detalles abren su propia hoja. */}
      <Hoja abierta={drawer && !!selected} onCerrar={() => setDrawer(false)} titulo="Detalles" ancho="w-[min(24rem,100vw)] xl:hidden" fondo={false}>
        <div className="min-h-0 flex-1">{detalles((p) => (open(p), setDrawer(false)))}</div>
      </Hoja>

      {dialog?.type === "crear" && (
        <NameDialog title="Nueva carpeta" initial="" hint={`Dentro de ${current}`} onClose={() => setDialog(null)} onSubmit={(name) => openPlan({ kind: "crear", path: current, name }, refresh)} />
      )}
      {dialog?.type === "renombrar" && (
        <NameDialog
          title={`Renombrar «${dialog.entry.name}»`}
          initial={dialog.entry.name}
          hint="Regla de nombres para entregas: AAAA-MM-DD_Materia_Tema_v1.ext"
          onClose={() => setDialog(null)}
          onSubmit={(name) => openPlan({ kind: "renombrar", path: dialog.entry.path, name }, refresh)}
        />
      )}
      {dialog?.type === "mover" && roots.data && (
        <MoveDialog roots={roots.data.roots} count={dialog.paths.length} start={current} onClose={() => setDialog(null)} onSubmit={(dest) => openPlan({ kind: "mover", paths: dialog.paths, dest }, refresh)} />
      )}
    </>
  );
}
