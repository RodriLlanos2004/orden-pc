import { createContext, useContext, useId, useMemo } from "react";
import { AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { formatBytes, fmtPct } from "../format";
import type { ArbolDatos, Hoja } from "./datos";

/**
 * Composición de Remotion: un árbol de circuito impreso, en grises cálidos y amarillo pastel.
 *
 * Entrada (3,4 s): un pulso nace del suelo y sube por el tronco; cada pista se traza con una chispa en la punta;
 * los puntos del follaje estallan desde la punta hacia su lugar; cada nodo lanza una onda al encenderse.
 * Después, vida continua: pulsos de luz recorren las pistas como corriente, luciérnagas titilan en el follaje
 * y los halos de los nodos respiran. La estructura queda congelada al terminar la entrada: cada fotograma solo
 * calcula lo que se mueve.
 *
 * - En tu carpeta de usuario: el árbol entero.
 * - Dentro de una carpeta: una rama que entra por el lado donde estaba esa carpeta.
 *
 * Todo se genera con una semilla tomada de la ruta: la misma carpeta siempre se ve igual.
 */
/** El árbol se dibuja en 1280×610 (con margen abajo: las placas nunca se cortan) y se coloca, ampliado,
 * en la parte baja de un escenario de 1600×900; arriba queda aire para la cabecera de la página. */
const W = 1280;
const H = 610;
export const ANCHO = 1600;
export const ALTO = 900;
const ESCALA = 1.05;
export const FPS = 30;
export const INTRO = Math.round(3.4 * FPS);
/** La entrada y después una hora de vida continua (los ciclos se calculan con módulo, no hay saltos). */
export const DURACION = INTRO + 3600 * FPS;

export type Lado = -1 | 0 | 1;
export type ArbolProps = ArbolDatos & {
  lado: Lado;
  onZoom: (path: string, el: HTMLElement) => void;
  onOpen: (path: string) => void;
};

const SANS = '"Geist Variable", system-ui, sans-serif';
const MONO = '"Martian Mono Variable", ui-monospace, monospace';
const TRAZA = "var(--traza)";
const COLOR_PUNTO = ["var(--hoja-a)", "var(--hoja-b)", "var(--traza-2)"];
const out = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const suave = Easing.bezier(0.22, 1, 0.36, 1);
const rebote = Easing.bezier(0.34, 1.7, 0.64, 1);

const SUELO = 505;
const CIMA = 385;
const CX = W / 2;
const COPA = { cx: CX, cy: 222, rx: 560, ry: 205 };

// ---------------------------------------------------------------------- geometría

type Pt = [number, number];
type Punto = { x: number; y: number; r: number; c: number };
/** Una pista, su tiempo de dibujo (fotogramas), sus puntos y si lleva chispa al trazarse y pulsos después. */
type Traza = { pts: Pt[]; from: number; dur: number; ancho: number; opac: number; puntos: Punto[]; chispa?: boolean; pulso?: boolean };

const trazo = (pts: Pt[]) => "M" + pts.map((p) => `${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(" L");
const largo = (pts: Pt[]) => pts.slice(1).reduce((s, p, i) => s + Math.hypot(p[0] - pts[i][0], p[1] - pts[i][1]), 0);
function enRuta(pts: Pt[], t: number): Pt {
  let rest = largo(pts) * Math.min(Math.max(t, 0), 1);
  for (let i = 1; i < pts.length; i++) {
    const seg = Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
    if (rest <= seg) {
      const f = seg ? rest / seg : 0;
      return [pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * f, pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * f];
    }
    rest -= seg;
  }
  return pts[pts.length - 1];
}
const dentroCopa = ([x, y]: Pt, margen = 1) => ((x - COPA.cx) / COPA.rx) ** 2 + ((y - COPA.cy) / COPA.ry) ** 2 <= margen && y <= CIMA - 10;

/** Generador pseudoaleatorio con semilla: la misma ruta da siempre las mismas ramas. */
function semilla(texto: string) {
  let h = 2166136261;
  for (let i = 0; i < texto.length; i++) h = Math.imul(h ^ texto.charCodeAt(i), 16777619);
  return () => {
    h += 0x6d2b79f5;
    let t = h;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
type Rnd = () => number;

/** Ruta de circuito de `a` a `b`: tramos en diagonal de 45° alternados con tramos rectos, terminando justo en `b`. */
function zigzag(a: Pt, b: Pt, rnd: Rnd, quiebres: number): Pt[] {
  const pts: Pt[] = [a];
  let c: Pt = a;
  const empuja = (p: Pt) => {
    if (Math.hypot(p[0] - c[0], p[1] - c[1]) > 0.5) pts.push(p);
    c = p;
  };
  for (let i = 0; i < quiebres; i++) {
    const parte = Math.min(1, (0.55 + 0.8 * rnd()) / (quiebres - i + 1));
    let dx = b[0] - c[0];
    let dy = b[1] - c[1];
    const d = Math.min(Math.abs(dx), Math.abs(dy)) * parte;
    empuja([c[0] + Math.sign(dx) * d, c[1] + Math.sign(dy) * d]);
    dx = b[0] - c[0];
    dy = b[1] - c[1];
    if (Math.abs(dx) > Math.abs(dy)) empuja([c[0] + Math.sign(dx) * (Math.abs(dx) - Math.abs(dy)) * parte, c[1]]);
    else empuja([c[0], c[1] + Math.sign(dy) * (Math.abs(dy) - Math.abs(dx)) * parte]);
  }
  const dx = b[0] - c[0];
  const dy = b[1] - c[1];
  const d = Math.min(Math.abs(dx), Math.abs(dy));
  empuja([c[0] + Math.sign(dx) * d, c[1] + Math.sign(dy) * d]);
  empuja(b);
  return pts;
}

/** Nube de puntos alrededor de una punta: casi todos amarillo pastel, algunos grises. */
function nube(p: Pt, rnd: Rnd, n: number, radio: number): Punto[] {
  const color = () => (rnd() < 0.5 ? 0 : rnd() < 0.6 ? 1 : 2);
  const out: Punto[] = [{ x: p[0], y: p[1], r: 1.8 + rnd() * 2.6, c: 1 }];
  for (let j = 0; j < n; j++) {
    const ang = rnd() * Math.PI * 2;
    const dist = 3 + rnd() * radio;
    out.push({ x: p[0] + Math.cos(ang) * dist, y: p[1] + Math.sin(ang) * dist, r: 0.8 + rnd() * 2.1, c: color() });
  }
  return out;
}

/** Brotes de una pista: ramas cortas en zigzag, a veces con su propio brote, que terminan en puntos. */
function brotar(padre: Traza, rnd: Rnd, cantidad: number, rumbo: (p: Pt) => number, cabe: (p: Pt) => boolean, profundidad = 0): Traza[] {
  const out: Traza[] = [];
  for (let i = 0; i < cantidad; i++) {
    const t = 0.22 + 0.76 * ((i + rnd()) / cantidad);
    const p = enRuta(padre.pts, t);
    const ang = ((rumbo(p) + (rnd() - 0.5) * 100) * Math.PI) / 180;
    const l = (profundidad ? 18 : 34) + rnd() * (profundidad ? 34 : 70);
    let fin: Pt = [p[0] + Math.cos(ang) * l, p[1] + Math.sin(ang) * l];
    for (let k = 0; k < 4 && !cabe(fin); k++) fin = [(p[0] + fin[0]) / 2, (p[1] + fin[1]) / 2];
    if (!cabe(fin)) continue;
    const from = padre.from + t * padre.dur;
    const traza: Traza = { pts: zigzag(p, fin, rnd, 1), from, dur: (0.18 + 0.12 * rnd()) * FPS, ancho: profundidad ? 0.9 : 1.2, opac: profundidad ? 0.55 : 0.75, puntos: nube(fin, rnd, 2 + Math.floor(rnd() * (profundidad ? 5 : 8)), profundidad ? 10 : 15) };
    out.push(traza);
    if (!profundidad && rnd() < 0.55) out.push(...brotar(traza, rnd, 1 + Math.floor(rnd() * 2), rumbo, cabe, 1));
  }
  return out;
}

// ---------------------------------------------------------------------- dibujo

/** Degradado radial de la chispa: uno por escena (dos escenas conviven durante el zoom), lo usan todos los brillos. */
const Chispa = createContext("arbol-chispa");
const Defs = ({ id }: { id: string }) => (
  <defs>
    <radialGradient id={id}>
      <stop offset="0%" stopColor="var(--chispa)" stopOpacity={1} />
      <stop offset="35%" stopColor="var(--hoja-a)" stopOpacity={0.7} />
      <stop offset="100%" stopColor="var(--hoja-a)" stopOpacity={0} />
    </radialGradient>
  </defs>
);

function Brillo({ x, y, r, o = 1 }: { x: number; y: number; r: number; o?: number }) {
  const id = useContext(Chispa);
  return (
  <>
    <circle cx={x} cy={y} r={r * 3.4} fill={`url(#${id})`} opacity={o} />
    <circle cx={x} cy={y} r={r} fill="var(--chispa)" opacity={o} />
  </>
  );
}

/** La estructura ya terminada: sin animación, se dibuja una vez. */
function TrazosFijos({ trazas }: { trazas: Traza[] }) {
  return (
    <>
      {/* Sombra proyectada sobre el escenario: la luz viene de arriba a la izquierda */}
      <g transform="translate(5 9)" opacity={0.14} style={{ filter: "blur(2.5px)" }}>
        {trazas.filter((tz) => tz.ancho >= 1.2).map((tz, i) => (
          <path key={i} d={trazo(tz.pts)} fill="none" stroke="var(--display)" strokeWidth={tz.ancho + 0.8} strokeLinecap="round" strokeLinejoin="round" />
        ))}
      </g>
      {trazas.map((tz, i) => (
        <g key={i}>
          <path d={trazo(tz.pts)} fill="none" stroke={TRAZA} strokeWidth={tz.ancho} strokeLinecap="round" strokeLinejoin="round" opacity={tz.opac} />
          {tz.puntos.map((d, j) => (
            <circle key={j} cx={d.x} cy={d.y} r={d.r} fill={COLOR_PUNTO[d.c]} />
          ))}
        </g>
      ))}
    </>
  );
}

/** Durante la entrada, cada pista se traza con una chispa en la punta y sus puntos estallan al llegar. */
function Trazos({ trazas }: { trazas: Traza[] }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const fijo = useMemo(() => <TrazosFijos trazas={trazas} />, [trazas]);
  if (frame >= INTRO) return fijo;
  return (
    <>
      {trazas.map((tz, i) => {
        const p = interpolate(frame, [tz.from, tz.from + tz.dur], [0, 1], { ...out, easing: suave });
        if (p <= 0) return null;
        const fin = tz.from + tz.dur;
        const e = tz.pts[tz.pts.length - 1];
        const s = interpolate(frame, [fin - 0.05 * fps, fin + 0.4 * fps], [0, 1], { ...out, easing: rebote });
        const punta = tz.chispa && p < 1 ? enRuta(tz.pts, p) : null;
        return (
          <g key={i}>
            <path
              d={trazo(tz.pts)}
              pathLength={1}
              fill="none"
              stroke={TRAZA}
              strokeWidth={tz.ancho}
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeDasharray="1 1"
              strokeDashoffset={1 - p}
              opacity={tz.opac}
            />
            {punta && <Brillo x={punta[0]} y={punta[1]} r={2.4 + tz.ancho * 0.4} />}
            {s > 0 &&
              tz.puntos.map((d, j) => (
                <circle key={j} cx={e[0] + (d.x - e[0]) * s} cy={e[1] + (d.y - e[1]) * s} r={d.r * Math.min(1, s * 1.15)} fill={COLOR_PUNTO[d.c]} />
              ))}
          </g>
        );
      })}
    </>
  );
}

type Pulso = { pts: Pt[]; periodo: number; desfase: number };
type Luz = { x: number; y: number; r: number; periodo: number; fase: number };

/** Vida continua: pulsos que recorren las pistas y luciérnagas en el follaje. Empieza cuando termina la entrada. */
function Vida({ pulsos, luces }: { pulsos: Pulso[]; luces: Luz[] }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const f = frame - INTRO;
  const aparece = interpolate(f, [-0.3 * fps, 0.6 * fps], [0, 1], out);
  if (aparece <= 0) return null;
  return (
    <g opacity={aparece}>
      {pulsos.map((pu, i) => {
        const u = ((((f + pu.desfase) % pu.periodo) + pu.periodo) % pu.periodo) / pu.periodo;
        const t = u / 0.62; // recorre en el 62 % del ciclo y descansa el resto
        if (t > 1) return null;
        const q = enRuta(pu.pts, Easing.inOut(Easing.quad)(t));
        return <Brillo key={i} x={q[0]} y={q[1]} r={2.3} o={Math.sin(Math.PI * t) ** 0.6} />;
      })}
      {luces.map((l, i) => {
        const v = Math.max(0, Math.sin((2 * Math.PI * f) / l.periodo + l.fase)) ** 4;
        return v > 0.02 ? <Brillo key={i} x={l.x} y={l.y} r={l.r} o={v} /> : null;
      })}
    </g>
  );
}

function Nodo({ x, y, r, from, fase }: { x: number; y: number; r: number; from: number; fase: number }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: frame - from, fps, config: { damping: 11, stiffness: 170 } });
  const onda = interpolate(frame, [from, from + 0.8 * fps], [0, 1], out);
  const respira = frame > INTRO ? Math.sin((2 * Math.PI * frame) / (2.6 * fps) + fase) : 0;
  return (
    <g transform={`translate(${x} ${y})`}>
      <circle cx={4} cy={9} r={(r + 9) * s} fill="var(--display)" opacity={0.14} style={{ filter: "blur(5px)" }} />
      {onda > 0 && onda < 1 && <circle r={r + 6 + 54 * Easing.out(Easing.cubic)(onda)} fill="none" stroke="var(--hoja-b)" strokeWidth={2.5 * (1 - onda)} opacity={1 - onda} />}
      <g transform={`scale(${s})`}>
        <circle r={r + 10 + 2.5 * respira} fill="var(--amarillo)" opacity={0.55 + 0.15 * respira} />
        <circle r={r + 2} fill="var(--superficie)" />
        <circle r={r} fill="var(--amarillo-fuerte)" stroke={TRAZA} strokeWidth={1.5} />
        <circle r={r * 0.35} fill="var(--chispa)" />
      </g>
    </g>
  );
}

/** Onda en el suelo al pie del tronco: al nacer y luego cada 6 s, muy suave. */
function OndaSuelo() {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const ciclo = 6 * fps;
  const u = frame < INTRO ? frame / (1.2 * fps) : ((frame - INTRO) % ciclo) / (1.6 * fps);
  if (u >= 1) return null;
  const e = Easing.out(Easing.cubic)(u);
  return <ellipse cx={CX} cy={SUELO + 8} rx={20 + 230 * e} ry={4 + 18 * e} fill="none" stroke="var(--hoja-b)" strokeWidth={2} opacity={(frame < INTRO ? 0.8 : 0.4) * (1 - u)} />;
}

type NodoInfo = { h: Hoja; x: number; y: number; r: number; lado: Lado; from: number };

/**
 * Un nodo y su etiqueta, juntos: acercarse a cualquiera de los dos los anima a ambos (CSS `.arbol-par:hover`).
 * La etiqueta es el botón y mide lo mismo que se ve: el contorno no rodea espacio vacío.
 */
function Par({ n, onClick }: { n: NodoInfo; onClick: (e: React.MouseEvent<HTMLElement>) => void }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const o = interpolate(frame, [n.from, n.from + 0.3 * fps], [0, 1], out);
  const { x, y, r, lado, h } = n;
  const s = r + 14;
  const sube = interpolate(o, [0, 1], [6, 0]);
  // Arriba al centro no cabe encima: va centrada sobre el nodo. A los lados, crece hacia afuera desde el nodo.
  const centro = lado === 0 && y > 120;
  const pos: React.CSSProperties = centro
    ? { left: x, top: y - r - 60, translate: `-50% ${sube}px`, transformOrigin: "center bottom", textAlign: "center" }
    : lado !== -1
      ? { left: x + r + 14, top: y - 22, translate: `0 ${sube}px`, transformOrigin: "left center", textAlign: "left" }
      : { left: x - r - 14, top: y - 22, translate: `-100% ${sube}px`, transformOrigin: "right center", textAlign: "right" };
  return (
    <div className="arbol-par">
      <button type="button" tabIndex={-1} aria-hidden="true" onClick={onClick} className="arbol-nodo arbol-toque" style={{ position: "absolute", left: x - s, top: y - s, width: 2 * s, height: 2 * s }} />
      <button
        type="button"
        onClick={onClick}
        aria-label={`${h.zoom ? "Entrar en" : "Abrir en la lista"} ${h.name}, ${formatBytes(h.size)}`}
        className="arbol-nodo arbol-etiqueta"
        style={{ position: "absolute", ...pos, opacity: o }}
      >
        <span style={{ display: "block", fontSize: 15, fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {h.name}
          {h.zoom && <span className="arbol-flecha">›</span>}
        </span>
        <span style={{ display: "block", fontSize: 13, color: "var(--acento)" }}>{formatBytes(h.size)}</span>
      </button>
    </div>
  );
}

function Placa({ titulo, tamano, nota, style, from, onClick, label }: { titulo: string; tamano: number; nota: string; style: React.CSSProperties; from: number; onClick: () => void; label: string }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const o = interpolate(frame, [from, from + 0.4 * fps], [0, 1], out);
  return (
    <button type="button" onClick={onClick} aria-label={label} className="arbol-nodo arbol-placa" style={{ position: "absolute", width: 280, padding: "4px 10px", borderRadius: 10, background: "color-mix(in oklab, var(--superficie) 80%, transparent)", opacity: o, color: "var(--texto)", ...style }}>
      <span style={{ display: "block", fontFamily: MONO, fontSize: 17, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {titulo} <span style={{ fontFamily: SANS, fontWeight: 600, color: "var(--acento)" }}>{formatBytes(tamano)}</span>
      </span>
      <span style={{ display: "block", fontSize: 12, color: "var(--tenue)" }}>{nota}</span>
    </button>
  );
}

/** Pulsos y luciérnagas a partir de la estructura: siempre los mismos para la misma carpeta. */
function vida(trazas: Traza[], rnd: Rnd, fps: number) {
  const pulsos: Pulso[] = trazas.filter((t) => t.pulso).map((t) => ({ pts: t.pts, periodo: Math.round((2.4 + rnd() * 3) * fps), desfase: Math.round(rnd() * 4 * fps) }));
  const luces: Luz[] = [];
  trazas.forEach((t) =>
    t.puntos.forEach((d, j) => {
      if (j % 4 === 1 && d.c !== 2 && luces.length < 80) luces.push({ x: d.x, y: d.y, r: d.r + 0.6, periodo: Math.round((2 + rnd() * 4) * fps), fase: rnd() * Math.PI * 2 });
    }),
  );
  return { pulsos, luces };
}

// ---------------------------------------------------------------------- escenas

export function ArbolPC(props: ArbolProps) {
  return (
    <AbsoluteFill>
      <div style={{ position: "absolute", width: W, height: H, left: (ANCHO - W * ESCALA) / 2, top: ALTO - H * ESCALA - 85, transform: `scale(${ESCALA})`, transformOrigin: "0 0" }}>
        {props.inicio ? <Arbol {...props} /> : <Rama {...props} />}
      </div>
    </AbsoluteFill>
  );
}

function textoPeso(p: ArbolProps) {
  const { inicio, raiz } = p;
  const share = inicio ? (raiz.disco ? raiz.disco.used / raiz.disco.total : 0) : raiz.padre?.size ? raiz.size / raiz.padre.size : 0;
  return inicio ? (raiz.disco ? `${fmtPct(share * 100)} del disco ${raiz.disco.drive} en uso` : "") : raiz.padre ? `${fmtPct(share * 100)} de ${raiz.padre.name}` : "";
}
const resto = (p: ArbolProps) => ({ size: p.otras.size + p.sueltos.size, nota: [p.otras.count && `${p.otras.count} carpetas`, p.sueltos.count && `${p.sueltos.count} archivos`].filter(Boolean).join(" y ") });
const abrir = (p: ArbolProps, h: Hoja) => (e: React.MouseEvent<HTMLElement>) => (h.zoom ? p.onZoom(h.path, e.currentTarget) : p.onOpen(h.path));

function Lienzo({ trazas, nodos, pulsos, luces, suelo }: { trazas: Traza[]; nodos: NodoInfo[]; pulsos: Pulso[]; luces: Luz[]; suelo: boolean }) {
  const { fps } = useVideoConfig();
  const id = "chispa" + useId().replace(/:/g, "");
  return (
    <Chispa.Provider value={id}>
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} style={{ position: "absolute", inset: 0 }} aria-hidden="true">
      <Defs id={id} />
      {/* Sombra de la copa sobre el piso y sombra de contacto del tronco */}
      {suelo && <ellipse cx={CX + 20} cy={SUELO + 14} rx={430} ry={30} fill="var(--display)" opacity={0.06} style={{ filter: "blur(14px)" }} />}
      {suelo && <ellipse cx={CX + 6} cy={SUELO + 9} rx={110} ry={10} fill="var(--display)" opacity={0.2} style={{ filter: "blur(4px)" }} />}
      {suelo && <OndaSuelo />}
      <Trazos trazas={trazas} />
      <Vida pulsos={pulsos} luces={luces} />
      {nodos.map((n, i) => (
        <Nodo key={n.h.path} x={n.x} y={n.y} r={n.r} from={n.from - 0.1 * fps} fase={i * 1.3} />
      ))}
    </svg>
    </Chispa.Provider>
  );
}

/** Tu carpeta de usuario: el árbol entero. */
function Arbol(p: ArbolProps) {
  const { raiz, ramas } = p;
  const { fps } = useVideoConfig();
  const r = resto(p);

  const escena = useMemo(() => {
    const rnd = semilla(raiz.path);
    const n = ramas.length;
    const max = Math.max(...ramas.map((x) => x.size), 1);
    const trazas: Traza[] = [];

    // Tronco: siete pistas que nacen separadas del suelo y se juntan al subir. El pulso inicial sube por ellas.
    const base = [-24, -16, -8, 0, 8, 16, 24];
    const cima = base.map((b) => b * 0.45);
    base.forEach((b, i) => {
      trazas.push({ pts: [[CX + b, SUELO + 6], [CX + b, SUELO - 26], [CX + cima[i], SUELO - 26 - Math.abs(b - cima[i])], [CX + cima[i], CIMA]], from: 0.15 * fps + i * 0.025 * fps, dur: 0.6 * fps, ancho: i === 3 ? 2.6 : 1.9, opac: 1, puntos: [], chispa: true, pulso: i % 2 === 1 });
    });
    trazas.push({ pts: [[CX - 34, SUELO + 4], [CX - 34, SUELO - 34]], from: 0.2 * fps, dur: 0.25 * fps, ancho: 3, opac: 1, puntos: [] });
    trazas.push({ pts: [[CX + 33, SUELO + 4], [CX + 33, SUELO - 18]], from: 0.25 * fps, dur: 0.25 * fps, ancho: 3, opac: 1, puntos: [] });

    // Nodos en el borde de la cúpula; la carpeta más grande al centro y las demás alternadas.
    const span = [0, 100, 128, 146, 156][Math.max(n - 1, 0)];
    const lugares = Array.from({ length: n }, (_, i) => {
      const a = ((-90 - span / 2 + (n > 1 ? (i * span) / (n - 1) : span / 2)) * Math.PI) / 180;
      return [CX + 420 * Math.cos(a), 262 + 182 * Math.sin(a)] as Pt;
    });
    const orden = [...lugares.keys()].sort((a, b) => Math.abs(lugares[a][0] - CX) - Math.abs(lugares[b][0] - CX) || lugares[b][0] - lugares[a][0]);
    const rumbo = (q: Pt) => (Math.atan2(q[1] - (CIMA + 40), q[0] - CX) * 180) / Math.PI;

    const nodos: NodoInfo[] = [];
    const principales: Traza[] = [];
    ramas.forEach((h, i) => {
      const fin = lugares[orden[i]];
      const lado: Lado = fin[0] < CX - 40 ? -1 : fin[0] > CX + 40 ? 1 : 0;
      // Cada carpeta sale de una de las pistas del tronco: las de la izquierda por la izquierda.
      const inicio: Pt = [CX + (cima[3 + Math.sign(fin[0] - CX) * Math.min(3, i + 1)] ?? 0), CIMA];
      const from = 0.65 * fps + i * 0.08 * fps;
      const tz: Traza = { pts: zigzag(inicio, fin, rnd, 3), from, dur: 0.85 * fps, ancho: 1.7 + 2.2 * Math.sqrt(h.size / Math.max(raiz.size, 1)), opac: 1, puntos: [], chispa: true, pulso: true };
      principales.push(tz);
      nodos.push({ h, x: fin[0], y: fin[1], r: 6 + 8 * Math.sqrt(h.size / max), lado, from: from + tz.dur });
    });

    // Pistas decorativas que rellenan la cúpula, en abanico desde la cima del tronco.
    for (let i = 0; i < 12; i++) {
      const a = ((-172 + (164 * (i + 0.3 + rnd() * 0.4)) / 12) * Math.PI) / 180;
      const dist = 0.55 + rnd() * 0.4;
      const fin: Pt = [CX + Math.cos(a) * COPA.rx * dist * 0.92, COPA.cy + 40 + Math.sin(a) * COPA.ry * dist];
      if (!dentroCopa(fin)) continue;
      const inicio: Pt = [CX + cima[Math.floor(rnd() * cima.length)], CIMA];
      principales.push({ pts: zigzag(inicio, fin, rnd, 2), from: 0.6 * fps + rnd() * 0.5 * fps, dur: (0.6 + 0.3 * rnd()) * fps, ancho: 1.3, opac: 0.85, puntos: nube(fin, rnd, 4 + Math.floor(rnd() * 6), 14), chispa: true, pulso: rnd() < 0.5 });
    }
    trazas.push(...principales);
    for (const tz of principales) trazas.push(...brotar(tz, rnd, 3 + Math.floor(rnd() * 3), rumbo, (q) => dentroCopa(q, 1.05)));
    return { trazas, nodos, ...vida(trazas, rnd, fps) };
  }, [raiz.path, raiz.size, ramas, fps]);

  return (
    <AbsoluteFill style={{ fontFamily: SANS }}>
      <Lienzo {...escena} suelo />
      {escena.nodos.map((n) => (
        <Par key={n.h.path} n={n} onClick={abrir(p, n.h)} />
      ))}
      <Placa
        titulo={raiz.name}
        tamano={raiz.size}
        nota={textoPeso(p)}
        from={0.3 * fps}
        style={{ left: CX - 140, top: SUELO + 16, textAlign: "center" }}
        onClick={() => p.onOpen(raiz.path)}
        label={`${raiz.name}, ${formatBytes(raiz.size)}. Abrir en la lista`}
      />
      {r.size > 0 && (
        <Placa titulo="Lo demás" tamano={r.size} nota={r.nota} from={2 * fps} style={{ left: CX + 170, top: SUELO - 20, width: 230, textAlign: "left" }} onClick={() => p.onOpen(raiz.path)} label={`Lo demás: ${r.nota}, ${formatBytes(r.size)}. Abrir en la lista`} />
      )}
      {ramas.length === 0 && <div style={{ position: "absolute", left: 0, right: 0, top: 120, textAlign: "center", color: "var(--tenue)", fontSize: 15 }}>Esta carpeta no tiene subcarpetas.</div>}
    </AbsoluteFill>
  );
}

/** Dentro de una carpeta: una rama que entra por el lado de donde vino y de la que brotan sus subcarpetas. */
function Rama(p: ArbolProps) {
  const { raiz, ramas, lado } = p;
  const { fps } = useVideoConfig();
  const r = resto(p);

  const escena = useMemo(() => {
    const rnd = semilla(raiz.path + "|rama");
    const n = ramas.length;
    const max = Math.max(...ramas.map((x) => x.size), 1);
    const espejo = (q: Pt): Pt => (lado === -1 ? [W - q[0], q[1]] : q);
    // El tallo: entra desde el borde y avanza en zigzag. Hacia arriba si la carpeta estaba al centro.
    const tallo: Pt[] = lado === 0 ? zigzag([CX, H + 10], [CX + 20, 60], rnd, 4) : zigzag([-10, 470], [1080, 250], rnd, 4).map(espejo);
    const principal: Traza = { pts: tallo, from: 0, dur: 1.1 * fps, ancho: 3, opac: 1, puntos: [], chispa: true, pulso: true };
    const paralelo: Traza = { pts: tallo.map(([x, y]) => [x + (lado === 0 ? 7 : 0), y + (lado === 0 ? 0 : 7)] as Pt), from: 0.06 * fps, dur: 1.1 * fps, ancho: 1.4, opac: 0.6, puntos: [], pulso: true };
    const trazas: Traza[] = [principal, paralelo];
    const nodos: NodoInfo[] = [];
    const cabe = ([x, y]: Pt) => x > 20 && x < W - 20 && y > 30 && y < H - 30;

    ramas.forEach((h, i) => {
      const t0 = 0.2 + (0.72 * (i + 0.5)) / Math.max(n, 1);
      const a = enRuta(tallo, t0);
      const arriba = i % 2 === 0;
      const largoH = 70 + 60 * Math.sqrt(h.size / max);
      const ladoNodo: Lado = lado === 0 ? (arriba ? -1 : 1) : lado;
      const dir = lado === 0 ? ladoNodo : lado;
      let fin: Pt = lado === 0 ? [a[0] + dir * largoH, a[1] - 60] : [a[0] + dir * largoH * 0.6, a[1] + (arriba ? -1 : 1) * (70 + 30 * rnd())];
      fin = [Math.min(Math.max(fin[0], 60), W - 60), Math.min(Math.max(fin[1], 60), H - 70)];
      const from = principal.from + t0 * principal.dur;
      const tz: Traza = { pts: zigzag(a, fin, rnd, 1), from, dur: 0.5 * fps, ancho: 1.6 + 2 * Math.sqrt(h.size / Math.max(raiz.size, 1)), opac: 1, puntos: [], chispa: true, pulso: true };
      trazas.push(tz, ...brotar(tz, rnd, 2 + Math.floor(rnd() * 2), () => (arriba ? -90 : 90) + (lado === -1 ? -30 : 30), cabe));
      nodos.push({ h, x: fin[0], y: fin[1], r: 6 + 8 * Math.sqrt(h.size / max), lado: ladoNodo, from: from + tz.dur });
    });
    // Follaje a lo largo del tallo: brotes arriba y abajo.
    const rumbo = (q: Pt) => (lado === 0 ? (q[0] < CX ? -150 : -30) : rnd() < 0.5 ? -90 + (lado === -1 ? -25 : 25) : 90 + (lado === -1 ? 25 : -25));
    trazas.push(...brotar(principal, rnd, 26, rumbo, cabe));
    const punta = tallo[tallo.length - 1];
    trazas.push({ pts: [punta, punta], from: principal.dur, dur: 1, ancho: 1, opac: 1, puntos: nube(punta, rnd, 9, 18) });
    return { trazas, nodos, punta, ...vida(trazas, rnd, fps) };
  }, [raiz.path, ramas, lado, fps]);
  const { nodos, punta } = escena;

  return (
    <AbsoluteFill style={{ fontFamily: SANS }}>
      <Lienzo {...escena} suelo={false} />
      {nodos.map((n) => (
        <Par key={n.h.path} n={n} onClick={abrir(p, n.h)} />
      ))}
      {/* La carpeta en la que estás, junto a la entrada del tallo */}
      <Placa
        titulo={raiz.name}
        tamano={raiz.size}
        nota={textoPeso(p)}
        from={0.2 * fps}
        style={lado === 0 ? { left: CX + 40, top: 500, textAlign: "left" } : lado === 1 ? { left: 24, top: 492, textAlign: "left" } : { left: W - 24 - 280, top: 492, textAlign: "right" }}
        onClick={() => p.onOpen(raiz.path)}
        label={`${raiz.name}, ${formatBytes(raiz.size)}. Abrir en la lista`}
      />
      {r.size > 0 && (
        <Placa
          titulo="Lo demás"
          tamano={r.size}
          nota={r.nota}
          from={1.2 * fps}
          style={lado === 0 ? { left: punta[0] + 30, top: punta[1] - 10, width: 220, textAlign: "left" } : lado === 1 ? { left: Math.min(punta[0] - 40, W - 220), top: punta[1] - 78, width: 200, textAlign: "left" } : { left: Math.max(punta[0] - 160, 20), top: punta[1] - 78, width: 200, textAlign: "right" }}
          onClick={() => p.onOpen(raiz.path)}
          label={`Lo demás: ${r.nota}, ${formatBytes(r.size)}. Abrir en la lista`}
        />
      )}
      {ramas.length === 0 && <div style={{ position: "absolute", left: 0, right: 0, top: 120, textAlign: "center", color: "var(--tenue)", fontSize: 15 }}>Esta carpeta no tiene subcarpetas.</div>}
    </AbsoluteFill>
  );
}
