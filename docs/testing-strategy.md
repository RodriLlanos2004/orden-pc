# Estrategia de pruebas

Objetivo: demostrar que la app **no puede** borrar de forma permanente ni tocar rutas protegidas, y que todo lo que escribe queda auditado y se puede revertir. La velocidad de las pruebas importa menos que su honestidad.

Comando único: `uv run pytest`.

## Regla de oro

Las pruebas solo tocan carpetas creadas en `tmp_path`. Como el Temp de Windows vive dentro de `AppData` (ruta protegida), pytest usa `--basetemp=pytest-tmp` dentro del proyecto. Un fixture `autouse` en `tests/conftest.py`:
- apunta `ORDEN_PC_DB` a `tmp_path` (hecho);
- hace fallar cualquier prueba que intente usar las raíces de escaneo reales (`scanner.default_roots`) (hecho);
- desde el hito 5: envuelve el módulo `ops` y falla si recibe una ruta fuera de `tmp_path`, y sustituye `send2trash` por un doble que mueve a `tmp_path/papelera`.

Una sola prueba marcada `@pytest.mark.papelera_real` usa la Papelera de Windows con un archivo temporal y lo restaura (valida ADR-003). Se excluye por defecto y se corre con `uv run pytest -m papelera_real`.

## Pirámide

| Nivel | Qué | Herramienta |
|---|---|---|
| Unidad (mayoría) | `safety`, reglas de recomendación, motor del organizador, renombrado, categorías de apps, parseo de winget | pytest puro |
| Integración | API HTTP con `TestClient`, escáner sobre árboles sintéticos, SQLite real en `tmp_path`, plan y aplicar y deshacer de punta a punta | pytest + TestClient |
| Código fuente | Sin llamadas de borrado permanente, sin guiones largos en la interfaz | pytest leyendo archivos |
| Interfaz | Lógica no trivial (formato de tamaños, textos de confirmación) | Vitest, solo donde haya lógica |
| Manual guiado | Cada pantalla en claro, oscuro, tablet y solo teclado | Navegador integrado al cerrar cada hito |

Sin pruebas E2E automatizadas por ahora: el costo de mantenerlas supera su valor en una app de una sola persona. Se reconsidera si el hito 5 muestra regresiones en flujos de varios pasos.

## Áreas críticas y casos

### Seguridad del servidor (hito 1, hecho)
- Host ajeno, vacío o con otro puerto: 400.
- Escritura sin token, con token incorrecto o con Origin ajeno: 403 y el estado no cambia.
- Ruta que escribe con modo edición apagado: 403.
- Modo edición arranca apagado y no sobrevive a un proceso nuevo.
- Token distinto por proceso, al menos 40 caracteres, presente en el HTML servido.
- El servidor se levanta en `127.0.0.1`.

### Validación de rutas (hito 2, hecho: `tests/test_safety.py`)
Cada caso debe ser rechazado por `safety.resolve_target`:
- `..` que escapa de la raíz, separadores mezclados `/` y `\`.
- `\\?\C:\Windows`, `\\servidor\recurso`, `C:\Windows` en mayúsculas o minúsculas.
- Nombre corto 8.3 (`C:\PROGRA~1`).
- Flujo alterno `archivo.txt:oculto`.
- Puntos o espacios finales (`carpeta.`, `carpeta `).
- Junction dentro de `tmp_path` que apunta a una ruta protegida.
- Raíz de disco (`C:\`), cualquier ruta dentro de `.git`, `AppData`, `$Recycle.Bin`.
- La configuración puede agregar rutas protegidas pero no quitar las de fábrica.

### Escáner (hito 2, hecho: `tests/test_scanner.py`)
- Árbol sintético con tamaños conocidos: totales exactos por carpeta y raíz.
- Archivo con atributo `RECALL_ON_DATA_ACCESS` simulado: nunca se abre ni se calcula su hash (doble de `open`).
- `node_modules` y `.git` se suman como un nodo, sin filas por archivo.
- Reescaneo: lo que no cambió conserva su fila y su hash; lo cambiado pierde el hash; lo eliminado sale del índice con todo su contenido.
- Un cambio profundo dentro de una carpeta sumada (juego que se actualiza) se refleja aunque la fecha de la carpeta no cambie.
- Junctions no se siguen; la raíz de usuario anidada dentro de `C:\` no se borra al recorrer el disco.
- Git: rama y cambios sobre un repo real en `tmp_path`, y `.git/index` no cambia tras `git status`.
- Proyectos en `AppData` o carpetas ocultas no cuentan.
- Duplicados: tamaño, luego hash parcial, luego completo; tamaños únicos ni se abren.
- Migración del esquema 1 al 2 conserva filas y búsqueda.
- Dos inicios seguidos lanzan un solo escaneo.

### Panel y Explorador (hito 3, hecho: `tests/test_insights.py`)
- Un disco en miniatura (juegos, Program Files con un juego de Epic adentro, Windows, archivos sueltos en la raíz, AppData, carpeta oculta, proyectos anidados, Descargas) con categorías exactas: nada se cuenta dos veces.
- Tarjetas: elementos en Descargas, duplicados solo dentro de tus carpetas (los de AppData no cuentan), lugares con código.
- Línea de tiempo: semanas completas, archivos nuevos solo fuera de AppData y carpetas ocultas.
- API: raíces, hijos con "archivos sueltos", listado con cada filtro y orden, parámetros inválidos con 422, ruta fuera del índice con 404 (no se sondea el disco), detalles con propietario, copias y proyecto, etiquetas y notas que exigen token y no tocan el archivo.
- Al terminar en verde, `pytest-tmp` se borra; las pruebas quitan sus junctions antes.

### Recomendaciones (hito 4, hecho: `tests/test_recommend.py`)
- Una carpeta de usuario sintética con un caso positivo y uno negativo por regla:
  - **instaladores:** otra versión, instaladores en carpetas ocultas, y GitHub Desktop que no se confunde con Git;
  - **copias exactas:** se conserva la que está en la estructura, la que no tiene marca de copia, y los gemelos dentro de un proyecto no se tocan;
  - **por nombre:** sin original no hay recomendación;
  - **regenerables:** solo en proyectos inactivos;
  - **zip:** al 50 % no basta;
  - **capturas y grandes:** recientes contra antiguos.
- Cada ruta aparece una sola vez, con la regla de mayor prioridad. Nada de AppData, carpetas ocultas ni proyectos.
- Si OneDrive liberó un archivo después del escaneo, ni el instalador ni el zip se abren (comprobación en vivo).
- Reglas desactivadas no producen resultados; umbrales y validación de ajustes con mensajes claros.
- API: analizar y marcar no cambian ningún archivo (se compara el árbol completo antes y después); marcar exige token; rutas fuera del índice dan 404.
- Calibración con datos reales: la regla de instaladores encontró los mismos 8 instaladores (1,15 GB) de la auditoría previa.

### Escritura, auditoría y deshacer (hito 5, hecho: `tests/test_ops.py`)
- Papelera simulada en `tmp_path` para todas las pruebas, y un guardián que falla si `ops` toca algo fuera de la carpeta de la prueba.
- Aplicar exige token y modo edición; un plan se usa una sola vez y caduca; con escaneo en curso no se aplica.
- Nombres inválidos (reservados de Windows, caracteres prohibidos, punto o espacio al final, demasiado largos).
- Crear, renombrar (también solo mayúsculas), mover archivos y carpetas: índice, búsqueda, notas y tamaños de las carpetas de arriba quedan al día.
- Bloqueos: mover dentro de sí misma, a la misma carpeta, con choque de nombre, desde o hacia rutas protegidas, entre discos.
- Nunca sobrescribe, aunque el destino aparezca entre la vista previa y la confirmación.
- Si algo cambió desde la vista previa, ese paso se omite y los siguientes no se hacen; todo queda en el historial.
- Repo con cambios sin commit: exige confirmar el aviso. Sacar archivos solo en la nube de OneDrive: avisa que se descargarán.
- Papelera: enviar y restaurar (índice incluido), lo que no cabe o con la Papelera desactivada se bloquea, Papelera llena avisa, un envío fallido detiene el resto, deshacer trae exactamente la copia que ese cambio envió.
- Deshacer mover, renombrar y crear (solo si está vacía); se bloquea si sobrescribiría o si el archivo cambió; no se deshace dos veces.
- Historial con filtros y exportación CSV con BOM.
- "Abrir en" exige modo edición y una ruta del índice; VS Code se lanza con `Code.exe`, nunca con `code.cmd`.
- Código: solo `ops.py` usa `os.rename`, `os.mkdir`; solo `trash.py` usa `DeleteItem`, y siempre con reciclar y aviso de borrado permanente.
- Papelera real: `uv run pytest -m papelera_real` envía un archivo temporal y lo restaura.
- De punta a punta en la app real (hito 5): crear `Dev\sandbox`, renombrarla, enviarla a la Papelera real y deshacer los tres pasos desde el Historial.

### Apps (hito 6, hecho: `tests/test_apps.py`)
- Guardián automático: ninguna prueba ejecuta winget ni PowerShell ni abre un desinstalador (`apps._run` y `apps.launch` fallan si se llaman sin doble).
- Tablas de winget en inglés y español, con basura de progreso al inicio y resumen al final, leídas por la posición del encabezado.
- Unión de fuentes: winget se cruza con el registro (`ARP\`), la Store (`MSIX\`) o por nombre; el paquete "sparse" de la Store de un programa clásico (McAfee) se une a su entrada del registro.
- Categorías y marcas de revisión de la sección 2 sobre nombres reales (incluido "MSTeams" que contiene "steam"); lo que eliges a mano gana y cambiar la categoría no borra la marca ni la nota.
- Nunca en silencio: un desinstalador registrado con `/quiet`, `/S`, `/qn` o `--silent` no se ejecuta, se abre Configuración; winget siempre lleva `--interactive`; componentes del sistema y drivers exigen confirmar el aviso; lo no desinstalable queda bloqueado.
- La búsqueda en winget rechaza símbolos de shell y un guion inicial (no se puede colar `--accept-source-agreements`).
- API: plan sin modo edición se puede ver pero no ejecutar; ejecutar exige token, modo edición y queda en el historial como "iniciado".
- Verificación manual (hito 6): inventario real de 251 apps, diálogos de desinstalar (McAfee), controlador con aviso, app no desinstalable bloqueada e instalar 7-Zip, todos sin ejecutar.

### Organizador (hito 7, hecho: `tests/test_organizer.py`)
- Guardián automático: `organizer.variables` falla si una prueba intenta leer Descargas, Escritorio u OneDrive reales; cada prueba arma su copia en miniatura del brief en `tmp_path`.
- Reglas iniciales clasifican los ejemplos del brief (`M02...dart`, `Chixi`, `HW07`, `ELAP`, `Curriculum`, repos, `Proyectos` con `video-semiconductores` anidado); `desktop.ini`, descargas a medias, `AppData`, OneDrive y Dev nunca aparecen como sueltos.
- Regla de nombres `AAAA-MM-DD_Materia_Tema_v1.ext`: quita `(1)`, `- Copy`, `- copia`, `Copia de`, versiones viejas y la materia repetida; si el nombre ya existe sube a `v2`.
- Dos elementos con el mismo destino y nombre (dos copias de `chixi-refactor`) se marcan como conflicto y la API de ops bloquea el segundo: nunca sobrescribe.
- Reglas en orden (la primera gana), desactivables, editables; reglas inválidas (sin criterio, variable desconocida, ruta relativa, tipo desconocido) devuelven 422. Guardar exige token.
- Plan: carpetas nuevas antes de mover, lo anidado sale antes que su carpeta padre, y lo que va dentro de una carpeta que el mismo plan mueve se hace al final (mover `Sexto_Semestre` y dejar una entrega dentro en un solo plan).
- Deshacer el lote completo deja el árbol idéntico al de antes; una carpeta creada que recibió algo nuevo no se elimina.
- Destinos protegidos, fuera de las raíces o con nombres inválidos quedan bloqueados; aplicar exige modo edición.
- Verificación manual (hito 7): propuesta sobre tus carpetas reales (39 con destino, 90 por clasificar) y vista previa completa con aviso de repo con cambios en `Proyectos`, sin aplicar.

### Configuración y cierre (hito 8, hecho: `tests/test_settings.py`)
- Una ruta protegida agregada bloquea mover y enviar a la Papelera, y sigue protegida al reiniciar la app.
- La lista protegida solo crece: quitar o reemplazar no existe (405); agregar algo ya protegido da 409; raíz de disco, rutas relativas, de red, con `..` o con `:` dan 422.
- Carpetas a escanear: se guardan, se validan (que existan, modo conocido, al menos una) y se puede volver a las de siempre.
- Copia de la base de datos con `VACUUM INTO`: es un SQLite válido con el historial y aparece en "Últimas copias".
- Ninguna otra página del navegador puede llamar a la API (`Sec-Fetch-Site` cross-site o same-site dan 403).
- Auditoría de accesibilidad en las 7 pantallas reales: sin controles sin nombre, sin IDs repetidos, un `h1` por pantalla, objetivos de al menos 24 px.

## Metas de cobertura

No se persigue un porcentaje global. Sí se exige cobertura de ramas completa en `safety.py` y `ops.py`, que son las dos puertas por donde pasa todo lo peligroso.

## Antes de cerrar cada hito

1. `uv run pytest` en verde.
2. `npm run build` sin errores de tipos.
3. Revisión de código del hito.
4. Recorrido manual en el navegador integrado.
