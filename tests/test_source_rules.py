"""Reglas que se verifican leyendo el código fuente, no ejecutándolo."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Borrado permanente: prohibido en todo el código de la app (regla de seguridad 1).
FORBIDDEN = re.compile(
    r"\bos\.(remove|unlink|rmdir|removedirs)\b"
    r"|\bshutil\.rmtree\b"
    r"|\.(unlink|rmdir)\s*\("
    r"|\bDeleteFile\w*\b|\bRemoveDirectory\w*\b"
    r"|\bFO_DELETE\b"
)


def test_forbidden_pattern_catches_known_calls():
    for bad in ("os.remove(p)", "os.unlink(p)", "shutil.rmtree(d)", "path.unlink()", "p.rmdir()", "win32file.DeleteFileW(p)"):
        assert FORBIDDEN.search(bad), bad
    for fine in ("send2trash(p)", "shutil.move(a, b)", "os.rename(a, b)"):
        assert not FORBIDDEN.search(fine), fine


def test_no_permanent_delete_calls():
    hits = [
        f"{p.relative_to(ROOT)}:{n}: {line.strip()}"
        for p in (ROOT / "src").rglob("*.py")
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if FORBIDDEN.search(line)
    ]
    assert not hits, "Llamadas de borrado permanente:\n" + "\n".join(hits)


def test_no_em_dash_in_ui_text():
    files = [*(ROOT / "src").rglob("*.py"), *(ROOT / "web" / "src").rglob("*.*"), ROOT / "web" / "index.html"]
    hits = [
        f"{p.relative_to(ROOT)}:{n}"
        for p in files
        if p.exists()
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if "—" in line
    ]
    assert not hits, "Guiones largos en la interfaz:\n" + "\n".join(hits)
