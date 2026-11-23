"""Recomendaciones de eliminación. Solo análisis: nada aquí toca archivos (ni los abre, salvo para leer
la versión de un instalador o el índice de un .zip, y nunca si están solo en la nube)."""

import os
import re
import sqlite3
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime

from orden_pc import apps, db, insights, safety, winfs

CONFIDENCES = ("alta", "media", "baja")

RULES: dict[str, dict] = {
    "instaladores": {
        "label": "Instaladores de apps que ya tienes",
        "description": "Archivos .exe y .msi de programas que ya están instalados en tu equipo.",
        "defaults": {"enabled": True, "confianza": "alta"},
    },
    "duplicados": {
        "label": "Copias exactas",
        "description": "Archivos idénticos byte a byte. Se conserva el que está en tu estructura, el que no tiene marca de copia o el más reciente.",
        "defaults": {"enabled": True, "confianza": "alta"},
    },
    "casi_duplicados": {
        "label": "Posibles copias por nombre",
        "description": "Archivos con “(1)”, “- Copy” o “- copia” junto al original. Compáralos antes de decidir.",
        "defaults": {"enabled": True, "confianza": "media"},
    },
    "regenerables": {
        "label": "Carpetas que se pueden regenerar",
        "description": "node_modules, .venv, __pycache__, dist, build y .next en proyectos sin actividad reciente.",
        "defaults": {"enabled": True, "confianza": "media", "dias": 60},
    },
    "zip_descomprimido": {
        "label": "Comprimidos ya extraídos",
        "description": "Archivos .zip cuyo contenido ya está descomprimido en una carpeta con el mismo nombre, a su lado.",
        "defaults": {"enabled": True, "confianza": "media", "coincidencia": 90},
    },
    "capturas": {
        "label": "Capturas de pantalla antiguas",
        "description": "Capturas que llevan tiempo sin moverse de donde cayeron.",
        "defaults": {"enabled": True, "confianza": "baja", "dias": 90},
    },
    "grandes": {
        "label": "Archivos grandes sin abrir",
        "description": "Archivos pesados que nadie abre desde hace meses.",
        "defaults": {"enabled": True, "confianza": "baja", "mb": 500, "dias": 180},
    },
}
NUMERIC_LIMITS = {"dias": (1, 3650), "mb": (10, 100_000), "coincidencia": (50, 100)}

COPY_NAME = re.compile(r"^(?P<base>.+?)(?:\s*-\s*(?:copy|copia)(?:\s*\(\d+\))?|\s*\(\d+\))$", re.I)
SCREENSHOT = re.compile(r"^(captura de pantalla|captura|screenshot|screen shot|recorte de pantalla|recorte)", re.I)
SCREENSHOT_DIRS = {"screenshots", "capturas de pantalla"}
VERSION = re.compile(r"(\d+)\.(\d+)")
REGEN_HOW = {
    "node_modules": "npm install",
    ".venv": "uv sync o pip install",
    "venv": "pip install",
    "__pycache__": "Python, que la recrea solo",
    "dist": "volver a compilar el proyecto",
    "build": "volver a compilar el proyecto",
    ".next": "volver a compilar el proyecto",
}
STOP = {
    "setup", "installer", "install", "x64", "x86", "amd64", "arm64", "win", "win32", "win64", "windows", "bit",
    "user", "system", "microsoft", "the", "for", "and", "de", "del", "la", "el", "version", "full", "offline",
    "online", "web", "js", "inc", "corporation", "corp", "llc", "ltd", "exe", "msi",
}


# ---------------------------------------------------------------------- configuración


def rules_config(conn: sqlite3.Connection) -> dict[str, dict]:
    stored = db.get_setting(conn, "reglas_recomendacion", {})
    return {rid: {**r["defaults"], **{k: v for k, v in stored.get(rid, {}).items() if k in r["defaults"]}} for rid, r in RULES.items()}


def validate_rules(body: dict) -> dict[str, dict]:
    """Valida lo que llega de la interfaz. Lanza ValueError con un mensaje para mostrar."""
    out = {}
    for rid, values in body.items():
        if rid not in RULES or not isinstance(values, dict):
            raise ValueError(f"No existe la regla «{rid}».")
        clean = {}
        for k, v in values.items():
            if k not in RULES[rid]["defaults"]:
                raise ValueError(f"La regla «{RULES[rid]['label']}» no tiene el ajuste «{k}».")
            if k == "enabled":
                if not isinstance(v, bool):
                    raise ValueError("Activar o desactivar una regla debe ser sí o no.")
            elif k == "confianza":
                if v not in CONFIDENCES:
                    raise ValueError("La confianza debe ser alta, media o baja.")
            else:
                lo, hi = NUMERIC_LIMITS[k]
                if not isinstance(v, int) or isinstance(v, bool) or not lo <= v <= hi:
                    raise ValueError(f"«{k}» debe ser un número entero entre {lo} y {hi}.")
            clean[k] = v
        out[rid] = clean
    return out


# ---------------------------------------------------------------------- utilidades


def name_tokens(text: str | None) -> set[str]:
    """Palabras de un nombre, partiendo CamelCase y uniendo pares (GitHubDesktop -> git, hub, github, desktop...)."""
    out: set[str] = set()
    for word in re.findall(r"[A-Za-z0-9]+", text or ""):
        parts = [p.lower() for p in re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+", word)]
        out.add(word.lower())
        out.update(parts)
        out.update(a + b for a, b in zip(parts, parts[1:]))
    return {t for t in out if len(t) > 1 and t not in STOP and not re.fullmatch(r"v?\d+", t)}


def app_key(name: str) -> list[str]:
    """Palabras que identifican una app instalada: sin paréntesis, versiones ni palabras genéricas."""
    words = re.findall(r"[A-Za-z0-9]+", re.sub(r"\(.*?\)", " ", name))
    key = [w.lower() for w in words if len(w) > 1 and w.lower() not in STOP and not re.fullmatch(r"v?\d+", w.lower())]
    return key[:3]


def product_name(path: str) -> str | None:
    """Nombre del producto en la información de versión de un .exe. Lee solo la cabecera."""
    import win32api

    try:
        lang, cp = win32api.GetFileVersionInfo(path, "\\VarFileInfo\\Translation")[0]
        for field_name in ("ProductName", "FileDescription"):
            v = win32api.GetFileVersionInfo(path, f"\\StringFileInfo\\{lang:04x}{cp:04x}\\{field_name}")
            if v and v.strip():
                return v.strip()
    except Exception:  # sin recurso de versión, archivo bloqueado
        return None
    return None


def _version(text: str | None) -> tuple[int, int] | None:
    m = VERSION.search(text or "")
    return (int(m[1]), int(m[2])) if m else None


def _days(ts: float | None, now: float) -> int:
    return int((now - (ts or now)) // 86400)


def _date(ts: float | None) -> str:
    return datetime.fromtimestamp(ts).strftime("%d/%m/%Y") if ts else "fecha desconocida"


@dataclass
class Ctx:
    conn: sqlite3.Connection
    home: str
    now: float
    where: str
    params: list
    projects: list[sqlite3.Row] = field(default_factory=list)  # más profundos primero
    apps: list[dict] | None = None

    def project_of(self, path: str) -> sqlite3.Row | None:
        low = path.lower()
        return next((p for p in self.projects if low.startswith(p["path"].lower() + "\\")), None)

    def in_structure(self, path: str) -> bool:
        return bool(re.match(rf"^{re.escape(self.home.lower())}\\(onedrive\\\d\d_|dev\\)", path.lower()))

    def files(self, extra: str, params: list = ()) -> list[sqlite3.Row]:
        return self.conn.execute(
            f"SELECT path, parent, name, ext, size, mtime, atime, cloud, hash_full FROM entries WHERE is_dir = 0 AND {self.where} AND {extra}",
            [*self.params, *params],
        ).fetchall()


def _rec(r, reason: str, **detail) -> dict:
    return {"path": r["path"], "name": r["name"], "parent": r["parent"], "size": r["size"], "reason": reason, "detail": detail}


# ---------------------------------------------------------------------- reglas


def rule_installers(ctx: Ctx, cfg: dict):
    if ctx.apps is None:
        ctx.apps = apps.installed_apps()
    keyed = [(a, set(k)) for a in ctx.apps if (k := app_key(a["name"]))]
    for r in ctx.files("ext IN ('exe', 'msi')"):
        product = product_name(r["path"]) if r["ext"] == "exe" and winfs.safe_to_read(r["path"]) else None
        tokens = name_tokens(product) | name_tokens(os.path.splitext(r["name"])[0])
        candidates = [(a, k) for a, k in keyed if k <= tokens]
        if not candidates:
            continue
        app, _ = max(candidates, key=lambda ak: len(ak[1]))
        mine, theirs = _version(product) or _version(r["name"]), _version(app["name"])
        if mine and theirs and mine != theirs:
            continue  # otra versión: quizá lo guardas para actualizar
        yield _rec(
            r,
            f"Ya tienes instalado {app['name']}. Este instalador ya cumplió su función; si algún día lo necesitas, se descarga de nuevo.",
            app=app["name"],
            product=product,
        )


def _is_copy_name(name: str) -> bool:
    return bool(COPY_NAME.match(os.path.splitext(name)[0]))


def rule_duplicates(ctx: Ctx, cfg: dict):
    rows = ctx.files(
        f"hash_full IS NOT NULL AND hash_full IN (SELECT hash_full FROM entries WHERE is_dir = 0 AND {ctx.where} GROUP BY hash_full HAVING count(*) > 1)",
        ctx.params,
    )
    groups: dict[str, list] = {}
    for r in rows:
        if not ctx.project_of(r["path"]):  # dentro de un repo, borrar rompe el proyecto
            groups.setdefault(r["hash_full"], []).append(r)
    for group in groups.values():
        if len(group) < 2:
            continue
        keep = sorted(group, key=lambda r: (not ctx.in_structure(r["path"]), _is_copy_name(r["name"]), -(r["mtime"] or 0), len(r["path"])))[0]
        if ctx.in_structure(keep["path"]):
            why = "ya está en tu estructura de carpetas"
        elif not _is_copy_name(keep["name"]) and any(_is_copy_name(g["name"]) for g in group):
            why = "no tiene marca de copia en el nombre"
        else:
            why = "es el más reciente"
        for r in group:
            if r is keep:
                continue
            yield _rec(
                r,
                f"Es idéntico byte a byte a «{keep['name']}» en {keep['parent']}. Se conserva ese porque {why}.",
                keep={"path": keep["path"], "name": keep["name"], "size": keep["size"], "mtime": keep["mtime"]},
            )


def rule_near_duplicates(ctx: Ctx, cfg: dict):
    for r in ctx.files("(name LIKE '%(%' OR name LIKE '%copy%' OR name LIKE '%copia%')"):
        stem, ext = os.path.splitext(r["name"])
        m = COPY_NAME.match(stem)
        if not m or ctx.project_of(r["path"]):
            continue
        original = None
        for base in dict.fromkeys((m["base"], m["base"].rstrip())):
            original = ctx.conn.execute(
                "SELECT path, name, size, mtime FROM entries WHERE path = ? AND is_dir = 0", (os.path.join(r["parent"], base + ext),)
            ).fetchone()
            if original:
                break
        if not original:
            continue
        if original["size"] == r["size"]:
            reason = f"Parece una copia de «{original['name']}», que está en la misma carpeta y pesa lo mismo. Compáralos antes de decidir."
        else:
            reason = (
                f"Se llama como «{original['name']}», que está en la misma carpeta, pero pesa distinto: "
                "puede ser otra versión o un archivo diferente. Compáralos antes de decidir."
            )
        yield _rec(
            r,
            reason,
            original=dict(original),
            copy={"size": r["size"], "mtime": r["mtime"]},
        )


def rule_regenerable(ctx: Ctx, cfg: dict):
    cutoff = ctx.now - cfg["dias"] * 86400
    rows = ctx.conn.execute(
        f"SELECT path, parent, name, size, mtime FROM entries WHERE is_dir = 1 AND ',' || tags || ',' LIKE '%,regenerable,%' AND {ctx.where}",
        ctx.params,
    ).fetchall()
    for r in rows:
        proj = ctx.project_of(r["path"])
        if not proj or proj["last_activity"] is None or proj["last_activity"] >= cutoff:
            continue
        how = REGEN_HOW.get(r["name"].lower(), "volver a compilar el proyecto")
        days = _days(proj["last_activity"], ctx.now)
        yield _rec(
            r,
            f"Se vuelve a generar con {how}. El proyecto «{os.path.basename(proj['path'])}» no tiene cambios desde hace {days} días.",
            project=proj["path"],
            inactive_days=days,
        )


def rule_extracted_zip(ctx: Ctx, cfg: dict):
    for r in ctx.files("ext = 'zip'"):
        stem = os.path.splitext(r["name"])[0]
        folder = os.path.join(r["parent"], stem)
        if not ctx.conn.execute("SELECT 1 FROM entries WHERE path = ? AND is_dir = 1", (folder,)).fetchone():
            continue
        if not winfs.safe_to_read(r["path"]):
            continue
        try:
            with zipfile.ZipFile(r["path"]) as z:
                members = [i for i in z.infolist() if not i.is_dir()][:5000]
        except (OSError, zipfile.BadZipFile, RuntimeError):
            continue
        if not members:
            continue
        names = [i.filename.replace("/", "\\") for i in members]
        prefix = stem.lower() + "\\"
        if all(n.lower().startswith(prefix) for n in names):  # el zip trae su propia carpeta raíz
            names = [n[len(prefix):] for n in names]
        extracted = {
            p.lower(): s
            for p, s in ctx.conn.execute(
                "SELECT path, size FROM entries WHERE is_dir = 0 AND path > ? AND path < ?", (folder + "\\", folder + "]")
            )
        }
        hits = sum(1 for n, i in zip(names, members) if extracted.get(os.path.join(folder, n).lower()) == i.file_size)
        pct = round(hits * 100 / len(members))
        if pct >= cfg["coincidencia"]:
            yield _rec(
                r,
                f"Su contenido ya está descomprimido en la carpeta «{stem}», a su lado: coinciden {hits} de {len(members)} archivos ({pct} %).",
                folder=folder,
                match_pct=pct,
            )


def rule_screenshots(ctx: Ctx, cfg: dict):
    exts = sorted(insights.TYPES["imagenes"])
    cutoff = ctx.now - cfg["dias"] * 86400
    for r in ctx.files(f"ext IN ({','.join('?' * len(exts))}) AND mtime < ?", [*exts, cutoff]):
        if SCREENSHOT.match(r["name"]) or os.path.basename(r["parent"]).lower() in SCREENSHOT_DIRS:
            yield _rec(
                r,
                f"Captura de pantalla de hace {_days(r['mtime'], ctx.now)} días. Si todavía la necesitas, muévela a la carpeta de su materia o proyecto.",
                age_days=_days(r["mtime"], ctx.now),
            )


def rule_big(ctx: Ctx, cfg: dict):
    cutoff = ctx.now - cfg["dias"] * 86400
    for r in ctx.files("size >= ? AND max(coalesce(atime, 0), coalesce(mtime, 0)) < ?", [cfg["mb"] * 1024 * 1024, cutoff]):
        last = max(r["atime"] or 0, r["mtime"] or 0)
        yield _rec(
            r,
            f"Ocupa mucho y, según Windows, no se abre desde el {_date(last)} (hace {_days(last, ctx.now)} días).",
            last_open=last,
        )


RULE_FUNCS = {
    "instaladores": rule_installers,
    "duplicados": rule_duplicates,
    "casi_duplicados": rule_near_duplicates,
    "regenerables": rule_regenerable,
    "zip_descomprimido": rule_extracted_zip,
    "capturas": rule_screenshots,
    "grandes": rule_big,
}


# ---------------------------------------------------------------------- motor


def analyze(conn: sqlite3.Connection) -> dict:
    cfg = rules_config(conn)
    h = insights.home()
    where, params = insights.user_scope_sql(h)
    ctx = Ctx(
        conn=conn, home=h, now=time.time(), where=where, params=params,
        projects=conn.execute("SELECT * FROM projects ORDER BY length(path) DESC").fetchall(),
    )
    items: list[dict] = []
    seen: set[str] = set()
    # El orden de las reglas es la prioridad: cada ruta aparece una vez, con su motivo más fuerte.
    for rid, fn in RULE_FUNCS.items():
        c = cfg[rid]
        if not c["enabled"]:
            continue
        for rec in fn(ctx, c):
            key = rec["path"].lower()
            if key in seen or safety.protected_reason(rec["path"]):
                continue
            seen.add(key)
            items.append({**rec, "rule": rid, "confidence": c["confianza"]})

    marked = {p.lower() for (p,) in conn.execute("SELECT path FROM rec_marks")}
    for i in items:
        i["marked"] = i["path"].lower() in marked
    items.sort(key=lambda i: (CONFIDENCES.index(i["confidence"]), -i["size"]))
    by_conf = {c: sum(i["size"] for i in items if i["confidence"] == c) for c in CONFIDENCES}
    return {
        "rules": [{"id": rid, "label": r["label"], "description": r["description"], **cfg[rid]} for rid, r in RULES.items()],
        "items": items,
        "summary": {
            "count": len(items),
            "total": sum(by_conf.values()),
            "by_confidence": by_conf,
            "by_rule": {rid: {"count": sum(1 for i in items if i["rule"] == rid), "bytes": sum(i["size"] for i in items if i["rule"] == rid)} for rid in RULES},
            "marked": {"count": sum(i["marked"] for i in items), "bytes": sum(i["size"] for i in items if i["marked"])},
        },
    }
