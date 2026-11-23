"""Servidor FastAPI. Modelo de seguridad en docs/adr/002-modelo-de-seguridad.md."""

import html
import secrets
import shutil
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from orden_pc import api, db, safety, winfs
from orden_pc.api import require_edit_mode  # noqa: F401  (las pruebas y rutas futuras la importan de aquí)
from orden_pc.apps import AppOps
from orden_pc.contenido import Lector
from orden_pc.sugerir import Sugeridor
from orden_pc.ops import Ops
from orden_pc.scanner import Scanner

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
TOKEN_HEADER = "x-orden-token"


class EditModeIn(BaseModel):
    enabled: bool


def create_app(port: int, token: str | None = None, static_dir: Path | None = None, db_path: Path | None = None) -> FastAPI:
    token = token or secrets.token_urlsafe(32)
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    origins = {f"http://{h}" for h in hosts}

    app = FastAPI(title="Orden PC", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.token = token
    app.state.edit_mode = False  # vive en memoria: se apaga al cerrar la app
    app.state.db_path = db_path or db.default_db_path()
    conn = db.connect(app.state.db_path)  # crea o migra el esquema al arrancar
    safety.EXTRA_PROTECTED[:] = db.get_setting(conn, "rutas_protegidas", [])
    conn.close()
    app.state.scanner = Scanner(app.state.db_path)
    app.state.ops = Ops(app.state.db_path, app.state.scanner)
    app.state.app_ops = AppOps()
    app.state.lector = Lector(app.state.db_path)
    app.state.sugeridor = Sugeridor(app.state.db_path)
    app.include_router(api.router)

    @app.middleware("http")
    async def guard(request: Request, call_next):
        # Host fijo: bloquea DNS rebinding.
        if request.headers.get("host") not in hosts:
            return JSONResponse({"detail": "Host no permitido."}, status_code=400)
        # Otra página abierta en el navegador no puede llamar a la API, ni siquiera para leer
        # (algunas lecturas ejecutan winget). "same-site" incluye otros puertos de 127.0.0.1.
        if request.url.path.startswith("/api/") and request.headers.get("sec-fetch-site") in ("cross-site", "same-site"):
            return JSONResponse({"detail": "Solicitud desde otra página bloqueada."}, status_code=403)
        if request.method in WRITE_METHODS:
            origin = request.headers.get("origin")
            if origin is not None and origin not in origins:
                return JSONResponse({"detail": "Origen no permitido."}, status_code=403)
            sent = request.headers.get(TOKEN_HEADER, "").encode("utf-8", "surrogateescape")
            if not secrets.compare_digest(sent, token.encode()):
                return JSONResponse({"detail": "Falta el token de sesión o no es válido."}, status_code=403)
        response = await call_next(request)
        # Ninguna otra página puede enmarcar la app (clickjacking sobre "Modo edición").
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.get("/api/disk")
    def disk():
        drives = []
        for root in winfs.fixed_drives():
            try:
                usage = shutil.disk_usage(root)
            except OSError:  # lector sin disco, unidad desconectada
                continue
            drives.append({"drive": root.rstrip("\\"), "total": usage.total, "used": usage.used, "free": usage.free})
        return {"drives": drives}

    @app.get("/api/session")
    def session():
        return {"edit_mode": app.state.edit_mode}

    @app.post("/api/session/edit-mode")
    def set_edit_mode(body: EditModeIn):
        app.state.edit_mode = body.enabled
        return {"edit_mode": app.state.edit_mode}

    if static_dir:
        meta = f'<meta name="orden-token" content="{html.escape(token)}">'
        app.mount("/assets", StaticFiles(directory=static_dir / "assets", check_dir=False), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            index = static_dir / "index.html"
            if path == "api" or path.startswith("api/") or not index.exists():
                raise HTTPException(404)
            # Se lee en cada petición: `npm run watch` cambia los nombres de los assets.
            page = index.read_text(encoding="utf-8").replace("</head>", f"{meta}</head>", 1)
            return HTMLResponse(page, headers={"Cache-Control": "no-store"})

    return app
