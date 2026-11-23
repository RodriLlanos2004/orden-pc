"""Rutas de lectura del índice y control del escáner. Ninguna toca archivos del usuario.

Las rutas que reciben `path` solo aceptan rutas que ya están en el índice: nada de sondear el disco.
"""

import asyncio
import json
import os
import re
import subprocess
import time
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from orden_pc import agente, apps, db, insights, ops, organizer, recommend, safety, scanner, winfs

router = APIRouter(prefix="/api")


def require_edit_mode(request: Request) -> None:
    """Dependencia para toda ruta que cambie algo en disco."""
    if not request.app.state.edit_mode:
        raise HTTPException(403, "El modo edición está apagado. Actívalo para hacer cambios.")

ENTRY_COLS = "e.path, e.parent, e.name, e.ext, e.is_dir, e.size, e.files, e.mtime, e.cloud, e.tags, e.collapsed"
HAS_CHILDREN = "EXISTS(SELECT 1 FROM entries c WHERE c.parent = e.path AND c.is_dir = 1) AS has_children"
LIST_LIMIT = 10_000


@contextmanager
def _conn(request: Request):
    conn = db.connect(request.app.state.db_path)
    try:
        yield conn
    finally:
        conn.close()


def _roots(conn) -> list[dict]:
    return scanner.configured_roots(conn)


def _mode(path: str, roots: list[dict]) -> str:
    """Modo de la raíz más específica que contiene la ruta."""
    best, mode = -1, "completo"
    for r in roots:
        rp = os.path.normpath(r["path"]).rstrip("\\").lower()
        if path.lower() == rp or path.lower().startswith(rp + "\\"):
            if len(rp) > best:
                best, mode = len(rp), r["mode"]
    return mode


def _entry_or_404(conn, path: str):
    row = conn.execute(f"SELECT {ENTRY_COLS}, e.ctime, e.atime, e.attrs, e.hash_partial, e.hash_full FROM entries e WHERE e.path = ?", (path,)).fetchone()
    if row is None:
        raise HTTPException(404, "Esta ruta no está en el índice. Vuelve a escanear para verla.")
    return row


def _item(r) -> dict:
    d = dict(r)
    d["type"] = "carpeta" if d["is_dir"] else insights.ext_type(d["ext"])
    d["tags"] = [t for t in d["tags"].split(",") if t]
    d["protected"] = safety.protected_reason(d["path"]) is not None
    return d


# ---------------------------------------------------------------------- escáner


@router.post("/scan", status_code=202)
def start_scan(request: Request):
    # Escanear solo lee archivos y escribe en el índice de la app: no exige modo edición.
    with _conn(request) as conn:
        roots = _roots(conn)
    if not request.app.state.scanner.start(roots):
        raise HTTPException(409, "Ya hay un escaneo en curso.")
    return request.app.state.scanner.snapshot()


@router.post("/scan/stop")
def stop_scan(request: Request):
    request.app.state.scanner.stop()
    return request.app.state.scanner.snapshot()


@router.get("/scan/status")
def scan_status(request: Request):
    return request.app.state.scanner.snapshot()


@router.get("/scan/events")
async def scan_events(request: Request):
    sc = request.app.state.scanner

    async def stream():
        while True:
            yield f"data: {json.dumps(sc.snapshot())}\n\n"
            if not sc.running or await request.is_disconnected():
                return
            await asyncio.sleep(0.25)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-store"})


@router.get("/summary")
def summary(request: Request):
    """Último escaneo terminado. Solo lee la tabla de escaneos: la interfaz la consulta a menudo."""
    with _conn(request) as conn:
        last = conn.execute("SELECT * FROM scans WHERE status = 'terminado' ORDER BY id DESC LIMIT 1").fetchone()
        if last is None:
            return {"scanned": False}
        return {
            "scanned": True,
            "finished": last["finished"],
            "duration": last["finished"] - last["started"],
            "scanned_files": last["files"],
            "scanned_bytes": last["bytes"],
        }


# ---------------------------------------------------------------------- panel


@router.get("/insights/categories")
def categories(request: Request):
    with _conn(request) as conn:
        return insights.categories(conn)


@router.get("/insights/cards")
def cards(request: Request):
    with _conn(request) as conn:
        return insights.status_cards(conn)


@router.get("/insights/timeline")
def timeline(request: Request, weeks: int = Query(26, ge=4, le=104)):
    with _conn(request) as conn:
        return {"weeks": insights.timeline(conn, weeks)}


# ---------------------------------------------------------------------- explorador


@router.get("/roots")
def roots(request: Request):
    with _conn(request) as conn:
        out = []
        for r in _roots(conn):
            path = os.path.normpath(r["path"])
            row = conn.execute(f"SELECT {ENTRY_COLS}, {HAS_CHILDREN} FROM entries e WHERE e.path = ?", (path,)).fetchone()
            if row:
                out.append({**_item(row), "mode": r["mode"]})
        return {"roots": out}


@router.get("/children")
def children(request: Request, path: str):
    """Subcarpetas de una carpeta, para el árbol y el treemap."""
    with _conn(request) as conn:
        parent = _entry_or_404(conn, path)
        rows = conn.execute(
            f"SELECT {ENTRY_COLS}, {HAS_CHILDREN} FROM entries e WHERE e.parent = ? AND e.is_dir = 1 ORDER BY e.size DESC",
            (path,),
        ).fetchall()
        items = [_item(r) for r in rows]
        files = conn.execute("SELECT count(*) FROM entries WHERE parent = ? AND is_dir = 0", (path,)).fetchone()[0]
        return {"entry": _item(parent), "children": items, "loose": max(0, parent["size"] - sum(i["size"] for i in items)), "loose_files": files}


@router.get("/list")
def list_folder(
    request: Request,
    path: str,
    type: str | None = None,
    since: int | None = Query(None, ge=1, description="modificados en los últimos N días"),
    older: int | None = Query(None, ge=1, description="sin modificar en más de N días"),
    tag: str | None = None,
    cloud: str | None = Query(None, pattern="^(solo_nube|local|fuera)$"),
    sort: str = Query("name", pattern="^(name|size|mtime|type)$"),
    order: str = Query("asc", pattern="^(asc|desc)$"),
):
    with _conn(request) as conn:
        parent = _entry_or_404(conn, path)
        where, params = ["e.parent = ?"], [path]
        if type == "carpeta":
            where.append("e.is_dir = 1")
        elif type == "otros":
            every = set().union(*insights.TYPES.values())
            where.append(f"e.is_dir = 0 AND (e.ext IS NULL OR e.ext NOT IN ({','.join('?' * len(every))}))")
            params += sorted(every)
        elif type:
            exts = insights.TYPES.get(type)
            if exts is None:
                raise HTTPException(422, "Tipo desconocido.")
            where.append(f"e.is_dir = 0 AND e.ext IN ({','.join('?' * len(exts))})")
            params += sorted(exts)
        if since:
            where.append("e.mtime >= ?")
            params.append(time.time() - since * 86400)
        if older:
            where.append("e.mtime < ?")
            params.append(time.time() - older * 86400)
        if tag:
            where.append("(',' || e.tags || ',' LIKE ? OR ',' || coalesce(m.tags, '') || ',' LIKE ?)")
            params += [f"%,{tag},%"] * 2
        if cloud == "solo_nube":
            where.append("e.cloud = 'solo_nube'")
        elif cloud == "local":
            where.append("e.cloud IN ('local', 'siempre_local')")
        elif cloud == "fuera":
            where.append("e.cloud IS NULL")
        key = {"name": "e.name COLLATE NOCASE", "size": "e.size", "mtime": "e.mtime", "type": "e.ext"}[sort]
        first = "e.is_dir DESC, " if sort in ("name", "type") else ""
        rows = conn.execute(
            f"""SELECT {ENTRY_COLS}, {HAS_CHILDREN}, m.tags AS user_tags FROM entries e
                LEFT JOIN user_meta m ON m.path = e.path
                WHERE {' AND '.join(where)} ORDER BY {first}{key} {order.upper()}, e.name COLLATE NOCASE LIMIT ?""",
            [*params, LIST_LIMIT + 1],
        ).fetchall()
        items = [_item(r) for r in rows[:LIST_LIMIT]]
        for i in items:
            i["user_tags"] = [t for t in (i["user_tags"] or "").split(",") if t]
        with_roots = _roots(conn)
        return {
            "entry": _item(parent),
            "mode": _mode(path, with_roots),
            "items": items,
            "truncated": len(rows) > LIST_LIMIT,
        }


@router.get("/entry")
def entry(request: Request, path: str):
    with _conn(request) as conn:
        r = _entry_or_404(conn, path)
        d = _item(r)
        d.update(ctime=r["ctime"], atime=r["atime"], attrs=insights.decode_attrs(r["attrs"]),
                 hash_partial=r["hash_partial"], hash_full=r["hash_full"])
        d["protected_reason"] = safety.protected_reason(path)
        d["owner"] = winfs.owner(path)
        d["mode"] = _mode(path, _roots(conn))
        proj = conn.execute(
            "SELECT * FROM projects WHERE path = ? OR (? > path || '\\' AND ? < path || ']') ORDER BY length(path) DESC LIMIT 1",
            (path, path, path),
        ).fetchone()
        d["project"] = dict(proj) if proj else None
        d["duplicates"] = (
            [x["path"] for x in conn.execute(
                "SELECT path FROM entries WHERE hash_full = ? AND path != ? ORDER BY path LIMIT 20", (r["hash_full"], path))]
            if r["hash_full"] else []
        )
        meta = conn.execute("SELECT tags, note, updated FROM user_meta WHERE path = ?", (path,)).fetchone()
        d["user_tags"] = [t for t in meta["tags"].split(",") if t] if meta else []
        d["note"] = meta["note"] if meta else ""
        return d


class MetaIn(BaseModel):
    path: str
    tags: list[str] = Field(default_factory=list, max_length=20)
    note: str = Field("", max_length=5000)


@router.post("/entry/meta")
def save_meta(request: Request, body: MetaIn):
    """Etiquetas y notas personales. Se guardan en el índice; el archivo no cambia."""
    tags = []
    for t in body.tags:
        t = t.strip().replace(",", " ")[:40]
        if t and t.lower() not in (x.lower() for x in tags):
            tags.append(t)
    with _conn(request) as conn:
        _entry_or_404(conn, body.path)
        with conn:
            if not tags and not body.note.strip():
                conn.execute("DELETE FROM user_meta WHERE path = ?", (body.path,))
            else:
                conn.execute(
                    "INSERT INTO user_meta(path, tags, note, updated) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(path) DO UPDATE SET tags = excluded.tags, note = excluded.note, updated = excluded.updated",
                    (body.path, ",".join(tags), body.note, time.time()),
                )
    return {"path": body.path, "user_tags": tags, "note": body.note}


@router.get("/tags")
def tags(request: Request):
    with _conn(request) as conn:
        user = set()
        for (t,) in conn.execute("SELECT tags FROM user_meta"):
            user.update(x for x in t.split(",") if x)
        return {
            "detected": ["git", "node", "python", "flutter", "regenerable", "git_interno", "sin_acceso"],
            "user": sorted(user, key=str.lower),
        }


# ---------------------------------------------------------------------- recomendaciones


@router.get("/recommendations")
def recommendations(request: Request):
    """Solo análisis: calcula qué podrías eliminar y por qué. No ejecuta nada."""
    with _conn(request) as conn:
        return recommend.analyze(conn)


class RulesIn(BaseModel):
    rules: dict[str, dict]


@router.put("/recommendations/rules")
def save_rules(request: Request, body: RulesIn):
    try:
        clean = recommend.validate_rules(body.rules)
    except ValueError as e:
        raise HTTPException(422, str(e))
    with _conn(request) as conn:
        stored = db.get_setting(conn, "reglas_recomendacion", {})
        for rid, values in clean.items():
            stored[rid] = {**stored.get(rid, {}), **values}
        db.set_setting(conn, "reglas_recomendacion", stored)
        return {"rules": recommend.rules_config(conn)}


class MarksIn(BaseModel):
    paths: list[str] = Field(min_length=1, max_length=20_000)
    marked: bool
    rule: str = ""


@router.post("/recommendations/marks")
def mark(request: Request, body: MarksIn):
    """Marcar una recomendación como aceptada. Solo se anota: enviar a la Papelera es otra acción, con vista previa."""
    with _conn(request) as conn, conn:
        if body.marked:
            known = {
                r["path"]
                for chunk in (body.paths[i:i + 500] for i in range(0, len(body.paths), 500))
                for r in conn.execute(f"SELECT path FROM entries WHERE path IN ({','.join('?' * len(chunk))})", chunk)
            }
            if len(known) != len({p.lower() for p in body.paths}):
                raise HTTPException(404, "Alguna ruta ya no está en el índice. Vuelve a escanear y revisa de nuevo.")
            conn.executemany(
                "INSERT INTO rec_marks(path, rule, marked) VALUES (?, ?, ?) ON CONFLICT(path) DO UPDATE SET marked = excluded.marked",
                [(p, body.rule, time.time()) for p in known],
            )
        else:
            conn.executemany("DELETE FROM rec_marks WHERE path = ?", [(p,) for p in body.paths])
        return {"marked": conn.execute("SELECT count(*) FROM rec_marks").fetchone()[0]}


# ---------------------------------------------------------------------- asistente


@router.get("/asistente/estado")
def asistente_estado(request: Request):
    with _conn(request) as conn:
        return {**agente.estado(conn), "lectura": request.app.state.lector.snapshot()}


@router.post("/asistente/preparar", status_code=202)
def asistente_preparar(request: Request):
    """Lee el texto de tus documentos para el asistente. Solo lee: no exige modo edición."""
    if request.app.state.scanner.running:
        raise HTTPException(409, "Hay un escaneo en curso. Espera a que termine.")
    request.app.state.lector.start()
    return request.app.state.lector.snapshot()


@router.post("/asistente/preparar/detener")
def asistente_detener(request: Request):
    request.app.state.lector.stop()
    return request.app.state.lector.snapshot()


class PreguntaIn(BaseModel):
    pregunta: str = Field(max_length=2000)
    historial: list[dict] = Field(default_factory=list, max_length=40)
    archivo: str | None = None


@router.post("/asistente/preguntar")
def asistente_preguntar(request: Request, body: PreguntaIn):
    """Respuesta en streaming (eventos de servidor): fuentes, pedazos de texto y fin."""
    if not body.pregunta.strip() and not body.archivo:
        raise HTTPException(422, "Escribe una pregunta.")
    if body.archivo:
        with _conn(request) as conn:
            if not conn.execute("SELECT 1 FROM doc_archivos WHERE path = ?", (body.archivo,)).fetchone():
                raise HTTPException(404, "El asistente todavía no leyó ese archivo. Pulsa Preparar y vuelve a intentar.")

    def eventos():
        conn = db.connect(request.app.state.db_path)
        try:
            for ev in agente.preguntar(conn, body.pregunta, body.historial, body.archivo):
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        finally:
            conn.close()

    return StreamingResponse(eventos(), media_type="text/event-stream", headers={"Cache-Control": "no-store"})


# ---------------------------------------------------------------------- configuración


def _normal_dir(raw: str) -> str:
    """Ruta absoluta de disco local, normalizada. Configuración no acepta rutas de red ni relativas."""
    if not isinstance(raw, str) or not safety.DRIVE_ABS.match(raw.strip()) or set(raw) & safety.BAD_CHARS or ":" in raw.strip()[2:]:
        raise HTTPException(422, "Escribe una ruta completa de un disco local, por ejemplo C:\\Users\\rodri\\Privado.")
    if any(p == ".." for p in re.split(r"[\\/]", raw)):
        raise HTTPException(422, "La ruta no puede contener '..'.")
    return os.path.normpath(raw.strip())


@router.get("/settings")
def settings(request: Request):
    with _conn(request) as conn:
        path = request.app.state.db_path
        backups = Path(path).parent / "respaldos"
        return {
            "protected_default": safety.default_protected(),
            "protected_rules": [
                "La raíz de cada disco",
                "Cualquier carpeta AppData",
                "El interior de cualquier .git",
                "$Recycle.Bin, System Volume Information y Recovery en la raíz de cada disco",
            ],
            "protected_extra": db.get_setting(conn, "rutas_protegidas", []),
            "roots": _roots(conn),
            "roots_custom": db.get_setting(conn, "scan_roots", None) is not None,
            "db": {
                "path": str(path),
                "size": os.path.getsize(path) if os.path.exists(path) else 0,
                "backups": str(backups),
                "last_backups": sorted((
                    {"name": f.name, "size": f.stat().st_size, "mtime": f.stat().st_mtime}
                    for f in backups.glob("orden-*.db")
                ), key=lambda b: -b["mtime"])[:5] if backups.is_dir() else [],
            },
        }


class ProtectedIn(BaseModel):
    path: str


@router.post("/settings/protected")
def add_protected(request: Request, body: ProtectedIn):
    """Solo agrega. No existe una ruta para quitar: la lista protegida nunca se achica desde la app."""
    path = _normal_dir(body.path)
    if os.path.splitdrive(path)[1] in ("", "\\"):
        raise HTTPException(422, "La raíz de cada disco ya está protegida.")
    with _conn(request) as conn:
        extra = db.get_setting(conn, "rutas_protegidas", [])
        if safety.protected_reason(path, extra):
            raise HTTPException(409, f"Ya está protegida: {safety.protected_reason(path, extra)}")
        extra.append(path)
        db.set_setting(conn, "rutas_protegidas", extra)
        safety.EXTRA_PROTECTED[:] = extra
        return {"protected_extra": extra}


class RootIn(BaseModel):
    path: str
    mode: Literal["completo", "carpetas"]


class RootsIn(BaseModel):
    roots: list[RootIn] | None = Field(default=None, max_length=50)  # None: volver a las de siempre


@router.put("/settings/roots")
def save_roots(request: Request, body: RootsIn):
    """Qué carpetas escanea Orden PC. Aplica en el próximo escaneo."""
    if request.app.state.scanner.running:
        raise HTTPException(409, "Hay un escaneo en curso. Espera a que termine para cambiar las carpetas.")
    with _conn(request) as conn:
        if body.roots is None:
            conn.execute("DELETE FROM settings WHERE key = 'scan_roots'")
            conn.commit()
            return {"roots": _roots(conn), "roots_custom": False}
        if not body.roots:
            raise HTTPException(422, "Deja al menos una carpeta para escanear.")
        roots, seen = [], set()
        for r in body.roots:
            path = _normal_dir(r.path)
            if not os.path.isdir(path):
                raise HTTPException(422, f"No existe la carpeta {path}.")
            if path.lower() in seen:
                continue
            seen.add(path.lower())
            roots.append({"path": path, "mode": r.mode, **({"depth": 3} if r.mode == "carpetas" else {})})
        db.set_setting(conn, "scan_roots", roots)
        return {"roots": roots, "roots_custom": True}


@router.post("/settings/backup")
def backup(request: Request):
    """Copia consistente de la base de datos (VACUUM INTO), aunque la app esté abierta."""
    folder = Path(request.app.state.db_path).parent / "respaldos"
    folder.mkdir(exist_ok=True)
    target = folder / time.strftime("orden-%Y%m%d-%H%M%S.db")
    if target.exists():
        raise HTTPException(409, "Ya hay una copia de este mismo segundo. Espera un momento.")
    with _conn(request) as conn:
        conn.execute("VACUUM INTO ?", (str(target),))
    return {"path": str(target), "size": target.stat().st_size}


# ---------------------------------------------------------------------- organizador


@router.get("/organizer")
def organizer_view(request: Request):
    """Propuesta del organizador. Solo lee nombres y atributos: no mueve nada."""
    with _conn(request) as conn:
        try:
            return organizer.propose(conn)
        except organizer.RuleError as e:
            raise HTTPException(422, str(e))


@router.post("/organizer/sugerir", status_code=202)
def organizer_sugerir(request: Request):
    """El asistente lee los documentos por clasificar y sugiere su carpeta. Solo sugiere: no exige modo edición."""
    if request.app.state.scanner.running or request.app.state.lector.leyendo:
        raise HTTPException(409, "Espera a que termine el escaneo o la lectura de documentos.")
    if not request.app.state.sugeridor.start(organizer.variables()):
        raise HTTPException(409, "El asistente ya está revisando tus documentos.")
    return request.app.state.sugeridor.snapshot()


@router.post("/organizer/sugerir/detener")
def organizer_sugerir_detener(request: Request):
    request.app.state.sugeridor.stop()
    return request.app.state.sugeridor.snapshot()


@router.get("/organizer/sugerencias")
def organizer_sugerencias(request: Request):
    return request.app.state.sugeridor.snapshot()


class StructureIn(BaseModel):
    materias: list[str]
    carpetas: list[str]
    origenes: list[str]


@router.put("/organizer/structure")
def save_structure(request: Request, body: StructureIn):
    """Guarda la estructura objetivo. Es configuración: no crea carpetas (eso es otra acción, con vista previa)."""
    with _conn(request) as conn:
        try:
            db.set_setting(conn, "estructura", organizer.validate_structure(body.model_dump(), organizer.variables()))
        except organizer.RuleError as e:
            raise HTTPException(422, str(e))
        return organizer.propose(conn)


class OrgRulesIn(BaseModel):
    rules: list[dict] = Field(max_length=200)


@router.put("/organizer/rules")
def save_org_rules(request: Request, body: OrgRulesIn):
    with _conn(request) as conn:
        try:
            db.set_setting(conn, "reglas_organizador", organizer.validate_rules(body.rules, organizer.variables()))
        except organizer.RuleError as e:
            raise HTTPException(422, str(e))
        return organizer.propose(conn)


# ---------------------------------------------------------------------- acciones de escritura


class MoveIn(BaseModel):
    src: str
    dest: str
    name: str


class PlanIn(BaseModel):
    kind: Literal["crear", "renombrar", "mover", "papelera", "deshacer", "organizar"]
    path: str | None = None
    paths: list[str] = Field(default_factory=list, max_length=20_000)
    dest: str | None = None
    name: str | None = None
    ids: list[int] = Field(default_factory=list, max_length=20_000)
    moves: list[MoveIn] = Field(default_factory=list, max_length=5_000)
    folders: list[str] = Field(default_factory=list, max_length=1_000)


@router.post("/ops/plan")
def make_plan(request: Request, body: PlanIn):
    """Vista previa: dice exactamente qué cambiaría. No toca nada."""
    o: ops.Ops = request.app.state.ops
    with _conn(request) as conn:
        try:
            if body.kind == "crear":
                plan = o.plan_create(conn, body.path or "", body.name or "")
            elif body.kind == "renombrar":
                plan = o.plan_rename(conn, body.path or "", body.name or "")
            elif body.kind == "mover":
                plan = o.plan_move(conn, body.paths, body.dest or "")
            elif body.kind == "papelera":
                plan = o.plan_trash(conn, body.paths)
            elif body.kind == "organizar":
                plan = o.plan_organize(conn, [m.model_dump() for m in body.moves], body.folders)
            else:
                plan = o.plan_undo(conn, body.ids)
        except ops.PlanError as e:
            raise HTTPException(422, str(e))
        return plan.to_dict()


class ApplyIn(BaseModel):
    ack: bool = False


@router.post("/ops/apply/{plan_id}", dependencies=[Depends(require_edit_mode)])
def apply_plan(request: Request, plan_id: str, body: ApplyIn):
    with _conn(request) as conn:
        try:
            return request.app.state.ops.apply(conn, plan_id, body.ack)
        except ops.PlanError as e:
            raise HTTPException(409, str(e))


@router.get("/history")
def history(request: Request, op: str | None = None, result: str | None = None, q: str | None = None):
    with _conn(request) as conn:
        return {"items": ops.history(conn, op, result, q)}


@router.get("/history.csv")
def history_csv(request: Request):
    with _conn(request) as conn:
        return Response(
            ops.history_csv(conn),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="historial-orden-pc.csv"'},
        )


class OpenIn(BaseModel):
    path: str
    app: Literal["explorer", "vscode"]


def _vscode() -> str | None:
    # Code.exe directo, nunca code.cmd: pasar rutas a un .cmd permite inyectar órdenes con nombres como "a&b".
    candidates = [
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Microsoft VS Code", "Code.exe"),
        os.path.join(os.environ.get("ProgramFiles", ""), "Microsoft VS Code", "Code.exe"),
    ]
    return next((c for c in candidates if os.path.isfile(c)), None)


@router.post("/open", dependencies=[Depends(require_edit_mode)])
def open_in(request: Request, body: OpenIn):
    with _conn(request) as conn:
        row = _entry_or_404(conn, body.path)
    if not os.path.lexists(body.path):
        raise HTTPException(404, "Ya no existe en esa ubicación. Vuelve a escanear.")
    if body.app == "explorer":
        args = ["explorer.exe", body.path] if row["is_dir"] else ["explorer.exe", "/select,", body.path]
    else:
        exe = _vscode()
        if not exe:
            raise HTTPException(404, "No encontré Visual Studio Code instalado.")
        args = [exe, body.path]
    subprocess.Popen(args, creationflags=subprocess.DETACHED_PROCESS)
    return {"ok": True}


# ---------------------------------------------------------------------- apps


@router.get("/apps")
def list_apps(request: Request, refresh: bool = False):
    with _conn(request) as conn:
        items = [asdict(a) for a in apps.inventory.list(conn, refresh)]
    by_cat = {c: sum(1 for a in items if a["category"] == c) for c in apps.CATEGORIES}
    return {
        "apps": items,
        "categories": apps.CATEGORIES,
        "summary": {
            "count": len(items),
            "updates": sum(1 for a in items if a["available"]),
            "review": sum(1 for a in items if a["review"]),
            "by_category": by_cat,
        },
    }


class AppMetaIn(BaseModel):
    key: str
    category: str | None = None
    review: Literal[0, 1] | None = None
    note: str = Field("", max_length=1000)


@router.post("/apps/meta")
def app_meta(request: Request, body: AppMetaIn):
    """Categoría y marca de revisión. Solo se guardan en Orden PC: la app no cambia."""
    fields = {k: getattr(body, k) for k in ("category", "review", "note") if k in body.model_fields_set}
    with _conn(request) as conn:
        try:
            apps.save_meta(conn, body.key, **fields)
        except ValueError as e:
            raise HTTPException(422, str(e))
    return {"ok": True}


@router.get("/apps/search")
def app_search(q: str):
    try:
        return {"results": apps.search(q)}
    except ValueError as e:
        raise HTTPException(422, str(e))


class AppPlanIn(BaseModel):
    action: Literal["desinstalar", "actualizar", "instalar"]
    key: str | None = None
    winget_id: str | None = None
    name: str | None = Field(None, max_length=200)


@router.post("/apps/plan")
def app_plan(request: Request, body: AppPlanIn):
    """Confirmación: qué se va a abrir y con qué avisos. No ejecuta nada."""
    with _conn(request) as conn:
        current = apps.inventory.list(conn) if body.action != "instalar" else []
    try:
        p = request.app.state.app_ops.plan(current, body.action, body.key, body.winget_id, body.name)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return asdict(p)


@router.post("/apps/run/{plan_id}", dependencies=[Depends(require_edit_mode)])
def app_run(request: Request, plan_id: str, body: ApplyIn):
    try:
        p = request.app.state.app_ops.run(plan_id, body.ack)
    except ValueError as e:
        raise HTTPException(409, str(e))
    except OSError as e:
        raise HTTPException(500, f"Windows no pudo abrirlo: {e}")
    with _conn(request) as conn, conn:
        conn.execute(
            """INSERT INTO audit_log(ts, batch, title, op, src, dst, result, message, reversible)
               VALUES (?, ?, ?, ?, ?, ?, 'iniciado', ?, 0)""",
            (time.time(), p.id, p.title, f"app_{p.action}", p.app, p.command,
             "Se abrió la ventana oficial; el resultado depende de lo que elijas ahí."),
        )
    return {"ok": True, "title": p.title}


@router.get("/search")
def search(request: Request, q: str, limit: int = Query(200, ge=1, le=500)):
    q = q.strip()
    if not q:
        return {"results": []}
    # LIKE sobre la tabla FTS usa el índice de trigramas (con 3 caracteres o más; con menos, recorre).
    # Sin ESCAPE para no perder el índice: '_' y '%' del texto actúan como comodines, lo que solo amplía.
    with _conn(request) as conn:
        rows = conn.execute(
            f"""SELECT {ENTRY_COLS}, {HAS_CHILDREN}
                FROM entries_fts f JOIN entries e ON e.id = f.rowid
                WHERE f.name LIKE :p OR f.path LIKE :p
                ORDER BY e.name LIKE :p DESC, e.is_dir DESC, e.size DESC
                LIMIT :limit""",
            {"p": f"%{q}%", "limit": limit},
        ).fetchall()
        return {"results": [_item(r) for r in rows]}
