import { useCallback, useEffect, useId, useRef, useState, type FormEvent, type ReactNode, type Ref } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Search, X } from "lucide-react";
import { CountUp, EASE } from "./motion";
import { fmtInt } from "../format";

/** Piezas que se repetían en todas las pantallas: acciones con error, avisos, diálogos, hojas, cifras. */

/** Corre una acción: `ocupado` mientras dura y su error como texto. Devuelve si salió bien. */
export function useAccion() {
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState("");
  const correr = useCallback(async (fn: () => Promise<unknown>) => {
    setOcupado(true);
    setError("");
    try {
      await fn();
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    } finally {
      setOcupado(false);
    }
  }, []);
  return { ocupado, error, setError, correr };
}

export function Alerta({ children, className = "" }: { children?: ReactNode; className?: string }) {
  if (!children) return null;
  return (
    <p role="alert" className={`text-sm text-error ${className}`}>
      {children}
    </p>
  );
}

export function Vacio({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <p className={`rounded-lg border border-dashed border-linea px-5 py-6 text-sm text-tenue ${className}`}>{children}</p>;
}

/** Casilla con estado intermedio (para "todas"). */
export function Casilla({ checked, mixed, onChange, label }: { checked: boolean; mixed?: boolean; onChange: (v: boolean) => void; label?: string }) {
  return (
    <input
      type="checkbox"
      checked={checked}
      ref={(el) => {
        if (el) el.indeterminate = !!mixed;
      }}
      onChange={(e) => onChange(e.target.checked)}
      aria-label={label}
      className="size-6 shrink-0 cursor-pointer accent-[var(--acento)]"
    />
  );
}

/** Cifras grandes que cuentan desde cero. */
export function Cifras({ items }: { items: { label: string; value: number; format?: (n: number) => string }[] }) {
  return (
    <dl className="flex flex-wrap gap-x-12 gap-y-6">
      {items.map((s) => (
        <div key={s.label} className="flex flex-col-reverse gap-1.5">
          <dt className="text-sm text-tenue">{s.label}</dt>
          <dd className="cifra text-[clamp(2.25rem,4.5vw,3.5rem)] text-acento">
            <CountUp value={s.value} format={s.format ?? fmtInt} />
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function Seccion({ titulo, descripcion, acciones, children, className = "" }: { titulo: ReactNode; descripcion?: ReactNode; acciones?: ReactNode; children: ReactNode; className?: string }) {
  const id = useId();
  return (
    <section aria-labelledby={id} className={className}>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 id={id} className="flex items-center gap-3 font-mono text-lg text-display">
            {titulo}
          </h2>
          {descripcion && <p className="mt-2 max-w-2xl text-sm text-tenue">{descripcion}</p>}
        </div>
        {acciones && <div className="flex flex-wrap gap-2">{acciones}</div>}
      </div>
      <div className="mt-6">{children}</div>
    </section>
  );
}

export function Selector({ label, value, options, onChange }: { label: string; value: string; options: string[][]; onChange: (v: string) => void }) {
  return (
    <label className="flex items-center">
      <span className="sr-only">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={`rounded-md border bg-superficie px-2.5 py-1.5 text-sm ${value ? "border-acento text-texto" : "border-linea text-tenue"}`}
      >
        {options.map(([v, l]) => (
          <option key={v} value={v}>
            {l}
          </option>
        ))}
      </select>
    </label>
  );
}

export function Buscador({ value, onChange, label, placeholder, className = "w-64", inputRef, autoFocus }: {
  value: string;
  onChange: (v: string) => void;
  label: string;
  placeholder: string;
  className?: string;
  inputRef?: Ref<HTMLInputElement>;
  autoFocus?: boolean;
}) {
  return (
    <label className={`relative block ${className}`}>
      <span className="sr-only">{label}</span>
      <Search size={14} aria-hidden="true" className="absolute top-1/2 left-3 -translate-y-1/2 text-tenue" />
      <input
        ref={inputRef}
        autoFocus={autoFocus}
        type="text"
        inputMode="search"
        enterKeyHint="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => e.key === "Escape" && value && (e.stopPropagation(), onChange(""))}
        placeholder={placeholder}
        className="campo-busqueda w-full rounded-md border border-linea bg-superficie py-2 pr-9 pl-8 text-sm text-texto placeholder:text-tenue/80 focus:border-acento"
      />
      {value && (
        <button type="button" onClick={() => onChange("")} aria-label="Borrar búsqueda" className="absolute top-1/2 right-1.5 -translate-y-1/2 rounded p-1 text-tenue hover:text-texto">
          <X size={14} aria-hidden="true" />
        </button>
      )}
    </label>
  );
}

/** "Mostrar N más" al final de una lista larga. */
export function MasFilas({ restantes, pagina, onMas }: { restantes: number; pagina: number; onMas: () => void }) {
  if (restantes <= 0) return null;
  return (
    <li className="border-t border-linea py-3">
      <button type="button" onClick={onMas} className="enlace text-sm">
        Mostrar {fmtInt(Math.min(pagina, restantes))} más de {fmtInt(restantes)} restantes
      </button>
    </li>
  );
}

/** Barra que sube desde abajo con lo elegido y la acción que lo aplica. Se pega al pie de la hoja que la contiene. */
export function BarraAccion({ visible, texto, detalle, children }: { visible: boolean; texto: ReactNode; detalle: ReactNode; children: ReactNode }) {
  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ y: 80, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: 80, opacity: 0 }}
          transition={{ duration: 0.4, ease: EASE }}
          className="sticky bottom-4 z-10 mt-8 flex flex-wrap items-center gap-4 rounded-lg border border-acento/50 bg-superficie px-5 py-4 shadow-2xl"
        >
          <div className="mr-auto">
            <p aria-live="polite" className="text-sm text-texto">
              {texto}
            </p>
            <p className="mt-1 text-xs text-tenue">{detalle}</p>
          </div>
          {children}
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/** Botón que cierra el diálogo que lo contiene (sin JavaScript: `formmethod="dialog"`). */
export function BotonCerrar({ children = "Cerrar", primario = false, autoFocus }: { children?: ReactNode; primario?: boolean; autoFocus?: boolean }) {
  return (
    <button type="submit" formMethod="dialog" formNoValidate autoFocus={autoFocus} className={primario ? "boton-primario" : "boton"}>
      {children}
    </button>
  );
}

/**
 * Diálogo modal nativo (`showModal`: foco atrapado, Escape y fondo inerte sin código propio).
 * Encabezado, cuerpo con desplazamiento, error y pie con Cancelar y la acción.
 * `onSubmit` corre al confirmar; si no lanza, el diálogo se cierra (salvo que devuelva `false`).
 */
export function Dialogo({ titulo, antetitulo, descripcion, ancho = "w-[min(40rem,calc(100vw-2rem))]", onClose, onSubmit, confirmar, peligro, deshabilitado, enfoque, pie, pieIzq, error, children }: {
  titulo: ReactNode;
  antetitulo?: ReactNode;
  descripcion?: ReactNode;
  ancho?: string;
  onClose: () => void;
  onSubmit?: () => unknown;
  confirmar?: ReactNode;
  peligro?: boolean;
  deshabilitado?: boolean;
  enfoque?: "cancelar" | "confirmar";
  pie?: ReactNode;
  pieIzq?: ReactNode;
  error?: string;
  children?: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const id = useId();
  const accion = useAccion();
  useEffect(() => {
    ref.current?.showModal();
  }, []);

  async function enviar(e: FormEvent<HTMLFormElement>) {
    if ((e.nativeEvent as SubmitEvent).submitter?.getAttribute("formmethod") === "dialog") return; // lo cierra el navegador
    e.preventDefault();
    if (!onSubmit) return;
    let seguir = false;
    if ((await accion.correr(async () => (seguir = (await onSubmit()) === false))) && !seguir) ref.current?.close();
  }

  return (
    <dialog ref={ref} onClose={onClose} aria-labelledby={id} className={`m-auto max-h-[88vh] overflow-hidden rounded-lg border border-linea bg-superficie p-0 text-texto backdrop:bg-[#2a2824]/55 ${ancho}`}>
      <form onSubmit={enviar} className="flex max-h-[88vh] flex-col">
        <div className="border-b border-linea px-6 py-5">
          {antetitulo && <p className="mb-1 text-xs text-tenue">{antetitulo}</p>}
          <h2 id={id} className="font-mono text-lg text-display">
            {titulo}
          </h2>
          {descripcion && <div className="mt-1 text-sm text-tenue">{descripcion}</div>}
        </div>
        {children && <div className="min-h-0 flex-1 overflow-auto px-6 py-4 text-sm">{children}</div>}
        <Alerta className="px-6 pb-2">{error || accion.error}</Alerta>
        <div className="flex flex-wrap items-center justify-end gap-3 border-t border-linea px-6 py-4">
          {pieIzq && <div className="mr-auto text-sm">{pieIzq}</div>}
          {pie ?? (
            <>
              <BotonCerrar autoFocus={enfoque === "cancelar"}>Cancelar</BotonCerrar>
              {confirmar && (
                <button type="submit" autoFocus={enfoque === "confirmar"} disabled={accion.ocupado || deshabilitado} className={peligro ? "boton-peligro" : "boton-primario"}>
                  {confirmar}
                </button>
              )}
            </>
          )}
        </div>
      </form>
    </dialog>
  );
}

/**
 * Hoja lateral que se abre sobre el árbol: así trabaja cada herramienta sin salir de la pantalla principal.
 * No es modal a propósito: se puede seguir usando el Modo edición de su cabecera y el árbol a su izquierda.
 * Escape la cierra; el foco entra al abrirla y vuelve a donde estaba al cerrarla.
 */
export function Hoja({ abierta, clave, onCerrar, titulo, subtitulo, icono, acciones, ancho = "w-[min(76rem,calc(100vw-1.5rem))]", fondo = true, children }: {
  abierta: boolean;
  clave?: string;
  onCerrar: () => void;
  titulo: ReactNode;
  subtitulo?: ReactNode;
  icono?: ReactNode;
  acciones?: ReactNode;
  ancho?: string;
  fondo?: boolean;
  children: ReactNode;
}) {
  const ref = useRef<HTMLElement>(null);
  const id = useId();
  useEffect(() => {
    if (!abierta) return;
    const antes = document.activeElement as HTMLElement | null;
    const raf = requestAnimationFrame(() => ref.current?.focus({ preventScroll: true }));
    return () => {
      cancelAnimationFrame(raf);
      antes?.focus?.({ preventScroll: true });
    };
  }, [abierta, clave]);

  return (
    <AnimatePresence>
      {abierta && fondo && (
        <motion.div
          key="velo"
          aria-hidden="true"
          onClick={onCerrar}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-30"
        />
      )}
      {abierta && (
        <motion.aside
          key={clave ?? "hoja"}
          ref={ref}
          tabIndex={-1}
          role="dialog"
          aria-modal="false"
          aria-labelledby={id}
          onKeyDown={(e) => {
            // Escape dentro de un diálogo modal lo cierra ese diálogo, no la hoja.
            if (e.key !== "Escape" || (e.target as Element).closest("dialog")) return;
            e.stopPropagation();
            onCerrar();
          }}
          initial={{ x: "100%" }}
          animate={{ x: 0 }}
          exit={{ x: "100%" }}
          transition={{ duration: 0.45, ease: EASE }}
          className={`bg-superficie fixed inset-y-0 right-0 z-40 flex max-w-full flex-col border-l border-linea shadow-[-30px_0_60px_-30px_rgb(42_40_36_/_0.45)] outline-none ${ancho}`}
        >
          <header className="flex items-center gap-3 border-b border-linea px-6 py-3.5">
            {icono && <span className="bg-amarillo grid size-9 shrink-0 place-items-center rounded-full text-acento-texto">{icono}</span>}
            <div className="min-w-0 flex-1">
              <h2 id={id} className="font-mono text-lg text-display">
                {titulo}
              </h2>
              {subtitulo && <div className="mt-0.5 text-xs text-tenue">{subtitulo}</div>}
            </div>
            {acciones}
            <button type="button" onClick={onCerrar} aria-label="Cerrar (Escape)" data-tip-abajo data-tip-izq className="boton-icono">
              <X size={16} aria-hidden="true" />
            </button>
          </header>
          {children}
        </motion.aside>
      )}
    </AnimatePresence>
  );
}
