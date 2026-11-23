# Sistema de diseño de Orden PC

Fuente de verdad del código: `web/src/index.css` (tokens) y `web/src/components/motion.tsx` (animaciones). Si algo cambia allí, cambia aquí.

## Dirección

Tercera dirección (pedida por Rodri): **consola retro futurista de los años 60**, con la esencia de Fallout 4 (pantalla de fósforo del Pip-Boy, terminales RobCo, optimismo atómico) y de Los 4 Fantásticos: Primeros pasos (plásticos crema, curvas de la era espacial, diales analógicos). Menos negro: la base es crema, blanca y gris cálida, y el color principal es un **amarillo crema**.

**Idea central: tu equipo como un árbol de circuito.** La app es una sola pantalla, el árbol: un tronco de pistas que nace del suelo y una copa de ramas y puntos donde cada carpeta es un nodo. Sin pestañas: cada herramienta se abre encima del árbol en una hoja lateral. Menos pasos: la app existe para acortar procesos.

Reglas:
- Una sola secuencia automática por pantalla (la entrada del titular; en el Árbol, el árbol que se dibuja). El resto del movimiento responde a una acción.
- `prefers-reduced-motion` desactiva todo: el contenido aparece directo, la rejilla ya ordenada, el árbol terminado y sin zoom.
- El estado se dice con forma y color a la vez.
- Alineación a la izquierda. Texto corrido a 72 caracteres como máximo.
- El tema claro (crema) es el predeterminado; el oscuro es grafito cálido, nunca negro. El árbol usa las mismas tarjetas y colores que el resto de la interfaz.
- Rellenos crema con canto inferior, como teclas de consola (`.bg-amarillo`). Cápsulas y círculos antes que esquinas rectas en las piezas protagonistas.

## Profundidad

- **Página:** luz cálida desde arriba (`amarillo-suave`), bordes apenas en sombra y un grano de película muy fino (ruido SVG al 5 %, multiplicado; en grafito, en modo pantalla).
- **Superficies (`bg-superficie`) y tarjetas (`bg-tarjeta`):** un brillo de 1 px en el canto superior, sombra de contacto y sombra de ambiente amplia. Se leen elevadas sobre el fondo.
- **Botones crema (`bg-amarillo`):** canto inferior de tecla, brillo arriba y un resplandor mostaza suave debajo.
- **Barra superior:** vidrio (`backdrop-blur`, saturación) con una sombra larga hacia abajo.
- **`.cristal`:** vidrio translúcido para lo que flota sobre el escenario del árbol (la ruta).

## Color

Tres papeles para el amarillo:
- `amarillo` es el **relleno crema**: botones principales, sección activa, selección, miga actual. Lleva texto grafito encima (`acento-texto`).
- `amarillo-fuerte` es la **tinta de datos**: barras por categoría, franja de la fila seleccionada. Más intenso para que se vea sobre crema.
- `acento` es **tinta legible**: cifras, enlaces, bordes y foco. Ocre en claro, crema en grafito.

| Token | Claro (crema) | Oscuro (grafito) | Uso |
|---|---|---|---|
| `fondo` | `#F3F0E7` | `#21201C` | Fondo general |
| `superficie` | `#FBFAF5` | `#2A2925` | Barra de navegación, paneles, tablas |
| `superficie-2` | `#E8E3D5` | `#35332D` | Pistas de barras |
| `tarjeta` | `#F1E3B3` | `#3B3727` | Tarjetas inclinadas, crema amarillo |
| `linea` | `#D8D1BF` | `#46433A` | Bordes y divisores (no lleva texto) |
| `display` | `#2A2824` | `#F7F0DC` | Titulares |
| `texto` | `#2A2824` | `#ECE6D5` | Texto principal |
| `tenue` | `#686354` | `#A9A291` | Texto secundario, iconos inactivos |
| `acento` | `#7D6420` | `#F2DA8E` | Tinta: cifras, enlaces, foco, carpetas |
| `amarillo` | `#F2D98A` | `#F0D485` | Relleno crema principal |
| `amarillo-fuerte` | `#D9B550` | `#E6C766` | Tinta de datos |
| `amarillo-suave` | `#F8EDC8` | `#3A3420` | Fondos teñidos |
| `acento-texto` | `#2A2824` | `#24221E` | Texto sobre `amarillo` |
| `particula` | `#B7B0A0` | `#77725F` | Puntos del campo de partículas |
| `horizonte` | `#F3E2A6` | `#4A4226` | Resplandor inferior del hero |
| `nube` | `#2D6F79` | `#86C3CB` | OneDrive: verde azulado de los sesenta |
| `cambios` | `#A2501D` | `#E9A36D` | Repo con cambios, advertencias: naranja tostado |
| `protegido` | `#6B4E8C` | `#BCA6D9` | Ruta protegida (candado): ciruela |
| `error` | `#A63A2C` | `#E8907F` | Errores y acciones de Papelera: ladrillo |
| `regenerable` | `#5D6670` | `#A9B2BC` | `node_modules`, `.venv` y similares |
| `exito` | `#4A6B39` | `#ABC98E` | Acción completada: salvia |
| `traza` / `traza-2` | `#8C8577` / `#B8B1A1` | `#A59D8A` / `#6F6A5D` | Pistas del árbol y puntos grises del follaje |
| `hoja-a` / `hoja-b` | `#ECD38A` / `#D8BC6A` | `#E9CF7F` / `#C9AD5D` | Follaje amarillo pastel, ondas |
| `chispa` | `#FFF4C8` | `#FFF1BD` | Centro de chispas, pulsos y luciérnagas |

Contraste (WCAG 2.x) contra `fondo` en claro: `texto` 13,4; `tenue` 5,6; `acento` 5,1; `nube` 5,1; `cambios` 5,0; `protegido` 6,1; `error` 5,7; `exito` 5,4. En grafito todos superan 6. Grafito sobre `amarillo`: 11,1. Todo cumple AA.

Los estados conservan su propio tono, apagado y cálido para convivir con el crema; el amarillo es la marca de la app y nunca significa un estado.

## Tipografía

| Familia | Uso |
|---|---|
| **Martian Mono** (variable, eje de anchura 75 a 112,5 %) | Titulares en mayúsculas a anchura 112,5 %, cifras grandes, títulos de bloque y logo |
| **Geist** (variable) | Texto de interfaz, párrafos, tablas, botones |

Las dos se empaquetan con `@fontsource-variable` y funcionan sin internet. Cifras tabulares activadas en todo el documento.

| Paso | Tamaño | Uso |
|---|---|---|
| `.titular` | fluido 36 a 88 px (hero hasta 120 px) | Un titular por pantalla, mayúsculas, interlineado 1,02 |
| `.cifra` | 36 a 44 px | Cifras del resumen del disco, en `acento` |
| `text-lg` mono | 21 px | Títulos de bloque y de tarjeta |
| `text-base` | 16 px | Bajadas y párrafos |
| `text-sm` | 14 px | Interfaz, tablas, navegación |
| `text-xs` | 12 px | Metadatos secundarios |

## Movimiento

Curva única `cubic-bezier(0.22, 1, 0.36, 1)` (`EASE`): sale rápido y se asienta suave.

| Patrón | Componente | Detalle |
|---|---|---|
| Titular desenfocado a nítido | `Titular` | Por línea: opacidad 0 a 1, desenfoque 16 px a 0, subida 0,2 em; 0,9 s, escalonado 90 ms |
| Bajada | `Bajada` | Línea amarilla a la izquierda; aparece 0,35 s después del titular |
| Cifras | `CountUp` | Cuentan desde 0 al entrar en pantalla, 1,6 s |
| Barras por categoría | `CategoryBar` | Crecen desde la izquierda al entrar en pantalla, escalonadas |
| Tarjetas inclinadas | `TiltCard` | Entran desde abajo con resorte y quedan inclinadas entre 1 y 2,5 grados; se enderezan y suben 6 px con el cursor o el foco |
| Barra de herramientas | `Herramientas` (`pages/Inicio.tsx`) | Una píldora suave sigue al cursor entre herramientas y la crema se desliza hasta la abierta (`layoutId`, resorte); el contador de pendientes rebota al cambiar |
| Hoja de herramienta | `Hoja` (`components/ui.tsx`) | Entra desde la derecha en 0,45 s, de arriba a abajo, sin oscurecer el árbol; un clic fuera la cierra. Su contenido sube en cascada (clase `entrada`). El árbol se pausa mientras la hoja está abierta |
| Barra para preguntar | `Pregunta` | Mientras espera, escribe ejemplos letra por letra; al enfocarla se ensancha y la estrella gira |
| Modo edición | `ModoEdicion` | Palanca con perilla que se desliza; el candado gira y se vuelve lápiz |
| Tema | `Tema` | El sol se hunde girando y sale la luna |

### Lenguaje de los botones (`index.css`, sección "movimiento")

Dos curvas: `--suave` (la de arriba) y `--resorte` (`cubic-bezier(0.34, 1.56, 0.64, 1)`, se pasa apenas y vuelve).

- **Teclas de consola:** todo `boton*` sube 2 px al acercarte, se hunde y se achica al presionar (el canto desaparece) y vuelve con resorte. Las teclas crema reciben un destello que las cruza.
- **Chispas:** al presionar una tecla crema, una herramienta o algo con `data-chispa`, saltan nueve partículas amarillas desde el punto exacto del clic.
- **Gestos de ícono:** cada ícono actúa su acción al acercarte: flechas avanzan, X y + giran, recargar y radar dan media vuelta, lápiz y varita se inclinan, papelera y candado tiemblan, la estrella titila. Se aplican por la clase `lucide-<nombre>`: un ícono nuevo hereda su gesto sin código extra.
- **Ayudas:** todo botón de solo ícono muestra su nombre (su `aria-label`) al acercarte o al llegar con el teclado. `data-tip` para otros textos, `data-tip-abajo` y `data-tip-izq` cerca de los bordes.
- **Foco, casillas y campos:** el anillo de foco llega desde afuera y se ajusta; las casillas rebotan al marcarse; los campos se rodean de un halo crema al escribir.
- **Regla:** nada se mueve solo salvo el escenario del árbol y los ejemplos de la barra (que se pausan con una hoja abierta). Con "reducir movimiento" en Windows, todo esto se apaga.

## Componentes base

### Sin barra superior
No hay. El árbol y su escenario ocupan la pantalla de borde a borde y nada se pinta encima (ni barra, ni degradados, ni grano). El Modo edición y el tema flotan a la derecha de la fila de ruta; con una hoja abierta, el Modo edición está en su cabecera.

### Interruptor "Modo edición"
`button role="switch" aria-checked`. Apagado: borde `linea`, candado, texto `tenue`. Encendido: fondo `amarillo`, lápiz, y la línea amarilla bajo la barra. El cambio se anuncia con `aria-live`.

### Tarjeta inclinada
`tarjeta` con radio de 8 px, sin sombra. Arriba, el icono dentro de un cuadro con contorno (`IconBox`). Título en Martian Mono 21 px. Se usa para estados vacíos y resúmenes, nunca para tablas.

### Botones y campos (utilidades en `index.css`)
| Clase | Uso |
|---|---|
| `boton-primario` | Fondo `amarillo` con canto de tecla, texto `acento-texto`. La acción principal |
| `boton` | Borde `linea`, texto `texto`. Acciones secundarias |
| `boton-peligro` | Fondo `error`, texto `error-texto`. Solo para enviar a la Papelera o desinstalar |
| `boton-icono` | Cuadro de 32 px sin borde, `tenue` a `texto` |
| `enlace` | Texto subrayado en `acento` |
| `campo` | Entradas y selectores de formularios |

Todos miden 36 px de alto. Una forma nueva de botón se agrega ahí, no en cada pantalla.

El texto del botón nombra la acción ("Mover 12 archivos", "Enviar a la Papelera"), nunca "Aceptar".

### Marcas de estado
| Estado | Icono (lucide) | Color | Texto accesible |
|---|---|---|---|
| Solo en la nube | `Cloud` | nube | "Solo en la nube" |
| Disponible sin conexión | `CloudCheck` | nube | "Disponible sin conexión" |
| Repo con cambios | `GitBranch` + punto | cambios | "Repo con cambios sin commit" |
| Repo limpio | `GitBranch` | tenue | "Repo sin cambios" |
| Protegido | `Lock` | protegido | "Ruta protegida: Orden PC no la modifica" |
| Regenerable | `RefreshCw` | regenerable | "Se puede regenerar" |

### Vista previa y confirmación (`ops.tsx`)
- `<dialog>` nativo con `showModal()`. Arriba dice "Vista previa: nada ha cambiado todavía".
- Título = la acción exacta ("Mover 12 elementos a C:\Users\…\Calidad_Software"); se abrevian solo las rutas muy largas.
- Avisos primero, con forma y color: `Info` (tenue), `AlertTriangle` (cambios), `AlertOctagon` (error). Un aviso de peligro exige marcar "Leí el aviso y quiero continuar".
- "Esto va a pasar": cada paso con su icono (crear, renombrar, mover, Papelera, restaurar) y tamaño, entrando escalonado.
- "No se incluye": cada elemento bloqueado con su motivo en lenguaje claro.
- Botón de confirmar con verbo y cantidad ("Enviar 3 elementos a la Papelera"), nunca "Aceptar". Si algún paso va a la Papelera: fondo `error` con texto `error-texto` y foco inicial en "Cancelar".
- Después de aplicar, el mismo diálogo muestra el resultado de cada paso (Hecho, Error, No se hizo) y ofrece "Deshacer", que abre otra vista previa.

### Barra de acciones del Explorador
Solo con el modo edición encendido: Nueva carpeta, Renombrar, Mover a, Enviar a la Papelera (en `error`), Abrir en el Explorador de Windows, Abrir en VS Code. Actúa sobre lo marcado o, si no hay marcas, sobre la fila seleccionada. Con el modo apagado se ve una línea con candado que explica cómo activarlo. Marcar: casillas, Ctrl o Mayús más clic, Espacio, Ctrl+A, Escape para quitar marcas. Arrastrar filas a una carpeta del árbol abre la vista previa de mover.

### Historial
Un bloque por lote (título de la confirmación, fecha, conteo por resultado), filas con el mismo lenguaje de pasos, "Deshacer" por fila y "Deshacer todo el lote". Filtros por acción, resultado y texto; "Exportar CSV".

### Mensajes
Errores con `Alerta` (`role="alert"` en `error`): qué pasó y qué hacer, sin disculpas. Estados vacíos con `Vacio`: qué falta y cómo conseguirlo.

### Piezas compartidas (`components/ui.tsx`)
`Hoja` (herramientas, asistente y detalles), `Dialogo` (diálogo modal nativo con encabezado, cuerpo, error y pie; Cancelar cierra con `formmethod="dialog"`), `useAccion` (ocupado y error de una acción), `Cifras`, `Seccion`, `Casilla`, `Selector`, `Buscador`, `MasFilas` y `BarraAccion` (barra que sube desde el pie de la hoja con lo elegido). Una pantalla nueva se arma con estas piezas.

## Visualización de datos

Método de la skill `dataviz`: primero la forma, el color al final y la paleta validada con su script.

| Gráfica | Forma | Color | Vista de tabla |
|---|---|---|---|
| Uso por categoría | Una barra horizontal por categoría, medida contra el disco completo, de mayor a menor | Un solo tono (`amarillo-fuerte`); "Libre" es una pista punteada | Es una tabla: nombre, tamaño y porcentaje en cada fila |

**Por qué ya no hay paleta categórica.** Rodri pidió todo en tonos de amarillo. Una paleta categórica de amarillos, ocres y oliva no pasa el validador: con protanopía el amarillo verdoso y el naranja quedan a ΔE 1,5 a 3,2 (mínimo 8) y salen del rango de luminosidad. En vez de forzar colores, se cambió la forma: la barra apilada pasó a barras por fila, donde la identidad la da la etiqueta y el color solo mide.

## Archivos (hoja): explorador de archivos

- Casi a lo ancho de la pantalla. Tres columnas desde 1280 px (árbol, tabla, detalles); por debajo, los detalles se abren en su propia hoja.
- Árbol: patrón ARIA treeview con `aria-activedescendant`; el borde amarillo del elemento activo solo aparece cuando el árbol tiene el foco.
- Tabla: patrón ARIA grid virtualizado; Enter abre, Retroceso sube, RePág/AvPág saltan. Cada tamaño lleva una barra de 2 px relativa al más grande de la carpeta.
- Búsqueda en todo el índice: Ctrl+K desde cualquier lugar abre Archivos con el foco en el buscador (nunca un atajo de una sola tecla).
- Filtros en una fila sobre la tabla; un filtro activo se marca con borde amarillo; "Quitar filtros" aparece solo cuando hay alguno.

## Navegación: una sola pantalla

El árbol ocupa toda la pantalla. Al pie, en vidrio: la barra para preguntar al asistente y la barra de herramientas. Cada herramienta abre una hoja lateral encima del árbol, que se pausa mientras tanto.

| Herramienta | Qué reúne |
|---|---|
| **Archivos** | El explorador: árbol de carpetas, tabla, detalles, búsqueda y acciones con vista previa. También se abre con "Ver en la lista", tocando el nombre de un nodo o con Ctrl+K. |
| **Ordenar** | "Limpiar" (qué eliminar y por qué) y "Organizar" (reglas que llevan lo suelto a su carpeta). Su botón muestra cuántos elementos sueltos ya tienen destino. |
| **Apps** | Inventario, revisión, instalar, actualizar y desinstalar. |
| **Disco** | El disco en cifras, barras por categoría y "Lo que necesita orden". |
| **Historial** | Cada cambio, con deshacer. |
| **Ajustes** | Rutas protegidas, carpetas a escanear y copia de la base de datos. |

La hoja abierta vive en la dirección (`/?panel=apps`, `/?panel=ordenar&ver=organizar`): Atrás del navegador la cierra, Escape también, y cualquier enlace puede abrir una herramienta. Las direcciones de antes (`/ordenar`, `/apps`, `/historial`, `/configuracion`, `/explorador`, `/recomendaciones`, `/organizador`) abren su herramienta sobre el árbol. Cada herramienta se descarga al abrirla: el paquete inicial bajó de 593 KB a 450 KB.

## Árbol del PC

La pieza central de la app, inspirada en un árbol de circuito impreso. Una composición de **Remotion** (`web/src/arbol/ArbolPC.tsx`) reproducida en vivo con `@remotion/player`; Remotion se descarga solo al abrir esta vista.

- **Paleta:** pistas en grises cálidos (`traza`), follaje en amarillo pastel (`hoja-a`, `hoja-b`) con algunos puntos grises (`traza-2`), nodos con núcleo `amarillo-fuerte`, halo `amarillo` y un punto de luz `chispa`. Todo con variables del tema: de día crema y gris, de noche oro sobre grafito.
- **El árbol es el escenario de la página, no una caja:** ocupa todo el ancho y el alto disponibles, recortado como una foto de fondo (16:9 que cubre). Arriba flota solo la fila de ruta (Atrás, ruta, Ver en la lista, Escanear); solo sus controles reciben clics. Abajo, un degradado lo funde con la página y lleva la barra para preguntar, las herramientas y la pausa.
- **Escenario (`Ambiente.tsx`, 1600×900, otra composición de Remotion detrás del árbol):** foco cálido que respira detrás de la copa; tres haces de luz desde arriba que se balancean apenas; bruma en el horizonte; piso con rejilla en perspectiva hacia el punto de fuga, desvanecida en los bordes; polen lejano fino y lento y bokeh cercano grande, desenfocado y más rápido (paralaje); y un enjambre de 55 puntos amarillo pastel, pequeños y rápidos, que cruza el fondo en corrientes onduladas, titila y se aviva al paso de una onda de luz que sale del pie del árbol cada 10 s. Una máscara apaga todas las partículas detrás de la copa, el tronco y las franjas de controles: solo viajan por el fondo. Bucle de 20 s con ciclos enteros. En el zoom, el escenario solo se empuja un poco mientras el árbol hace todo el acercamiento.
- **Sombras:** las pistas proyectan una sombra difusa sobre el escenario (luz desde arriba a la izquierda), los nodos tienen sombra propia, la copa deja una sombra ancha en el piso y el tronco una sombra de contacto. Las etiquetas flotan con sombra y vidrio esmerilado.
- **Encuadre:** el árbol se dibuja en 1280×610 (con margen abajo, para que las placas nunca se corten) y se coloca a 1,05× en la parte baja del escenario, dejando arriba aire para la cabecera.
- **Tu carpeta:** el tronco es un haz de siete pistas que nacen separadas del suelo y se juntan al subir. Desde su cima sale un abanico de pistas en zigzag: las de las carpetas (hasta 5, más gruesas cuanto más pesan) terminan en su nodo en el borde de la cúpula, con la más grande al centro; otras doce son decorativas y rellenan la copa. Cada pista echa brotes, y algunos brotes otros, con su nube de puntos, sin salirse de la elipse de la copa.
- **Dentro de una carpeta, una rama, no otro árbol:** la rama entra por el lado donde estaba la carpeta. Si estaba a la derecha, entra por la izquierda y avanza hacia la derecha; si estaba a la izquierda, al revés; si estaba arriba al centro, sube desde abajo. Las subcarpetas brotan del tallo alternando arriba y abajo, y dentro de una rama los brotes siguen hacia el mismo lado.
- **Semilla:** ramas, brotes y puntos salen de un generador con semilla tomada de la ruta: cada carpeta se ve siempre igual.
- **Entrada, 3,4 s:** una onda nace en el suelo; el tronco y cada pista se trazan con una chispa brillante en la punta; cada brote nace cuando su pista pasa por ese punto; los puntos del follaje estallan desde la punta hacia su lugar con rebote; cada nodo aparece con resorte y lanza una onda expansiva; luego su etiqueta.
- **Vida continua después de la entrada:** pulsos de luz recorren el tronco y las pistas principales como corriente por un circuito (cada uno con su periodo, del 62 % del ciclo en movimiento y el resto en reposo); hasta 80 luciérnagas titilan en el follaje; los halos de los nodos respiran; una onda suave sale del pie del tronco cada 6 s. La estructura se congela al terminar la entrada y cada fotograma solo calcula lo que se mueve. La composición dura una hora y los ciclos van por módulo, así que nunca se reinicia.
- **Pausa:** un botón redondo abajo a la derecha detiene todo el movimiento continuo (árbol y ambiente). Con movimiento reducido, todo arranca quieto y cada escena aparece ya armada.
- **Etiquetas:** nombre y tamaño hacia afuera del árbol, sobre un fondo `superficie` translúcido para leerse sobre el follaje. La carpeta actual va al pie del tronco (o junto a la entrada del tallo) y "Lo demás" (subcarpetas chicas y archivos sueltos) al lado.
- **Cámara de zoom (`ArbolVista.tsx`):** las dos escenas viven a la vez y una sola animación las mueve como un mismo espacio. Al entrar, la escena actual se acerca hacia el nodo tocado y la rama de esa carpeta sale de dentro de él, ya creciendo; al volver, la escena actual se encoge hacia su nodo y la madre se aleja hasta su tamaño, ya armada. Escala geométrica (k elevado al progreso), 0,95 s.
- **Atrás:** botón principal "Atrás" a la izquierda de la ruta (desactivado en tu carpeta), la ruta misma y las teclas Retroceso o Escape con el foco en el árbol. Los árboles visitados se guardan en memoria.
- **Interacción:** el nodo y su etiqueta entran en la carpeta; las carpetas que Orden PC suma sin listar (node_modules, .git y similares) se abren en la lista. El nombre de la carpeta actual, "Lo demás" y "Ver en la lista" abren la carpeta en la lista. En tu carpeta, un enlace debajo avisa cuántos elementos sueltos ya tienen destino en Ordenar.
- **Accesibilidad:** cada nodo es un botón con nombre ("Entrar en Proyectos, 967 MB"); el dibujo es decorativo (`aria-hidden`); un resumen en texto (`sr-only`) dice lo mismo que la escena visible. Con movimiento reducido cada escena aparece terminada y sin zoom.

Detalle de la lista:

- Carpetas con ícono en `acento` relleno de `amarillo` y nombre en peso medio; archivos en gris. Filas de 44 px. La fila seleccionada lleva fondo `amarillo` al 15 % y una franja `amarillo-fuerte` de 3 px a la izquierda.

## Ordenar: Limpiar (antes Recomendaciones)

- Cifra principal en amarillo con el total recuperable; debajo, el reparto por confianza.
- Confianza con forma y texto: `SignalHigh`, `SignalMedium`, `SignalLow` más "Confianza alta, media o baja". No usa colores de estado: la confianza no es ni buena ni mala.
- Una sección por regla, en orden de prioridad, con casilla de "aceptar todas" (admite estado mixto), total y cantidad; se pliega con animación de altura. Muestra 100 filas y luego "Mostrar más".
- Posibles copias por nombre: comparación lado a lado (copia y original, con tamaño y fecha).
- Copias exactas: la ruta que se conserva va debajo del motivo.
- Barra inferior al aceptar: cuántas y cuánto. Aceptar solo anota; el envío a la Papelera es otra acción con vista previa.
- "Ajustar reglas" usa `<dialog>` nativo: activar, confianza y umbrales (días, MB, % de coincidencia), con "Guardar reglas" y "Cancelar".

## Apps

- Tres cifras en amarillo (instaladas, con actualización, para revisar). Los componentes del sistema no cuentan hasta que se activa "Mostrar componentes del sistema".
- "Para revisar": tarjetas inclinadas con el motivo en una frase y dos acciones, "Desinstalar" y "La conservo" (quita la marca).
- Lista con columnas fijas (nombre y editor, versión, tamaño, categoría, acciones) para que "Actualizar" no desplace nada; cada fila se despliega con origen, ubicación, desinstalador, id de winget y la marca de revisión.
- Categoría editable en la fila; la automática se indica como "(automática)" y volver a ella borra la elección manual.
- Confirmación (`<dialog>`): título con la acción y la app, avisos con ícono y nivel (información, aviso, peligro), y el comando exacto que se va a abrir en monoespaciada. Peligro exige marcar "Leí el aviso y quiero continuar". El botón dice qué se abre: "Abrir el desinstalador de X". Desinstalar usa el botón en color de error.
- Botones repetidos por fila llevan nombre accesible con la app ("Desinstalar McAfee").

## Ordenar: Organizar (antes Organizador)

- Tres cifras en amarillo: con destino propuesto, por clasificar, carpetas por crear.
- Plan propuesto agrupado por carpeta destino (ruta legible: "OneDrive\20_Carrera", "Dev\uni"), con casilla de grupo (admite estado mixto) y casilla por elemento. El nombre en el destino es un campo editable con apariencia de texto; si cambia respecto al original va en amarillo.
- Conflictos (mismo destino y nombre) se muestran con ícono de aviso y empiezan sin marcar: Orden PC no elige por ti.
- Barra inferior fija: cuántos elementos, a cuántas carpetas y cuánto pesan, con "Revisar movimientos". La vista previa se puede abrir sin Modo edición; aplicar no.
- Por clasificar: selector de destino por fila ("Dejar donde está" por defecto) y "Crear regla", que abre el editor con nombre, tipo y palabra clave sugeridos.
- Reglas: lista numerada (el orden importa), con activar, subir, bajar, editar y quitar; cada una se describe en una frase ("Archivos .dart que empiezan con «M02»").
- Estructura objetivo como árbol: círculo verde si la carpeta existe, círculo punteado si falta. Editar estructura usa tres áreas de texto (carpetas con `{Materia}`, materias, carpetas de origen). "Crear carpetas que faltan" pasa por la vista previa.

## Configuración (engranaje de la barra superior)

- Tres secciones en tarjeta, cada una con ícono amarillo y una frase que explica qué protege o qué cambia: Rutas protegidas, Carpetas a escanear, Base de datos.
- Rutas protegidas en dos columnas: "Siempre protegidas" (candado gris) y "Agregadas por ti" (candado amarillo). Agregar pide una segunda confirmación en línea ("Proteger para siempre") porque no se puede deshacer.
- Carpetas a escanear: lista editable con modo por carpeta; "Guardar carpetas" solo se activa si cambiaste algo.
- Base de datos: ruta del archivo, tamaño, "Crear copia ahora", últimas cinco copias y cómo restaurar.

## Asistente (botón "Preguntar" y barra al pie del árbol)

- Panel lateral derecho (`asistente/Asistente.tsx`), abierto desde la barra para preguntar al pie del árbol o con "Explícame este archivo" en Detalles. Usa la misma `Hoja` que las herramientas y queda encima de ellas.
- Tarjetas de preparación independientes: falta Ollama o el modelo (comandos para copiar y "Comprobar de nuevo"; la app nunca los ejecuta) y falta leer documentos ("Preparar", barra de avance, "Detener").
- Respuesta: texto con citas `[n]` como círculos amarillos; al tocar una cita se resalta su fuente. Cada fuente abre su carpeta en el árbol.
- Regla de contenido: solo responde con fragmentos de tus archivos. Si no hay coincidencias, lo dice sin consultar al modelo.
- La cabecera del árbol no lleva título visible (hay un `h1` solo para lectores de pantalla).

## Sugerencias de orden (Ordenar → Organizar → Por clasificar)

- "Que el asistente sugiera" (o "Sugiere cómo ordenar mis documentos" en el asistente) lee cada documento por clasificar y propone su carpeta (`sugerir.py`). Solo propone: "Usar" llena el destino y el nombre de la fila, y aplicar pasa por la vista previa de siempre.
- Cada sugerencia va en una franja crema bajo su fila: destino, nombre nuevo si cambia, el motivo citando el documento y de dónde salió (leyó el documento, palabras clave, antigüedad).
- Lógica, basada en PARA, Johnny.Decimal y las guías de nombres de bibliotecas universitarias: si el documento declara su materia, solo se elige entre Material y Entregas de esa materia; trabajo tuyo (tu nombre, integrantes, matrícula) va a Entregas con nombre AAAA-MM-DD_Materia_Tema_v1; sin evidencia en el texto no se mueve; lo que lleva más de un año sin cambios va al Archivo; copias y formatos del mismo documento van juntos.
- Si los documentos declaran una materia que no está en tu estructura, no se fuerzan a otra: aparece una recomendación con "Agregar a mi estructura", que abre "Editar estructura" ya con la materia para que la revises y guardes.

## Redacción

Español, tuteo, frases cortas, verbos concretos. Nunca guion largo (lo verifica `test_no_em_dash_in_ui_text`). La misma acción se llama igual en botón, diálogo e historial.
