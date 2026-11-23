import { useEffect, useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { ArrowDown, ArrowUp } from "lucide-react";
import { fmtDate, formatBytes } from "../format";
import { StatusMarks, TYPE_LABELS, TypeIcon } from "./StatusMarks";
import type { Entry } from "../types";

export type SortKey = "name" | "size" | "mtime" | "type";
export type Sort = { key: SortKey; order: "asc" | "desc" };

const ROW = 44;

type Props = {
  items: Entry[];
  searchMode: boolean;
  sort: Sort;
  onSort: (s: Sort) => void;
  selected: string | null;
  onSelect: (e: Entry) => void;
  onOpen: (e: Entry) => void;
  onUp: () => void;
  empty: React.ReactNode;
  dim: boolean;
  editMode: boolean;
  marked: Set<string>;
  onMarked: (next: Set<string>) => void;
};

export const DRAG_TYPE = "application/x-orden-pc-rutas";
const rowId = (i: number) => `fila-${i}`;

/**
 * Tabla de contenido (patrón ARIA grid con aria-activedescendant, porque las filas se virtualizan).
 * Teclado: flechas, Inicio/Fin, RePág/AvPág, Enter abre la carpeta, Retroceso sube un nivel.
 */
export default function FileTable({ items, searchMode, sort, onSort, selected, onSelect, onOpen, onUp, empty, dim, editMode, marked, onMarked }: Props) {
  const scroller = useRef<HTMLDivElement>(null);
  const anchor = useRef<number>(-1);
  const v = useVirtualizer({ count: items.length, getScrollElement: () => scroller.current, estimateSize: () => ROW, overscan: 12 });
  const index = items.findIndex((e) => e.path === selected);
  const maxSize = items.reduce((m, e) => Math.max(m, e.size), 1);
  // Clases completas y literales: Tailwind no ve las que se arman con plantillas.
  const cols = searchMode
    ? editMode
      ? "grid-cols-[1.75rem_minmax(0,1.4fr)_minmax(0,1fr)_7.5rem_8rem]"
      : "grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_7.5rem_8rem]"
    : editMode
      ? "grid-cols-[1.75rem_minmax(0,1fr)_7.5rem_8rem_8rem]"
      : "grid-cols-[minmax(0,1fr)_7.5rem_8rem_8rem]";

  function toggle(i: number, range = false) {
    const next = new Set(marked);
    if (range && anchor.current >= 0) {
      const [a, b] = [Math.min(anchor.current, i), Math.max(anchor.current, i)];
      items.slice(a, b + 1).forEach((e) => next.add(e.path));
    } else {
      const p = items[i].path;
      if (next.has(p)) next.delete(p);
      else next.add(p);
      anchor.current = i;
    }
    onMarked(next);
  }

  useEffect(() => {
    if (index >= 0) v.scrollToIndex(index, { align: "auto" });
  }, [index, v]);

  function onKey(ev: React.KeyboardEvent) {
    const move = (j: number) => {
      const e = items[Math.max(0, Math.min(items.length - 1, j))];
      if (e) onSelect(e);
    };
    const page = Math.max(1, Math.floor((scroller.current?.clientHeight ?? 400) / ROW) - 1);
    const keys: Record<string, () => void> = {
      ArrowDown: () => move(index + 1),
      ArrowUp: () => move(index <= 0 ? 0 : index - 1),
      Home: () => move(0),
      End: () => move(items.length - 1),
      PageDown: () => move(index + page),
      PageUp: () => move(index - page),
      Enter: () => index >= 0 && onOpen(items[index]),
      Backspace: () => !searchMode && onUp(),
      " ": () => editMode && index >= 0 && toggle(index, ev.shiftKey),
    };
    if (editMode && ev.key.toLowerCase() === "a" && (ev.ctrlKey || ev.metaKey)) {
      ev.preventDefault();
      onMarked(marked.size === items.length ? new Set() : new Set(items.map((e) => e.path)));
      return;
    }
    if (editMode && ev.key === "Escape" && marked.size) {
      ev.preventDefault();
      ev.stopPropagation(); // quita las marcas sin cerrar la hoja
      onMarked(new Set());
      return;
    }
    if (keys[ev.key]) {
      ev.preventDefault();
      keys[ev.key]();
    }
  }

  const header = (key: SortKey, label: string, align = "text-left") => {
    const on = sort.key === key;
    const Arrow = sort.order === "asc" ? ArrowUp : ArrowDown;
    return (
      <div role="columnheader" aria-sort={on ? (sort.order === "asc" ? "ascending" : "descending") : "none"} className={align}>
        <button
          type="button"
          onClick={() => onSort({ key, order: on && sort.order === "asc" ? "desc" : key === "name" || key === "type" ? "asc" : "desc" })}
          className={`inline-flex min-h-6 items-center gap-1 rounded px-1 py-0.5 hover:text-texto ${on ? "text-texto" : ""}`}
        >
          {label}
          {on && <Arrow size={12} aria-hidden="true" />}
        </button>
      </div>
    );
  };

  return (
    <div
      role="grid"
      aria-label="Contenido"
      aria-rowcount={items.length + 1}
      aria-activedescendant={index >= 0 ? rowId(index) : undefined}
      tabIndex={0}
      onKeyDown={onKey}
      onFocus={() => index < 0 && items[0] && onSelect(items[0])}
      className="flex h-full min-h-0 flex-col outline-none focus-visible:ring-2 focus-visible:ring-acento focus-visible:ring-inset"
    >
      <div role="row" aria-rowindex={1} className={`grid ${cols} gap-4 border-b border-linea px-4 py-2 text-xs text-tenue`}>
        {editMode && (
          <div role="columnheader" className="flex items-center">
            <input
              type="checkbox"
              aria-label="Marcar todos"
              checked={items.length > 0 && marked.size === items.length}
              ref={(el) => {
                if (el) el.indeterminate = marked.size > 0 && marked.size < items.length;
              }}
              onChange={() => onMarked(marked.size === items.length ? new Set() : new Set(items.map((e) => e.path)))}
              className="size-4 accent-[var(--acento)]"
            />
          </div>
        )}
        {header("name", "Nombre")}
        {searchMode && (
          <div role="columnheader" className="px-1 py-0.5">
            Carpeta
          </div>
        )}
        {header("size", "Tamaño", "text-right")}
        {!searchMode && header("type", "Tipo")}
        {header("mtime", "Modificado")}
      </div>

      <div ref={scroller} className={`min-h-0 flex-1 overflow-auto transition-opacity ${dim ? "opacity-50" : ""}`}>
        {items.length === 0 ? (
          <div className="p-6">{empty}</div>
        ) : (
          <div className="relative" style={{ height: v.getTotalSize() }}>
            {v.getVirtualItems().map((vi) => {
              const e = items[vi.index];
              const isSel = e.path === selected;
              const isMarked = marked.has(e.path);
              return (
                <div
                  key={e.path}
                  id={rowId(vi.index)}
                  role="row"
                  aria-rowindex={vi.index + 2}
                  aria-selected={editMode ? isMarked : isSel}
                  draggable={editMode && !e.protected}
                  onDragStart={(ev) => {
                    const paths = isMarked ? [...marked] : [e.path];
                    ev.dataTransfer.setData(DRAG_TYPE, JSON.stringify(paths));
                    ev.dataTransfer.effectAllowed = "move";
                  }}
                  onClick={(ev) => {
                    onSelect(e);
                    if (editMode && (ev.ctrlKey || ev.metaKey || ev.shiftKey)) toggle(vi.index, ev.shiftKey);
                  }}
                  onDoubleClick={() => onOpen(e)}
                  className={`absolute inset-x-0 grid ${cols} cursor-default items-center gap-4 px-4 text-sm ${
                    isSel ? "bg-amarillo/15 shadow-[inset_3px_0_0_var(--amarillo-fuerte)]" : isMarked ? "bg-amarillo/8" : "hover:bg-amarillo/5"
                  }`}
                  style={{ height: ROW, transform: `translateY(${vi.start}px)` }}
                >
                  {editMode && (
                    <div role="gridcell" className="flex items-center">
                      <input
                        type="checkbox"
                        tabIndex={-1}
                        aria-label={`Marcar ${e.name}`}
                        checked={isMarked}
                        onClick={(ev) => ev.stopPropagation()}
                        onChange={(ev) => toggle(vi.index, (ev.nativeEvent as MouseEvent).shiftKey)}
                        className="size-4 accent-[var(--acento)]"
                      />
                    </div>
                  )}
                  <div role="gridcell" className="flex min-w-0 items-center gap-2.5">
                    <TypeIcon entry={e} />
                    <span className={`truncate ${e.is_dir ? "font-medium text-texto" : "text-texto/90"}`}>{e.name}</span>
                    <StatusMarks entry={e} />
                    {e.user_tags?.map((t) => (
                      <span key={t} className="hidden shrink-0 rounded border border-linea px-1.5 text-[11px] text-tenue md:inline">
                        {t}
                      </span>
                    ))}
                  </div>
                  {searchMode && (
                    <div role="gridcell" className="truncate font-mono text-xs text-tenue" title={e.parent ?? ""}>
                      {e.parent}
                    </div>
                  )}
                  <div role="gridcell" className="text-right">
                    <span className="tabular-nums text-texto/90">{formatBytes(e.size)}</span>
                    <span aria-hidden="true" className="mt-1 block h-[2px] rounded-full bg-superficie-2">
                      <span className="block h-full rounded-full bg-amarillo/70" style={{ width: `${Math.max(1, (e.size / maxSize) * 100)}%` }} />
                    </span>
                  </div>
                  {!searchMode && (
                    <div role="gridcell" className="truncate text-tenue">
                      {e.type ? TYPE_LABELS[e.type] : e.ext ? e.ext.toUpperCase() : "Archivo"}
                    </div>
                  )}
                  <div role="gridcell" className="text-tenue tabular-nums">
                    {fmtDate(e.mtime)}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
