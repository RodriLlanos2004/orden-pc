# ADR-003: Estrategia de borrado y deshacer

**Estado:** Aceptado. Revisado el 2026-10-08 tras el spike del hito 5 (ver "Cambio respecto a la versión inicial").
**Fecha:** 2026-10-08
**Decide:** Rodri

## Contexto

Regla 1: nada se borra de forma permanente. Regla 3: todo cambio queda auditado; mover y renombrar se deshacen desde el historial; eliminar se deshace restaurando desde la Papelera.

Riesgo real: cuando un elemento no cabe en la Papelera, una operación de Shell con flags silenciosos lo borra **permanentemente sin avisar**.

## Spike (hito 5)

Hecho con un archivo de prueba propio en `pytest-tmp`:

- `send2trash` 2.1.0 usa `FOF_NOCONFIRMATION | FOF_NOERRORUI | FOF_SILENT` y **no** pide `FOF_WANTNUKEWARNING`: confirma el riesgo.
- La capacidad está en `HKCU\...\Explorer\BitBucket\Volume\{GUID}`: `MaxCapacity` (MB) y `NukeOnDelete`. En este equipo: 26 343 MB y 0 (activa).
- Cada elemento de la Papelera tiene un `$I` con la ruta original y la fecha de borrado; el nombre que da el Shell oculta la extensión, así que se identifica por el `$I`.
- El verbo canónico `undelete` restaura aunque el menú diga "&Restaurar" (no depende del idioma).

## Decisión

### Eliminar (`trash.py`, el único módulo que elimina)
1. Validar la ruta (ADR-002).
2. Si la Papelera del volumen está desactivada (`NukeOnDelete = 1`) o el elemento pesa más que `MaxCapacity`, **no se intenta**: la vista previa lo muestra como bloqueado y explica por qué. Sin ajuste en el registro se asume el 5 % del volumen.
3. Enviar con `IFileOperation` y `FOFX_RECYCLEONDELETE | FOFX_ADDUNDORECORD | FOF_WANTNUKEWARNING`: si aun así Windows fuera a borrar en vez de reciclar, pregunta en lugar de hacerlo en silencio.
4. Verificar que ya no está en su lugar y que sí aparece en la Papelera (por su `$I`). Si no, el paso queda como error y los siguientes no se hacen.

### Deshacer eliminar
Buscar en la Papelera el elemento con esa ruta original borrado en la ventana del cambio (un minuto antes a cinco segundos después del registro; si hay varios, el más cercano) y ejecutar `undelete`. Se espera a que reaparezca en su ruta.

### Deshacer mover y renombrar
Movimiento inverso solo si el elemento sigue donde quedó, el lugar original está libre y, para archivos, tamaño y fecha coinciden con lo registrado. Si no, la vista previa lo bloquea y explica por qué; nada se toca.

### Deshacer crear carpeta
Solo si sigue vacía; entonces va a la Papelera.

### Lotes
Cada plan aplicado es un lote. Si un paso falla, los siguientes se registran como "No se hizo" y no se ejecutan. Deshacer un lote es un plan nuevo, con su propia vista previa, en orden inverso.

### OneDrive
Mover dentro de OneDrive no descarga archivos. Sacarlos de OneDrive sí: la vista previa avisa cuántos están solo en la nube y cuánto pesan. Eliminar algo de OneDrive también lo quita de la nube; la vista previa lo dice.

## Cambio respecto a la versión inicial

La versión inicial decía "Eliminar = `send2trash`". El spike mostró que `send2trash` silencia el aviso de borrado permanente, así que se reemplazó por una llamada directa a `IFileOperation` (unas 20 líneas con pywin32) que sí lo pide. La comprobación de capacidad y la verificación posterior se mantienen.

## Opciones consideradas

- **Papelera propia de la app** (mover a una carpeta interna): deshacer trivial, pero no libera espacio y el usuario pierde la Papelera de Windows que ya conoce.
- **Leer `$I` y mover `$R` a mano para restaurar:** funciona, pero escribe dentro de `$Recycle.Bin`, que es ruta protegida. El verbo `undelete` evita tocarla.

## Consecuencias

- Lo que no cabe en la Papelera no se puede eliminar desde la app; Rodri lo hace a mano si quiere.
- Las pruebas usan una Papelera simulada; `uv run pytest -m papelera_real` hace un viaje de ida y vuelta real con un archivo temporal.
