import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

import orden_pc.__main__ as entry
from orden_pc.app import create_app, require_edit_mode

PORT = 8765
TOKEN = "token-de-prueba"
BASE = f"http://127.0.0.1:{PORT}"


@pytest.fixture
def app(tmp_path):
    (tmp_path / "index.html").write_text("<html><head></head><body></body></html>", encoding="utf-8")
    app = create_app(PORT, token=TOKEN, static_dir=tmp_path)

    @app.post("/api/test/write", dependencies=[Depends(require_edit_mode)])
    def fake_write():
        return {"ok": True}

    return app


@pytest.fixture
def client(app):
    return TestClient(app, base_url=BASE)


def ok_headers(**extra):
    return {"X-Orden-Token": TOKEN, **extra}


def test_health(client):
    assert client.get("/api/health").json() == {"ok": True}


def test_disk_usage_is_real_and_consistent(client):
    drives = client.get("/api/disk").json()["drives"]
    assert any(d["drive"].upper().startswith("C:") for d in drives)
    for d in drives:
        assert d["total"] > 0 and d["used"] + d["free"] <= d["total"]


@pytest.mark.parametrize("host", ["evil.com", f"evil.com:{PORT}", "127.0.0.1:9999", "0.0.0.0:8765", ""])
def test_foreign_host_rejected(client, host):
    assert client.get("/api/health", headers={"Host": host}).status_code == 400


def test_localhost_host_allowed(client):
    assert client.get("/api/health", headers={"Host": f"localhost:{PORT}"}).status_code == 200


@pytest.mark.parametrize("headers", [{}, {"X-Orden-Token": "otro"}, {"X-Orden-Token": ""}])
def test_write_without_valid_token_rejected(client, headers):
    r = client.post("/api/session/edit-mode", json={"enabled": True}, headers=headers)
    assert r.status_code == 403
    assert client.get("/api/session").json() == {"edit_mode": False}


def test_write_from_foreign_origin_rejected(client):
    r = client.post(
        "/api/session/edit-mode",
        json={"enabled": True},
        headers=ok_headers(Origin="http://evil.com"),
    )
    assert r.status_code == 403


def test_non_ascii_token_rejected_not_crashing(client):
    r = client.post("/api/session/edit-mode", json={"enabled": True}, headers={"X-Orden-Token": "ñ".encode()})
    assert r.status_code == 403


@pytest.mark.parametrize("path", ["/", "/api/health"])
def test_cannot_be_framed(client, path):
    r = client.get(path)
    assert r.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]


def test_index_reread_after_rebuild(client, tmp_path):
    (tmp_path / "index.html").write_text("<html><head></head><body>v2</body></html>", encoding="utf-8")
    assert "v2" in client.get("/").text


def test_edit_mode_starts_off_and_toggles(client):
    assert client.get("/api/session").json() == {"edit_mode": False}
    r = client.post("/api/session/edit-mode", json={"enabled": True}, headers=ok_headers(Origin=BASE))
    assert r.json() == {"edit_mode": True}
    r = client.post("/api/session/edit-mode", json={"enabled": False}, headers=ok_headers())
    assert r.json() == {"edit_mode": False}


def test_write_route_needs_edit_mode(client):
    assert client.post("/api/test/write", headers=ok_headers()).status_code == 403
    client.post("/api/session/edit-mode", json={"enabled": True}, headers=ok_headers())
    assert client.post("/api/test/write", headers=ok_headers()).status_code == 200


def test_new_app_resets_edit_mode(app):
    app.state.edit_mode = True
    fresh = TestClient(create_app(PORT, token=TOKEN), base_url=BASE)
    assert fresh.get("/api/session").json() == {"edit_mode": False}


def test_index_carries_token_and_spa_fallback(client):
    for path in ("/", "/explorador"):
        r = client.get(path)
        assert f'<meta name="orden-token" content="{TOKEN}">' in r.text
        assert r.headers["cache-control"] == "no-store"
    assert client.get("/api/no-existe").status_code == 404


def test_random_token_per_app():
    a, b = create_app(PORT), create_app(PORT)
    assert a.state.token != b.state.token and len(a.state.token) >= 40


def test_main_binds_loopback_only(monkeypatch):
    calls = {}
    monkeypatch.setattr(entry, "ensure_frontend_built", lambda: None)
    monkeypatch.setattr(entry.webbrowser, "open", lambda url: None)
    monkeypatch.setattr(entry.uvicorn, "run", lambda app, **kw: calls.update(kw))
    entry.main()
    assert calls["host"] == "127.0.0.1"
