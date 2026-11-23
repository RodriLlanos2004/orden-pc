import { motion } from "motion/react";
import { EASE } from "./motion";
import { formatBytes, fmtPct } from "../format";

export type Categories = {
  drive: string;
  total: number;
  used: number;
  free: number;
  categories: { key: string; label: string; bytes: number }[];
};

const HINTS: Record<string, string> = {
  juegos: "Carpetas de Riot, Epic, Steam y Xbox",
  desarrollo: "Proyectos de código y carpetas ocultas de herramientas (.docker, .cache)",
  documentos: "PDF, Word, Excel, PowerPoint y texto en tus carpetas",
  multimedia: "Fotos, video y audio en tus carpetas",
  apps: "Program Files y AppData",
  sistema: "Windows, ProgramData y archivos de memoria virtual",
  otros: "Todo lo demás, incluido lo que Windows no deja leer",
};

/**
 * Magnitud por categoría: una barra por fila, todas del mismo amarillo, medidas contra el disco completo.
 * La identidad la da la etiqueta de la fila, no el color (una paleta categórica solo de amarillos no se
 * distingue con daltonismo; ver docs/design-system.md).
 */
export default function CategoryBar({ data }: { data: Categories }) {
  const rows = [...data.categories.filter((c) => c.bytes > 0).sort((a, b) => b.bytes - a.bytes), { key: "libre", label: "Libre", bytes: data.free }];
  return (
    <table className="w-full text-sm">
      <caption className="sr-only">Uso del disco {data.drive} por categoría</caption>
      <thead>
        <tr className="text-left text-xs text-tenue">
          <th scope="col" className="pb-3 font-normal">Categoría</th>
          <th scope="col" className="hidden w-[42%] pb-3 font-normal sm:table-cell">
            <span className="sr-only">Proporción del disco</span>
          </th>
          <th scope="col" className="pb-3 text-right font-normal">Tamaño</th>
          <th scope="col" className="pb-3 text-right font-normal">Del disco</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((c, i) => {
          const pct = (c.bytes / data.total) * 100;
          const free = c.key === "libre";
          return (
            <tr key={c.key} className="border-t border-linea">
              <th scope="row" className="w-[32%] py-3 pr-4 text-left align-top font-normal">
                <span className={free ? "text-tenue" : "text-texto"}>{c.label}</span>
                {HINTS[c.key] && <span className="block text-xs text-tenue">{HINTS[c.key]}</span>}
              </th>
              <td className="hidden py-3 pr-6 align-middle sm:table-cell" aria-hidden="true">
                <div className="h-2.5 w-full rounded-r-[4px] bg-superficie-2">
                  <motion.div
                    className={`h-full origin-left rounded-r-[4px] ${free ? "border border-dashed border-tenue/60 bg-transparent" : "bg-amarillo-fuerte"}`}
                    style={{ width: `${Math.max(pct, 0.4)}%` }}
                    initial={{ scaleX: 0 }}
                    whileInView={{ scaleX: 1 }}
                    viewport={{ once: true }}
                    transition={{ duration: 0.9, delay: i * 0.07, ease: EASE }}
                  />
                </div>
              </td>
              <td className="py-3 text-right align-top tabular-nums text-texto">{formatBytes(c.bytes)}</td>
              <td className="py-3 pl-4 text-right align-top tabular-nums text-tenue">{fmtPct(pct)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
