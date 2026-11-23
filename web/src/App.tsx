import { useEffect } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router";
import { MotionConfig } from "motion/react";
import { AsistenteProvider } from "./asistente/Asistente";
import Inicio from "./pages/Inicio";
import { rutaPanel } from "./paneles";

// Direcciones de cuando había pestañas: siguen funcionando y abren su herramienta sobre el árbol.
const ANTES: Record<string, (search: string) => string> = {
  "/explorador": (s) => `${rutaPanel("archivos")}&${s.slice(1)}`,
  "/ordenar": (s) => `${rutaPanel("ordenar")}&${s.slice(1)}`,
  "/recomendaciones": () => rutaPanel("ordenar", { ver: "limpiar" }),
  "/organizador": () => rutaPanel("ordenar", { ver: "organizar" }),
  "/apps": () => rutaPanel("apps"),
  "/historial": () => rutaPanel("historial"),
  "/configuracion": () => rutaPanel("ajustes"),
};

/** Al presionar una tecla crema (o algo marcado con data-chispa) saltan chispas del punto exacto donde tocaste. */
function useChispas() {
  useEffect(() => {
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const alPresionar = (e: PointerEvent) => {
      const b = (e.target as Element).closest<HTMLButtonElement>(".boton-primario, .boton-peligro, [data-chispa]");
      if (!b || b.disabled) return;
      for (let i = 0; i < 9; i++) {
        const angulo = (i / 9) * Math.PI * 2 + Math.random() * 0.6;
        const lejos = 18 + Math.random() * 22;
        const c = document.createElement("span");
        c.className = "chispa";
        c.style.left = `${e.clientX}px`;
        c.style.top = `${e.clientY}px`;
        c.style.setProperty("--dx", `${Math.cos(angulo) * lejos}px`);
        c.style.setProperty("--dy", `${Math.sin(angulo) * lejos}px`);
        c.addEventListener("animationend", () => c.remove());
        document.body.append(c);
      }
    };
    document.addEventListener("pointerdown", alPresionar);
    return () => document.removeEventListener("pointerdown", alPresionar);
  }, []);
}

/** Sin barra superior: la app es el árbol y su escenario, de borde a borde. */
export default function App() {
  const location = useLocation();
  useChispas();
  return (
    <MotionConfig reducedMotion="user">
      <AsistenteProvider>
        <main id="contenido" className="outline-none">
          <Routes>
            <Route path="/" element={<Inicio />} />
            {Object.entries(ANTES).map(([path, to]) => (
              <Route key={path} path={path} element={<Navigate to={to(location.search)} replace />} />
            ))}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </AsistenteProvider>
    </MotionConfig>
  );
}
