import _winapi
import os
import shutil
import stat
import time
from pathlib import Path

import pytest

from orden_pc import agente, apps, ops, organizer, safety, scanner, trash


def _writable_then_retry(func, path, _exc):
    os.chmod(path, stat.S_IWRITE)  # los objetos de .git son de solo lectura
    func(path)


def pytest_sessionfinish(session, exitstatus):
    """Si todo pasó, borra pytest-tmp: vive dentro de tu carpeta y el escáner lo vería como proyectos.

    Las pruebas quitan sus junctions antes de terminar; además rmtree no entra en junctions desde Python 3.8.
    """
    if exitstatus == 0 and session.config.option.basetemp:
        shutil.rmtree(Path(session.config.rootpath, session.config.option.basetemp), onexc=_writable_then_retry)


@pytest.fixture(autouse=True)
def solo_carpetas_temporales(tmp_path, monkeypatch):
    """Regla 10: las pruebas nunca tocan archivos reales ni la base de datos real."""
    monkeypatch.setenv("ORDEN_PC_DB", str(tmp_path / "prueba.db"))

    def prohibido():
        raise AssertionError("Una prueba intentó escanear las carpetas reales del usuario.")

    monkeypatch.setattr(scanner, "default_roots", prohibido)

    def carpetas_reales():
        raise AssertionError("Una prueba intentó leer las carpetas reales (Descargas, Escritorio, OneDrive).")

    monkeypatch.setattr(organizer, "variables", carpetas_reales)
    monkeypatch.setattr(safety, "EXTRA_PROTECTED", [])  # lo que una prueba agrega no se filtra a otras


class FakeBin:
    """Papelera simulada dentro de tmp_path: las pruebas nunca tocan la Papelera real."""

    def __init__(self, folder: Path):
        self.folder = folder
        self.items: list[tuple[str, str, float]] = []  # (original, guardado, fecha)
        self.enabled = True
        self.max_bytes = 10 * 2**30
        self.used_bytes = 0

    def send(self, path: str) -> None:
        self.folder.mkdir(exist_ok=True)
        stored = self.folder / f"{len(self.items)}_{os.path.basename(path)}"
        os.rename(path, stored)
        self.items.append((path, str(stored), time.time()))

    def _match(self, original, after, before):
        return [i for i in self.items if i[0].lower() == original.lower() and i[2] >= after and (before is None or i[2] <= before)]

    def in_bin(self, original: str, deleted_after: float, deleted_before: float | None = None) -> bool:
        return bool(self._match(original, deleted_after, deleted_before))

    def restore(self, original: str, deleted_after: float, deleted_before: float | None = None, wait: float = 0) -> None:
        match = self._match(original, deleted_after, deleted_before)
        if not match:
            raise OSError("No está en la Papelera.")
        item = match[0]
        os.rename(item[1], item[0])
        self.items.remove(item)

    def limits(self, path: str) -> dict:
        return {"drive": "C:\\", "enabled": self.enabled, "max_bytes": self.max_bytes, "used_bytes": self.used_bytes, "items": len(self.items)}


@pytest.fixture(autouse=True)
def papelera_falsa(tmp_path, monkeypatch, request):
    if "papelera_real" in request.keywords:
        yield None
        return
    fake = FakeBin(tmp_path / "_papelera")
    for name in ("send", "in_bin", "restore", "limits"):
        monkeypatch.setattr(trash, name, getattr(fake, name))

    # Guardián: ops nunca debe tocar algo fuera de la carpeta temporal de la prueba.
    real_execute = ops.Ops._execute
    base = tmp_path.resolve()

    def guarded(self, step):
        for p in (step.src, step.dst):
            if p:
                assert Path(p).resolve().is_relative_to(base), f"ops intentó tocar {p}, fuera de la carpeta de la prueba"
        return real_execute(self, step)

    monkeypatch.setattr(ops.Ops, "_execute", guarded)
    yield fake


@pytest.fixture(autouse=True)
def sin_programas_reales(monkeypatch):
    """Ninguna prueba ejecuta winget o PowerShell de verdad, ni abre un instalador o desinstalador."""

    def no_run(*a, **kw):
        raise AssertionError("Una prueba intentó ejecutar winget o PowerShell de verdad.")

    def no_launch(spec):
        raise AssertionError(f"Una prueba intentó abrir {spec}.")

    monkeypatch.setattr(apps, "_run", no_run)
    monkeypatch.setattr(apps, "launch", no_launch)

    def sin_modelo(*a, **kw):
        raise AssertionError("Una prueba intentó hablar con un Ollama real.")

    monkeypatch.setattr(agente, "_chat", sin_modelo)
    monkeypatch.setattr(agente, "_get", sin_modelo)


@pytest.fixture
def junction():
    """Crea junctions y los quita al terminar (os.rmdir sobre un junction borra solo el enlace)."""
    made = []

    def make(target, link):
        _winapi.CreateJunction(str(target), str(link))
        made.append(link)
        return link

    yield make
    for link in made:
        os.rmdir(link)
