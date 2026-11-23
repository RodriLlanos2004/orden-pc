import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from orden_pc import db
from orden_pc.app import create_app

PORT, TOKEN = 8765, "t"
H = {"X-Orden-Token": TOKEN}


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "rodri"
    (h / "Privado").mkdir(parents=True)
    (h / "Privado" / "diario.txt").write_text("x")
    (h / "Downloads").mkdir()
    monkeypatch.setenv("USERPROFILE", str(h))
    conn = db.connect(tmp_path / "prueba.db")
    db.set_setting(conn, "scan_roots", [{"path": str(h), "mode": "completo"}])
    conn.close()
    return h


@pytest.fixture
def client(tmp_path, home):
    c = TestClient(create_app(PORT, token=TOKEN, db_path=tmp_path / "prueba.db"), base_url=f"http://127.0.0.1:{PORT}")
    c.post("/api/session/edit-mode", json={"enabled": True}, headers=H)
    return c


def test_added_protected_path_blocks_writes(client, home):
    r = client.post("/api/settings/protected", json={"path": str(home / "Privado")}, headers=H)
    assert r.status_code == 200 and r.json()["protected_extra"] == [str(home / "Privado")]
    p = client.post("/api/ops/plan", json={"kind": "mover", "paths": [str(home / "Privado" / "diario.txt")], "dest": str(home / "Downloads")}, headers=H).json()
    assert p["steps"] == [] and "ruta protegida" in p["blocked"][0]["reason"]
    assert client.post("/api/ops/plan", json={"kind": "papelera", "paths": [str(home / "Privado")]}, headers=H).json()["steps"] == []
    # Sobrevive a reiniciar la app.
    again = TestClient(create_app(PORT, token=TOKEN, db_path=Path(home).parent / "prueba.db"), base_url=f"http://127.0.0.1:{PORT}")
    assert again.get("/api/settings").json()["protected_extra"] == [str(home / "Privado")]


def test_protected_list_only_grows(client, home):
    client.post("/api/settings/protected", json={"path": str(home / "Privado")}, headers=H)
    for method in ("delete", "put", "patch"):
        r = getattr(client, method)("/api/settings/protected", headers=H)
        assert r.status_code == 405  # no existe forma de quitar ni reemplazar
    assert client.post("/api/settings/protected", json={"path": str(home / "Privado" / "sub")}, headers=H).status_code == 409
    assert client.post("/api/settings/protected", json={"path": "C:\\Windows\\Temp"}, headers=H).status_code == 409


@pytest.mark.parametrize("raw", ["C:\\", "relativa\\x", "\\\\servidor\\x", "C:\\a\\..\\b", "C:\\a:b"])
def test_protected_rejects_bad_paths(client, raw):
    assert client.post("/api/settings/protected", json={"path": raw}, headers=H).status_code == 422


def test_settings_writes_need_token(client, home):
    assert client.post("/api/settings/protected", json={"path": str(home / "Privado")}).status_code == 403
    assert client.post("/api/settings/backup").status_code == 403


def test_scan_roots(client, home, tmp_path, monkeypatch):
    monkeypatch.setattr("orden_pc.scanner.default_roots", lambda: [{"path": str(home), "mode": "completo"}])
    r = client.put("/api/settings/roots", json={"roots": [{"path": str(home), "mode": "completo"}, {"path": str(home / "Downloads"), "mode": "carpetas"}]}, headers=H)
    assert r.status_code == 200 and r.json()["roots"][1] == {"path": str(home / "Downloads"), "mode": "carpetas", "depth": 3}
    assert client.put("/api/settings/roots", json={"roots": []}, headers=H).status_code == 422
    assert client.put("/api/settings/roots", json={"roots": [{"path": str(home / "no-existe"), "mode": "completo"}]}, headers=H).status_code == 422
    assert client.put("/api/settings/roots", json={"roots": [{"path": str(home), "mode": "todo"}]}, headers=H).status_code == 422
    # Volver a las de siempre borra la elección.
    assert client.put("/api/settings/roots", json={"roots": None}, headers=H).json()["roots_custom"] is False
    conn = db.connect(tmp_path / "prueba.db")
    assert db.get_setting(conn, "scan_roots", None) is None
    conn.close()


def test_backup_is_a_working_copy(client, tmp_path):
    r = client.post("/api/settings/backup", headers=H)
    assert r.status_code == 200
    copy = Path(r.json()["path"])
    assert copy.parent == tmp_path / "respaldos" and copy.stat().st_size > 0
    c = sqlite3.connect(copy)  # `with` de sqlite3 no cierra la conexión
    try:
        assert c.execute("SELECT count(*) FROM sqlite_master WHERE name = 'audit_log'").fetchone()[0] == 1
    finally:
        c.close()
    assert client.get("/api/settings").json()["db"]["last_backups"][0]["name"] == copy.name


@pytest.mark.parametrize("site", ["cross-site", "same-site"])
def test_other_pages_cannot_call_the_api(client, site):
    assert client.get("/api/health", headers={"Sec-Fetch-Site": site}).status_code == 403
    assert client.get("/api/apps/search", params={"q": "x"}, headers={"Sec-Fetch-Site": site}).status_code == 403
    assert client.get("/api/health", headers={"Sec-Fetch-Site": "same-origin"}).status_code == 200
