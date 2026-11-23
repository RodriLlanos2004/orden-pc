import { useEffect, useState } from "react";
import { api } from "../api";
import { qs } from "../useApi";

/**
 * Lo que dibuja el árbol: una carpeta y, en una fila debajo, sus subcarpetas más grandes.
 * Poca información a propósito: nombre, tamaño y cuánto pesa cada una. El detalle está en Archivos.
 */
export type Hoja = { name: string; path: string; size: number; zoom: boolean };
export type ArbolDatos = {
  inicio: boolean;
  raiz: Hoja & {
    disco: { drive: string; used: number; total: number } | null;
    padre: { name: string; size: number } | null;
  };
  ramas: Hoja[];
  otras: { count: number; size: number };
  sueltos: { count: number; size: number };
};

type Entry = { path: string; name: string; size: number; collapsed?: number | boolean };
type Children = { entry: Entry; children: Entry[]; loose: number; loose_files: number };

const RAMAS = 5;
const parent = (p: string) => p.slice(0, p.lastIndexOf("\\"));
const hoja = (e: Entry): Hoja => ({ name: e.name, path: e.path, size: e.size, zoom: !e.collapsed });

// Árboles ya leídos en esta pestaña, por versión del índice: volver con zoom no espera a la API.
// ponytail: crece sin límite mientras la pestaña viva; cada árbol pesa menos de 1 KB.
const cache = new Map<string, ArbolDatos>();

/** Datos del árbol de `path`: una sola consulta (dos fuera de la carpeta de usuario, para comparar con la madre). */
export function useArbol(path: string | undefined, home: string | undefined, version: number) {
  const [state, setState] = useState<{ path: string; data: ArbolDatos } | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!path || !home) return;
    let off = false;
    setError("");
    const key = `${version}|${path.toLowerCase()}`;
    const hit = cache.get(key);
    if (hit) {
      setState({ path, data: hit });
      return;
    }
    (async () => {
      try {
        const inicio = path.toLowerCase() === home.toLowerCase();
        const [top, disk, up] = await Promise.all([
          api<Children>(`/api/children?${qs({ path })}`),
          inicio ? api<{ drives: { drive: string; used: number; total: number }[] }>("/api/disk") : null,
          inicio ? null : api<Children>(`/api/children?${qs({ path: parent(path) })}`).catch(() => null),
        ]);
        const rest = top.children.slice(RAMAS);
        const drive = path.slice(0, 2).toUpperCase();
        const data: ArbolDatos = {
          inicio,
          raiz: {
            ...hoja(top.entry),
            name: top.entry.name || path,
            disco: disk?.drives.find((x) => x.drive.toUpperCase() === drive) ?? null,
            padre: up ? { name: up.entry.name || parent(path), size: up.entry.size } : null,
          },
          ramas: top.children.slice(0, RAMAS).map(hoja),
          otras: { count: rest.length, size: rest.reduce((s, c) => s + c.size, 0) },
          sueltos: { count: top.loose_files, size: top.loose },
        };
        cache.set(key, data);
        if (!off) setState({ path, data });
      } catch (e) {
        if (!off) setError((e as Error).message);
      }
    })();
    return () => {
      off = true;
    };
  }, [path, home, version]);
  // Solo se entregan los datos de la carpeta pedida: mientras carga la siguiente, no se muestra la anterior.
  return { data: state && state.path === path ? state.data : null, error };
}
