"""Lecturas agregadas del índice para el Panel: categorías de uso, tarjetas de estado y línea de tiempo."""

import os
import shutil
import sqlite3
from datetime import datetime, timedelta

from orden_pc import db

TYPES: dict[str, set[str]] = {
    "documentos": {"pdf", "doc", "docx", "odt", "rtf", "txt", "md", "xls", "xlsx", "ods", "csv", "ppt", "pptx", "odp", "epub"},
    "imagenes": {"jpg", "jpeg", "png", "gif", "webp", "heic", "bmp", "svg", "tif", "tiff", "raw", "psd", "ai"},
    "video": {"mp4", "mov", "mkv", "avi", "webm", "wmv", "m4v"},
    "audio": {"mp3", "wav", "flac", "m4a", "aac", "ogg", "wma"},
    "codigo": {"py", "js", "ts", "tsx", "jsx", "java", "c", "cpp", "h", "cs", "go", "rs", "dart", "kt", "swift", "rb",
               "php", "html", "css", "scss", "json", "yml", "yaml", "toml", "sql", "sh", "ps1", "ipynb"},
    "comprimidos": {"zip", "rar", "7z", "tar", "gz", "tgz", "bz2", "xz"},
    "instaladores": {"exe", "msi", "msix", "appx", "appxbundle"},
}
MULTIMEDIA = TYPES["imagenes"] | TYPES["video"] | TYPES["audio"]

DEFAULT_CATEGORY_RULES = {
    # Rutas editables desde Configuración (clave de ajustes "categorias").
    "juegos": [r"C:\Riot Games", r"C:\Program Files\Epic Games", r"C:\Program Files (x86)\Steam\steamapps",
               r"C:\XboxGames", r"C:\Program Files\EA Games", r"C:\Program Files (x86)\Ubisoft"],
    "sistema": [r"C:\Windows", r"C:\ProgramData", r"C:\Drivers", r"C:\Recovery", r"C:\$Recycle.Bin",
                r"C:\System Volume Information"],
    "apps": [r"C:\Program Files", r"C:\Program Files (x86)"],
}

CATEGORY_LABELS = {
    "juegos": "Juegos",
    "desarrollo": "Desarrollo",
    "documentos": "Documentos",
    "multimedia": "Multimedia",
    "apps": "Apps y sus datos",
    "sistema": "Sistema",
    "otros": "Otros",
}


def home() -> str:
    return os.path.normpath(os.environ["USERPROFILE"])


def inside(path: str) -> tuple[str, str]:
    """Rango (exclusivo) de todo lo que está dentro de `path`: '\\' es 0x5C y ']' es 0x5D."""
    return path + "\\", path + "]"


def user_scope_sql(h: str) -> tuple[str, list]:
    """Tus carpetas: dentro de la carpeta de usuario, fuera de AppData y de las carpetas ocultas de primer nivel."""
    lo, hi = inside(h)
    alo, ahi = inside(os.path.join(h, "AppData"))
    return (
        "path > ? AND path < ? AND NOT (path > ? AND path < ?) AND path NOT LIKE ?",
        [lo, hi, alo, ahi, os.path.join(h, ".") + "%"],
    )


def _size(conn: sqlite3.Connection, path: str) -> int:
    row = conn.execute("SELECT size FROM entries WHERE path = ?", (path,)).fetchone()
    return row["size"] if row else 0


def top_projects(conn: sqlite3.Connection) -> list[str]:
    """Proyectos que no están dentro de otro (Proyectos contiene video-semiconductores: cuenta una vez)."""
    tops: list[str] = []
    for (p,) in conn.execute("SELECT path FROM projects ORDER BY path COLLATE NOCASE"):
        if not any(p.lower().startswith(t.lower() + "\\") for t in tops):
            tops.append(p)
    return tops


def _ext_bytes(conn: sqlite3.Connection, where: str, params: list, exts: set[str]) -> int:
    marks = ",".join("?" * len(exts))
    return conn.execute(
        f"SELECT coalesce(sum(size), 0) FROM entries WHERE is_dir = 0 AND {where} AND ext IN ({marks})",
        [*params, *exts],
    ).fetchone()[0]


def categories(conn: sqlite3.Connection, drive: str = "C:\\") -> dict:
    usage = shutil.disk_usage(drive)
    rules = db.get_setting(conn, "categorias", DEFAULT_CATEGORY_RULES)
    h = home()
    out = dict.fromkeys(CATEGORY_LABELS, 0)

    games = [p for p in rules["juegos"] if p.upper().startswith(drive[:2].upper())]
    out["juegos"] = sum(_size(conn, p) for p in games)

    root_path = os.path.normpath(drive)
    root = conn.execute("SELECT size FROM entries WHERE path = ?", (root_path,)).fetchone()
    child_dirs = conn.execute("SELECT coalesce(sum(size), 0) FROM entries WHERE parent = ?", (root_path,)).fetchone()[0]
    root_files = (root["size"] - child_dirs) if root else 0  # pagefile.sys, hiberfil.sys, swapfile.sys
    out["sistema"] = sum(_size(conn, p) for p in rules["sistema"]) + root_files

    apps = sum(_size(conn, p) for p in rules["apps"])
    apps -= sum(_size(conn, g) for g in games if any(g.lower().startswith(a.lower() + "\\") for a in rules["apps"]))
    out["apps"] = apps + _size(conn, os.path.join(h, "AppData"))

    projects = [p for p in top_projects(conn) if p.lower().startswith(h.lower() + "\\")]
    dot_dirs = [r["path"] for r in conn.execute("SELECT path FROM entries WHERE parent = ? AND is_dir = 1 AND name LIKE '.%'", (h,))]
    out["desarrollo"] = sum(_size(conn, p) for p in projects + dot_dirs)

    where, params = user_scope_sql(h)
    for key, exts in (("documentos", TYPES["documentos"]), ("multimedia", MULTIMEDIA)):
        total = _ext_bytes(conn, where, params, exts)
        total -= sum(_ext_bytes(conn, "path > ? AND path < ?", list(inside(p)), exts) for p in projects)
        out[key] = total

    used = usage.used
    out["otros"] = max(0, used - sum(v for k, v in out.items() if k != "otros"))
    return {
        "drive": root_path.rstrip("\\"),
        "total": usage.total,
        "used": used,
        "free": usage.free,
        "categories": [{"key": k, "label": CATEGORY_LABELS[k], "bytes": v} for k, v in out.items()],
    }


def _location(path: str, h: str) -> str:
    """Primer nivel bajo tu carpeta (Desktop, Documents...) o la carpeta raíz fuera de ella."""
    if path.lower().startswith(h.lower() + "\\"):
        return path[len(h) + 1:].split("\\")[0]
    return "\\".join(path.split("\\")[:2])


def status_cards(conn: sqlite3.Connection) -> dict:
    h = home()
    downloads = os.path.join(h, "Downloads")
    dl = conn.execute("SELECT count(*) AS n, coalesce(sum(size), 0) AS b FROM entries WHERE parent = ?", (downloads,)).fetchone()

    where, params = user_scope_sql(h)
    dups = conn.execute(
        f"""SELECT count(*) AS groups, coalesce(sum(wasted), 0) AS wasted FROM (
                SELECT sum(size) - max(size) AS wasted FROM entries
                WHERE is_dir = 0 AND hash_full IS NOT NULL AND {where}
                GROUP BY hash_full HAVING count(*) > 1)""",
        params,
    ).fetchone()

    places: dict[str, int] = {}
    for p in top_projects(conn):
        loc = _location(p, h)
        places[loc] = places.get(loc, 0) + 1
    dirty = [r["path"] for r in conn.execute("SELECT path FROM projects WHERE git_dirty = 1 ORDER BY path")]
    return {
        "downloads": {"path": downloads, "items": dl["n"], "bytes": dl["b"]},
        "duplicates": {"groups": dups["groups"], "wasted": dups["wasted"]},
        "code": {"places": [{"name": k, "projects": v} for k, v in sorted(places.items())], "dirty": dirty},
    }


def timeline(conn: sqlite3.Connection, weeks: int = 26) -> list[dict]:
    """Archivos nuevos por semana (fecha de creación en este equipo), de lunes a domingo, en tus carpetas."""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start = today - timedelta(days=today.weekday()) - timedelta(weeks=weeks - 1)
    t0 = start.timestamp()
    where, params = user_scope_sql(home())
    rows = conn.execute(
        f"""SELECT CAST((ctime - ?) / 604800 AS INTEGER) AS w, count(*) AS files, coalesce(sum(size), 0) AS bytes
            FROM entries WHERE is_dir = 0 AND ctime >= ? AND {where} GROUP BY w""",
        [t0, t0, *params],
    ).fetchall()
    by_week = {r["w"]: r for r in rows}
    return [
        {
            "week": (start + timedelta(weeks=i)).strftime("%Y-%m-%d"),
            "files": by_week[i]["files"] if i in by_week else 0,
            "bytes": by_week[i]["bytes"] if i in by_week else 0,
        }
        for i in range(weeks)
    ]


def ext_type(ext: str | None) -> str | None:
    return next((t for t, exts in TYPES.items() if ext in exts), None)


ATTRIBUTES = {
    0x1: "Solo lectura",
    0x2: "Oculto",
    0x4: "Sistema",
    0x20: "Archivo",
    0x200: "Disperso",
    0x400: "Punto de análisis",
    0x800: "Comprimido",
    0x1000: "Sin conexión",
    0x2000: "Sin indexar por Windows",
    0x4000: "Cifrado",
    0x40000: "Se descarga al abrir",
    0x80000: "Siempre en este dispositivo",
    0x100000: "Liberable",
    0x400000: "Se descarga al leer",
}


def decode_attrs(attrs: int | None) -> list[str]:
    return [label for bit, label in ATTRIBUTES.items() if attrs and attrs & bit]
