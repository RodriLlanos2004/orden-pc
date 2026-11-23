import { lazy, Suspense, useEffect, useState } from "react";
import { Link } from "react-router";
import { motion } from "motion/react";
import { ArrowUp, Sparkles } from "lucide-react";
import { useAsistente } from "../asistente/Asistente";
import { Titular } from "../components/motion";
import { ModoEdicion, Tema } from "../components/Controles";
import { Escaneo } from "../components/Escaneo";
import { Hoja } from "../components/ui";
import { fmtInt } from "../format";
import { useOps } from "../ops";
import { PANELES, rutaPanel, usePanel } from "../paneles";
import { useApi } from "../useApi";
import { useScan } from "../useScan";
import type { Entry } from "../types";

// Remotion solo se descarga con el árbol.
const ArbolVista = lazy(() => import("../arbol/ArbolVista"));

const RESORTE = { type: "spring", stiffness: 420, damping: 34 } as const;
const EJEMPLOS = ["Busca mi currículum", "¿De qué trata la tarea de repaso?", "Resume lo que tengo de Bases de Datos", "¿Dónde guardé la práctica de Docker?", "Explícame el caso Tonnies Minis"];

/** Escribe ejemplos de preguntas, letra por letra, mientras la barra espera: así se entiende qué se puede pedir. */
function useEjemplos(activo: boolean) {
  const [texto, setTexto] = useState("");
  useEffect(() => {
    if (!activo || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let frase = 0;
    let letras = 0;
    let borrando = false;
    let t = 0;
    const paso = () => {
      const f = EJEMPLOS[frase % EJEMPLOS.length];
      letras += borrando ? -1 : 1;
      setTexto(f.slice(0, letras));
      if (!borrando && letras === f.length) {
        borrando = true;
        t = window.setTimeout(paso, 2000);
      } else if (borrando && letras === 0) {
        borrando = false;
        frase++;
        t = window.setTimeout(paso, 400);
      } else t = window.setTimeout(paso, borrando ? 22 : 45 + Math.random() * 55);
    };
    t = window.setTimeout(paso, 1400);
    return () => window.clearTimeout(t);
  }, [activo]);
  return activo ? texto : "";
}

/** Preguntar al asistente desde el escenario. Vacía, abre la conversación. Al enfocarla se ensancha. */
function Pregunta({ pausada }: { pausada: boolean }) {
  const { abrir } = useAsistente();
  const [texto, setTexto] = useState("");
  const [foco, setFoco] = useState(false);
  const ejemplo = useEjemplos(!texto && !foco && !pausada);
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        abrir({ pregunta: texto });
        setTexto("");
      }}
      onFocus={() => setFoco(true)}
      onBlur={() => setFoco(false)}
      className="cristal flex w-full max-w-md items-center gap-2 rounded-full border border-linea py-1 pr-1 pl-4 transition-[max-width,border-color,box-shadow] duration-500 ease-[var(--suave)] focus-within:max-w-xl focus-within:border-acento focus-within:shadow-[0_0_0_4px_color-mix(in_oklab,var(--amarillo)_40%,transparent)]"
    >
      <Sparkles size={15} aria-hidden="true" className={`shrink-0 text-acento transition-transform duration-500 ${foco ? "scale-125 rotate-12" : ""}`} />
      <label className="flex-1">
        <span className="sr-only">Pregunta a tus archivos: busca, identifica o explica</span>
        <input
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          placeholder={foco ? "Pregunta, busca o pide que te explique un archivo" : ejemplo ? `${ejemplo}|` : "Pregunta a tus archivos"}
          className="w-full bg-transparent py-1.5 text-sm text-texto outline-none placeholder:text-tenue"
        />
      </label>
      <button type="submit" aria-label="Preguntar" data-chispa className="bg-amarillo boton-icono size-8 rounded-full text-acento-texto hover:bg-amarillo">
        <ArrowUp size={15} aria-hidden="true" />
      </button>
    </form>
  );
}

/**
 * Las herramientas, al pie del árbol. Una píldora suave sigue al cursor entre ellas
 * y la crema se desliza hasta la que está abierta. Cada una abre su hoja encima.
 */
function Herramientas({ actual, avisos }: { actual?: string; avisos: Record<string, number> }) {
  const [sobre, setSobre] = useState<string | null>(null);
  return (
    <nav aria-label="Herramientas" onMouseLeave={() => setSobre(null)} className="cristal flex flex-wrap items-center gap-0.5 rounded-full p-1">
      {PANELES.map(({ id, label, icon: Icon }) => {
        const activa = actual === id;
        return (
          <Link
            key={id}
            to={rutaPanel(id)}
            aria-current={activa ? "page" : undefined}
            data-tip={id === "archivos" ? `${label} (Ctrl K)` : label}
            data-chispa
            onMouseEnter={() => setSobre(id)}
            onFocus={() => setSobre(id)}
            onBlur={() => setSobre(null)}
            className={`tip-angosto relative flex min-h-9 items-center rounded-full px-3.5 text-sm ${activa ? "text-acento-texto" : "text-texto"}`}
          >
            {activa && <motion.span layoutId="dock-activa" transition={RESORTE} className="bg-amarillo absolute inset-0 rounded-full" />}
            {sobre === id && !activa && <motion.span layoutId="dock-sobre" transition={RESORTE} className="absolute inset-0 rounded-full bg-amarillo-suave" />}
            <span className="relative flex items-center gap-2">
              <Icon size={15} aria-hidden="true" className={activa ? "" : "text-acento"} />
              <span className="sr-only lg:not-sr-only">{label}</span>
              {!!avisos[id] && (
                <motion.span key={avisos[id]} initial={{ scale: 0.4 }} animate={{ scale: 1 }} transition={{ type: "spring", stiffness: 500, damping: 14 }} className="rounded-full bg-amarillo px-1.5 text-[11px] font-medium text-acento-texto tabular-nums">
                  {fmtInt(avisos[id])}
                  <span className="sr-only"> pendientes</span>
                </motion.span>
              )}
            </span>
          </Link>
        );
      })}
    </nav>
  );
}

export default function Inicio() {
  const { actual, abrir, cerrar } = usePanel();
  const { cambios } = useOps();
  const scan = useScan();
  // Al terminar un escaneo o aplicar un cambio, el árbol y las cifras se vuelven a leer.
  const version = (scan.summary?.scanned ? scan.summary.finished : 0) + cambios;
  const roots = useApi<{ roots: Entry[] }>(`/api/roots?v=${version}`);
  const home = roots.data?.roots.find((r) => r.mode === "completo") ?? roots.data?.roots[0];
  const org = useApi<{ propuestas: { conflict: string | null }[] }>(home ? `/api/organizer?v=${version}` : null);
  const avisos = { ordenar: org.data?.propuestas.filter((p) => !p.conflict).length ?? 0 };

  useEffect(() => {
    document.title = actual ? `${actual.label} - Orden PC` : "Orden PC";
  }, [actual]);

  useEffect(() => {
    // Ctrl+K y no "/": un atajo de una sola tecla choca con lectores de pantalla y control por voz (WCAG 2.1.4).
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() === "k" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        abrir("archivos", { buscar: "1" });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [abrir]);

  const controles = (
    <span className="flex items-center gap-2">
      <ModoEdicion />
      <Tema />
    </span>
  );
  const pie = (
    <>
      <Pregunta pausada={!!actual} />
      <Herramientas actual={actual?.id} avisos={avisos} />
    </>
  );

  return (
    <>
      <h1 id="titulo" className="sr-only">
        Orden PC: tus carpetas
      </h1>
      {roots.data && !home ? (
        <div className="escenario flex min-h-dvh flex-col justify-between gap-12 px-6 pt-6 pb-6 lg:px-10">
          <div className="flex justify-end">{controles}</div>
          <div>
            <Titular lines={["Tu equipo,", "en orden."]} />
            <p className="mt-8 mb-6 max-w-xl text-tenue">Escanea tu equipo una vez y tus carpetas crecerán aquí como un árbol. Solo se leen: nada cambia hasta que actives el Modo edición.</p>
            <Escaneo scan={scan} />
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3">{pie}</div>
        </div>
      ) : (
        <Suspense fallback={<div className="escenario h-dvh" />}>
          <ArbolVista
            home={home?.path}
            version={version}
            onOpen={(path) => abrir("archivos", { ruta: path })}
            pausado={!!actual}
            acciones={
              <>
                <Escaneo scan={scan} compacto />
                {controles}
              </>
            }
            pie={pie}
          />
        </Suspense>
      )}

      <Hoja abierta={!!actual} clave={actual?.id} onCerrar={cerrar} titulo={actual?.label} icono={actual && <actual.icon size={16} aria-hidden="true" />} acciones={<ModoEdicion />} ancho={actual?.ancho}>
        {actual && (
          <div className={`entrada min-h-0 flex-1 ${actual.lleno ? "flex flex-col" : "overflow-y-auto px-6 pt-6 pb-8 lg:px-10"}`}>
            <Suspense fallback={<p className="p-6 text-sm text-tenue">Cargando</p>}>
              <actual.Componente />
            </Suspense>
          </div>
        )}
      </Hoja>
    </>
  );
}
