"""Organizador por reglas. Solo propone: los movimientos los hace ops.plan_organize, con vista previa.

La estructura objetivo y las reglas viven en settings ("estructura" y "reglas_organizador") y se editan desde
la interfaz. Las rutas usan variables para no depender de este equipo: {Usuario}, {OneDrive}, {Descargas},
{Escritorio}; en la estructura, {Materia} se repite por cada materia.
"""

import os
import re
import sqlite3
import time
import unicodedata

from orden_pc import db, safety, winfs

DEFAULT_STRUCTURE = {
    "materias": [
        "Bases_Avanzadas", "Calidad_Software", "DiseñoDeFlujos", "Electricidad_Magnetismo", "Implementacion_Sistemas",
        "Ingenieria_Software_II", "Oportunidades_Generar_Negocios", "Prog_Dispositivos_Moviles",
    ],
    "carpetas": [
        "{OneDrive}\\00_Bandeja",
        "{OneDrive}\\10_Universidad\\Sexto_Semestre\\{Materia}\\Material",
        "{OneDrive}\\10_Universidad\\Sexto_Semestre\\{Materia}\\Entregas",
        "{OneDrive}\\20_Carrera\\CV_y_Perfil",
        "{OneDrive}\\20_Carrera\\SecOps",
        "{OneDrive}\\20_Carrera\\Machine_Learning",
        "{OneDrive}\\30_Genera\\ELAP",
        "{OneDrive}\\30_Genera\\Visitas_Empresariales",
        "{OneDrive}\\40_Emprendimientos",
        "{OneDrive}\\90_Archivo",
        "{Usuario}\\Dev\\uni",
        "{Usuario}\\Dev\\personal",
        "{Usuario}\\Dev\\sandbox",
    ],
    # Carpetas donde se buscan elementos sueltos. Lo que ninguna regla clasifica queda "Por clasificar".
    "origenes": ["{Descargas}", "{Escritorio}", "{Usuario}\\Documents", "{OneDrive}\\00_Bandeja"],
}

UNI = "{OneDrive}\\10_Universidad\\Sexto_Semestre"
DEFAULT_RULES = [
    {"id": "repos-uni", "nombre": "Repos de la universidad", "tipo": "carpetas",
     "palabras": ["chixi-refactor", "elevator-simulator", "practica_docker"], "destino": "{Usuario}\\Dev\\uni", "renombrar": "minusculas"},
    {"id": "repos-personales", "nombre": "Proyectos personales", "tipo": "carpetas",
     "palabras": ["openmontage"], "destino": "{Usuario}\\Dev\\personal", "renombrar": "minusculas"},
    {"id": "video-semiconductores", "nombre": "Video de semiconductores (dentro de Proyectos)", "tipo": "carpetas",
     "palabras": ["video-semiconductores"], "origen": ["{Usuario}\\Proyectos"], "destino": "{Usuario}\\Dev\\personal"},
    {"id": "remotion", "nombre": "Proyecto de Remotion (la carpeta Proyectos)", "tipo": "carpetas",
     "empieza": ["Proyectos"], "origen": ["{Usuario}"], "destino": "{Usuario}\\Dev\\personal"},
    {"id": "moviles", "nombre": "Prácticas M02 de Dart", "tipo": "archivos", "extensiones": ["dart"], "empieza": ["M02"],
     "destino": UNI + "\\Prog_Dispositivos_Moviles\\Entregas"},
    {"id": "chixi", "nombre": "Entregas de Chixi", "tipo": "archivos", "palabras": ["chixi"],
     "destino": UNI + "\\Calidad_Software\\Entregas", "renombrar": "entrega"},
    {"id": "hw07", "nombre": "Tarea HW07", "tipo": "archivos", "palabras": ["hw07"],
     "destino": UNI + "\\Ingenieria_Software_II\\Entregas", "renombrar": "entrega"},
    {"id": "visitas", "nombre": "Genera: visitas empresariales", "tipo": "ambos", "palabras": ["visita empresarial"],
     "destino": "{OneDrive}\\30_Genera\\Visitas_Empresariales"},
    {"id": "genera", "nombre": "Genera: ELAP y networking", "tipo": "ambos", "palabras": ["elap", "minamin", "networking"],
     "destino": "{OneDrive}\\30_Genera\\ELAP"},
    {"id": "cv", "nombre": "CV y perfil", "tipo": "archivos", "palabras": ["curriculum", "software_developer"],
     "destino": "{OneDrive}\\20_Carrera\\CV_y_Perfil"},
]
RULE_FIELDS = {"tipo": "ambos", "extensiones": [], "empieza": [], "palabras": [], "origen": [], "renombrar": "no", "activa": True}
TIPOS = {"archivos", "carpetas", "ambos"}
RENOMBRAR = {"no", "entrega", "minusculas"}
VARIABLES = ("Usuario", "OneDrive", "Descargas", "Escritorio")

IGNORE_NAMES = {"desktop.ini", "thumbs.db"}
IGNORE_EXT = {".crdownload", ".part", ".partial", ".tmp", ".download"}
HIDDEN, SYSTEM = 0x2, 0x4


class RuleError(ValueError):
    """Configuración no válida. El mensaje se muestra tal cual."""


# ---------------------------------------------------------------------- variables y configuración


def variables() -> dict[str, str]:
    from win32com.shell import shell, shellcon

    home = os.environ["USERPROFILE"]

    def known(folder_id, fallback):
        try:
            return shell.SHGetKnownFolderPath(folder_id)
        except Exception:
            return fallback

    return {
        "Usuario": home,
        "OneDrive": os.environ.get("OneDrive") or os.path.join(home, "OneDrive"),
        "Descargas": known(shellcon.FOLDERID_Downloads, os.path.join(home, "Downloads")),
        "Escritorio": known(shellcon.FOLDERID_Desktop, os.path.join(home, "Desktop")),
    }


def expand(template: str, vars: dict[str, str]) -> str:
    def sub(m):
        if m[1] not in vars:
            raise RuleError(f"«{{{m[1]}}}» no es una variable conocida. Usa {', '.join('{' + v + '}' for v in VARIABLES)}.")
        return vars[m[1]]

    path = os.path.normpath(re.sub(r"\{(\w+)\}", sub, template.strip()))
    if not re.match(r"^[A-Za-z]:\\", path):
        raise RuleError(f"«{template}» no es una ruta completa. Empieza con una variable o con la letra del disco.")
    return path


def structure(conn: sqlite3.Connection) -> dict:
    return {**DEFAULT_STRUCTURE, **db.get_setting(conn, "estructura", {})}


def rules(conn: sqlite3.Connection) -> list[dict]:
    return [{**RULE_FIELDS, **r} for r in db.get_setting(conn, "reglas_organizador", DEFAULT_RULES)]


def folders(st: dict, vars: dict[str, str]) -> list[dict]:
    """Carpetas de la estructura, con {Materia} repetida por materia."""
    out, seen = [], set()
    for line in st["carpetas"]:
        for t in ([line.replace("{Materia}", m) for m in st["materias"]] if "{Materia}" in line else [line]):
            path = expand(t, vars)
            if path.lower() not in seen:
                seen.add(path.lower())
                out.append({"template": t, "path": path, "exists": os.path.isdir(path)})
    return out


def _list(value, field: str, limit: int = 50) -> list[str]:
    if not isinstance(value, list) or len(value) > limit or not all(isinstance(v, str) and 0 < len(v.strip()) <= 200 for v in value):
        raise RuleError(f"«{field}» debe ser una lista de hasta {limit} textos.")
    return [v.strip() for v in value]


def validate_structure(data: dict, vars: dict[str, str]) -> dict:
    st = {
        "materias": _list(data.get("materias", []), "Materias"),
        "carpetas": _list(data.get("carpetas", []), "Carpetas", 300),
        "origenes": _list(data.get("origenes", []), "Carpetas de origen"),
    }
    for m in st["materias"]:
        if set(m) & set('<>:"/\\|?*'):
            raise RuleError(f"La materia «{m}» tiene caracteres que Windows no permite en carpetas.")
    folders(st, vars)  # que todas se puedan expandir
    for o in st["origenes"]:
        expand(o, vars)
    return st


def validate_rules(data: list, vars: dict[str, str]) -> list[dict]:
    if not isinstance(data, list) or len(data) > 200:
        raise RuleError("Las reglas deben ser una lista de hasta 200.")
    out, ids = [], set()
    for r in data:
        if not isinstance(r, dict):
            raise RuleError("Cada regla debe ser un objeto.")
        name = str(r.get("nombre", "")).strip()
        if not 0 < len(name) <= 120:
            raise RuleError("Cada regla necesita un nombre de hasta 120 caracteres.")
        rid = str(r.get("id") or re.sub(r"\W+", "-", name.lower())).strip("-")[:60] or "regla"
        while rid in ids:
            rid += "-2"
        ids.add(rid)
        rule = {
            "id": rid,
            "nombre": name,
            "activa": bool(r.get("activa", True)),
            "tipo": r.get("tipo", "ambos"),
            "extensiones": [e.lower().lstrip(".") for e in _list(r.get("extensiones", []), "Extensiones")],
            "empieza": _list(r.get("empieza", []), "Empieza con"),
            "palabras": _list(r.get("palabras", []), "Palabras clave"),
            "origen": _list(r.get("origen", []), "Solo en estas carpetas"),
            "destino": str(r.get("destino", "")).strip(),
            "renombrar": r.get("renombrar", "no"),
        }
        if rule["tipo"] not in TIPOS:
            raise RuleError(f"Regla «{name}»: el tipo debe ser archivos, carpetas o ambos.")
        if rule["renombrar"] not in RENOMBRAR:
            raise RuleError(f"Regla «{name}»: forma de renombrar desconocida.")
        if not (rule["extensiones"] or rule["empieza"] or rule["palabras"]):
            raise RuleError(f"Regla «{name}»: indica al menos una extensión, un inicio de nombre o una palabra clave.")
        expand(rule["destino"], vars)
        for o in rule["origen"]:
            expand(o, vars)
        out.append(rule)
    return out


# ---------------------------------------------------------------------- nombres


def _fold(s: str) -> str:
    """Para comparar: sin acentos, sin mayúsculas, y guiones, guiones bajos y espacios iguales."""
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).casefold()
    return re.sub(r"[\s_\-.]+", " ", s).strip()


COPY_SUFFIX = re.compile(r"(\s*\(\d+\)|\s*-\s*(copy|copia)(\s*\(\d+\))?)$", re.I)
COPY_PREFIX = re.compile(r"^(copia de|copy of)\s+", re.I)
VERSION = re.compile(r"[\s_\-]*v\d+$", re.I)
DATED = re.compile(r"^\d{4}-\d{2}-\d{2}_")


def delivery_name(name: str, mtime: float, materia: str | None, version: int = 1) -> str:
    """Regla de nombres: AAAA-MM-DD_Materia_Tema_v1.ext. Sin "(1)" ni "- Copy"."""
    stem, ext = os.path.splitext(name)
    if DATED.match(stem):
        stem = VERSION.sub("", stem)
        return f"{stem}_v{version}{ext.lower()}"
    stem = COPY_PREFIX.sub("", stem)
    while COPY_SUFFIX.search(stem):
        stem = COPY_SUFFIX.sub("", stem)
    stem = VERSION.sub("", stem)
    if materia:  # que la materia no salga dos veces
        stem = re.sub(re.escape(materia).replace("_", "[_ \\-]?"), " ", stem, flags=re.I)
    tema = re.sub(r"[^\w]+", "_", stem).strip("_") or "Sin_tema"
    parts = [time.strftime("%Y-%m-%d", time.localtime(mtime)), materia, tema]
    return "_".join(p for p in parts if p) + f"_v{version}{ext.lower()}"


def lower_name(name: str) -> str:
    return re.sub(r"[\s_]+", "-", name.strip()).lower()


def _materia(dest: str, materias: list[str]) -> str | None:
    parts = {p.lower() for p in dest.split("\\")}
    return next((m for m in materias if m.lower() in parts), None)


def new_name(item: dict, rule: dict, dest: str, materias: list[str], taken: set[str]) -> str:
    """Nombre en el destino. Con la regla de entregas, si ya existe se sube la versión: v2, v3..."""
    mode = rule["renombrar"]
    if mode == "minusculas":
        return lower_name(item["name"])
    if mode == "entrega" and not item["is_dir"]:
        materia = _materia(dest, materias)
        for v in range(1, 100):
            name = delivery_name(item["name"], item["mtime"], materia, v)
            if os.path.join(dest, name).lower() not in taken:
                return name
    return item["name"]


# ---------------------------------------------------------------------- propuesta


def matches(rule: dict, item: dict, parent: str, vars: dict[str, str]) -> bool:
    if not rule["activa"]:
        return False
    if rule["tipo"] == "archivos" and item["is_dir"] or rule["tipo"] == "carpetas" and not item["is_dir"]:
        return False
    if rule["origen"] and parent.lower() not in {expand(o, vars).lower() for o in rule["origen"]}:
        return False
    name = _fold(item["name"])
    if rule["extensiones"] and (item["is_dir"] or os.path.splitext(item["name"])[1].lower().lstrip(".") not in rule["extensiones"]):
        return False
    if rule["empieza"] and not any(name.startswith(_fold(p)) for p in rule["empieza"]):
        return False
    if rule["palabras"] and not any(_fold(w) in name for w in rule["palabras"]):
        return False
    return True


def _children(folder: str, conn: sqlite3.Connection, skip: set[str]) -> list[dict]:
    """Elementos sueltos de una carpeta. Solo atributos: nunca se lee contenido ni se descarga nada de la nube."""
    od = os.environ.get("OneDrive", "")
    out = []
    try:
        entries = list(os.scandir(folder))
    except OSError:
        return out
    for e in entries:
        try:
            st = e.stat(follow_symlinks=False)
        except OSError:
            continue
        attrs = st.st_file_attributes
        if (attrs & (HIDDEN | SYSTEM) or winfs.is_link(st) or e.name.lower() in IGNORE_NAMES
                or os.path.splitext(e.name)[1].lower() in IGNORE_EXT or e.path.lower() in skip
                or safety.protected_reason(e.path)):
            continue
        is_dir = e.is_dir(follow_symlinks=False)
        size = st.st_size
        if is_dir:
            row = conn.execute("SELECT size FROM entries WHERE path = ?", (e.path,)).fetchone()
            size = row["size"] if row else None
        in_od = bool(od) and e.path.lower().startswith(od.lower() + "\\")
        out.append({"path": e.path, "name": e.name, "is_dir": is_dir, "size": size, "mtime": st.st_mtime,
                    "cloud": winfs.cloud_state(attrs, in_od)})
    return out


def propose(conn: sqlite3.Connection, vars: dict[str, str] | None = None) -> dict:
    vars = vars or variables()
    st, rs = structure(conn), rules(conn)
    tree = folders(st, vars)
    # Nunca se proponen como elementos sueltos las carpetas de la estructura ni las que las contienen (OneDrive, Dev).
    skip = {f["path"].lower() for f in tree}
    for f in tree:
        p = f["path"]
        while os.path.dirname(p) != p:
            p = os.path.dirname(p)
            skip.add(p.lower())

    general = {expand(o, vars).lower(): expand(o, vars) for o in st["origenes"]}
    only_rules = {expand(o, vars).lower(): expand(o, vars) for r in rs if r["activa"] for o in r["origen"]}
    proposals, unsorted, taken, seen = [], [], set(), set()
    for key, folder in [*general.items(), *only_rules.items()]:
        if key in seen:
            continue
        seen.add(key)
        for item in _children(folder, conn, skip):
            rule = next((r for r in rs if matches(r, item, folder, vars)), None)
            if rule is None:
                if key in general:
                    unsorted.append(item)
                continue
            dest = expand(rule["destino"], vars)
            if folder.lower() == dest.lower():
                continue  # ya está donde va
            name = new_name(item, rule, dest, st["materias"], taken | _existing(dest))
            taken.add(os.path.join(dest, name).lower())
            proposals.append({**item, "rule": rule["id"], "rule_name": rule["nombre"], "dest": dest, "new_name": name, "conflict": None})

    # Dos elementos que acabarían con el mismo nombre en la misma carpeta (dos copias de un repo):
    # Orden PC no elige por ti. Se marcan y no se incluyen hasta que quitas uno.
    targets: dict[str, list[dict]] = {}
    for p in proposals:
        targets.setdefault(os.path.join(p["dest"], p["new_name"]).lower(), []).append(p)
    for group in targets.values():
        if len(group) > 1:
            for p in group:
                others = ", ".join(o["path"] for o in group if o is not p)
                p["conflict"] = f"También va ahí con el mismo nombre: {others}. Elige cuál mover."
    return {
        "estructura": st,
        "reglas": rs,
        "variables": vars,
        "carpetas": tree,
        "propuestas": proposals,
        "por_clasificar": sorted(unsorted, key=lambda i: i["name"].lower()),
    }


def _existing(folder: str) -> set[str]:
    try:
        return {os.path.join(folder, n).lower() for n in os.listdir(folder)}
    except OSError:
        return set()
