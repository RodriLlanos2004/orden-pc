"""Detalles de Windows: atributos de archivo, estado de OneDrive, reparse points y propietario."""

import os
import stat

# Atributos de archivo (winnt.h)
OFFLINE = 0x1000
RECALL_ON_OPEN = 0x40000
PINNED = 0x80000
UNPINNED = 0x100000
RECALL_ON_DATA_ACCESS = 0x400000
CLOUD_ONLY = OFFLINE | RECALL_ON_OPEN | RECALL_ON_DATA_ACCESS

# Reparse tags que no se siguen: llevan a otro lugar del disco (posibles ciclos o doble conteo).
# Los de OneDrive (IO_REPARSE_TAG_CLOUD_*) sí se recorren: son carpetas reales.
REPARSE_SYMLINK = 0xA000000C
REPARSE_MOUNT_POINT = 0xA0000003  # junctions y puntos de montaje


DRIVE_FIXED = 3


def fixed_drives() -> list[str]:
    """Discos locales. Fuera quedan unidades de red, USB sin medio y lectores ópticos."""
    import ctypes

    return [d for d in os.listdrives() if ctypes.windll.kernel32.GetDriveTypeW(d) == DRIVE_FIXED]


def is_cloud_only(attrs: int) -> bool:
    """Leer el contenido de estos archivos los descargaría. Nunca se abren."""
    return bool(attrs & CLOUD_ONLY)


def file_attrs(path: str) -> int:
    return os.stat(path, follow_symlinks=False).st_file_attributes


def safe_to_read(path: str) -> bool:
    """Mira los atributos justo antes de abrir: OneDrive pudo liberar el archivo después del escaneo.
    Todo código que lea contenido de archivos del usuario pasa por aquí."""
    try:
        return not is_cloud_only(file_attrs(path))
    except OSError:
        return False


def cloud_state(attrs: int, in_onedrive: bool) -> str | None:
    if is_cloud_only(attrs):
        return "solo_nube"
    if not in_onedrive:
        return None
    return "siempre_local" if attrs & PINNED else "local"


def is_link(st: os.stat_result) -> bool:
    return stat.S_ISLNK(st.st_mode) or getattr(st, "st_reparse_tag", 0) in (REPARSE_SYMLINK, REPARSE_MOUNT_POINT)


def owner(path: str) -> str | None:
    """Propietario como DOMINIO\\usuario. Lento: solo bajo demanda."""
    import win32security

    try:
        sd = win32security.GetFileSecurity(path, win32security.OWNER_SECURITY_INFORMATION)
        name, domain, _ = win32security.LookupAccountSid(None, sd.GetSecurityDescriptorOwner())
        return f"{domain}\\{name}" if domain else name
    except Exception:  # sin permiso, SID huérfano, ruta desaparecida
        return None
