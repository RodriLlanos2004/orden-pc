import { AnimatePresence, motion } from "motion/react";
import { Radar, Square } from "lucide-react";
import { EASE } from "./motion";
import { Alerta } from "./ui";
import { formatBytes, fmtDuration, fmtInt, timeAgo } from "../format";
import type { ScanSnapshot, useScan } from "../useScan";

const PHASES: Record<string, string> = {
  recorrido: "Recorriendo tus carpetas",
  proyectos: "Revisando proyectos y repos",
  duplicados: "Buscando duplicados exactos",
};
const ENDINGS: Record<string, string> = {
  cancelado: "Detuviste el escaneo. El índice conserva lo que ya se había recorrido.",
  error: "El escaneo se interrumpió por un error. Puedes intentarlo de nuevo.",
};

/** Botón de escanear y su estado. `compacto`: solo el botón (y el avance); el detalle del último escaneo va en su título. */
export function Escaneo({ scan, compacto = false }: { scan: ReturnType<typeof useScan>; compacto?: boolean }) {
  const { snap, summary, scanning, start, stop, error } = scan;
  const ended = snap && ENDINGS[snap.status];
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        {scanning ? (
          <button type="button" onClick={stop} className="boton bg-superficie font-medium">
            <Square size={14} aria-hidden="true" />
            Detener escaneo
          </button>
        ) : (
          <button
            type="button"
            onClick={start}
            disabled={!snap}
            title={compacto && summary?.scanned ? `Último escaneo ${timeAgo(summary.finished)}: ${fmtInt(summary.scanned_files)} archivos, ${formatBytes(summary.scanned_bytes)}` : undefined}
            className="boton-primario"
          >
            <Radar size={15} aria-hidden="true" />
            {summary?.scanned ? "Volver a escanear" : "Escanear mi equipo"}
          </button>
        )}
        {!compacto && !scanning && summary?.scanned && (
          <p className="text-sm text-tenue">
            Último escaneo {timeAgo(summary.finished)}, tardó {fmtDuration(summary.duration)}. {fmtInt(summary.scanned_files)} archivos, {formatBytes(summary.scanned_bytes)}.
          </p>
        )}
      </div>
      <AnimatePresence mode="wait">{scanning && snap && <Progreso key="vivo" snap={snap} />}</AnimatePresence>
      <Alerta className="max-w-xl">
        {(error || ended) && (
          <>
            {error || ended}
            {snap?.error && <span className="mt-1 block font-mono text-xs text-tenue">{snap.error}</span>}
          </>
        )}
      </Alerta>
    </div>
  );
}

function Progreso({ snap }: { snap: ScanSnapshot }) {
  return (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.35, ease: EASE }} className="cristal max-w-2xl rounded-md px-3 py-2">
      <p className="text-sm text-texto" aria-live="polite">
        {PHASES[snap.phase] ?? "Preparando"}
      </p>
      <dl className="mt-2 flex flex-wrap gap-x-8 gap-y-1 text-sm">
        {[
          ["Archivos", fmtInt(snap.files)],
          ["Carpetas", fmtInt(snap.dirs)],
          ["Tamaño", formatBytes(snap.bytes)],
          ...(snap.phase === "duplicados" ? [["Revisados", fmtInt(snap.hashed)]] : []),
        ].map(([k, v]) => (
          <div key={k} className="flex gap-2">
            <dt className="text-tenue">{k}</dt>
            <dd className="cifra text-acento">{v}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-2 truncate font-mono text-xs text-tenue" title={snap.current}>
        {snap.current || " "}
      </p>
    </motion.div>
  );
}
