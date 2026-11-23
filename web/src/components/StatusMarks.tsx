import {
  Archive,
  Cloud,
  CloudCheck,
  Code2,
  File,
  FileText,
  Film,
  Folder,
  GitBranch,
  Image,
  Lock,
  Music,
  Package,
  RefreshCw,
  ShieldAlert,
  type LucideIcon,
} from "lucide-react";
import type { Entry } from "../types";

const TYPE_ICONS: Record<string, LucideIcon> = {
  carpeta: Folder,
  documentos: FileText,
  imagenes: Image,
  video: Film,
  audio: Music,
  codigo: Code2,
  comprimidos: Archive,
  instaladores: Package,
};

export const TYPE_LABELS: Record<string, string> = {
  carpeta: "Carpeta",
  documentos: "Documento",
  imagenes: "Imagen",
  video: "Video",
  audio: "Audio",
  codigo: "Código",
  comprimidos: "Comprimido",
  instaladores: "Instalador",
};

export const CLOUD_LABELS: Record<string, string> = {
  solo_nube: "Solo en la nube",
  local: "En este equipo",
  siempre_local: "Siempre en este equipo",
};

export function TypeIcon({ entry, size = 16 }: { entry: Pick<Entry, "type">; size?: number }) {
  const Icon = TYPE_ICONS[entry.type ?? ""] ?? File;
  return <Icon size={size} aria-hidden="true" className={entry.type === "carpeta" ? "fill-amarillo/20 text-acento" : "text-tenue"} />;
}

type Mark = { key: string; icon: LucideIcon; color: string; label: string; dot?: boolean };

export function marksFor(e: Pick<Entry, "cloud" | "tags" | "protected">, dirty?: boolean | null): Mark[] {
  const m: Mark[] = [];
  if (e.protected) m.push({ key: "p", icon: Lock, color: "text-protegido", label: "Ruta protegida: Orden PC no la modifica" });
  if (e.cloud === "solo_nube") m.push({ key: "n", icon: Cloud, color: "text-nube", label: CLOUD_LABELS.solo_nube });
  if (e.cloud === "siempre_local") m.push({ key: "s", icon: CloudCheck, color: "text-nube", label: CLOUD_LABELS.siempre_local });
  if (e.tags.includes("git"))
    m.push(
      dirty
        ? { key: "g", icon: GitBranch, color: "text-cambios", label: "Repo con cambios sin commit", dot: true }
        : { key: "g", icon: GitBranch, color: "text-tenue", label: "Repo de Git" },
    );
  if (e.tags.includes("regenerable")) m.push({ key: "r", icon: RefreshCw, color: "text-regenerable", label: "Se puede regenerar" });
  if (e.tags.includes("sin_acceso")) m.push({ key: "a", icon: ShieldAlert, color: "text-cambios", label: "Windows no dejó leer parte de su contenido" });
  return m;
}

/** Estado por forma y color a la vez; el texto queda para lectores de pantalla y como título. */
export function StatusMarks({ entry, dirty }: { entry: Pick<Entry, "cloud" | "tags" | "protected">; dirty?: boolean | null }) {
  const marks = marksFor(entry, dirty);
  if (!marks.length) return null;
  return (
    <span className="inline-flex shrink-0 items-center gap-1.5">
      {marks.map(({ key, icon: Icon, color, label, dot }) => (
        <span key={key} title={label} className={`relative inline-flex ${color}`}>
          <Icon size={13} aria-hidden="true" />
          {dot && <span aria-hidden="true" className="absolute -top-0.5 -right-0.5 size-1.5 rounded-full bg-current" />}
          <span className="sr-only">{label}</span>
        </span>
      ))}
    </span>
  );
}
