import { useEffect, useRef, type ReactNode } from "react";
import { animate, motion, useInView } from "motion/react";

export const EASE = [0.22, 1, 0.36, 1] as const;

/** Titular que pasa de desenfocado a nítido, línea por línea. */
export function Titular({ lines, id, className = "" }: { lines: string[]; id?: string; className?: string }) {
  return (
    <motion.h1
      id={id}
      className={`titular ${className}`}
      initial="oculto"
      animate="visible"
      variants={{ visible: { transition: { staggerChildren: 0.09 } } }}
    >
      {lines.map((line) => (
        <motion.span
          key={line}
          className="block"
          variants={{
            oculto: { opacity: 0, filter: "blur(16px)", y: "0.2em" },
            visible: { opacity: 1, filter: "blur(0px)", y: 0, transition: { duration: 0.9, ease: EASE } },
          }}
        >
          {line}
        </motion.span>
      ))}
    </motion.h1>
  );
}

/** Párrafo con la línea vertical de acento. */
export function Bajada({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <motion.p
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.7, delay: 0.35, ease: EASE }}
      className={`max-w-md border-l-2 border-acento pl-4 text-base leading-relaxed text-tenue ${className}`}
    >
      {children}
    </motion.p>
  );
}

/** Cifra que cuenta desde 0 cuando entra en pantalla. */
export function CountUp({ value, format, className = "" }: { value: number; format: (n: number) => string; className?: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true });
  // El formato va en una ref: una función nueva en cada render no debe reiniciar el conteo.
  const fmt = useRef(format);
  fmt.current = format;
  useEffect(() => {
    const el = ref.current;
    if (!el || !inView) return;
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) {
      el.textContent = fmt.current(value);
      return;
    }
    const controls = animate(0, value, { duration: 1.6, ease: EASE, onUpdate: (n) => (el.textContent = fmt.current(n)) });
    return () => controls.stop();
  }, [inView, value]);
  return (
    <span ref={ref} className={`cifra ${className}`}>
      {format(0)}
    </span>
  );
}

/** Tarjeta inclinada que se endereza al pasar el cursor o recibir foco. */
export function TiltCard({ tilt, delay = 0, children, className = "" }: { tilt: number; delay?: number; children: ReactNode; className?: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 48, rotate: 0 }}
      whileInView={{ opacity: 1, y: 0, rotate: tilt }}
      whileHover={{ rotate: 0, y: -6 }}
      whileFocus={{ rotate: 0, y: -6 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ type: "spring", stiffness: 120, damping: 18, delay }}
      className={`rounded-lg bg-tarjeta p-6 text-texto ${className}`}
    >
      {children}
    </motion.div>
  );
}

/** Icono dentro de un cuadro con contorno, como en las tarjetas de la referencia. */
export function IconBox({ children }: { children: ReactNode }) {
  return <div className="grid size-11 place-items-center rounded-md border border-current/40 text-display">{children}</div>;
}
