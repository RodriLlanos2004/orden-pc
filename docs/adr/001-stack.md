# ADR-001: Stack de la aplicación

**Estado:** Aceptado
**Fecha:** 2026-10-08
**Decide:** Rodri

## Contexto

Orden PC es una herramienta local, para un solo usuario, que lee y modifica archivos reales en Windows 11. Rodri trabaja principalmente en Python con uv. Requisitos clave: arrancar con un solo comando, abrir en el navegador, interfaz rica (tablas grandes, treemap, gráficas) y acceso a APIs de Windows (registro, atributos de OneDrive, Papelera).

## Decisión

- Backend: Python 3.12 + FastAPI + uvicorn, gestionado con uv.
- Índice: SQLite (WAL, FTS5 con tokenizer trigram).
- Frontend: React + TypeScript + Vite + Tailwind v4, servido como estáticos por el mismo proceso.
- Arranque: `uv run orden-pc` compila la interfaz si falta o está desactualizada, escucha en `127.0.0.1:8765` y abre el navegador.
- Desarrollo: `npm run watch` en `web/` recompila; no se usa el servidor de desarrollo de Vite con proxy, para que token y chequeo de Host se comporten igual que en uso real.

## Opciones consideradas

### A: FastAPI + navegador (elegida)
| Dimensión | Evaluación |
|---|---|
| Complejidad | Baja: un proceso, un lenguaje para la lógica nativa |
| Costo | Ninguno; todo ya instalado |
| Familiaridad | Alta: stack principal de Rodri |

**Pros:** registro (`winreg`), atributos (`os.stat`), Papelera (`send2trash`, pywin32) y git por subprocess, todo en Python. Pruebas con pytest.
**Contras:** expone un puerto local; se mitiga en ADR-002.

### B: Tauri
**Pros:** binario pequeño, ventana nativa.
**Contras:** exige toolchain de Rust y obliga a escribir la capa nativa en Rust o a llamar a Python como sidecar, lo que suma un segundo proceso igual.

### C: Electron
**Pros:** ventana nativa, ecosistema grande.
**Contras:** unos 150 MB extra y un runtime Node con acceso total al disco: más superficie de ataque, no menos. La lógica nativa tendría que pasar a Node o seguir en Python como proceso aparte.

## Consecuencias

- Más fácil: una sola base de código de backend, pruebas en pytest, cero toolchains nuevas.
- Más difícil: la seguridad del puerto local es responsabilidad nuestra (ADR-002).
- Revisar si algún día se quiere distribuir a otras personas como instalador.
