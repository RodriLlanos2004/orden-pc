"""Única puerta para autorizar rutas. Ver docs/adr/002-modelo-de-seguridad.md, punto 7."""

import os
import re
from pathlib import Path

DRIVE_ABS = re.compile(r"^[A-Za-z]:[\\/]")
BAD_CHARS = set('<>"|?*') | {chr(c) for c in range(32)}
# Nombres que protegen la ruta en cualquier nivel (comparación sin mayúsculas).
PROTECTED_COMPONENTS = {"appdata", ".git"}
# Nombres protegidos en la raíz de cualquier unidad.
PROTECTED_AT_ROOT = {"$recycle.bin", "system volume information", "recovery"}


# Rutas que agregaste en Configuración. Se cargan al arrancar y solo crecen (regla 4: la lista solo admite agregar).
EXTRA_PROTECTED: list[str] = []


class UnsafePath(ValueError):
    """La ruta no se puede usar. El mensaje se muestra tal cual en la interfaz."""


def _env_path(var: str, fallback: str) -> str:
    return os.environ.get(var) or fallback


def default_protected() -> list[str]:
    return [
        _env_path("SystemRoot", r"C:\Windows"),
        _env_path("ProgramFiles", r"C:\Program Files"),
        _env_path("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        _env_path("ProgramData", r"C:\ProgramData"),
    ]


def _key(p: str) -> str:
    return os.path.normcase(os.path.normpath(p)).rstrip("\\")


def _inside(path_key: str, base_key: str) -> bool:
    return path_key == base_key or path_key.startswith(base_key + "\\")


def protected_reason(path: str, extra: list[str] = ()) -> str | None:
    """Motivo por el que la ruta está protegida, o None. `path` debe venir ya resuelta."""
    k = _key(path)
    drive, rest = os.path.splitdrive(k)
    parts = [p for p in rest.split("\\") if p]
    if not parts:
        return "Es la raíz de un disco."
    if parts[0] in PROTECTED_AT_ROOT:
        return f"{path} es una carpeta del sistema."
    if PROTECTED_COMPONENTS & set(parts):
        hit = next(p for p in parts if p in PROTECTED_COMPONENTS)
        return "Está dentro de un repositorio Git (.git)." if hit == ".git" else "Está dentro de AppData."
    for base in [*default_protected(), *EXTRA_PROTECTED, *extra]:
        if _inside(k, _key(base)):
            return f"Está dentro de {base}, que es una ruta protegida."
    return None


def resolve_target(raw: str, roots: list[str], extra_protected: list[str] = ()) -> Path:
    """Valida y normaliza una ruta recibida de la interfaz. Lanza UnsafePath si no se puede usar."""
    if not isinstance(raw, str) or not raw:
        raise UnsafePath("La ruta está vacía.")
    if raw.startswith(("\\\\", "//")):
        raise UnsafePath("No se aceptan rutas de red ni rutas con prefijo \\\\?\\.")
    if not DRIVE_ABS.match(raw):
        raise UnsafePath("La ruta debe ser absoluta y empezar con la letra de una unidad, por ejemplo C:\\.")
    if set(raw) & BAD_CHARS or ":" in raw[2:]:
        raise UnsafePath("La ruta tiene caracteres no válidos o un flujo alternativo (:).")
    parts = re.split(r"[\\/]", raw[3:])
    if any(p == ".." for p in parts):
        raise UnsafePath("La ruta no puede contener '..'.")
    if any(p and p != "." and p[-1] in ". " for p in parts):
        raise UnsafePath("Ningún nombre de la ruta puede terminar en punto o espacio.")

    # realpath sigue junctions y symlinks y expande nombres cortos 8.3 (PROGRA~1).
    resolved = os.path.realpath(raw)
    if resolved.startswith("\\\\"):
        raise UnsafePath("La ruta apunta a una ubicación de red.")
    if reason := protected_reason(resolved, extra_protected):
        raise UnsafePath(reason)
    if not any(_inside(_key(resolved), _key(r)) for r in roots):
        raise UnsafePath("La ruta está fuera de las carpetas que Orden PC tiene permitido ver.")
    return Path(resolved)
