"""Papelera de reciclaje de Windows. Ver docs/adr/003-borrado-y-deshacer.md.

Este es el único módulo que elimina, y siempre hacia la Papelera:
- antes de enviar, ops comprueba que el elemento quepa (si no cabe, Windows lo borraría para siempre);
- al enviar se pide FOF_WANTNUKEWARNING: si aun así Windows fuera a borrar en vez de reciclar, pregunta;
- después se verifica que el elemento esté de verdad en la Papelera.
"""

import os
import struct
import time
import winreg
from contextlib import contextmanager

FOFX_ADDUNDORECORD = 0x20000000
FOFX_RECYCLEONDELETE = 0x00080000


@contextmanager
def _com():
    import pythoncom

    pythoncom.CoInitialize()
    try:
        yield
    finally:
        pythoncom.CoUninitialize()


def limits(path: str) -> dict:
    """Capacidad de la Papelera del volumen de `path` (por usuario, en el registro de Explorer)."""
    import win32file
    from win32com.shell import shell

    drive = os.path.splitdrive(os.path.abspath(path))[0] + "\\"
    used, items = shell.SHQueryRecycleBin(drive)
    max_bytes, enabled = None, True
    try:
        vol = win32file.GetVolumeNameForVolumeMountPoint(drive)
        guid = vol[vol.index("{"): vol.index("}") + 1]
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"Software\Microsoft\Windows\CurrentVersion\Explorer\BitBucket\Volume\{guid}") as k:
            max_bytes = winreg.QueryValueEx(k, "MaxCapacity")[0] * 1024 * 1024
            enabled = winreg.QueryValueEx(k, "NukeOnDelete")[0] == 0
    except (OSError, ValueError):
        pass
    if max_bytes is None:
        # Sin ajuste explícito Windows reserva cerca del 5 % del volumen; se asume eso (conservador).
        import shutil

        max_bytes = int(shutil.disk_usage(drive).total * 0.05)
    return {"drive": drive, "enabled": enabled, "max_bytes": max_bytes, "used_bytes": used, "items": items}


def send(path: str) -> None:
    """Envía a la Papelera. Lanza OSError si Windows no lo hizo."""
    import pythoncom
    from win32com.shell import shell, shellcon

    flags = (
        shellcon.FOF_NOCONFIRMATION
        | shellcon.FOF_WANTNUKEWARNING  # si no puede reciclar, Windows pregunta en vez de borrar en silencio
        | shellcon.FOF_SILENT
        | shellcon.FOFX_EARLYFAILURE
        | FOFX_ADDUNDORECORD
        | FOFX_RECYCLEONDELETE
    )
    with _com():
        op = pythoncom.CoCreateInstance(shell.CLSID_FileOperation, None, pythoncom.CLSCTX_ALL, shell.IID_IFileOperation)
        op.SetOperationFlags(flags)
        op.DeleteItem(shell.SHCreateItemFromParsingName(path, None, shell.IID_IShellItem), None)
        try:
            op.PerformOperations()
        except Exception as e:  # pywintypes.com_error
            raise OSError(f"Windows no pudo enviar a la Papelera: {e}") from e
        if op.GetAnyOperationsAborted():
            raise OSError("La operación se canceló antes de terminar.")


def _read_info(recycled_path: str) -> tuple[str, int, float]:
    """Lee el $I que acompaña a cada $R: ruta original, tamaño y fecha de borrado."""
    folder, name = os.path.split(recycled_path)
    with open(os.path.join(folder, "$I" + name[2:]), "rb") as f:
        data = f.read()
    version, size, filetime = struct.unpack_from("<qqq", data, 0)
    if version >= 2:
        n = struct.unpack_from("<i", data, 24)[0]
        original = data[28: 28 + n * 2].decode("utf-16-le")
    else:
        original = data[24: 24 + 520].decode("utf-16-le")
    return original.split("\x00")[0], size, filetime / 1e7 - 11644473600


def _find(shell_app, original: str, deleted_after: float, deleted_before: float | None = None):
    """El elemento de la Papelera que vino de `original` dentro de la ventana de tiempo.

    Si hay varios (borraste lo mismo dos veces), el más cercano al inicio de la ventana:
    deshacer debe traer de vuelta justo lo que ese cambio envió.
    """
    best = None
    for item in shell_app.Namespace(10).Items():
        try:
            orig, size, deleted = _read_info(item.Path)
        except (OSError, struct.error, UnicodeDecodeError):
            continue
        if orig.lower() != original.lower() or deleted < deleted_after:
            continue
        if deleted_before is not None and deleted > deleted_before:
            continue
        if best is None or deleted < best[1]:
            best = (item, deleted, size)
    return best


def in_bin(original: str, deleted_after: float, deleted_before: float | None = None) -> bool:
    import win32com.client

    with _com():
        return _find(win32com.client.Dispatch("Shell.Application"), original, deleted_after, deleted_before) is not None


def restore(original: str, deleted_after: float, deleted_before: float | None = None, wait: float = 5.0) -> None:
    """Restaura con el verbo canónico 'undelete' (no depende del idioma de Windows). Lanza OSError si no puede."""
    import win32com.client

    with _com():
        found = _find(win32com.client.Dispatch("Shell.Application"), original, deleted_after, deleted_before)
        if not found:
            raise OSError("No está en la Papelera: quizá se vació o ya se restauró.")
        found[0].InvokeVerb("undelete")
    end = time.monotonic() + wait
    while time.monotonic() < end:
        if os.path.lexists(original):
            return
        time.sleep(0.1)
    raise OSError("Windows no confirmó la restauración. Revisa la Papelera.")
