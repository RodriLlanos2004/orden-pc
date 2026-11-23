import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { ArrowUp, BookOpen, Copy, FileText, FolderTree, Loader2, RotateCcw, ShieldCheck, Sparkles } from "lucide-react";
import { api, token } from "../api";
import { Alerta, Hoja } from "../components/ui";
import { fmtInt, timeAgo } from "../format";
import { rutaPanel } from "../paneles";

/**
 * El asistente de tus archivos: un panel lateral de conversación, como un cuaderno de notas sobre tus documentos.
 * Solo sabe lo que dicen tus archivos (el servidor le pasa al modelo los fragmentos encontrados) y cita cada dato.
 * El modelo corre en tu PC con Ollama.
 */

type Fuente = { n: number; path: string; nombre: string; extracto: string | null; trozo: number | null };
type Mensaje = { rol: "usuario" | "asistente"; texto: string; fuentes?: Fuente[]; error?: string; pendiente?: boolean };
type Lectura = { estado: string; total: number; hechos: number; leidos: number; trozos: number; omitidos: number; actual: string; error: string | null };
type Estado = {
  ollama: boolean;
  modelo: string;
  modelo_listo: boolean;
  indice: { archivos: number; con_texto: number; trozos: number; leido: number | null };
  lectura: Lectura;
};
type Abrir = { pregunta?: string; archivo?: { path: string; nombre: string } };

const Ctx = createContext<{ abrir: (o?: Abrir) => void }>({ abrir: () => {} });
export const useAsistente = () => useContext(Ctx);

const SUGERENCIAS = ["¿Qué entregas tengo de Calidad de Software?", "Busca mi currículum", "¿De qué trata la tarea HW07?", "Resume lo que tengo del programa Genera"];
const carpeta = (p: string) => p.slice(0, p.lastIndexOf("\\"));

/** Texto del asistente con formato mínimo: párrafos, viñetas, **negritas** y citas [n] como botones. */
function Respuesta({ texto, onCita }: { texto: string; onCita: (n: number) => void }) {
  const linea = (l: string, key: number) =>
    l.split(/(\[\d+\]|\*\*[^*]+\*\*)/g).map((parte, i) => {
      const cita = parte.match(/^\[(\d+)\]$/);
      if (cita)
        return (
          <button
            key={`${key}-${i}`}
            type="button"
            onClick={() => onCita(Number(cita[1]))}
            aria-label={`Ver la fuente ${cita[1]}`}
            className="mx-0.5 inline-grid h-5 min-w-5 place-items-center rounded-full bg-amarillo-suave px-1 align-text-top text-[11px] font-semibold text-acento hover:bg-amarillo"
          >
            {cita[1]}
          </button>
        );
      if (parte.startsWith("**") && parte.endsWith("**")) return <strong key={`${key}-${i}`}>{parte.slice(2, -2)}</strong>;
      return parte;
    });
  const bloques = texto.split(/\n{2,}/);
  return (
    <div className="space-y-2 text-sm leading-relaxed">
      {bloques.map((b, i) => {
        const filas = b.split("\n");
        if (filas.every((f) => /^\s*([-*•]|\d+\.)\s/.test(f) || !f.trim()))
          return (
            <ul key={i} className="list-disc space-y-1 pl-5">
              {filas.filter((f) => f.trim()).map((f, j) => (
                <li key={j}>{linea(f.replace(/^\s*([-*•]|\d+\.)\s/, ""), i * 100 + j)}</li>
              ))}
            </ul>
          );
        return <p key={i}>{linea(b, i)}</p>;
      })}
    </div>
  );
}

function Comando({ texto }: { texto: string }) {
  const [copiado, setCopiado] = useState(false);
  return (
    <div className="mt-2 flex items-center gap-2 rounded-md bg-fondo px-3 py-2 font-mono text-xs">
      <span className="flex-1 select-all">{texto}</span>
      <button
        type="button"
        onClick={() => navigator.clipboard.writeText(texto).then(() => setCopiado(true))}
        aria-label={`Copiar ${texto}`}
        data-tip-izq className="boton-icono size-7"
      >
        <Copy size={13} aria-hidden="true" />
      </button>
      <span aria-live="polite" className="sr-only">
        {copiado ? "Copiado" : ""}
      </span>
    </div>
  );
}

/** Lo que falta para poder preguntar: Ollama, el modelo y que el asistente haya leído tus documentos. */
function Preparacion({ e, onComprobar, onPreparar, onDetener }: { e: Estado; onComprobar: () => void; onPreparar: () => void; onDetener: () => void }) {
  const leyendo = e.lectura.estado === "leyendo";
  // Las dos tarjetas son independientes: puedes leer tus documentos mientras se instala Ollama.
  return (
    <>
      {(!e.ollama || !e.modelo_listo) && (
      <div className="bg-superficie rounded-lg border border-linea p-4 text-sm">
        <p className="font-medium text-texto">{e.ollama ? `Falta descargar el modelo ${e.modelo}` : "Falta Ollama, el programa que corre el modelo en tu PC"}</p>
        <p className="mt-1 text-tenue">Todo se queda en tu equipo: tus archivos no salen. Ejecuta en una terminal:</p>
        {!e.ollama && <Comando texto="winget install Ollama.Ollama" />}
        <Comando texto={`ollama pull ${e.modelo}`} />
        <button type="button" onClick={onComprobar} className="boton mt-3">
          <RotateCcw size={13} aria-hidden="true" />
          Comprobar de nuevo
        </button>
      </div>
      )}
      {(leyendo || e.indice.con_texto === 0) && (
      <div className="bg-superficie rounded-lg border border-linea p-4 text-sm">
        <p className="flex items-center gap-2 font-medium text-texto">
          <BookOpen size={15} aria-hidden="true" className="text-acento" />
          {leyendo ? "Leyendo tus documentos" : "Primero tengo que leer tus documentos"}
        </p>
        <p className="mt-1 text-tenue">
          PDF, Word, PowerPoint, Excel, texto y código de tus carpetas. Guardo el texto solo en tu PC. Nunca abro archivos que están solo en la nube ni carpetas protegidas.
        </p>
        {leyendo ? (
          <div className="mt-3" aria-live="polite">
            <div className="h-1.5 overflow-hidden rounded-full bg-superficie-2">
              <div className="bg-amarillo-fuerte h-full rounded-full transition-[width]" style={{ width: `${(e.lectura.hechos / Math.max(e.lectura.total, 1)) * 100}%` }} />
            </div>
            <p className="mt-2 text-xs text-tenue">
              {fmtInt(e.lectura.hechos)} de {fmtInt(e.lectura.total)} archivos. <span className="break-all">{e.lectura.actual.split("\\").pop()}</span>
            </p>
            <button type="button" onClick={onDetener} className="mt-2 text-xs text-tenue underline decoration-linea underline-offset-4 hover:text-texto">
              Detener
            </button>
          </div>
        ) : (
          <button type="button" onClick={onPreparar} className="boton-primario mt-3">
            <BookOpen size={14} aria-hidden="true" />
            Preparar
          </button>
        )}
        <Alerta className="mt-2">{e.lectura.error}</Alerta>
      </div>
      )}
    </>
  );
}

export function AsistenteProvider({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate();
  const [abierto, setAbierto] = useState(false);
  const [mensajes, setMensajes] = useState<Mensaje[]>([]);
  const [estado, setEstado] = useState<Estado | null>(null);
  const [texto, setTexto] = useState("");
  const [resaltada, setResaltada] = useState<string | null>(null);
  const lista = useRef<HTMLDivElement>(null);
  const entrada = useRef<HTMLTextAreaElement>(null);
  const pendiente = mensajes.some((m) => m.pendiente);

  const comprobar = useCallback(() => {
    api<Estado>("/api/asistente/estado").then(setEstado).catch(() => setEstado(null));
  }, []);

  // Mientras lee, el avance se consulta cada segundo.
  useEffect(() => {
    if (!abierto) return;
    comprobar();
    if (estado?.lectura.estado !== "leyendo") return;
    const t = setInterval(comprobar, 1000);
    return () => clearInterval(t);
  }, [abierto, estado?.lectura.estado, comprobar]);

  useEffect(() => {
    lista.current?.scrollTo({ top: lista.current.scrollHeight, behavior: "smooth" });
  }, [mensajes]);

  const enviar = useCallback(
    async (pregunta: string, archivo?: { path: string; nombre: string }) => {
      const historial = mensajes.filter((m) => !m.pendiente && !m.error).map((m) => ({ rol: m.rol, texto: m.texto }));
      setMensajes((ms) => [...ms, { rol: "usuario", texto: pregunta || `Explícame ${archivo?.nombre}` }, { rol: "asistente", texto: "", pendiente: true }]);
      const actualizar = (f: (m: Mensaje) => Mensaje) => setMensajes((ms) => [...ms.slice(0, -1), f(ms[ms.length - 1])]);
      try {
        const r = await fetch("/api/asistente/preguntar", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-Orden-Token": token },
          body: JSON.stringify({ pregunta, historial, archivo: archivo?.path ?? null }),
        });
        if (!r.ok || !r.body) {
          const cuerpo = await r.json().catch(() => ({}));
          throw new Error(cuerpo.detail ?? `El servidor respondió con el código ${r.status}.`);
        }
        const lector = r.body.getReader();
        const dec = new TextDecoder();
        let resto = "";
        for (;;) {
          const { value, done } = await lector.read();
          if (done) break;
          resto += dec.decode(value, { stream: true });
          const partes = resto.split("\n\n");
          resto = partes.pop() ?? "";
          for (const p of partes) {
            if (!p.startsWith("data: ")) continue;
            const ev = JSON.parse(p.slice(6));
            if (ev.tipo === "fuentes") actualizar((m) => ({ ...m, fuentes: ev.fuentes }));
            else if (ev.tipo === "texto") actualizar((m) => ({ ...m, texto: m.texto + ev.texto }));
            else if (ev.tipo === "error") actualizar((m) => ({ ...m, error: ev.texto }));
          }
        }
        actualizar((m) => ({ ...m, pendiente: false }));
      } catch (e) {
        actualizar((m) => ({ ...m, pendiente: false, error: (e as Error).message }));
      }
    },
    [mensajes],
  );

  const abrir = useCallback(
    (o?: Abrir) => {
      setAbierto(true);
      if (o?.pregunta?.trim() || o?.archivo) enviar(o.pregunta?.trim() ?? "", o.archivo);
      else setTimeout(() => entrada.current?.focus(), 250);
    },
    [enviar],
  );

  const listo = estado && estado.ollama && estado.modelo_listo && estado.indice.con_texto > 0 && estado.lectura.estado !== "leyendo";
  const preparar = () => api("/api/asistente/preparar", { method: "POST" }).then(comprobar).catch(comprobar);
  const detener = () => api("/api/asistente/preparar/detener", { method: "POST" }).then(comprobar).catch(comprobar);
  const mandar = () => {
    if (!texto.trim() || pendiente) return;
    enviar(texto.trim());
    setTexto("");
  };
  const verFuente = (f: Fuente) => {
    navigate(rutaPanel("archivos", { ruta: carpeta(f.path) }));
    setAbierto(false);
  };

  return (
    <Ctx.Provider value={{ abrir }}>
      {children}
      <Hoja
        abierta={abierto}
        onCerrar={() => setAbierto(false)}
        fondo={false}
        ancho="w-[min(30rem,100vw)]"
        icono={<Sparkles size={16} aria-hidden="true" />}
        titulo="Pregúntale a tus archivos"
        subtitulo={
          <span className="flex items-center gap-1.5">
            <ShieldCheck size={12} aria-hidden="true" />
            Solo sabe lo que dicen tus documentos. Corre en tu PC{estado ? ` con ${estado.modelo}` : ""}.
          </span>
        }
        acciones={
          mensajes.length > 0 && (
            <button type="button" onClick={() => setMensajes([])} disabled={pendiente} aria-label="Nueva conversación" data-tip-abajo data-tip-izq className="boton-icono">
              <RotateCcw size={15} aria-hidden="true" />
            </button>
          )
        }
      >
            <div ref={lista} className="flex-1 space-y-5 overflow-y-auto px-5 py-5">
              {estado && <Preparacion e={estado} onComprobar={comprobar} onPreparar={preparar} onDetener={detener} />}
              {listo && mensajes.length === 0 && (
                <div>
                  <p className="text-sm text-tenue">
                    Leí {fmtInt(estado!.indice.con_texto)} documentos{estado!.indice.leido ? ` (${timeAgo(estado!.indice.leido)})` : ""}. Puedes preguntar, pedirme que busque un archivo o que te explique uno.
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {SUGERENCIAS.map((s) => (
                      <button key={s} type="button" onClick={() => enviar(s)} className="rounded-full border border-linea px-3 py-1.5 text-left text-sm text-texto hover:border-acento">
                        {s}
                      </button>
                    ))}
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      navigate(rutaPanel("ordenar", { ver: "organizar", sugerir: "1" }));
                      setAbierto(false);
                    }}
                    className="boton-primario mt-4"
                  >
                    <FolderTree size={14} aria-hidden="true" />
                    Sugiere cómo ordenar mis documentos
                  </button>
                  <button type="button" onClick={preparar} className="mt-4 block text-xs text-tenue underline decoration-linea underline-offset-4 hover:text-texto">
                    Volver a leer mis documentos
                  </button>
                </div>
              )}
              {mensajes.map((m, i) =>
                m.rol === "usuario" ? (
                  <p key={i} className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-md bg-amarillo-suave px-4 py-2 text-sm text-texto">
                    {m.texto}
                  </p>
                ) : (
                  <div key={i} className="max-w-full">
                    {m.texto ? (
                      <Respuesta texto={m.texto} onCita={(n) => setResaltada(`${i}-${n}`)} />
                    ) : m.pendiente ? (
                      <p className="flex items-center gap-2 text-sm text-tenue" aria-live="polite">
                        <Loader2 size={14} aria-hidden="true" className="animate-spin motion-reduce:animate-none" />
                        {m.fuentes
                          ? `Leyendo ${m.fuentes.length} ${m.fuentes.length === 1 ? "fragmento" : "fragmentos"} de tus archivos. La primera respuesta tarda hasta dos minutos mientras el modelo carga.`
                          : "Buscando en tus archivos"}
                      </p>
                    ) : null}
                    <Alerta className="mt-2">{m.error}</Alerta>
                    {!!m.fuentes?.length && (
                      <details open={!m.pendiente && m.fuentes.length <= 3} className="mt-3">
                        <summary className="cursor-pointer text-xs text-tenue">Fuentes ({m.fuentes.length})</summary>
                        <ol className="mt-2 space-y-2">
                          {m.fuentes.map((f) => (
                            <li key={f.n}>
                              <button
                                type="button"
                                onClick={() => verFuente(f)}
                                className={`w-full rounded-md border px-3 py-2 text-left text-xs transition-colors ${resaltada === `${i}-${f.n}` ? "border-acento bg-amarillo-suave" : "border-linea hover:border-tenue"}`}
                              >
                                <span className="flex items-center gap-2">
                                  <span className="grid size-5 shrink-0 place-items-center rounded-full bg-amarillo-suave text-[11px] font-semibold text-acento">{f.n}</span>
                                  <FileText size={13} aria-hidden="true" className="shrink-0 text-tenue" />
                                  <span className="truncate font-medium text-texto">{f.nombre}</span>
                                </span>
                                <span className="mt-1 block truncate text-tenue">{carpeta(f.path)}</span>
                                {f.extracto && <span className="mt-1 line-clamp-2 block text-texto/80">{f.extracto}</span>}
                              </button>
                            </li>
                          ))}
                        </ol>
                      </details>
                    )}
                  </div>
                ),
              )}
            </div>

            <form
              onSubmit={(e) => {
                e.preventDefault();
                mandar();
              }}
              className="border-t border-linea p-4"
            >
              <label className="bg-fondo flex items-end gap-2 rounded-xl border border-linea p-2 focus-within:border-acento">
                <span className="sr-only">Tu pregunta</span>
                <textarea
                  ref={entrada}
                  rows={1}
                  value={texto}
                  onChange={(e) => setTexto(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      mandar();
                    }
                  }}
                  placeholder="Pregunta, busca o pide que te explique un archivo"
                  className="max-h-40 min-h-9 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm text-texto outline-none placeholder:text-tenue/80 [field-sizing:content] disabled:opacity-60"
                />
                <button type="submit" disabled={pendiente || !texto.trim()} aria-label="Enviar pregunta" className="bg-amarillo grid size-9 shrink-0 place-items-center rounded-lg text-acento-texto disabled:opacity-40 disabled:shadow-none">
                  <ArrowUp size={16} aria-hidden="true" />
                </button>
              </label>
            </form>
      </Hoja>
    </Ctx.Provider>
  );
}
