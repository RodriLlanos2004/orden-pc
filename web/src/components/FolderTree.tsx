import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChevronRight, Folder, HardDrive, User } from "lucide-react";
import { api } from "../api";
import { formatBytes } from "../format";
import { qs } from "../useApi";
import { DRAG_TYPE } from "./FileTable";
import { StatusMarks } from "./StatusMarks";
import type { Entry } from "../types";

type Node = Entry & { level: number };

const isInside = (path: string, base: string) => path.toLowerCase() === base.toLowerCase() || path.toLowerCase().startsWith(base.toLowerCase().replace(/\\$/, "") + "\\");
const domId = (path: string) => "arbol-" + Array.from(path).map((c) => c.charCodeAt(0).toString(36)).join("");

/**
 * Árbol de carpetas (patrón ARIA treeview). Carga hijos bajo demanda.
 * Teclado: flechas arriba/abajo, derecha abre o baja, izquierda cierra o sube, Inicio/Fin, Enter abre la carpeta.
 */
export default function FolderTree({ roots, current, onOpen, version = 0, onDropPaths, label = "Carpetas" }: {
  roots: Entry[];
  current: string;
  onOpen: (path: string) => void;
  version?: number;
  onDropPaths?: (paths: string[], dest: string) => void;
  label?: string;
}) {
  const [children, setChildren] = useState<Map<string, Entry[]>>(new Map());
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [active, setActive] = useState<string>(current);
  const [focused, setFocused] = useState(false);
  const [dropTarget, setDropTarget] = useState<string | null>(null);
  const ref = useRef<HTMLUListElement>(null);
  const cache = useRef(new Map<string, Entry[]>());

  const load = useCallback(async (path: string, force = false) => {
    if (!force && cache.current.has(path)) return;
    const d = await api<{ children: Entry[] }>(`/api/children?${qs({ path })}`);
    cache.current.set(path, d.children);
    setChildren(new Map(cache.current));
  }, []);

  // Después de un cambio, vuelve a pedir las carpetas abiertas.
  useEffect(() => {
    if (!version) return;
    for (const p of expanded) load(p, true).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [version]);

  // Abre los ancestros de la carpeta actual (por ejemplo, al llegar desde el Panel).
  useEffect(() => {
    setActive(current);
    const root = roots.filter((r) => isInside(current, r.path)).sort((a, b) => b.path.length - a.path.length)[0];
    if (!root) return;
    const chain = [root.path];
    const rest = current.slice(root.path.replace(/\\$/, "").length + 1);
    if (rest) {
      let acc = root.path.replace(/\\$/, "");
      for (const part of rest.split("\\").slice(0, -1)) {
        acc = `${acc}\\${part}`;
        chain.push(acc);
      }
    }
    (async () => {
      for (const p of chain) await load(p).catch(() => undefined);
      setExpanded((s) => new Set([...s, ...chain]));
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current, roots]);

  const visible: Node[] = useMemo(() => {
    const out: Node[] = [];
    const walk = (items: Entry[], level: number) => {
      for (const e of items) {
        out.push({ ...e, level });
        if (expanded.has(e.path)) walk(children.get(e.path) ?? [], level + 1);
      }
    };
    walk(roots, 1);
    return out;
  }, [roots, children, expanded]);

  async function toggle(e: Entry, open?: boolean) {
    const willOpen = open ?? !expanded.has(e.path);
    if (willOpen) await load(e.path);
    setExpanded((s) => {
      const n = new Set(s);
      if (willOpen) n.add(e.path);
      else n.delete(e.path);
      return n;
    });
  }

  function onKey(ev: React.KeyboardEvent) {
    const i = visible.findIndex((n) => n.path === active);
    const node = visible[i];
    const go = (j: number) => {
      const n = visible[Math.max(0, Math.min(visible.length - 1, j))];
      if (n) {
        setActive(n.path);
        document.getElementById(domId(n.path))?.scrollIntoView({ block: "nearest" });
      }
    };
    const keys: Record<string, () => void> = {
      ArrowDown: () => go(i + 1),
      ArrowUp: () => go(i - 1),
      Home: () => go(0),
      End: () => go(visible.length - 1),
      ArrowRight: () => {
        if (!node?.has_children) return;
        if (!expanded.has(node.path)) toggle(node, true);
        else go(i + 1);
      },
      ArrowLeft: () => {
        if (node && expanded.has(node.path)) toggle(node, false);
        else {
          const parent = visible.slice(0, i).reverse().find((n) => n.level === (node?.level ?? 1) - 1);
          if (parent) go(visible.indexOf(parent));
        }
      },
      Enter: () => node && onOpen(node.path),
      " ": () => node && onOpen(node.path),
    };
    if (keys[ev.key]) {
      ev.preventDefault();
      keys[ev.key]();
    }
  }

  return (
    <ul
      ref={ref}
      role="tree"
      aria-label={label}
      tabIndex={0}
      aria-activedescendant={visible.some((n) => n.path === active) ? domId(active) : undefined}
      onKeyDown={onKey}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
      className="h-full overflow-auto py-2 text-sm outline-none"
    >
      {visible.map((n) => {
        const open = expanded.has(n.path);
        const isCurrent = n.path.toLowerCase() === current.toLowerCase();
        const Icon = n.level === 1 ? (n.mode === "completo" ? User : HardDrive) : Folder;
        return (
          <li
            key={n.path}
            id={domId(n.path)}
            role="treeitem"
            aria-level={n.level}
            aria-expanded={n.has_children ? open : undefined}
            aria-selected={isCurrent}
            onClick={() => {
              setActive(n.path);
              onOpen(n.path);
            }}
            onDragOver={(ev) => {
              if (!onDropPaths || n.protected || !ev.dataTransfer.types.includes(DRAG_TYPE)) return;
              ev.preventDefault();
              ev.dataTransfer.dropEffect = "move";
              setDropTarget(n.path);
            }}
            onDragLeave={() => setDropTarget((t) => (t === n.path ? null : t))}
            onDrop={(ev) => {
              ev.preventDefault();
              setDropTarget(null);
              const raw = ev.dataTransfer.getData(DRAG_TYPE);
              if (raw && onDropPaths) onDropPaths(JSON.parse(raw), n.path);
            }}
            className={`group flex cursor-pointer items-center gap-1.5 py-1 pr-3 ${
              isCurrent ? "bg-amarillo/15 text-texto" : "text-tenue hover:text-texto"
            } ${focused && n.path === active ? "outline-2 -outline-offset-2 outline-acento outline" : ""} ${
              dropTarget === n.path ? "bg-amarillo/25 text-texto outline-2 -outline-offset-2 outline-dashed outline-acento" : ""
            }`}
            style={{ paddingLeft: `${(n.level - 1) * 14 + 8}px` }}
          >
            <span
              aria-hidden="true"
              onClick={(ev) => {
                ev.stopPropagation();
                toggle(n);
              }}
              className={`grid size-4 shrink-0 place-items-center rounded ${n.has_children ? "" : "invisible"}`}
            >
              <ChevronRight size={13} className={`transition-transform ${open ? "rotate-90" : ""}`} />
            </span>
            <Icon size={14} aria-hidden="true" className={isCurrent ? "text-acento" : ""} />
            <span className="min-w-0 flex-1 truncate">{n.level === 1 ? (n.mode === "completo" ? "Mi carpeta" : n.path) : n.name}</span>
            <StatusMarks entry={n} />
            <span className="shrink-0 text-xs tabular-nums text-tenue opacity-0 group-hover:opacity-100">{formatBytes(n.size)}</span>
          </li>
        );
      })}
    </ul>
  );
}
