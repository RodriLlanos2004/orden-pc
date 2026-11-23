import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Sin servidor de desarrollo con proxy: `npm run watch` recompila y el backend sirve dist/,
// así el token y el chequeo de Host funcionan igual que en uso real.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Se sirve desde 127.0.0.1: el tamaño del bundle no cruza ninguna red. Dividir no compensa.
  build: { chunkSizeWarningLimit: 1500 },
});
