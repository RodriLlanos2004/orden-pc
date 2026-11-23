import { useState } from "react";
import FolderTree from "./FolderTree";
import { Dialogo } from "./ui";
import type { Entry } from "../types";

const BAD = /[<>:"/\\|?*\x00-\x1f]/;
const RESERVED = /^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?$/i;

/** Misma validación que el servidor, para avisar mientras escribes. El servidor vuelve a validar. */
export function nameProblem(name: string): string {
  if (!name) return "Escribe un nombre.";
  if (name !== name.trim()) return "El nombre no puede empezar ni terminar con espacios.";
  if (BAD.test(name)) return 'El nombre no puede llevar estos caracteres: < > : " / \\ | ? *';
  if (name.endsWith(".")) return "El nombre no puede terminar en punto.";
  if (RESERVED.test(name)) return `«${name}» es un nombre reservado por Windows.`;
  if (name.length > 200) return "El nombre es demasiado largo (máximo 200 caracteres).";
  return "";
}

export function NameDialog({ title, initial, hint, onSubmit, onClose }: {
  title: string;
  initial: string;
  hint?: string;
  onSubmit: (name: string) => void;
  onClose: () => void;
}) {
  const [name, setName] = useState(initial);
  const [touched, setTouched] = useState(false);
  const problem = nameProblem(name);

  return (
    <Dialogo
      titulo={title}
      descripcion={hint}
      ancho="w-[min(32rem,calc(100vw-2rem))]"
      onClose={onClose}
      confirmar="Ver vista previa"
      deshabilitado={touched && !!problem}
      onSubmit={() => {
        setTouched(true);
        if (problem) return false;
        onSubmit(name);
      }}
    >
      <label htmlFor="nombre" className="block text-xs text-tenue">
        Nombre
      </label>
      <input
        id="nombre"
        autoFocus
        value={name}
        // Selecciona el nombre sin la extensión, como el Explorador de Windows.
        onFocus={(e) => {
          const dot = initial.lastIndexOf(".");
          if (!touched) e.target.setSelectionRange(0, dot > 0 ? dot : initial.length);
        }}
        onChange={(e) => (setName(e.target.value), setTouched(true))}
        aria-invalid={touched && !!problem}
        aria-describedby="nombre-error"
        className="campo mt-1 aria-[invalid=true]:border-error"
      />
      <p id="nombre-error" role={touched && problem ? "alert" : undefined} className="mt-2 min-h-5 text-xs text-error">
        {touched ? problem : ""}
      </p>
    </Dialogo>
  );
}

export function MoveDialog({ roots, count, start, onSubmit, onClose }: {
  roots: Entry[];
  count: number;
  start: string;
  onSubmit: (dest: string) => void;
  onClose: () => void;
}) {
  const [dest, setDest] = useState(start);
  return (
    <Dialogo
      titulo={`Mover ${count === 1 ? "1 elemento" : `${count} elementos`}`}
      descripcion="Elige la carpeta de destino. Antes de mover verás exactamente qué cambia."
      onClose={onClose}
      confirmar="Ver vista previa"
      onSubmit={() => onSubmit(dest)}
      pieIzq={
        <p className="max-w-64 truncate font-mono text-xs text-tenue" title={dest}>
          Destino: {dest}
        </p>
      }
    >
      <div className="-mx-6 -my-4 h-80">
        <FolderTree roots={roots} current={dest} onOpen={setDest} label="Carpeta de destino" />
      </div>
    </Dialogo>
  );
}
