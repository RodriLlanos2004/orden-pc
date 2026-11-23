import os
import subprocess
import time

import pytest
from fastapi.testclient import TestClient

from orden_pc import db, hashing, winfs
from orden_pc.app import create_app
from orden_pc.scanner import Scanner


def write(path, size=0, data=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if data is not None else b"x" * size)
    return path


@pytest.fixture
def tree(tmp_path):
    r = tmp_path / "usuario"
    write(r / "Downloads" / "ELAP_reporte.pdf", 5000)
    write(r / "Downloads" / "CV (1).docx", 100)
    write(r / "Dev" / "web" / "package.json", 20)
    write(r / "Dev" / "web" / "node_modules" / "lib" / "index.js", 3000)
    write(r / "Dev" / "web" / "node_modules" / "lib" / "deep" / "x.js", 1000)
    write(r / "Dev" / "api" / "pyproject.toml", 30)
    write(r / "Dev" / "app" / "pubspec.yaml", 40)
    return r


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "prueba.db")
    yield c
    c.close()


def scan(tmp_path, roots):
    s = Scanner(tmp_path / "prueba.db")
    s.run(roots)
    assert s.progress.status == "terminado", s.progress.error
    return s


def full(root):
    return [{"path": str(root), "mode": "completo"}]


def row(conn, path):
    return conn.execute("SELECT * FROM entries WHERE path = ?", (str(path),)).fetchone()


def test_sizes_and_counts(tmp_path, tree, conn):
    s = scan(tmp_path, full(tree))
    root = row(conn, tree)
    assert root["size"] == 5000 + 100 + 20 + 3000 + 1000 + 30 + 40
    assert root["files"] == 7
    assert row(conn, tree / "Downloads")["size"] == 5100
    assert s.progress.files == 7 and s.progress.bytes == root["size"]
    f = row(conn, tree / "Downloads" / "ELAP_reporte.pdf")
    assert (f["ext"], f["is_dir"], f["parent"]) == ("pdf", 0, str(tree / "Downloads"))
    assert f["ctime"] and f["mtime"] and f["atime"] and f["attrs"] is not None


def test_regenerable_folder_is_summed_not_indexed(tmp_path, tree, conn):
    scan(tmp_path, full(tree))
    nm = row(conn, tree / "Dev" / "web" / "node_modules")
    assert nm["collapsed"] == 1 and "regenerable" in nm["tags"]
    assert nm["size"] == 4000 and nm["files"] == 2
    assert row(conn, tree / "Dev" / "web" / "node_modules" / "lib") is None


def test_projects_detected(tmp_path, tree, conn):
    scan(tmp_path, full(tree))
    kinds = {r["path"]: r["kinds"] for r in conn.execute("SELECT * FROM projects")}
    assert kinds[str(tree / "Dev" / "web")] == "node"
    assert kinds[str(tree / "Dev" / "api")] == "python"
    assert kinds[str(tree / "Dev" / "app")] == "flutter"
    assert "node" in row(conn, tree / "Dev" / "web")["tags"]
    # node_modules contiene package.json en la vida real; no debe contar como proyecto.
    assert not any("node_modules" in p for p in kinds)


def test_projects_in_appdata_or_hidden_folders_are_ignored(tmp_path, conn):
    r = tmp_path / "usuario"
    write(r / "AppData" / "Local" / "Programs" / "Code" / "package.json", 5)
    write(r / ".vscode" / "extensions" / "ext" / "package.json", 5)
    write(r / "Proyectos" / "package.json", 5)
    scan(tmp_path, full(r))
    assert [p["path"] for p in conn.execute("SELECT path FROM projects")] == [str(r / "Proyectos")]
    assert row(conn, r / "AppData" / "Local" / "Programs" / "Code" / "package.json") is not None  # sí se indexa


def test_migration_from_v1_keeps_rows_and_search(tmp_path):
    import sqlite3

    p = tmp_path / "v1.db"
    old = sqlite3.connect(p)
    old.executescript(db.MIGRATIONS[0])
    old.execute("PRAGMA user_version = 1")
    old.execute("INSERT INTO entries(path, parent, name, is_dir) VALUES ('C:\\x\\ELAP.pdf', 'C:\\x', 'ELAP.pdf', 0)")
    old.commit()
    old.close()
    c = db.connect(p)
    assert c.execute("PRAGMA user_version").fetchone()[0] == len(db.MIGRATIONS)
    assert c.execute("SELECT count(*) FROM entries_fts WHERE name LIKE '%elap%'").fetchone()[0] == 1
    c.close()


def test_git_repo_branch_and_dirty(tmp_path, tree, conn):
    repo = tree / "Dev" / "repo"
    repo.mkdir(parents=True)
    git = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)
    git("init", "-b", "main")
    write(repo / "README.md", 10)
    git("-c", "user.name=t", "-c", "user.email=t@t", "add", ".")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "x")
    index_mtime = (repo / ".git" / "index").stat().st_mtime_ns

    scan(tmp_path, full(tree))
    p = conn.execute("SELECT * FROM projects WHERE path = ?", (str(repo),)).fetchone()
    assert (p["kinds"], p["git_branch"], p["git_dirty"]) == ("git", "main", 0)
    assert row(conn, repo / ".git")["collapsed"] == 1
    assert row(conn, repo / ".git" / "HEAD") is None

    write(repo / "nuevo.txt", 5)
    scan(tmp_path, full(tree))
    assert conn.execute("SELECT git_dirty FROM projects WHERE path = ?", (str(repo),)).fetchone()[0] == 1
    assert (repo / ".git" / "index").stat().st_mtime_ns == index_mtime, "git status reescribió .git/index"


def test_incremental_rescan(tmp_path, tree, conn):
    scan(tmp_path, full(tree))
    keep = tree / "Downloads" / "ELAP_reporte.pdf"
    conn.execute("UPDATE entries SET hash_partial = 'previo' WHERE path = ?", (str(keep),))
    changed = tree / "Downloads" / "CV (1).docx"
    conn.execute("UPDATE entries SET hash_partial = 'viejo' WHERE path = ?", (str(changed),))
    conn.commit()
    keep_id = row(conn, keep)["id"]

    time.sleep(0.01)
    write(changed, 250)
    os.remove(tree / "Dev" / "api" / "pyproject.toml")
    for p in sorted((tree / "Dev" / "app").rglob("*"), reverse=True):
        p.unlink() if p.is_file() else p.rmdir()
    (tree / "Dev" / "app").rmdir()
    scan(tmp_path, full(tree))

    assert row(conn, keep)["hash_partial"] == "previo" and row(conn, keep)["id"] == keep_id
    assert row(conn, changed)["size"] == 250 and row(conn, changed)["hash_partial"] is None
    assert row(conn, tree / "Dev" / "api" / "pyproject.toml") is None
    assert row(conn, tree / "Dev" / "app") is None and row(conn, tree / "Dev" / "app" / "pubspec.yaml") is None
    assert row(conn, tree)["size"] == 5000 + 250 + 20 + 4000
    assert str(tree / "Dev" / "app") not in {r["path"] for r in conn.execute("SELECT path FROM projects")}


def test_junctions_are_not_followed(tmp_path, tree, conn, tmp_path_factory, junction):
    outside = tmp_path_factory.mktemp("afuera")
    write(outside / "grande.bin", 10_000)
    junction(outside, tree / "atajo")
    scan(tmp_path, full(tree))
    assert row(conn, tree / "atajo") is None
    assert row(conn, tree)["size"] < 10_000


def test_folder_mode_indexes_only_folders_to_depth(tmp_path, tree, conn):
    drive_like = tmp_path / "disco"
    write(drive_like / "Juegos" / "Riot" / "lol" / "data.pak", 7000)
    write(drive_like / "suelto.txt", 10)
    scan(tmp_path, [{"path": str(drive_like), "mode": "carpetas", "depth": 2}])
    assert row(conn, drive_like)["size"] == 7010
    assert row(conn, drive_like / "Juegos")["size"] == 7000
    assert row(conn, drive_like / "Juegos" / "Riot")["collapsed"] == 1
    assert row(conn, drive_like / "Juegos" / "Riot" / "lol") is None
    assert row(conn, drive_like / "suelto.txt") is None


def test_deep_change_in_collapsed_folder_is_counted(tmp_path, conn):
    drive_like = tmp_path / "disco"
    deep = drive_like / "Juegos" / "Riot" / "lol" / "data.pak"
    write(deep, 7000)
    roots = [{"path": str(drive_like), "mode": "carpetas", "depth": 1}]
    scan(tmp_path, roots)
    riot = drive_like / "Juegos" / "Riot"
    mtime = riot.stat().st_mtime
    write(deep, 9000)  # actualización dentro: la fecha de Riot no cambia
    os.utime(riot, (mtime, mtime))
    scan(tmp_path, roots)
    assert row(conn, drive_like / "Juegos")["size"] == 9000


def test_nested_full_root_is_kept_and_counted(tmp_path, conn):
    drive_like = tmp_path / "disco"
    home = drive_like / "Users" / "rodri"
    write(home / "doc.txt", 300)
    write(drive_like / "Windows" / "sys.dll", 50)
    roots = [{"path": str(drive_like), "mode": "carpetas", "depth": 3}, {"path": str(home), "mode": "completo"}]
    scan(tmp_path, roots)
    scan(tmp_path, roots)  # el segundo pase no debe borrar lo de la raíz completa
    assert row(conn, home / "doc.txt") is not None
    assert row(conn, drive_like)["size"] == 350
    assert row(conn, drive_like / "Users")["size"] == 300


def test_duplicates_hashed_in_stages(tmp_path, conn):
    r = tmp_path / "dups"
    a = write(r / "a.zip", data=b"A" * 9000)
    b = write(r / "copia" / "a.zip", data=b"A" * 9000)
    c = write(r / "c.zip", data=b"B" * 9000)
    unico = write(r / "unico.bin", data=b"C" * 9001)
    scan(tmp_path, full(r))
    ha, hb, hc = (row(conn, p) for p in (a, b, c))
    assert ha["hash_partial"] == hb["hash_partial"] != hc["hash_partial"]
    assert ha["hash_full"] == hb["hash_full"] is not None
    assert hc["hash_full"] is None  # su hash parcial no choca con nadie
    assert row(conn, unico)["hash_partial"] is None  # tamaño único: ni se abre


def test_cloud_only_files_are_never_opened(tmp_path, conn, monkeypatch):
    r = tmp_path / "onedrive"
    local = write(r / "a.bin", data=b"Z" * 9000)
    nube = write(r / "b.bin", data=b"Z" * 9000)
    opened = []
    real_open = open
    monkeypatch.setattr(hashing, "open", lambda p, *a: opened.append(p) or real_open(p, *a), raising=False)
    monkeypatch.setattr(winfs, "file_attrs", lambda p: winfs.RECALL_ON_DATA_ACCESS if p == str(nube) else 0)
    scan(tmp_path, full(r))
    assert str(nube) not in opened
    assert row(conn, nube)["hash_partial"] is None


def test_cloud_state_from_attributes():
    assert winfs.cloud_state(winfs.RECALL_ON_DATA_ACCESS, True) == "solo_nube"
    assert winfs.cloud_state(winfs.OFFLINE, False) == "solo_nube"
    assert winfs.cloud_state(winfs.PINNED, True) == "siempre_local"
    assert winfs.cloud_state(winfs.UNPINNED, True) == "local"
    assert winfs.cloud_state(0, False) is None


def test_only_fixed_drives():
    drives = winfs.fixed_drives()
    assert "C:\\" in drives and set(drives) <= set(os.listdrives())


def test_double_start_runs_once(tmp_path, tree):
    s = Scanner(tmp_path / "prueba.db")
    results = [s.start(full(tree)) for _ in range(5)]
    s._thread.join(30)
    assert results.count(True) == 1
    assert s.progress.status == "terminado"


def test_owner_on_demand(tmp_path):
    f = write(tmp_path / "x.txt", 1)
    o = winfs.owner(str(f))
    assert o and "\\" in o
    assert winfs.owner(str(tmp_path / "no-existe")) is None


def test_cancel_keeps_previous_index(tmp_path, tree, conn):
    scan(tmp_path, full(tree))
    before = conn.execute("SELECT count(*) FROM entries").fetchone()[0]
    s = Scanner(tmp_path / "prueba.db")
    s.stop()
    s.run(full(tree))  # start() limpia la señal; run() directo arranca ya detenido
    assert s.progress.status == "cancelado"
    assert conn.execute("SELECT count(*) FROM entries").fetchone()[0] == before


# --------------------------------------------------------------------- API

PORT, TOKEN = 8765, "t"


@pytest.fixture
def client(tmp_path, tree):
    app = create_app(PORT, token=TOKEN, db_path=tmp_path / "prueba.db")
    c = db.connect(tmp_path / "prueba.db")
    db.set_setting(c, "scan_roots", full(tree))
    c.close()
    return TestClient(app, base_url=f"http://127.0.0.1:{PORT}")


def wait_done(client):
    for _ in range(200):
        snap = client.get("/api/scan/status").json()
        if snap["status"] not in ("escaneando",):
            return snap
        time.sleep(0.05)
    raise AssertionError("el escaneo no terminó")


def test_api_scan_flow(client):
    assert client.get("/api/summary").json() == {"scanned": False}
    assert client.post("/api/scan").status_code == 403  # sin token
    assert client.post("/api/scan", headers={"X-Orden-Token": TOKEN}).status_code == 202
    assert wait_done(client)["status"] == "terminado"
    s = client.get("/api/summary").json()
    assert s["scanned"] and s["scanned_files"] > 0 and s["duration"] >= 0

    events = client.get("/api/scan/events").text
    assert events.startswith("data: ") and '"terminado"' in events


def test_api_search(client):
    client.post("/api/scan", headers={"X-Orden-Token": TOKEN})
    wait_done(client)
    names = lambda q: [r["name"] for r in client.get("/api/search", params={"q": q}).json()["results"]]
    assert names("elap") == ["ELAP_reporte.pdf"]
    assert names("(1)") == ["CV (1).docx"]
    assert "pubspec.yaml" in names("spec")
    assert names("cv") == ["CV (1).docx"]  # menos de 3 caracteres: LIKE
    assert names('"; DROP') == []
