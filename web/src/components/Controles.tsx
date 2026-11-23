import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Lock, Moon, Pencil, Sun } from "lucide-react";
import { useOps } from "../ops";

const RESORTE = { type: "spring", stiffness: 520, damping: 30 } as const;

/**
 * Interruptor del Modo edición: una palanca con perilla que se desliza, como en un tablero.
 * Va sobre el escenario y en la cabecera de cada hoja: siempre a mano.
 */
export function ModoEdicion() {
  const { editMode: on, setEditMode, editError } = useOps();
  return (
    <span className="flex items-center gap-3">
      {editError && (
        <span role="alert" className="max-w-56 text-xs text-error">
          {editError}
        </span>
      )}
      <button
        type="button"
        role="switch"
        aria-checked={!!on}
        disabled={on === null}
        onClick={() => setEditMode(!on)}
        data-chispa
        className={`boton gap-2.5 pr-2 ${on ? "border-acento bg-amarillo-suave text-texto" : "bg-superficie text-tenue hover:text-texto"}`}
      >
        Modo edición
        <span className="sr-only">{on ? "activado: los cambios se aplican a tus archivos reales" : "apagado: solo lectura"}</span>
        <span aria-hidden="true" className={`flex h-5 w-9 items-center rounded-full p-0.5 transition-colors ${on ? "justify-end bg-amarillo-fuerte" : "justify-start bg-superficie-2"}`}>
          <motion.span layout transition={RESORTE} className="grid size-4 place-items-center rounded-full bg-superficie shadow-[0_1px_3px_rgb(42_40_36/0.35)]">
            <AnimatePresence mode="popLayout" initial={false}>
              <motion.span key={on ? "si" : "no"} initial={{ scale: 0, rotate: -90 }} animate={{ scale: 1, rotate: 0 }} exit={{ scale: 0, rotate: 90 }} transition={RESORTE} className="grid place-items-center">
                {on ? <Pencil size={9} className="text-acento" /> : <Lock size={9} className="text-tenue" />}
              </motion.span>
            </AnimatePresence>
          </motion.span>
        </span>
      </button>
      <span aria-live="polite" className="sr-only">
        {on ? "Modo edición activado" : ""}
      </span>
    </span>
  );
}

/** Tema claro u oscuro: el sol se hunde girando y sale la luna (y al revés). */
export function Tema() {
  const [tema, setTema] = useState(() => document.documentElement.dataset.theme ?? "light");
  useEffect(() => {
    document.documentElement.dataset.theme = tema;
    try {
      localStorage.setItem("tema-crema", tema);
    } catch {
      /* sin almacenamiento: el tema dura lo que la pestaña */
    }
  }, [tema]);
  const oscuro = tema === "dark";
  return (
    <button
      type="button"
      onClick={() => setTema(oscuro ? "light" : "dark")}
      aria-label={`Cambiar a tema ${oscuro ? "claro" : "oscuro"}`}
      data-tip={oscuro ? "Tema claro" : "Tema oscuro"}
      data-tip-abajo
      data-tip-izq
      className="boton-icono size-9 border border-linea bg-superficie"
    >
      {/* El recorte va adentro: la ayuda del botón tiene que poder salir de él. */}
      <span className="grid size-full place-items-center overflow-hidden rounded-md">
      <AnimatePresence mode="popLayout" initial={false}>
        <motion.span
          key={tema}
          initial={{ y: 22, rotate: -90, opacity: 0 }}
          animate={{ y: 0, rotate: 0, opacity: 1 }}
          exit={{ y: -22, rotate: 90, opacity: 0 }}
          transition={RESORTE}
          className="grid place-items-center"
        >
          {oscuro ? <Sun size={17} aria-hidden="true" /> : <Moon size={17} aria-hidden="true" />}
        </motion.span>
      </AnimatePresence>
      </span>
    </button>
  );
}
