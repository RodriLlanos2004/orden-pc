import { useMemo } from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";

/**
 * Composición de Remotion: el escenario detrás del árbol, en 1600×900. Luz y profundidad:
 * un foco cálido que respira detrás de la copa, tres haces de luz desde arriba que se balancean apenas,
 * un horizonte con bruma, un piso con rejilla en perspectiva hacia el punto de fuga, polen lejano fino y
 * bokeh cercano desenfocado (más grande y más rápido: paralaje) y un enjambre de puntos amarillo pastel
 * que cruza el fondo en corrientes. Las partículas nunca pasan por detrás del árbol ni de los controles.
 * Grises y amarillo pastel del tema.
 * Bucle de 20 s: cada movimiento completa ciclos enteros, así que al repetir no hay salto.
 */
export const ANCHO = 1600;
export const ALTO = 900;
export const FPS = 30;
export const VUELTA = 20 * FPS;

const HORIZONTE = 640;
const FUGA = { x: ANCHO / 2, y: 600 };
const TAU = Math.PI * 2;
/** Fase de un ciclo que se repite `veces` en el bucle. */
const ciclo = (frame: number, veces: number, fase = 0) => (TAU * veces * frame) / VUELTA + fase;

function semilla(n: number) {
  let h = n;
  return () => {
    h = (h * 1664525 + 1013904223) >>> 0;
    return h / 4294967296;
  };
}

/** Piso: rejilla en perspectiva que se desvanece hacia el horizonte. Estática: se dibuja una vez. */
function Piso() {
  const radiales = Array.from({ length: 23 }, (_, i) => -2200 + i * 200);
  const lineas = Array.from({ length: 9 }, (_, i) => HORIZONTE + (ALTO - HORIZONTE) * ((i + 1) / 9) ** 1.8);
  return (
    <svg width={ANCHO} height={ALTO} viewBox={`0 0 ${ANCHO} ${ALTO}`} style={{ position: "absolute", inset: 0, maskImage: "radial-gradient(ellipse 60% 45% at 50% 85%, black 20%, transparent 75%)" }} aria-hidden="true">
      {radiales.map((x) => (
        <line key={x} x1={FUGA.x} y1={FUGA.y} x2={FUGA.x + x} y2={ALTO} stroke="var(--traza-2)" strokeWidth={1} opacity={0.5} />
      ))}
      {lineas.map((y) => (
        <line key={y} x1={0} y1={y} x2={ANCHO} y2={y} stroke="var(--traza-2)" strokeWidth={1} opacity={0.45} strokeDasharray="2 7" />
      ))}
    </svg>
  );
}

/**
 * Enjambre: puntos amarillo pastel, pequeños y rápidos, que cruzan el fondo en corrientes onduladas y titilan.
 * Cada 10 s una onda de luz sale desde el pie del árbol y los aviva a su paso.
 * Todo en ciclos enteros del bucle: x da de dos a cuatro vueltas completas; la onda, dos por vuelta.
 */
const CENTRO = { x: ANCHO / 2, y: 470 };
const VIAJE = ANCHO + 40;
function Enjambre({ frame }: { frame: number }) {
  const puntos = useMemo(() => {
    const rnd = semilla(29);
    return Array.from({ length: 55 }, () => ({
      x0: rnd() * VIAJE,
      y0: 30 + rnd() * (ALTO - 60),
      vueltas: (2 + Math.floor(rnd() * 3)) * (rnd() < 0.7 ? 1 : -1),
      onda: 8 + rnd() * 26,
      fase: rnd() * TAU,
      r: 0.9 + rnd() ** 2 * 1.5,
      color: rnd() < 0.5 ? "var(--hoja-a)" : rnd() < 0.6 ? "var(--hoja-b)" : "var(--amarillo-fuerte)",
    }));
  }, []);
  // La onda de luz: un anillo que crece desde el pie del árbol, dos veces por vuelta.
  const radio = ((frame % (VUELTA / 2)) / (VUELTA / 2)) * 1150;
  return (
    <>
      {puntos.map((p, i) => {
        const x = ((((p.x0 + (p.vueltas * VIAJE * frame) / VUELTA) % VIAJE) + VIAJE) % VIAJE) - 20;
        const y = p.y0 + Math.sin(ciclo(frame, 2, p.fase + p.x0 / 260)) * p.onda;
        const brillo = Math.exp(-(((Math.hypot(x - CENTRO.x, y - CENTRO.y) - radio) / 70) ** 2));
        const titila = 0.5 + 0.5 * Math.sin(ciclo(frame, 4, p.fase * 3));
        return <circle key={i} cx={x} cy={y} r={p.r * (1 + 0.4 * brillo)} fill={p.color} opacity={Math.min(1, 0.6 + 0.3 * titila + 0.3 * brillo)} />;
      })}
    </>
  );
}

/**
 * Por dónde pueden pasar las partículas: solo el fondo. Se apagan detrás de la copa y el tronco
 * y en las franjas de arriba y abajo, donde están la ruta y las herramientas.
 */
function Mascara() {
  return (
    <>
      <linearGradient id="ambiente-franjas" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0.07" stopColor="black" />
        <stop offset="0.16" stopColor="white" />
        <stop offset="0.8" stopColor="white" />
        <stop offset="0.88" stopColor="black" />
      </linearGradient>
      <radialGradient id="ambiente-hueco">
        <stop offset="0.7" stopColor="black" />
        <stop offset="1" stopColor="black" stopOpacity={0} />
      </radialGradient>
      <mask id="ambiente-fondo" maskUnits="userSpaceOnUse" x={0} y={0} width={ANCHO} height={ALTO}>
        <rect width={ANCHO} height={ALTO} fill="url(#ambiente-franjas)" />
        <ellipse cx={ANCHO / 2} cy={350} rx={640} ry={330} fill="url(#ambiente-hueco)" />
        <ellipse cx={ANCHO / 2} cy={700} rx={260} ry={190} fill="url(#ambiente-hueco)" />
      </mask>
    </>
  );
}

export function Ambiente() {
  const frame = useCurrentFrame();
  const { lejos, cerca } = useMemo(() => {
    const rnd = semilla(11);
    return {
      lejos: Array.from({ length: 30 }, () => ({ x: rnd() * ANCHO, y0: rnd() * ALTO, sube: 1, vaiven: 6 + rnd() * 14, fase: rnd() * TAU, r: 0.6 + rnd() * 1.4, amarillo: rnd() < 0.65 })),
      cerca: Array.from({ length: 8 }, () => ({ x: rnd() * ANCHO, y0: rnd() * ALTO, sube: 2, vaiven: 20 + rnd() * 40, fase: rnd() * TAU, r: 7 + rnd() * 12 })),
    };
  }, []);
  const piso = useMemo(() => <Piso />, []);
  const respira = 0.5 + 0.5 * Math.sin(ciclo(frame, 2));
  const sube = (p: { y0: number; sube: number }) => (((p.y0 - (frame / VUELTA) * p.sube * (ALTO + 60)) % (ALTO + 60)) + (ALTO + 60)) % (ALTO + 60) - 30;

  return (
    <AbsoluteFill>
      {/* Bruma del horizonte */}
      <AbsoluteFill style={{ background: `radial-gradient(ellipse 70% 12% at 50% ${(HORIZONTE / ALTO) * 100}%, color-mix(in oklab, var(--amarillo-suave) 70%, transparent), transparent 80%)` }} />
      {piso}
      {/* Foco cálido detrás de la copa */}
      <AbsoluteFill
        style={{
          background: `radial-gradient(ellipse 34% 40% at 50% 48%, color-mix(in oklab, var(--hoja-a) ${22 + 12 * respira}%, transparent), transparent 75%)`,
        }}
      />
      {/* Haces de luz desde arriba, que se balancean apenas */}
      {[
        { x: 610, giro: -9, ancho: 360, veces: 1, fase: 0 },
        { x: 800, giro: 0, ancho: 460, veces: 1, fase: 2 },
        { x: 990, giro: 9, ancho: 360, veces: 1, fase: 4 },
      ].map((h, i) => (
        <div
          key={i}
          style={{
            position: "absolute",
            left: h.x - h.ancho / 2,
            top: -60,
            width: h.ancho,
            height: HORIZONTE + 40,
            transformOrigin: "50% 0",
            rotate: `${h.giro + 2.5 * Math.sin(ciclo(frame, h.veces, h.fase))}deg`,
            clipPath: "polygon(42% 0, 58% 0, 100% 100%, 0 100%)",
            background: "linear-gradient(to bottom, color-mix(in oklab, var(--chispa) 55%, transparent), transparent 85%)",
            filter: "blur(22px)",
            opacity: 0.35 + 0.15 * Math.sin(ciclo(frame, 2, h.fase)),
          }}
        />
      ))}
      <svg width={ANCHO} height={ALTO} viewBox={`0 0 ${ANCHO} ${ALTO}`} style={{ position: "absolute", inset: 0 }} aria-hidden="true">
        <defs>
          <Mascara />
          <radialGradient id="ambiente-bokeh">
            <stop offset="0%" stopColor="var(--hoja-a)" stopOpacity={0.55} />
            <stop offset="70%" stopColor="var(--hoja-a)" stopOpacity={0.18} />
            <stop offset="100%" stopColor="var(--hoja-a)" stopOpacity={0} />
          </radialGradient>
        </defs>
        <g mask="url(#ambiente-fondo)">
        <Enjambre frame={frame} />
        {/* Polen lejano: fino y lento */}
        {lejos.map((p, i) => {
          const y = sube(p);
          const borde = Math.max(0, Math.min(1, (y + 30) / 120, (ALTO - y) / 120));
          return <circle key={i} cx={p.x + Math.sin(ciclo(frame, 3, p.fase)) * p.vaiven} cy={y} r={p.r} fill={p.amarillo ? "var(--hoja-b)" : "var(--traza-2)"} opacity={0.6 * borde} />;
        })}
        {/* Bokeh cercano: grande, desenfocado y más rápido */}
        {cerca.map((p, i) => {
          const y = sube(p);
          const borde = Math.max(0, Math.min(1, (y + 30) / 160, (ALTO - y) / 160));
          return <circle key={i} cx={p.x + Math.sin(ciclo(frame, 2, p.fase)) * p.vaiven} cy={y} r={p.r} fill="url(#ambiente-bokeh)" opacity={0.7 * borde} />;
        })}
        </g>
      </svg>
    </AbsoluteFill>
  );
}
