import { FolderInput, Recycle } from "lucide-react";
import { usePanel } from "../paneles";
import Organizer from "./Organizer";
import Recommendations from "./Recommendations";

const MODOS = [
  { id: "limpiar", label: "Limpiar", icon: Recycle },
  { id: "organizar", label: "Organizar", icon: FolderInput },
] as const;

/** Ordenar: limpiar lo que sobra y llevar lo suelto a su carpeta. */
export default function Ordenar() {
  const { params, abrir } = usePanel();
  const modo = params.get("ver") === "organizar" ? "organizar" : "limpiar";
  return (
    <>
      <div role="tablist" aria-label="Qué quieres ordenar" className="flex w-fit rounded-md border border-linea bg-superficie p-0.5 text-sm">
        {MODOS.map(({ id, label, icon: Icon }) => {
          const on = modo === id;
          return (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={on}
              aria-controls="panel-ordenar"
              onClick={() => abrir("ordenar", { ver: id })}
              className={`flex min-h-8 items-center gap-1.5 rounded px-3 ${on ? "bg-amarillo font-medium text-acento-texto" : "text-tenue hover:text-texto"}`}
            >
              <Icon size={14} aria-hidden="true" />
              {label}
            </button>
          );
        })}
      </div>
      <div id="panel-ordenar" role="tabpanel" aria-label={modo === "limpiar" ? "Limpiar" : "Organizar"} className="mt-6">
        {modo === "limpiar" ? <Recommendations /> : <Organizer />}
      </div>
    </>
  );
}
