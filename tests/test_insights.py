import time

import pytest
from fastapi.testclient import TestClient

from orden_pc import db, insights
from orden_pc.app import create_app
from orden_pc.scanner import Scanner

PORT, TOKEN = 8765, "t"
KB = 1024


def write(path, size=0, data=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if data is not None else b"x" * size)
    return path


@pytest.fixture
def disk(tmp_path, monkeypatch):
    """Un 'disco' en miniatura con carpeta de usuario dentro, escaneado como en la vida real."""
    d = tmp_path / "disco"
    h = d / "Users" / "rodri"
    write(d / "pagefile.sys", 900)
    write(d / "Windows" / "System32" / "k.dll", 500)
    write(d / "Riot Games" / "VALORANT" / "x.pak", 8000)
    write(d / "Program Files" / "App" / "app.exe", 300)
    write(d / "Program Files" / "Epic Games" / "Juego" / "j.pak", 2000)
    write(h / "AppData" / "Local" / "cache.bin", data=b"D" * 5000)
    write(h / "AppData" / "Local" / "cache2.bin", data=b"D" * 5000)  # duplicado, pero en AppData
    write(h / ".docker" / "img.tar", 700)
    write(h / "Proyectos" / "package.json", 10)
    write(h / "Proyectos" / "docs" / "manual.pdf", 100)  # dentro de un proyecto: cuenta como desarrollo
    write(h / "Proyectos" / "video" / "package.json", 10)
    write(h / "Desktop" / "chixi" / ".git" / "HEAD", 5)
    write(h / "Downloads" / "CV.pdf", data=b"C" * 6000)
    write(h / "Downloads" / "CV (1).pdf", data=b"C" * 6000)
    write(h / "Downloads" / "foto.jpg", 400)
    write(h / "Downloads" / "Genera" / "ELAP.docx", 50)
    monkeypatch.setenv("USERPROFILE", str(h))
    roots = [{"path": str(d), "mode": "carpetas", "depth": 3}, {"path": str(h), "mode": "completo"}]
    conn = db.connect(tmp_path / "prueba.db")
    db.set_setting(conn, "scan_roots", roots)
    db.set_setting(conn, "categorias", {
        "juegos": [str(d / "Riot Games"), str(d / "Program Files" / "Epic Games")],
        "sistema": [str(d / "Windows")],
        "apps": [str(d / "Program Files")],
    })
    s = Scanner(tmp_path / "prueba.db")
    s.run(roots)
    assert s.progress.status == "terminado", s.progress.error
    yield {"root": d, "home": h, "conn": conn}
    conn.close()


def test_categories(disk):
    c = insights.categories(disk["conn"], drive=str(disk["root"]) + "\\")
    by = {x["key"]: x["bytes"] for x in c["categories"]}
    assert by["juegos"] == 8000 + 2000
    assert by["sistema"] == 500 + 900  # Windows + archivos sueltos de la raíz
    assert by["apps"] == 300 + 10_000  # Program Files sin el juego de Epic, más AppData
    assert by["desarrollo"] == 10 + 100 + 10 + 5 + 700  # Proyectos (una vez), chixi y .docker
    assert by["documentos"] == 6000 * 2 + 50  # el manual.pdf del proyecto no se cuenta dos veces
    assert by["multimedia"] == 400
    assert by["otros"] >= 0
    assert [x["key"] for x in c["categories"]] == list(insights.CATEGORY_LABELS)


def test_status_cards(disk):
    cards = insights.status_cards(disk["conn"])
    assert cards["downloads"]["items"] == 4
    assert cards["duplicates"] == {"groups": 1, "wasted": 6000}  # el de AppData no cuenta
    assert {p["name"]: p["projects"] for p in cards["code"]["places"]} == {"Desktop": 1, "Proyectos": 1}


def test_timeline_counts_new_files_in_user_folders(disk):
    weeks = insights.timeline(disk["conn"], weeks=8)
    assert len(weeks) == 8
    # Archivos creados ahora, fuera de AppData y carpetas ocultas de primer nivel.
    assert weeks[-1]["files"] == 7  # 3 en Proyectos, 4 en Descargas
    assert sum(w["files"] for w in weeks[:-1]) == 0


def test_top_projects_skip_nested(disk):
    tops = insights.top_projects(disk["conn"])
    assert str(disk["home"] / "Proyectos") in tops
    assert str(disk["home"] / "Proyectos" / "video") not in tops


# ------------------------------------------------------------------------ API


@pytest.fixture
def client(tmp_path, disk):
    return TestClient(create_app(PORT, token=TOKEN, db_path=tmp_path / "prueba.db"), base_url=f"http://127.0.0.1:{PORT}")


def test_roots_and_children(client, disk):
    roots = client.get("/api/roots").json()["roots"]
    assert [r["mode"] for r in roots] == ["carpetas", "completo"]
    kids = client.get("/api/children", params={"path": str(disk["root"])}).json()
    names = [k["name"] for k in kids["children"]]
    assert names[0] == "Users" and "Riot Games" in names
    assert kids["loose"] == 900
    home_kids = client.get("/api/children", params={"path": str(disk["home"])}).json()["children"]
    assert next(k for k in home_kids if k["name"] == "AppData")["protected"] is True
    assert next(k for k in home_kids if k["name"] == "Downloads")["protected"] is False


def test_list_filters_and_sort(client, disk):
    dl = str(disk["home"] / "Downloads")
    get = lambda **p: client.get("/api/list", params={"path": dl, **p}).json()
    assert [i["name"] for i in get()["items"]] == ["Genera", "CV (1).pdf", "CV.pdf", "foto.jpg"]
    assert [i["name"] for i in get(sort="size", order="desc")["items"]][:2] == ["CV (1).pdf", "CV.pdf"]
    assert [i["name"] for i in get(type="imagenes")["items"]] == ["foto.jpg"]
    assert [i["name"] for i in get(type="carpeta")["items"]] == ["Genera"]
    assert get(older=30)["items"] == []
    assert len(get(since=1)["items"]) == 4
    assert get(cloud="solo_nube")["items"] == []
    assert get()["mode"] == "completo"
    assert client.get("/api/list", params={"path": dl, "sort": "drop table"}).status_code == 422
    assert client.get("/api/list", params={"path": dl, "type": "raro"}).status_code == 422


def test_folder_mode_listing(client, disk):
    r = client.get("/api/list", params={"path": str(disk["root"])}).json()
    assert r["mode"] == "carpetas"
    assert all(i["is_dir"] for i in r["items"])


def test_entry_details(client, disk):
    cv = str(disk["home"] / "Downloads" / "CV.pdf")
    d = client.get("/api/entry", params={"path": cv}).json()
    assert d["type"] == "documentos" and d["size"] == 6000
    assert d["duplicates"] == [str(disk["home"] / "Downloads" / "CV (1).pdf")]
    assert d["owner"] and "\\" in d["owner"]
    assert isinstance(d["attrs"], list)
    assert d["protected_reason"] is None
    pj = client.get("/api/entry", params={"path": str(disk["home"] / "Proyectos" / "docs" / "manual.pdf")}).json()
    assert pj["project"]["path"] == str(disk["home"] / "Proyectos")
    cache = client.get("/api/entry", params={"path": str(disk["home"] / "AppData" / "Local" / "cache.bin")}).json()
    assert "AppData" in cache["protected_reason"]


def test_unknown_path_is_404_not_probed(client):
    assert client.get("/api/entry", params={"path": "C:\\Windows\\System32"}).status_code == 404
    assert client.get("/api/list", params={"path": "C:\\no\\existe"}).status_code == 404


def test_user_meta(client, disk):
    cv = str(disk["home"] / "Downloads" / "CV.pdf")
    body = {"path": cv, "tags": ["Carrera", " carrera ", "CV,2026"], "note": "Versión enviada a Cambridge"}
    assert client.post("/api/entry/meta", json=body).status_code == 403  # sin token
    h = {"X-Orden-Token": TOKEN}
    r = client.post("/api/entry/meta", json=body, headers=h).json()
    assert r["user_tags"] == ["Carrera", "CV 2026"]
    d = client.get("/api/entry", params={"path": cv}).json()
    assert d["note"] == "Versión enviada a Cambridge" and d["user_tags"] == ["Carrera", "CV 2026"]
    assert client.get("/api/tags").json()["user"] == ["Carrera", "CV 2026"]
    listed = client.get("/api/list", params={"path": str(disk["home"] / "Downloads"), "tag": "Carrera"}).json()["items"]
    assert [i["name"] for i in listed] == ["CV.pdf"]
    client.post("/api/entry/meta", json={"path": cv, "tags": [], "note": "  "}, headers=h)
    assert client.get("/api/tags").json()["user"] == []
    assert client.post("/api/entry/meta", json={"path": "C:\\x.txt", "tags": ["a"]}, headers=h).status_code == 404
    # La nota no toca el archivo.
    assert (disk["home"] / "Downloads" / "CV.pdf").read_bytes() == b"C" * 6000


def test_insights_endpoints(client, disk, monkeypatch):
    monkeypatch.setattr(insights.shutil, "disk_usage", lambda d: type("U", (), {"total": 10**6, "used": 5 * 10**5, "free": 5 * 10**5})())
    cats = client.get("/api/insights/categories").json()
    assert cats["free"] == 5 * 10**5 and len(cats["categories"]) == 7
    assert client.get("/api/insights/cards").json()["downloads"]["items"] == 4
    assert len(client.get("/api/insights/timeline", params={"weeks": 12}).json()["weeks"]) == 12
    assert client.get("/api/insights/timeline", params={"weeks": 1000}).status_code == 422
