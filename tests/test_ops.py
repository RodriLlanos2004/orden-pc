import os
import re
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from orden_pc import db, ops, trash
from orden_pc.app import create_app
from orden_pc.scanner import Scanner

PORT, TOKEN = 8765, "t"
H = {"X-Orden-Token": TOKEN}
ROOT = Path(__file__).resolve().parents[1]


def write(path, size=0, data=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if data is not None else b"x" * size)
    return path


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "rodri"
    dl = h / "Downloads"
    write(dl / "CV.pdf", 600)
    write(dl / "notas.txt", 40)
    write(dl / "Genera" / "ELAP.docx", 300)
    write(dl / "Genera" / "fotos" / "a.jpg", 200)
    write(h / "OneDrive" / "Sexto" / "tarea.pdf", 500)
    write(h / "OneDrive" / "Sexto" / "lectura.pdf", 700)
    write(h / "AppData" / "Local" / "cache.bin", 10)
    (h / "Dev").mkdir()
    monkeypatch.setenv("USERPROFILE", str(h))
    monkeypatch.setenv("OneDrive", str(h / "OneDrive"))
    roots = [{"path": str(h), "mode": "completo"}]
    conn = db.connect(tmp_path / "prueba.db")
    db.set_setting(conn, "scan_roots", roots)
    conn.close()
    Scanner(tmp_path / "prueba.db").run(roots)
    return h


@pytest.fixture
def client(tmp_path, home):
    c = TestClient(create_app(PORT, token=TOKEN, db_path=tmp_path / "prueba.db"), base_url=f"http://127.0.0.1:{PORT}")
    c.post("/api/session/edit-mode", json={"enabled": True}, headers=H)
    return c


@pytest.fixture
def conn(tmp_path, home):
    c = db.connect(tmp_path / "prueba.db")
    yield c
    c.close()


def plan(client, **body):
    r = client.post("/api/ops/plan", json=body, headers=H)
    assert r.status_code == 200, r.text
    return r.json()


def apply(client, p, ack=False, status=200):
    r = client.post(f"/api/ops/apply/{p['id']}", json={"ack": ack}, headers=H)
    assert r.status_code == status, r.text
    return r.json()


def size_of(conn, path):
    row = conn.execute("SELECT size FROM entries WHERE path = ?", (str(path),)).fetchone()
    return row["size"] if row else None


def names(client, q):
    return [r["name"] for r in client.get("/api/search", params={"q": q}).json()["results"]]


# ---------------------------------------------------------------------- seguridad del flujo


def test_apply_needs_edit_mode_and_token(client, home):
    client.post("/api/session/edit-mode", json={"enabled": False}, headers=H)
    p = plan(client, kind="crear", path=str(home / "Downloads"), name="Nueva")
    assert client.post(f"/api/ops/apply/{p['id']}", json={}, headers=H).status_code == 403
    assert client.post(f"/api/ops/apply/{p['id']}", json={}).status_code == 403  # sin token
    assert not (home / "Downloads" / "Nueva").exists()
    client.post("/api/session/edit-mode", json={"enabled": True}, headers=H)
    assert apply(client, p)["done"] == 1


def test_plan_is_used_once_and_expires(client, home, monkeypatch):
    p = plan(client, kind="crear", path=str(home / "Downloads"), name="Una")
    apply(client, p)
    assert "caducó" in apply(client, p, status=409)["detail"]
    monkeypatch.setattr(ops, "PLAN_TTL", 0)
    p2 = plan(client, kind="crear", path=str(home / "Downloads"), name="Dos")
    apply(client, p2, status=409)
    assert not (home / "Downloads" / "Dos").exists()


def test_scan_in_progress_blocks_apply(client, home, monkeypatch):
    p = plan(client, kind="crear", path=str(home / "Downloads"), name="X")
    monkeypatch.setattr(Scanner, "running", property(lambda self: True))
    assert "escaneo" in apply(client, p, status=409)["detail"]


@pytest.mark.parametrize("name", ["", "CON", "nul.txt", "a.", " a", "a ", "a/b", "a:b", "a*b", "x" * 201])
def test_bad_names(client, home, name):
    r = client.post("/api/ops/plan", json={"kind": "crear", "path": str(home / "Downloads"), "name": name}, headers=H)
    assert r.status_code == 422


# ---------------------------------------------------------------------- crear, renombrar, mover


def test_create_folder(client, conn, home):
    p = plan(client, kind="crear", path=str(home / "Downloads"), name="00_Bandeja")
    assert p["confirm"] == "Crear carpeta" and "00_Bandeja" in p["title"]
    r = apply(client, p)
    assert r["results"][0]["result"] == "hecho"
    assert (home / "Downloads" / "00_Bandeja").is_dir()
    assert "00_Bandeja" in names(client, "Bandeja")
    log = client.get("/api/history").json()["items"][0]
    assert (log["op"], log["result"], log["can_undo"]) == ("crear", "hecho", True)


def test_rename_updates_index_search_and_notes(client, conn, home):
    cv = home / "Downloads" / "CV.pdf"
    client.post("/api/entry/meta", json={"path": str(cv), "tags": ["Carrera"], "note": "enviado"}, headers=H)
    apply(client, plan(client, kind="renombrar", path=str(cv), name="2026-10-08_CV_v1.pdf"))
    new = home / "Downloads" / "2026-10-08_CV_v1.pdf"
    assert new.exists() and not cv.exists()
    assert names(client, "2026-10-08") == ["2026-10-08_CV_v1.pdf"]
    assert "CV.pdf" not in names(client, "CV.pdf")
    d = client.get("/api/entry", params={"path": str(new)}).json()
    assert d["ext"] == "pdf" and d["note"] == "enviado"
    # Cambio solo de mayúsculas
    apply(client, plan(client, kind="renombrar", path=str(new), name="2026-10-08_cv_v1.pdf"))
    assert os.listdir(home / "Downloads").count("2026-10-08_cv_v1.pdf") == 1


def test_move_updates_sizes_up_the_tree(client, conn, home):
    dl, dev = home / "Downloads", home / "Dev"
    before_dl, before_home = size_of(conn, dl), size_of(conn, home)
    r = apply(client, plan(client, kind="mover", paths=[str(dl / "Genera"), str(dl / "notas.txt")], dest=str(dev)))
    assert r["done"] == 2
    assert (dev / "Genera" / "fotos" / "a.jpg").exists() and (dev / "notas.txt").exists()
    assert size_of(conn, dl) == before_dl - 540
    assert size_of(conn, dev) == 540
    assert size_of(conn, home) == before_home
    assert size_of(conn, dev / "Genera" / "fotos" / "a.jpg") == 200
    assert size_of(conn, dl / "Genera") is None


def test_move_blocked_cases(client, home):
    dl = home / "Downloads"
    write(home / "Dev" / "CV.pdf", 1)
    p = plan(client, kind="mover", paths=[str(dl / "CV.pdf"), str(dl / "Genera"), str(dl / "notas.txt"),
                                         str(home / "AppData" / "Local" / "cache.bin"), "C:\\Windows\\win.ini"],
             dest=str(dl / "Genera" / "fotos"))
    reasons = {Path(b["path"]).name: b["reason"] for b in p["blocked"]}
    assert "dentro de sí misma" in reasons["Genera"]
    assert "AppData" in reasons["cache.bin"]
    assert "protegida" in reasons["win.ini"]
    assert [Path(s["src"]).name for s in p["steps"]] == ["CV.pdf", "notas.txt"]
    p2 = plan(client, kind="mover", paths=[str(dl / "CV.pdf"), str(dl / "notas.txt")], dest=str(home / "Dev"))
    assert "sobrescribe" in p2["blocked"][0]["reason"]
    assert client.post("/api/ops/plan", json={"kind": "mover", "paths": [str(dl / "CV.pdf")], "dest": str(home / "AppData")}, headers=H).status_code == 422


def test_never_overwrites_even_if_destination_appears_after_preview(client, home):
    dl = home / "Downloads"
    p = plan(client, kind="mover", paths=[str(dl / "CV.pdf")], dest=str(home / "Dev"))
    write(home / "Dev" / "CV.pdf", data=b"otro")
    r = apply(client, p)
    assert r["results"][0]["result"] == "omitido" and "sobrescribe" in r["results"][0]["message"]
    assert (home / "Dev" / "CV.pdf").read_bytes() == b"otro" and (dl / "CV.pdf").exists()


def test_changed_after_preview_is_skipped_and_stops_the_rest(client, home):
    dl = home / "Downloads"
    p = plan(client, kind="mover", paths=[str(dl / "CV.pdf"), str(dl / "notas.txt")], dest=str(home / "Dev"))
    time.sleep(0.02)
    write(dl / "CV.pdf", 999)
    r = apply(client, p)
    assert [x["result"] for x in r["results"]] == ["omitido", "omitido"]
    assert "Cambió desde la vista previa" in r["results"][0]["message"]
    assert "paso anterior" in r["results"][1]["message"]
    assert (dl / "notas.txt").exists()
    assert {i["result"] for i in client.get("/api/history").json()["items"]} == {"omitido"}


def test_git_repo_with_changes_needs_explicit_ack(client, home):
    repo = home / "Downloads" / "chixi-refactor"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    write(repo / "main.py", 10)
    p = plan(client, kind="mover", paths=[str(repo)], dest=str(home / "Dev"))
    assert p["needs_ack"] and p["warnings"][0]["level"] == "peligro" and "sin commit" in p["warnings"][0]["text"]
    assert "aviso" in apply(client, p, status=409)["detail"]
    assert apply(client, p, ack=True)["done"] == 1
    assert (home / "Dev" / "chixi-refactor" / ".git").is_dir()


def test_moving_cloud_only_files_out_of_onedrive_warns(client, conn, home):
    folder = home / "OneDrive" / "Sexto"
    conn.execute("UPDATE entries SET cloud = 'solo_nube' WHERE path = ?", (str(folder / "lectura.pdf"),))
    conn.commit()
    p = plan(client, kind="mover", paths=[str(folder)], dest=str(home / "Dev"))
    assert any("descargará" in w["text"] for w in p["warnings"])
    inside = plan(client, kind="mover", paths=[str(folder / "tarea.pdf")], dest=str(home / "OneDrive"))
    assert not inside["warnings"]


# ---------------------------------------------------------------------- Papelera y deshacer


def test_trash_then_undo(client, conn, home, papelera_falsa):
    dl = home / "Downloads"
    before = size_of(conn, dl)
    p = plan(client, kind="papelera", paths=[str(dl / "CV.pdf"), str(dl / "Genera")])
    assert p["confirm"] == "Enviar 2 elementos a la Papelera"
    r = apply(client, p)
    assert r["done"] == 2 and not (dl / "CV.pdf").exists() and not (dl / "Genera").exists()
    assert len(papelera_falsa.items) == 2
    assert size_of(conn, dl) == before - 1100 and size_of(conn, dl / "Genera" / "ELAP.docx") is None

    ids = [x["audit_id"] for x in r["results"]]
    u = plan(client, kind="deshacer", ids=ids)
    assert u["confirm"] == "Deshacer 2 cambios" and {s["op"] for s in u["steps"]} == {"restaurar"}
    assert apply(client, u)["done"] == 2
    assert (dl / "CV.pdf").exists() and (dl / "Genera" / "fotos" / "a.jpg").exists()
    assert size_of(conn, dl) == before and size_of(conn, dl / "Genera" / "fotos" / "a.jpg") == 200
    hist = {h["id"]: h for h in client.get("/api/history").json()["items"]}
    assert all(hist[i]["undone_by"] and not hist[i]["can_undo"] for i in ids)
    again = plan(client, kind="deshacer", ids=ids)
    assert not again["steps"] and all("Ya se deshizo" in b["reason"] for b in again["blocked"])


def test_undo_restores_the_exact_copy_that_change_sent(client, home, papelera_falsa):
    """Mismo nombre enviado dos veces: deshacer el primer envío trae la primera versión, no la última."""
    f = home / "Downloads" / "notas.txt"
    first = apply(client, plan(client, kind="papelera", paths=[str(f)]))
    write(f, data=b"segunda version")
    apply(client, plan(client, kind="crear", path=str(home / "Downloads"), name="tmp"))  # cualquier cambio entre medio
    papelera_falsa.items = [(o, s, t - 120) for o, s, t in papelera_falsa.items]  # el primer envío fue hace 2 min
    c = db.connect(db.default_db_path())
    c.execute("UPDATE audit_log SET ts = ts - 120 WHERE id = ?", (first["results"][0]["audit_id"],))
    c.commit()
    c.close()
    second = apply(client, plan(client, kind="papelera", paths=[str(f)]))
    assert second["done"] == 1 and len(papelera_falsa.items) == 2
    apply(client, plan(client, kind="deshacer", ids=[first["results"][0]["audit_id"]]))
    assert f.read_bytes() == b"x" * 40  # la primera versión


def test_trash_refuses_what_would_be_deleted_forever(client, home, papelera_falsa):
    papelera_falsa.max_bytes = 100
    p = plan(client, kind="papelera", paths=[str(home / "Downloads" / "CV.pdf")])
    assert not p["steps"] and "para siempre" in p["blocked"][0]["reason"]
    papelera_falsa.max_bytes = 10**9
    papelera_falsa.enabled = False
    p = plan(client, kind="papelera", paths=[str(home / "Downloads" / "CV.pdf")])
    assert not p["steps"] and "desactivada" in p["blocked"][0]["reason"]
    assert (home / "Downloads" / "CV.pdf").exists()


def test_trash_full_bin_warns(client, home, papelera_falsa):
    papelera_falsa.max_bytes, papelera_falsa.used_bytes = 1000, 900
    p = plan(client, kind="papelera", paths=[str(home / "Downloads" / "CV.pdf")])
    assert p["steps"] and any("lo más antiguo" in w["text"] for w in p["warnings"])


def test_failed_trash_is_reported_and_stops(client, home, papelera_falsa, monkeypatch):
    monkeypatch.setattr(trash, "send", lambda p: (_ for _ in ()).throw(OSError("Acceso denegado")))
    r = apply(client, plan(client, kind="papelera", paths=[str(home / "Downloads" / "CV.pdf"), str(home / "Downloads" / "notas.txt")]))
    assert [x["result"] for x in r["results"]] == ["error", "omitido"]
    assert (home / "Downloads" / "CV.pdf").exists()


def test_undo_move_and_rename(client, home):
    dl = home / "Downloads"
    r1 = apply(client, plan(client, kind="mover", paths=[str(dl / "CV.pdf")], dest=str(home / "Dev")))
    r2 = apply(client, plan(client, kind="renombrar", path=str(dl / "notas.txt"), name="notas_clase.txt"))
    u = plan(client, kind="deshacer", ids=[r1["results"][0]["audit_id"], r2["results"][0]["audit_id"]])
    assert apply(client, u)["done"] == 2
    assert (dl / "CV.pdf").exists() and (dl / "notas.txt").exists() and not (home / "Dev" / "CV.pdf").exists()


def test_undo_blocked_when_it_would_overwrite_or_file_changed(client, home):
    dl = home / "Downloads"
    r = apply(client, plan(client, kind="mover", paths=[str(dl / "CV.pdf"), str(dl / "notas.txt")], dest=str(home / "Dev")))
    write(dl / "CV.pdf", data=b"nuevo")  # alguien ocupó el lugar original
    time.sleep(0.02)
    write(home / "Dev" / "notas.txt", 77)  # el archivo cambió después de moverlo
    u = plan(client, kind="deshacer", ids=[x["audit_id"] for x in r["results"]])
    reasons = " ".join(b["reason"] for b in u["blocked"])
    assert not u["steps"] and "sobrescribe" in reasons and "cambió" in reasons


def test_undo_create_only_when_empty(client, home):
    r = apply(client, plan(client, kind="crear", path=str(home / "Downloads"), name="Vacía"))
    write(home / "Downloads" / "Vacía" / "algo.txt", 1)
    u = plan(client, kind="deshacer", ids=[r["results"][0]["audit_id"]])
    assert not u["steps"] and "contenido" in u["blocked"][0]["reason"]


# ---------------------------------------------------------------------- historial y abrir


def test_history_filters_and_csv(client, home):
    apply(client, plan(client, kind="crear", path=str(home / "Downloads"), name="Uno"))
    apply(client, plan(client, kind="renombrar", path=str(home / "Downloads" / "notas.txt"), name="n.txt"))
    assert [h["op"] for h in client.get("/api/history", params={"op": "renombrar"}).json()["items"]] == ["renombrar"]
    assert len(client.get("/api/history", params={"q": "Uno"}).json()["items"]) == 1
    csv_text = client.get("/api/history.csv").content.decode("utf-8")
    assert csv_text.startswith("\ufeffid,fecha,lote,acción") and "renombrar" in csv_text


def test_open_in_needs_edit_mode_and_known_path(client, home, monkeypatch):
    launched = []
    monkeypatch.setattr(subprocess, "Popen", lambda args, **kw: launched.append(args))
    body = {"path": str(home / "Downloads" / "CV.pdf"), "app": "explorer"}
    assert client.post("/api/open", json=body, headers=H).status_code == 200
    assert launched[-1] == ["explorer.exe", "/select,", body["path"]]
    assert client.post("/api/open", json={"path": "C:\\Windows\\notepad.exe", "app": "explorer"}, headers=H).status_code == 404
    client.post("/api/session/edit-mode", json={"enabled": False}, headers=H)
    assert client.post("/api/open", json=body, headers=H).status_code == 403


# ---------------------------------------------------------------------- reglas de código


def test_only_ops_and_trash_write_user_files():
    src = ROOT / "src" / "orden_pc"
    for p in src.glob("*.py"):
        text = p.read_text(encoding="utf-8")
        if p.name not in ("ops.py",):
            assert not re.search(r"\bos\.(rename|replace|mkdir|makedirs)\(", text), f"{p.name} escribe en disco fuera de ops"
        if p.name != "trash.py":
            assert "DeleteItem" not in text, f"{p.name} elimina fuera de trash.py"
    t = (src / "trash.py").read_text(encoding="utf-8")
    assert "FOFX_RECYCLEONDELETE" in t and "FOF_WANTNUKEWARNING" in t


@pytest.mark.papelera_real
def test_real_recycle_bin_roundtrip(tmp_path):
    """Usa la Papelera real con un archivo temporal y lo restaura. Se pide con: uv run pytest -m papelera_real"""
    f = write(tmp_path / f"orden-pc-prueba-{time.time_ns()}.txt", data=b"prueba")
    t0 = time.time() - 2
    assert trash.limits(str(f))["enabled"]
    trash.send(str(f))
    assert not f.exists() and trash.in_bin(str(f), t0)
    trash.restore(str(f), t0)
    assert f.read_bytes() == b"prueba"
