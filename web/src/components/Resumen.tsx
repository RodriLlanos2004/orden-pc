import { Link } from "react-router";
import { Download, FolderGit2, GitBranch, Recycle, type LucideIcon } from "lucide-react";
import CategoryBar, { type Categories } from "./CategoryBar";
import { IconBox, TiltCard } from "./motion";
import { Cifras, Seccion } from "./ui";
import { formatBytes, fmtInt, fmtPct, toGB } from "../format";
import { useOps } from "../ops";
import { rutaPanel } from "../paneles";
import { useApi } from "../useApi";
import type { Summary } from "../useScan";

/** El disco en cifras y lo que necesita orden. Se abre como herramienta desde el pie del árbol. */

type Cards = {
  downloads: { path: string; items: number; bytes: number };
  code: { places: { name: string; projects: number }[]; dirty: string[] };
};
type RecSummary = { summary: { total: number; count: number } };

function Pendientes({ cards, recs }: { cards: Cards; recs: RecSummary | null }) {
  const dirty = cards.code.dirty;
  const items: { icon: LucideIcon; title: string; value: string; body: string; to?: string; link?: string; tilt: number }[] = [
    {
      icon: Download,
      title: "Sueltos en Descargas",
      value: fmtInt(cards.downloads.items),
      body: `${formatBytes(cards.downloads.bytes)} sin ordenar.`,
      to: rutaPanel("ordenar", { ver: "organizar" }),
      link: "Darles carpeta",
      tilt: -2,
    },
    {
      icon: Recycle,
      title: "Espacio recuperable",
      value: recs ? `${toGB(recs.summary.total).toLocaleString("es-MX", { maximumFractionDigits: 1 })} GB` : "Calculando",
      body: recs ? `${fmtInt(recs.summary.count)} recomendaciones; tú decides cuáles aceptar.` : "Revisando instaladores, copias y archivos viejos.",
      to: rutaPanel("ordenar", { ver: "limpiar" }),
      link: "Revisar qué eliminar",
      tilt: 1.5,
    },
    {
      icon: dirty.length ? GitBranch : FolderGit2,
      title: dirty.length ? "Repos con cambios" : "Código",
      value: dirty.length ? fmtInt(dirty.length) : `${fmtInt(cards.code.places.length)} lugares`,
      body: dirty.length ? `${dirty.map((p) => p.split("\\").pop()).join(", ")}: haz commit antes de moverlos.` : cards.code.places.map((p) => p.name).join(", ") || "Sin proyectos detectados.",
      tilt: -1,
    },
  ];
  return (
    <div className="grid gap-6 md:grid-cols-3">
      {items.map(({ icon: Icon, title, value, body, to, link, tilt }, i) => (
        <TiltCard key={title} tilt={tilt} delay={i * 0.07}>
          <IconBox>
            <Icon size={18} aria-hidden="true" />
          </IconBox>
          <h3 className="mt-5 font-mono text-base">{title}</h3>
          <p className="cifra mt-2 text-3xl text-acento">{value}</p>
          <p className="mt-2 text-sm leading-relaxed text-texto/80">{body}</p>
          {to && (
            <Link to={to} className="enlace mt-3 text-sm">
              {link}
            </Link>
          )}
        </TiltCard>
      ))}
    </div>
  );
}

export default function Resumen() {
  const { cambios } = useOps();
  const summary = useApi<Summary>("/api/summary");
  const v = `${summary.data?.scanned ? summary.data.finished : 0}-${cambios}`;
  const scanned = summary.data?.scanned === true;
  const cats = useApi<Categories>(scanned ? `/api/insights/categories?v=${v}` : null);
  const cards = useApi<Cards>(scanned ? `/api/insights/cards?v=${v}` : null);
  const recs = useApi<RecSummary>(scanned ? `/api/recommendations?v=${v}` : null);
  const c = cats.data;
  if (summary.data && !scanned) return <p className="text-tenue">Escanea tu equipo desde el árbol para ver tu disco en cifras.</p>;
  return (
    <div className="flex flex-col gap-14">
      <Seccion titulo={`Tu disco ${c?.drive ?? "C:"}`}>
        {c && (
          <>
            <Cifras
              items={[
                { label: "GB usados", value: toGB(c.used) },
                { label: "GB libres", value: toGB(c.free) },
                { label: "ocupado", value: (c.used / c.total) * 100, format: fmtPct },
              ]}
            />
            <div className="mt-8">
              <CategoryBar data={c} />
            </div>
          </>
        )}
      </Seccion>
      <Seccion titulo="Lo que necesita orden">{cards.data && <Pendientes cards={cards.data} recs={recs.data} />}</Seccion>
    </div>
  );
}
