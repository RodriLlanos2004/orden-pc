# Orden PC

Organizador local de archivos y apps para Windows 11. Corre en tu navegador en `http://127.0.0.1:8765` y no sale de tu equipo: el servidor solo escucha en `127.0.0.1`.

Qué hace: escanea tus discos, muestra qué ocupa espacio, recomienda qué eliminar y por qué, ordena tus archivos con reglas, gestiona tus apps y guarda un historial de cada cambio para deshacerlo.

## Instalar

Necesitas, una sola vez:

- [uv](https://docs.astral.sh/uv/) (instala Python 3.12 si no lo tienes)
- [Node.js](https://nodejs.org/) 20 o más reciente, para compilar la interfaz
- Git y winget (vienen con Windows 11 o ya los tienes)

Luego, en la carpeta del proyecto:

```bash
uv sync
```

## Ejecutar

```bash
uv run orden-pc
```

La primera vez instala las dependencias de la interfaz y la compila (tarda un minuto); después arranca al instante y abre el navegador. Si el puerto 8765 está ocupado, usa otro libre; la consola muestra la dirección. Para cerrar la app, cierra la terminal o pulsa Ctrl+C en ella.

Primer uso:

1. En la pantalla del árbol, pulsa "Escanear mi equipo". El primer escaneo completo tarda unos minutos; los siguientes solo revisan lo que cambió.
2. Recorre tu árbol. Al pie están las herramientas (Archivos, Ordenar, Apps, Disco, Historial, Ajustes): cada una se abre encima del árbol. Todo es solo lectura hasta que activas "Modo edición" arriba a la derecha.
3. Con el Modo edición activo, cada cambio muestra una vista previa exacta y pide confirmación. El Modo edición se apaga solo al cerrar la app.

## Asistente: pregúntale a tus archivos

Un asistente que solo sabe lo que dicen tus documentos: busca, identifica y explica tus archivos, y cita de dónde sacó cada dato. Corre entero en tu PC con [Ollama](https://ollama.com); tus archivos no salen de tu equipo. Instálalo una vez:

```bash
winget install Ollama.Ollama
```

```bash
ollama pull qwen2.5:7b
```

Después, escribe en la barra "Pregunta a tus archivos" al pie del árbol (o déjala vacía y pulsa la flecha) y luego "Preparar": lee el texto de tus PDF, Word, PowerPoint, Excel, texto y código (nunca AppData, carpetas protegidas, ocultas ni archivos solo en la nube) y lo guarda en la base de datos local. Sin Ollama la búsqueda igual te muestra los archivos que coinciden. Para usar otro modelo, cambia el ajuste `asistente_modelo`.

**Que el asistente sugiera cómo ordenar.** En Ordenar → Organizar → Por clasificar, pulsa "Que el asistente sugiera". Lee cada documento suelto y propone su carpeta dentro de tu estructura, con un motivo: respeta la materia que el documento declara, manda tu trabajo a Entregas con nombre `AAAA-MM-DD_Materia_Tema_v1`, deja quieto lo que no da evidencia clara y te avisa si tus documentos mencionan una materia que tu estructura no tiene. Nada se mueve hasta que revisas la vista previa y confirmas con el Modo edición activo. La lógica sigue el método PARA de Tiago Forte, Johnny.Decimal y las guías de nombres de bibliotecas universitarias (Princeton, Iowa State, UBC).

## Cómo te protege

- Nada se borra para siempre: eliminar es enviar a la Papelera, y si algo no cabe en ella, Orden PC no lo envía.
- Toda acción de escritura pasa por una vista previa y una confirmación, y queda en el Historial. Mover, renombrar y crear se deshacen desde ahí; lo enviado a la Papelera se restaura desde ahí.
- Nunca toca `C:\Windows`, `Program Files`, `ProgramData`, `AppData`, el interior de un `.git`, carpetas del sistema ni la raíz de un disco. Puedes agregar más rutas protegidas en Configuración; ninguna se puede quitar.
- No lee ni descarga archivos de OneDrive que están solo en la nube.
- Antes de mover un repo con cambios sin commit, te avisa.
- Instalar, actualizar o desinstalar apps siempre abre la ventana oficial; tú terminas el proceso ahí.

El detalle está en [docs/adr/002-modelo-de-seguridad.md](docs/adr/002-modelo-de-seguridad.md).

## Respaldar la base de datos

Todo lo que Orden PC sabe (índice, etiquetas, notas, reglas, estructura, historial) vive en un solo archivo:

```
%LOCALAPPDATA%\OrdenPC\orden.db
```

Para respaldarlo, cualquiera de estas dos:

- **Con la app abierta:** Configuración (el engranaje de arriba a la derecha), sección "Base de datos", botón "Crear copia ahora". Guarda una copia consistente en `%LOCALAPPDATA%\OrdenPC\respaldos\orden-AAAAMMDD-HHMMSS.db`.
- **Con la app cerrada:** copia `orden.db` a donde quieras. Si junto a él ves `orden.db-wal` y `orden.db-shm`, cópialos también.

Para restaurar: cierra Orden PC, reemplaza `orden.db` por la copia (renómbrala a `orden.db`) y borra `orden.db-wal` y `orden.db-shm` si existen. Vuelve a abrir la app.

El índice se puede reconstruir siempre con un escaneo; lo que no se reconstruye son tus etiquetas, notas, reglas y el historial, así que eso es lo que vale la pena respaldar.

Para usar otra ubicación, define la variable de entorno `ORDEN_PC_DB` con la ruta completa del archivo antes de arrancar.

## Pruebas

```bash
uv run pytest
```

Las pruebas trabajan solo en carpetas temporales (`pytest-tmp/`, se borra al terminar bien), con una Papelera simulada, y fallan si algo intenta tocar tus carpetas reales, ejecutar winget o abrir un desinstalador. Una prueba opcional hace ida y vuelta con la Papelera real usando un archivo temporal:

```bash
uv run pytest -m papelera_real
```

## Desarrollo

- Interfaz: `npm run watch` dentro de `web/` recompila al guardar; recarga el navegador.
- `ORDEN_PC_NO_BROWSER=1` evita que el servidor abra una pestaña nueva al arrancar.
- Stack: Python 3.12 + FastAPI + SQLite (FTS5) en el servidor; React + TypeScript + Vite + Tailwind + Recharts en la interfaz.

Documentación: [decisiones de arquitectura](docs/adr/), [sistema de diseño](docs/design-system.md), [estrategia de pruebas](docs/testing-strategy.md).
