import { lazy } from "react";
import { useSearchParams } from "react-router";
import { AppWindow, FolderOpen, HardDrive, History, Settings2, Wand2, type LucideIcon } from "lucide-react";
import { qs } from "./useApi";

/**
 * Una sola pantalla: el árbol. Todo lo demás se abre encima, en una hoja lateral, sin cambiar de pestaña.
 * La hoja abierta vive en la dirección (`?panel=apps`): Atrás del navegador la cierra y los enlaces la abren.
 * Cada herramienta se descarga recién al abrirla.
 */
export type Panel = { id: string; label: string; icon: LucideIcon; Componente: React.LazyExoticComponent<() => React.ReactNode>; ancho?: string; lleno?: boolean };

export const PANELES: Panel[] = [
  { id: "archivos", label: "Archivos", icon: FolderOpen, Componente: lazy(() => import("./pages/Archivos")), ancho: "w-[calc(100vw-1.5rem)] xl:w-[calc(100vw-5rem)]", lleno: true },
  { id: "ordenar", label: "Ordenar", icon: Wand2, Componente: lazy(() => import("./pages/Ordenar")) },
  { id: "apps", label: "Apps", icon: AppWindow, Componente: lazy(() => import("./pages/Apps")) },
  { id: "disco", label: "Disco", icon: HardDrive, Componente: lazy(() => import("./components/Resumen")), ancho: "w-[min(64rem,calc(100vw-1.5rem))]" },
  { id: "historial", label: "Historial", icon: History, Componente: lazy(() => import("./pages/History")), ancho: "w-[min(64rem,calc(100vw-1.5rem))]" },
  { id: "ajustes", label: "Ajustes", icon: Settings2, Componente: lazy(() => import("./pages/Settings")), ancho: "w-[min(64rem,calc(100vw-1.5rem))]" },
];

/** Enlace a una herramienta: `/?panel=ordenar&ver=organizar`. */
export const rutaPanel = (id: string, extra: Record<string, string> = {}) => `/?${qs({ panel: id, ...extra })}`;

export function usePanel() {
  const [params, setParams] = useSearchParams();
  return {
    params,
    setParams,
    actual: PANELES.find((p) => p.id === params.get("panel")),
    abrir: (id: string, extra: Record<string, string> = {}) => setParams({ panel: id, ...extra }),
    cerrar: () => setParams({}),
  };
}
