"""Escáner en segundo plano: recorre carpetas, guarda metadatos en SQLite y detecta proyectos.

Solo lee. Nunca abre archivos en esta fase (los hashes van aparte, en hashing.py).
"""

import os
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

from orden_pc import db, hashing, safety, winfs

REGENERABLE = {"node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next"}
PROJECT_MARKERS = {
    "package.json": "node",
    "pyproject.toml": "python",
    "requirements.txt": "python",
    "setup.py": "python",
    "pubspec.yaml": "flutter",
}
GIT_TIMEOUT = 15
COMMIT_EVERY = 2.0  # segundos


def configured_roots(conn) -> list[dict]:
    return db.get_setting(conn, "scan_roots", None) or default_roots()


def root_for(path: str, roots: list[dict]) -> dict | None:
    """La raíz más específica que contiene la ruta."""
    low = os.path.normcase(os.path.normpath(path))
    inside = [
        r for r in roots
        if low == os.path.normcase(os.path.normpath(r["path"])).rstrip("\\")
        or low.startswith(os.path.normcase(os.path.normpath(r["path"])).rstrip("\\") + "\\")
    ]
    return max(inside, key=lambda r: len(r["path"]), default=None)


def default_roots() -> list[dict]:
    """Carpeta de usuario completa (incluye OneDrive) y cada disco a nivel de carpetas."""
    roots = [{"path": os.environ["USERPROFILE"], "mode": "completo"}]
    roots += [{"path": d, "mode": "carpetas", "depth": 3} for d in winfs.fixed_drives()]
    return roots


class Cancelled(Exception):
    pass


def git_status(path: str) -> tuple[str | None, int | None]:
    """(rama, 1 si hay cambios sin commit). None si no se pudo saber.

    --no-optional-locks: git status no reescribe .git/index (regla: nunca tocar el interior de .git).
    """
    try:
        out = subprocess.run(
            ["git", "--no-optional-locks", "-C", path, "status", "--porcelain=v1", "--branch"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=GIT_TIMEOUT,
            creationflags=subprocess.CREATE_NO_WINDOW, env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
        )
    except (OSError, subprocess.TimeoutExpired):
        return None, None
    if out.returncode != 0:
        return None, None
    lines = out.stdout.splitlines()
    branch = None
    if lines and lines[0].startswith("## "):
        branch = lines[0][3:].split("...")[0].removeprefix("No commits yet on ").strip()
    return branch, int(any(not line.startswith("##") for line in lines))


def _is_user_project(path: str) -> bool:
    """Fuera quedan los de AppData y carpetas ocultas (.vscode, .claude, cachés): no son tuyos para ordenar.

    En el primer escaneo real, 419 "proyectos" bajaron a los que de verdad viven en tus carpetas.
    """
    if safety.protected_reason(path):
        return False
    return not any(part.startswith(".") for part in os.path.splitdrive(path)[1].split("\\") if part)


@dataclass
class Progress:
    status: str = "inactivo"  # inactivo | escaneando | terminado | cancelado | error
    phase: str = ""  # recorrido | proyectos | duplicados
    files: int = 0
    dirs: int = 0
    bytes: int = 0
    hashed: int = 0
    current: str = ""
    expected_files: int | None = None  # archivos del escaneo anterior, para estimar avance
    started: float | None = None
    finished: float | None = None
    error: str | None = None


@dataclass
class _Root:
    path: str
    mode: str  # completo | carpetas
    depth: int
    skip: set[str] = field(default_factory=set)  # otras raíces dentro de esta (ya escaneadas aparte)
    onedrive: str | None = None


class Scanner:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.progress = Progress()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, roots: list[dict]) -> bool:
        with self._lock:  # dos clics seguidos no deben lanzar dos escaneos
            if self.running:
                return False
            self._stop.clear()
            self.progress = Progress(status="escaneando", phase="recorrido")
            self._thread = threading.Thread(target=self.run, args=(roots,), name="orden-pc-escaner", daemon=True)
            self._thread.start()
            return True

    def stop(self) -> None:
        self._stop.set()

    def snapshot(self) -> dict:
        return asdict(self.progress)

    def index_one(self, conn, path: str, root_cfg: dict) -> tuple[int, int]:
        """Indexa una ruta suelta (recién creada o restaurada) sin reescanear todo. Devuelve (bytes, archivos).

        No toca los tamaños de las carpetas de arriba: eso lo ajusta quien llama (ops).
        """
        self._conn = conn
        self._last_commit = time.monotonic()
        self._projects = {}
        root_path = os.path.normpath(root_cfg["path"])
        root = _Root(path=root_path, mode=root_cfg["mode"], depth=root_cfg.get("depth", 0), onedrive=os.environ.get("OneDrive"))
        parent = os.path.dirname(path)
        depth = len(os.path.relpath(path, root_path).split("\\"))
        with os.scandir(parent) as it:
            e = next((x for x in it if x.name.lower() == os.path.basename(path).lower()), None)
        if e is None:
            return 0, 0
        st = e.stat(follow_symlinks=False)
        if e.is_dir(follow_symlinks=False):
            size, files, kinds, ok = self._scan_dir(path, root, depth)
            if root.mode == "completo" or depth <= root.depth:
                self._write_dir(path, parent, st, size, files, kinds, ok, collapsed=False, root=root)
            return size, files
        if root.mode == "completo":
            self._write_file(e, parent, st, root, None)
        return st.st_size, 1

    # ------------------------------------------------------------------ ejecución

    def run(self, roots: list[dict]) -> None:
        conn = db.connect(self.db_path)
        last = conn.execute("SELECT files FROM scans WHERE status = 'terminado' ORDER BY id DESC LIMIT 1").fetchone()
        self.progress = Progress(status="escaneando", phase="recorrido", started=time.time(), expected_files=last["files"] if last else None)
        with conn:
            scan_id = conn.execute("INSERT INTO scans(started, status) VALUES (?, 'escaneando')", (self.progress.started,)).lastrowid
        self._conn = conn
        self._last_commit = time.monotonic()
        self._projects: dict[str, set[str]] = {}
        try:
            # Primero las raíces completas: así las de carpetas pueden sumar su tamaño ya calculado.
            ordered = sorted(roots, key=lambda r: r["mode"] != "completo")
            keys = [os.path.normcase(os.path.normpath(r["path"])) for r in ordered]
            for cfg in ordered:
                root = _Root(
                    path=os.path.normpath(cfg["path"]),
                    mode=cfg["mode"],
                    depth=cfg.get("depth", 0),
                    skip={k for k in keys if k != os.path.normcase(os.path.normpath(cfg["path"]))},
                    onedrive=os.environ.get("OneDrive"),
                )
                self._scan_root(root)
            conn.commit()
            self.progress.phase = "proyectos"
            self._update_projects()
            self.progress.phase = "duplicados"
            self.progress.current = ""
            hashing.hash_candidates(conn, self.progress, self._stop)
            self.progress.status = "terminado"
        except Cancelled:
            self.progress.status = "cancelado"
        except Exception as e:  # el escaneo no debe tumbar el servidor
            self.progress.status = "error"
            self.progress.error = f"{type(e).__name__}: {e}"
        finally:
            conn.commit()
            p = self.progress
            p.finished = time.time()
            p.current = ""
            with conn:
                conn.execute(
                    "UPDATE scans SET finished=?, status=?, files=?, dirs=?, bytes=?, error=? WHERE id=?",
                    (p.finished, p.status, p.files, p.dirs, p.bytes, p.error, scan_id),
                )
            conn.close()

    def _scan_root(self, root: _Root) -> None:
        try:
            st = os.stat(root.path)
        except OSError:
            return  # raíz configurada que ya no existe
        size, files, kinds, ok = self._scan_dir(root.path, root, 0)
        parent = os.path.dirname(root.path)
        self._write_dir(root.path, parent if parent != root.path else None, st, size, files, kinds, ok, collapsed=False, root=root)

    # ------------------------------------------------------------------ recorrido

    def _check_stop(self) -> None:
        if self._stop.is_set():
            raise Cancelled
        if time.monotonic() - self._last_commit > COMMIT_EVERY:
            self._conn.commit()
            self._last_commit = time.monotonic()

    def _scan_dir(self, path: str, root: _Root, depth: int) -> tuple[int, int, set[str], bool]:
        """Devuelve (bytes, archivos, tipos de proyecto, se pudo leer)."""
        self._check_stop()
        self.progress.current = path
        index_files = root.mode == "completo"
        index_dirs = index_files or depth < root.depth
        existing = {}
        if index_dirs:
            existing = {
                r["path"].lower(): r
                for r in self._conn.execute("SELECT path, size, files, mtime, attrs FROM entries WHERE parent = ?", (path,))
            }
        try:
            it = os.scandir(path)
        except OSError:
            return 0, 0, set(), False

        total = nfiles = 0
        kinds: set[str] = set()
        seen: set[str] = set()
        with it:
            for e in it:
                try:
                    st = e.stat(follow_symlinks=False)
                except OSError:
                    continue
                if winfs.is_link(st):
                    continue
                key = e.path.lower()
                if e.is_dir(follow_symlinks=False):
                    name = e.name.lower()
                    if name == ".git":
                        kinds.add("git")
                    if os.path.normcase(e.path) in root.skip:
                        seen.add(key)  # otra raíz: se escaneó aparte; se suma su tamaño
                        row = self._conn.execute("SELECT size, files FROM entries WHERE path = ?", (e.path,)).fetchone()
                        if row:
                            total += row["size"]
                            nfiles += row["files"]
                        continue
                    self.progress.dirs += 1
                    collapsed = name in REGENERABLE or name == ".git" or not (index_files or depth + 1 < root.depth)
                    if collapsed:
                        size, files, ok = self._sum_dir(e.path, existing.get(key), st)
                        sub_kinds: set[str] = set()
                    else:
                        size, files, sub_kinds, ok = self._scan_dir(e.path, root, depth + 1)
                    total += size
                    nfiles += files
                    if index_dirs:
                        seen.add(key)
                        tags = set(sub_kinds)
                        if name in REGENERABLE:
                            tags.add("regenerable")
                        if name == ".git":
                            tags.add("git_interno")
                        self._write_dir(e.path, path, st, size, files, tags, ok, collapsed, root, existing.get(key))
                else:
                    if kind := PROJECT_MARKERS.get(e.name.lower()):
                        kinds.add(kind)
                    elif e.name.lower() == ".git":  # worktree o submódulo: .git es un archivo
                        kinds.add("git")
                    total += st.st_size
                    nfiles += 1
                    self.progress.files += 1
                    self.progress.bytes += st.st_size
                    if index_files:
                        seen.add(key)
                        self._write_file(e, path, st, root, existing.get(key))

        if index_dirs:
            for gone in existing.keys() - seen:
                self._delete_subtree(existing[gone]["path"])
        if kinds and index_files and _is_user_project(path):
            self._projects[path] = kinds
        return total, nfiles, kinds, True

    def _sum_dir(self, path: str, prev, st) -> tuple[int, int, bool]:
        """Suma una carpeta sin indexar su contenido."""
        # ponytail: en carpetas regenerables y .git se reutiliza el tamaño si su fecha no cambió; un cambio
        # muy profundo (node_modules/x/y) no la mueve y el tamaño queda aproximado. Solo ahí: una carpeta
        # de juego o de sistema que se actualiza por dentro debe sumarse de nuevo siempre.
        reusable = os.path.basename(path).lower() in REGENERABLE | {".git"}
        if reusable and prev is not None and prev["mtime"] == st.st_mtime and prev["size"]:
            self.progress.files += prev["files"]
            self.progress.bytes += prev["size"]
            return prev["size"], prev["files"], True
        total = nfiles = 0
        stack = [path]
        ok = True
        while stack:
            self._check_stop()
            d = stack.pop()
            try:
                it = os.scandir(d)
            except OSError:
                ok = False
                continue
            with it:
                for e in it:
                    try:
                        est = e.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    if winfs.is_link(est):
                        continue
                    if e.is_dir(follow_symlinks=False):
                        stack.append(e.path)
                    else:
                        total += est.st_size
                        nfiles += 1
        self.progress.files += nfiles
        self.progress.bytes += total
        return total, nfiles, ok

    # ------------------------------------------------------------------ escritura en el índice

    def _cloud(self, path: str, attrs: int, root: _Root) -> str | None:
        in_od = bool(root.onedrive) and os.path.normcase(path).startswith(os.path.normcase(root.onedrive) + "\\")
        return winfs.cloud_state(attrs, in_od)

    def _write_file(self, e: os.DirEntry, parent: str, st, root: _Root, prev) -> None:
        attrs = st.st_file_attributes
        if prev is not None and prev["size"] == st.st_size and prev["mtime"] == st.st_mtime and prev["attrs"] == attrs:
            return  # sin cambios: incremental
        ext = os.path.splitext(e.name)[1].lower().lstrip(".") or None
        self._upsert((e.path, parent, e.name, ext, 0, st.st_size, 0, st.st_birthtime, st.st_mtime, st.st_atime, attrs, self._cloud(e.path, attrs, root), "", 0))

    def _write_dir(self, path, parent, st, size, files, tags, ok, collapsed, root, prev=None) -> None:
        if not ok:
            tags = set(tags) | {"sin_acceso"}
        tag_str = ",".join(sorted(tags))
        attrs = st.st_file_attributes
        if prev is not None and prev["size"] == size and prev["files"] == files and prev["mtime"] == st.st_mtime and prev["attrs"] == attrs:
            # Los tipos de proyecto pueden cambiar sin que cambie el tamaño.
            self._conn.execute("UPDATE entries SET tags = ? WHERE path = ? AND tags != ?", (tag_str, path, tag_str))
            return
        name = os.path.basename(path) or path
        self._upsert((path, parent, name, None, 1, size, files, st.st_birthtime, st.st_mtime, st.st_atime, attrs, self._cloud(path, attrs, root), tag_str, int(collapsed)))

    def _upsert(self, row: tuple) -> None:
        self._conn.execute(
            """
            INSERT INTO entries(path, parent, name, ext, is_dir, size, files, ctime, mtime, atime, attrs, cloud, tags, collapsed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                parent = excluded.parent, is_dir = excluded.is_dir, ext = excluded.ext,
                hash_partial = CASE WHEN size = excluded.size AND mtime = excluded.mtime THEN hash_partial END,
                hash_full = CASE WHEN size = excluded.size AND mtime = excluded.mtime THEN hash_full END,
                size = excluded.size, files = excluded.files, ctime = excluded.ctime, mtime = excluded.mtime,
                atime = excluded.atime, attrs = excluded.attrs, cloud = excluded.cloud, tags = excluded.tags,
                collapsed = excluded.collapsed
            """,
            row,
        )

    def _delete_subtree(self, path: str) -> None:
        # Borra filas del índice (no archivos). '\' es 0x5C y ']' 0x5D: el rango cubre todo lo de adentro.
        self._conn.execute("DELETE FROM entries WHERE path = ? OR (path > ? AND path < ?)", (path, path + "\\", path + "]"))

    # ------------------------------------------------------------------ proyectos

    def _update_projects(self) -> None:
        conn = self._conn
        items = sorted(self._projects.items())
        with ThreadPoolExecutor(max_workers=4) as pool:
            gits = list(pool.map(lambda kv: git_status(kv[0]) if "git" in kv[1] else (None, None), items))
        with conn:
            conn.execute("DELETE FROM projects")
            for (path, kinds), (branch, dirty) in zip(items, gits):
                self._check_stop()
                last = conn.execute(
                    "SELECT max(mtime) FROM entries WHERE is_dir = 0 AND path > ? AND path < ?", (path + "\\", path + "]")
                ).fetchone()[0]
                conn.execute(
                    "INSERT INTO projects(path, kinds, git_branch, git_dirty, last_activity) VALUES (?, ?, ?, ?, ?)",
                    (path, ",".join(sorted(kinds)), branch, dirty, last),
                )
