import { memo, useEffect, useRef, useState, type ReactNode, type Ref } from "react";
import { Player, type PlayerRef } from "@remotion/player";
import { animate, motion, useMotionValue, useTransform } from "motion/react";
import { ArrowLeft, ChevronRight, List, Pause, Play } from "lucide-react";
import { formatBytes, fmtInt } from "../format";
import { Ambiente, VUELTA } from "./Ambiente";
import { ALTO, ANCHO, ArbolPC, DURACION, FPS, INTRO, type ArbolProps, type Lado } from "./ArbolPC";
import { useArbol, type ArbolDatos } from "./datos";

const reducido = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Rutas desde `home` hasta `path`, para la ruta de arriba y para volver con zoom. */
function camino(home: string, path: string) {
  if (!path.toLowerCase().startsWith(home.toLowerCase())) return [home];
  const out = [home];
  for (const part of path.slice(home.length).split("\\").filter(Boolean)) out.push(`${out[out.length - 1]}\\${part}`);
  return out;
}

/** Cómo arranca una escena: con su entrada desde cero, o ya armada (al volver atrás). Las dos siguen vivas después. */
type Inicio = "crecer" | "final";
/** `lado`: hacia dónde crece la rama de esta carpeta (-1 izquierda, 1 derecha, 0 arriba). */
type Capa = { path: string; data: ArbolDatos; inicio: Inicio; lado: Lado };
/** Dónde estaba la tarjeta de cada carpeta dentro de su madre (fracción del cuadro) y cuánto hay que acercarse. */
type Foco = { x: number; y: number; k: number };
type Viaje = { dir: "entrar" | "salir"; foco: Foco };

const Escena = memo(function Escena({ capa, onZoom, onOpen, playerRef, quieto }: { capa: Capa; onZoom: ArbolProps["onZoom"]; onOpen: (p: string) => void; playerRef?: Ref<PlayerRef>; quieto: boolean }) {
  const armada = capa.inicio === "final" || reducido();
  return (
    <Player
      ref={playerRef}
      component={ArbolPC}
      inputProps={{ ...capa.data, lado: capa.lado, onZoom, onOpen }}
      durationInFrames={DURACION}
      fps={FPS}
      compositionWidth={ANCHO}
      compositionHeight={ALTO}
      style={{ width: "100%", height: "100%" }}
      autoPlay={!quieto && !reducido()}
      initialFrame={armada || quieto ? INTRO : 0}
      controls={false}
      clickToPlay={false}
      doubleClickToFullscreen={false}
      spaceKeyToPlayOrPause={false}
      moveToBeginningWhenEnded={false}
    />
  );
});

/** El ambiente de fondo: un bucle que no se reinicia al cambiar de carpeta. */
const Fondo = memo(function Fondo({ playerRef }: { playerRef: Ref<PlayerRef> }) {
  return (
    <Player
      ref={playerRef}
      component={Ambiente}
      durationInFrames={VUELTA}
      fps={FPS}
      compositionWidth={ANCHO}
      compositionHeight={ALTO}
      style={{ width: "100%", height: "100%" }}
      autoPlay={!reducido()}
      loop
      controls={false}
      clickToPlay={false}
      doubleClickToFullscreen={false}
      spaceKeyToPlayOrPause={false}
    />
  );
});

const tramo = (v: number, a: number, b: number) => Math.min(Math.max((v - a) / (b - a), 0), 1);

/**
 * El árbol de circuito. Una cámara mueve dos escenas a la vez:
 * al entrar, la escena actual se acerca hacia el nodo tocado y la rama de esa carpeta sale de dentro de él;
 * al volver, la escena actual se encoge hacia su nodo y la madre se aleja hasta su tamaño.
 * El acercamiento es geométrico (k elevado al progreso): la velocidad se percibe constante, como un zoom real.
 * `pausado`: hay una hoja encima; el árbol no se ve, así que deja de animarse y no gasta.
 */
export default function ArbolVista({ home, version, onOpen, pausado, acciones, pie }: { home?: string; version: number; onOpen: (path: string) => void; pausado: boolean; acciones?: ReactNode; pie?: ReactNode }) {
  const [trail, setTrail] = useState<string[]>([]);
  const [actual, setActual] = useState<Capa | null>(null);
  const [siguiente, setSiguiente] = useState<Capa | null>(null);
  const viaje = useRef<Viaje | null>(null);
  const espera = useRef<Viaje | null>(null);
  const focos = useRef<Record<string, Foco>>({});
  const lados = useRef<Record<string, Lado>>({});
  const ladoDe = (path: string): Lado => lados.current[path.toLowerCase()] ?? 1;
  const box = useRef<HTMLDivElement>(null);
  const progreso = useMotionValue(0);

  useEffect(() => {
    if (home) setTrail(camino(home, home));
  }, [home]);

  const current = trail[trail.length - 1];
  const { data, error } = useArbol(current, home, version);

  // Llegaron los datos de la carpeta pedida: primera escena, o arranca el viaje de cámara.
  useEffect(() => {
    if (!data || !current) return;
    if (!actual || !espera.current) {
      setActual({ path: current, data, inicio: actual ? "final" : "crecer", lado: ladoDe(current) });
      return;
    }
    if (actual.path === current) return;
    const v = espera.current;
    espera.current = null;
    viaje.current = v;
    const inicio: Inicio = v.dir === "entrar" ? "crecer" : "final";
    setSiguiente({ path: current, data, inicio, lado: ladoDe(current) });
    progreso.set(0);
    animate(progreso, 1, { duration: reducido() ? 0 : 0.95, ease: [0.62, 0, 0.28, 1] }).then(() => {
      setActual({ path: current, data, inicio, lado: ladoDe(current) });
      setSiguiente(null);
      viaje.current = null;
      progreso.set(0);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, current]);

  const escala = (quien: "actual" | "siguiente") => (p: number) => {
    const v = viaje.current;
    if (!v) return 1;
    const k = v.foco.k;
    if (v.dir === "entrar") return quien === "actual" ? k ** p : k ** (p - 1);
    return quien === "actual" ? k ** -p : k ** (1 - p);
  };
  const opacidad = (quien: "actual" | "siguiente") => (p: number) => {
    const v = viaje.current;
    if (!v) return 1;
    if (v.dir === "entrar") return quien === "actual" ? 1 - tramo(p, 0.45, 0.85) : tramo(p, 0.25, 0.65);
    return quien === "actual" ? 1 - tramo(p, 0.1, 0.55) : 1;
  };
  // Paralaje: el ambiente está lejos; en el viaje solo se empuja un poco y vuelve.
  const escalaFondo = useTransform(progreso, (p) => (viaje.current ? 1 + 0.05 * Math.sin(Math.PI * p) : 1));
  const fondo = useRef<PlayerRef>(null);
  const escenas = useRef<Record<string, PlayerRef | null>>({});
  const refs = useRef(new Map<string, (pl: PlayerRef | null) => void>());
  const refDe = (path: string) => {
    if (!refs.current.has(path)) refs.current.set(path, (pl) => (escenas.current[path] = pl));
    return refs.current.get(path)!;
  };
  // Todo el movimiento continuo (árbol vivo y ambiente) se puede pausar; con movimiento reducido empieza quieto.
  const [quieto, setQuieto] = useState(reducido());
  const reproducir = (si: boolean) => [fondo.current, ...Object.values(escenas.current)].forEach((pl) => (si ? pl?.play() : pl?.pause()));
  const alternar = () => {
    reproducir(quieto);
    setQuieto(!quieto);
  };
  useEffect(() => {
    if (!quieto) reproducir(!pausado);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pausado]);
  const escalaActual = useTransform(progreso, escala("actual"));
  const escalaSiguiente = useTransform(progreso, escala("siguiente"));
  const opacidadActual = useTransform(progreso, opacidad("actual"));
  const opacidadSiguiente = useTransform(progreso, opacidad("siguiente"));

  function entrar(path: string, el: HTMLElement) {
    if (viaje.current || espera.current) return;
    const b = box.current!.getBoundingClientRect();
    const r = el.getBoundingClientRect();
    const foco = { x: (r.left + r.width / 2 - b.left) / b.width, y: (r.top + r.height / 2 - b.top) / b.height, k: Math.min(Math.max(b.width / r.width, 3), 7) };
    focos.current[path.toLowerCase()] = foco;
    // La rama de la carpeta crece hacia donde estaba su nodo: izquierda, derecha o (si estaba al centro) arriba.
    // Dentro de una rama que ya va a un lado, sus brotes siguen hacia ese mismo lado.
    const porPosicion: Lado = foco.x < 0.45 ? -1 : foco.x > 0.55 ? 1 : 0;
    const ladoActual = actual && !actual.data.inicio ? actual.lado : 0;
    lados.current[path.toLowerCase()] = ladoActual !== 0 ? ladoActual : porPosicion;
    espera.current = { dir: "entrar", foco };
    // La tarjeta tocada va a crecer varias veces: si conserva el foco, el navegador desplaza la página para seguirla.
    box.current!.focus({ preventScroll: true });
    setTrail((t) => [...t, path]);
  }
  function volver(index: number) {
    if (index < 0 || index >= trail.length - 1 || viaje.current || espera.current) return;
    // Se vuelve hacia la tarjeta de la carpeta hija por la que se entró.
    const hija = trail[index + 1];
    espera.current = { dir: "salir", foco: focos.current[hija.toLowerCase()] ?? { x: 0.5, y: 0.75, k: 5 } };
    setTrail((t) => t.slice(0, index + 1));
  }
  const atras = () => volver(trail.length - 2);

  if (error) {
    return (
      <p role="alert" className="px-6 py-10 text-sm text-error">
        No se pudo armar el árbol: {error}
      </p>
    );
  }

  const name = (p: string) => p.slice(p.lastIndexOf("\\") + 1) || p;
  const foco = viaje.current?.foco;
  const origen = foco ? `${foco.x * 100}% ${foco.y * 100}%` : "50% 50%";
  const mostrado = siguiente?.data ?? actual?.data;
  const pasar = "pointer-events-none [&_a]:pointer-events-auto [&_button]:pointer-events-auto [&_input]:pointer-events-auto [&_nav]:pointer-events-auto";
  const salir = viaje.current?.dir === "salir";
  const puedeVolver = trail.length > 1;

  const capa = (c: Capa, quien: "actual" | "siguiente") => {
    const arriba = (quien === "siguiente") !== salir;
    return (
      <motion.div
        key={c.path}
        className="absolute inset-0 overflow-hidden"
        style={{
          transformOrigin: origen,
          scale: quien === "actual" ? escalaActual : escalaSiguiente,
          opacity: quien === "actual" ? opacidadActual : opacidadSiguiente,
          zIndex: arriba ? 2 : 1,
        }}
      >
        <Escena capa={c} onZoom={entrar} onOpen={onOpen} quieto={quieto} playerRef={refDe(c.path)} />
      </motion.div>
    );
  };

  const ruta = (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
      <button type="button" onClick={atras} disabled={!puedeVolver} className="boton-primario">
        <ArrowLeft size={15} aria-hidden="true" />
        Atrás
      </button>
      <nav aria-label="Dónde estás en el árbol" className="cristal mr-auto flex min-w-0 flex-wrap items-center gap-1 rounded-md px-2 py-1 text-sm">
        {trail.map((p, i) => (
          <span key={p} className="flex items-center gap-1">
            {i > 0 && <ChevronRight size={14} aria-hidden="true" className="text-tenue" />}
            {i === trail.length - 1 ? (
              <span aria-current="location" className="font-medium text-texto">
                {name(p)}
              </span>
            ) : (
              <button type="button" onClick={() => volver(i)} className="min-h-6 rounded px-1 text-tenue hover:text-texto">
                {name(p)}
              </button>
            )}
          </span>
        ))}
      </nav>
      {current && (
        <button type="button" onClick={() => onOpen(current)} className="boton bg-superficie">
          <List size={14} aria-hidden="true" />
          Ver en la lista
        </button>
      )}
      {acciones}
    </div>
  );

  return (
    <section aria-labelledby="titulo" className="escenario relative isolate h-dvh min-h-[620px] overflow-hidden">
      {/* El lienzo cubre todo el escenario, como una foto de fondo (recorta en vez de dejar bordes). */}
      <div
        ref={box}
        tabIndex={-1}
        role="group"
        aria-label="Árbol de carpetas. Retroceso o Escape para volver atrás"
        onKeyDown={(e) => {
          if ((e.key === "Backspace" || e.key === "Escape") && puedeVolver) {
            e.preventDefault();
            atras();
          }
        }}
        className="absolute top-1/2 left-1/2 aspect-[16/9] w-[max(100%,calc(max(100dvh,620px)*16/9))] -translate-x-1/2 -translate-y-1/2 outline-none"
      >
        <motion.div className="absolute inset-0" style={{ transformOrigin: origen, scale: escalaFondo }}>
          <Fondo playerRef={fondo} />
        </motion.div>
        {!actual && (
          <p className="absolute inset-0 grid place-items-center text-sm text-tenue" aria-live="polite">
            Leyendo tus carpetas
          </p>
        )}
        {/* Un solo arreglo con clave: al terminar el viaje, la escena nueva sigue siendo la misma (no se reinicia). */}
        {[actual && capa(actual, "actual"), siguiente && capa(siguiente, "siguiente")].filter(Boolean)}
      </div>

      {/* La ruta flota sobre el escenario; solo sus controles reciben clics. */}
      <div className={`relative z-10 px-6 pt-6 lg:px-10 ${pasar}`}>{ruta}</div>

      {/* Pie del escenario: solo los controles, sin franja ni degradado encima del árbol. */}
      <div className={`absolute inset-x-0 bottom-0 z-10 pb-5 ${pasar} [&_form]:pointer-events-auto`}>
        <div className="flex flex-wrap items-center justify-between gap-3 px-6 lg:px-10">
          {pie}
          <button type="button" onClick={alternar} aria-label={quieto ? "Animar el árbol" : "Pausar la animación del árbol"} data-tip-izq className="boton-icono rounded-full border border-linea bg-superficie">
            {quieto ? <Play size={13} aria-hidden="true" /> : <Pause size={13} aria-hidden="true" />}
          </button>
        </div>
      </div>

      {/* Lo mismo en texto, para lectores de pantalla. */}
      {mostrado && (
        <p className="sr-only" aria-live="polite">
          {mostrado.raiz.name} ocupa {formatBytes(mostrado.raiz.size)}. Subcarpetas más grandes: {mostrado.ramas.map((r) => `${r.name}, ${formatBytes(r.size)}`).join("; ") || "ninguna"}.
          {mostrado.sueltos.count > 0 && ` ${fmtInt(mostrado.sueltos.count)} archivos sueltos.`}
        </p>
      )}
    </section>
  );
}
