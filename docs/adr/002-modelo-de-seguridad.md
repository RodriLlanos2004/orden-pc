# ADR-002: Modelo de seguridad

**Estado:** Aceptado
**Fecha:** 2026-10-08
**Decide:** Rodri

## Contexto

La app modifica archivos reales a través de una API HTTP local. Cualquier página abierta en el navegador puede intentar enviar peticiones a `127.0.0.1`. Prioridad declarada: lenta y segura antes que rápida y peligrosa.

## Decisión

Capas, de afuera hacia adentro:

1. **Red.** Solo `127.0.0.1`. Probado en `test_main_binds_loopback_only`.
2. **Host.** El middleware rechaza con 400 todo `Host` que no sea `127.0.0.1:<puerto>` o `localhost:<puerto>`. Bloquea DNS rebinding.
3. **Origen.** En métodos de escritura, un `Origin` presente y ajeno se rechaza con 403.
4. **Token.** `secrets.token_urlsafe(32)` por proceso, inyectado como `<meta name="orden-token">` en el `index.html` servido (con `Cache-Control: no-store`). Toda escritura exige `X-Orden-Token`, comparado en tiempo constante. Un header personalizado obliga a preflight CORS y no habilitamos CORS, así que otra página no puede enviarlo ni leer el HTML que lo contiene.
5. **Modo edición.** Bandera en memoria, falsa al arrancar. Las rutas que escriben en disco dependen de `require_edit_mode` y devuelven 403 si está apagada. Desaparece al cerrar el proceso.
6. **GET sin efectos.** Ninguna ruta GET cambia estado (las páginas ajenas pueden disparar GET aunque no lean la respuesta). Iniciar un escaneo es POST.
7. **Rutas** (hito 2, `safety.resolve_target`, único punto de entrada): rechaza `\\?\`, UNC, flujos alternos (`a:b`), puntos y espacios finales; expande nombres 8.3; resuelve junctions y symlinks; compara sin distinguir mayúsculas; rechaza raíces de disco, rutas protegidas, el interior de cualquier `.git` y todo lo que esté fuera de las raíces configuradas.
8. **Rutas protegidas.** Las de la regla 4 del brief viven en código y siempre aplican; la configuración solo puede agregar (hito 8: `POST /api/settings/protected`; no existe ruta para quitar ni reemplazar, `test_protected_list_only_grows`). Las agregadas aplican en `safety.protected_reason`, así que bloquean escrituras y además se ocultan de recomendaciones y del organizador.
9. **Vista previa obligatoria** (hito 5): `POST /plan` devuelve los cambios exactos; `POST /apply/{plan_id}` los ejecuta tras revalidar. Los planes caducan a los 10 minutos.
10. **Sin borrado permanente.** `test_no_permanent_delete_calls` falla si el código de la app contiene `os.remove`, `os.unlink`, `shutil.rmtree`, `.unlink()`, `.rmdir()`, `DeleteFile*`, `RemoveDirectory*` o `FO_DELETE`.
11. **Desinstalar.** Solo se lanza el desinstalador oficial o `winget uninstall --interactive`; nunca flags silenciosos.
12. **Lecturas desde otras páginas** (hito 8). Algunas lecturas ejecutan herramientas (winget, PowerShell). Toda petición a `/api/` con `Sec-Fetch-Site: cross-site` o `same-site` se rechaza con 403; `same-site` cubre otras apps en otros puertos de `127.0.0.1`. Navegadores sin ese header siguen protegidos por las capas 2 a 5 para todo lo que escribe.
13. **Sin marcos.** `X-Frame-Options: DENY` y `frame-ancestors 'none'`: ninguna página puede enmarcar la app para engañar un clic sobre "Modo edición".

## Opciones consideradas

- **Sin token, solo Host y Origin:** algunas peticiones simples (formularios) no envían Origin de forma confiable; insuficiente.
- **Token en cookie:** las cookies viajan solas en peticiones de otras páginas (CSRF); un header explícito no.
- **Autenticación con contraseña:** fricción sin beneficio en una app de un solo usuario local.

## Consecuencias

- Abrir `http://127.0.0.1:8765` desde otro navegador o pestaña funciona porque el HTML trae su token; reiniciar la app invalida pestañas viejas (deben recargar).
- Herramientas como curl pueden escribir solo si conocen el token, que nunca se guarda en disco ni se imprime.
