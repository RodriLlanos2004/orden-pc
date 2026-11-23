import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from orden_pc import db, organizer
from orden_pc.app import create_app

PORT, TOKEN = 8765, "t"
H = {"X-Orden-Token": TOKEN}
UNI = Path("OneDrive", "10_Universidad", "Sexto_Semestre")


def write(path, size=10):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    return path


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Copia en miniatura de lo que describe el brief, dentro de la carpeta temporal."""
    h = tmp_path / "rodri"
    dl, desk = h / "Downloads", h / "Desktop"
    for name in ["M02_widgets.dart", "Chixi_Reporte (1).pdf", "HW07 - Copy.docx", "ELAP_presentacion.pptx",
                 "Curriculum_Rodri.pdf", "random.txt", "desktop.ini", "setup.crdownload"]:
        write(dl / name)
    write(dl / "chixi-refactor" / "README.md")  # segunda copia del repo
    write(desk / "chixi-refactor" / "README.md")
    write(desk / "PRACTICA_DOCKER" / "Dockerfile")
    write(h / "Documents" / "Elevator-Simulator" / "main.py")
    write(h / "Proyectos" / "package.json")
    write(h / "Proyectos" / "video-semiconductores" / "index.ts")
    (h / "OneDrive").mkdir()
    write(h / "AppData" / "Local" / "x.bin")
    monkeypatch.setenv("USERPROFILE", str(h))
    monkeypatch.setenv("OneDrive", str(h / "OneDrive"))
    vars = {"Usuario": str(h), "OneDrive": str(h / "OneDrive"), "Descargas": str(dl), "Escritorio": str(desk)}
    monkeypatch.setattr(organizer, "variables", lambda: vars)
    conn = db.connect(tmp_path / "prueba.db")
    db.set_setting(conn, "scan_roots", [{"path": str(h), "mode": "completo"}])
    conn.close()
    return h


@pytest.fixture
def client(tmp_path, home):
    c = TestClient(create_app(PORT, token=TOKEN, db_path=tmp_path / "prueba.db"), base_url=f"http://127.0.0.1:{PORT}")
    c.post("/api/session/edit-mode", json={"enabled": True}, headers=H)
    return c


def by_name(view):
    return {p["name"]: p for p in view["propuestas"]}


def plan(client, **body):
    r = client.post("/api/ops/plan", json=body, headers=H)
    assert r.status_code == 200, r.text
    return r.json()


def apply(client, p, ack=False):
    r = client.post(f"/api/ops/apply/{p['id']}", json={"ack": ack}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------- nombres


def test_delivery_name():
    t = time.mktime((2026, 3, 9, 12, 0, 0, 0, 0, -1))
    assert organizer.delivery_name("Chixi_Reporte (1).pdf", t, "Calidad_Software") == "2026-03-09_Calidad_Software_Chixi_Reporte_v1.pdf"
    assert organizer.delivery_name("HW07 - Copy.DOCX", t, "Ingenieria_Software_II") == "2026-03-09_Ingenieria_Software_II_HW07_v1.docx"
    assert organizer.delivery_name("Copia de informe final - copia (2).pdf", t, None) == "2026-03-09_informe_final_v1.pdf"
    assert organizer.delivery_name("Calidad Software tarea 3 v2.pdf", t, "Calidad_Software") == "2026-03-09_Calidad_Software_tarea_3_v1.pdf"
    assert organizer.delivery_name("2026-01-02_Bases_Avanzadas_ER_v1.pdf", t, "Bases_Avanzadas", 2) == "2026-01-02_Bases_Avanzadas_ER_v2.pdf"
    assert organizer.lower_name("PRACTICA_DOCKER") == "practica-docker"
    assert organizer.lower_name("Elevator-Simulator") == "elevator-simulator"


# ---------------------------------------------------------------------- propuesta


def test_propose_classifies_brief_examples(client, home):
    view = client.get("/api/organizer").json()
    got = by_name(view)
    uni = str(home / UNI)
    assert got["M02_widgets.dart"]["dest"] == os.path.join(uni, "Prog_Dispositivos_Moviles", "Entregas")
    assert got["M02_widgets.dart"]["new_name"] == "M02_widgets.dart"
    assert got["Chixi_Reporte (1).pdf"]["dest"] == os.path.join(uni, "Calidad_Software", "Entregas")
    assert got["Chixi_Reporte (1).pdf"]["new_name"].endswith("_Calidad_Software_Chixi_Reporte_v1.pdf")
    assert got["HW07 - Copy.docx"]["new_name"].endswith("_Ingenieria_Software_II_HW07_v1.docx")
    assert got["ELAP_presentacion.pptx"]["dest"] == str(home / "OneDrive" / "30_Genera" / "ELAP")
    assert got["Curriculum_Rodri.pdf"]["dest"] == str(home / "OneDrive" / "20_Carrera" / "CV_y_Perfil")
    assert got["PRACTICA_DOCKER"]["new_name"] == "practica-docker" and got["PRACTICA_DOCKER"]["dest"] == str(home / "Dev" / "uni")
    assert got["Elevator-Simulator"]["new_name"] == "elevator-simulator"
    assert got["video-semiconductores"]["rule"] == "video-semiconductores"
    assert got["Proyectos"]["rule"] == "remotion"
    chixi = [p for p in view["propuestas"] if p["name"] == "chixi-refactor"]
    assert len(chixi) == 2 and all("Elige cuál mover" in p["conflict"] for p in chixi)
    assert got["PRACTICA_DOCKER"]["conflict"] is None
    assert [p["name"] for p in view["por_clasificar"]] == ["random.txt"]  # sin desktop.ini ni descargas a medias
    names = {p["name"] for p in view["propuestas"]} | {p["name"] for p in view["por_clasificar"]}
    assert not names & {"AppData", "OneDrive", "Downloads", "Desktop", "Documents", "package.json"}
    assert {f["exists"] for f in view["carpetas"]} == {False}
    assert len(view["carpetas"]) == 13 - 2 + 2 * 8  # {Materia} se repite en dos líneas


def test_delivery_version_goes_up_when_taken(client, home):
    entregas = home / UNI / "Calidad_Software" / "Entregas"
    first = client.get("/api/organizer").json()
    name = by_name(first)["Chixi_Reporte (1).pdf"]["new_name"]
    write(entregas / name)
    assert by_name(client.get("/api/organizer").json())["Chixi_Reporte (1).pdf"]["new_name"] == name.replace("_v1", "_v2")


def test_rules_are_ordered_and_can_be_disabled(client, home):
    rules = client.get("/api/organizer").json()["reglas"]
    for r in rules:
        r["activa"] = r["id"] != "cv"
    rules.insert(0, {"nombre": "Todo PDF a la bandeja", "extensiones": ["PDF"], "destino": "{OneDrive}\\00_Bandeja"})
    r = client.put("/api/organizer/rules", json={"rules": rules}, headers=H)
    assert r.status_code == 200, r.text
    got = by_name(r.json())
    assert got["Curriculum_Rodri.pdf"]["dest"] == str(home / "OneDrive" / "00_Bandeja")
    assert got["Chixi_Reporte (1).pdf"]["rule_name"] == "Todo PDF a la bandeja"  # la primera que coincide gana
    assert r.json()["reglas"][0]["extensiones"] == ["pdf"]


@pytest.mark.parametrize(
    "rule,msg",
    [
        ({"nombre": "x", "destino": "{OneDrive}\\a"}, "al menos una"),
        ({"nombre": "x", "palabras": ["a"], "destino": "{Nube}\\a"}, "variable"),
        ({"nombre": "x", "palabras": ["a"], "destino": "carpeta\\a"}, "ruta completa"),
        ({"nombre": "x", "palabras": ["a"], "destino": "{OneDrive}\\a", "tipo": "todo"}, "tipo"),
        ({"nombre": "", "palabras": ["a"], "destino": "{OneDrive}\\a"}, "nombre"),
    ],
)
def test_invalid_rules_are_rejected(client, rule, msg):
    r = client.put("/api/organizer/rules", json={"rules": [rule]}, headers=H)
    assert r.status_code == 422 and msg in r.json()["detail"]


def test_structure_is_editable(client, home):
    r = client.put("/api/organizer/structure", headers=H, json={
        "materias": ["Redes"], "carpetas": ["{OneDrive}\\10_U\\{Materia}\\Entregas"], "origenes": ["{Descargas}"],
    })
    assert r.status_code == 200, r.text
    assert [f["path"] for f in r.json()["carpetas"]] == [str(home / "OneDrive" / "10_U" / "Redes" / "Entregas")]
    assert client.put("/api/organizer/structure", headers=H, json={"materias": ["a/b"], "carpetas": [], "origenes": []}).status_code == 422


def test_settings_need_token(client):
    assert client.put("/api/organizer/rules", json={"rules": []}).status_code == 403


# ---------------------------------------------------------------------- plan y aplicar


def moves_of(view, *names):
    return [{"src": p["path"], "dest": p["dest"], "name": p["new_name"]} for p in view["propuestas"] if not names or p["name"] in names]


def test_organize_end_to_end_and_undo(client, home):
    before = sorted(str(p.relative_to(home)) for p in home.rglob("*"))
    view = client.get("/api/organizer").json()
    p = plan(client, kind="organizar", moves=moves_of(view))
    ops_ = [s["op"] for s in p["steps"]]
    assert ops_.index("mover") > max(i for i, o in enumerate(ops_) if o == "crear")  # carpetas antes de mover
    # Dos repos chixi-refactor van al mismo destino: el segundo se bloquea, nunca se sobrescribe.
    assert [b["reason"] for b in p["blocked"]] == ["Ya existe «chixi-refactor» en el destino. Orden PC nunca sobrescribe."]
    movers = [s for s in p["steps"] if s["op"] == "mover"]
    assert movers.index(next(s for s in movers if s["src"].endswith("video-semiconductores"))) < \
        movers.index(next(s for s in movers if s["src"] == str(home / "Proyectos")))  # el anidado sale primero
    assert p["confirm"].startswith("Crear ") and " y mover " in p["confirm"]

    result = apply(client, p)
    assert result["done"] == result["total"]
    assert (home / "Dev" / "uni" / "practica-docker" / "Dockerfile").exists()
    assert (home / "Dev" / "personal" / "video-semiconductores" / "index.ts").exists()
    assert (home / "Dev" / "personal" / "Proyectos" / "package.json").exists()
    assert not (home / "Dev" / "personal" / "Proyectos" / "video-semiconductores").exists()
    entregas = home / UNI / "Calidad_Software" / "Entregas"
    assert [f.name for f in entregas.iterdir()][0].endswith("_Calidad_Software_Chixi_Reporte_v1.pdf")
    assert by_name(client.get("/api/organizer").json()).keys() == {"chixi-refactor"}  # solo queda la copia bloqueada

    undo = plan(client, kind="deshacer", ids=[r["audit_id"] for r in result["results"]])
    assert undo["blocked"] == []
    assert apply(client, undo)["done"] == len(result["results"])
    after = sorted(str(p.relative_to(home)) for p in home.rglob("*"))
    assert after == before  # todo en su lugar; las carpetas creadas (vacías) fueron a la Papelera


def test_folder_move_then_files_inside_it(client, home):
    """Mover Sexto_Semestre a 10_Universidad y en el mismo plan dejar una entrega dentro de él."""
    sexto = home / "OneDrive" / "Sexto_Semestre"
    write(sexto / "Calidad_Software" / "notas.pdf")
    tarea = write(home / "Downloads" / "tarea.pdf")
    uni = home / "OneDrive" / "10_Universidad"
    p = plan(client, kind="organizar", moves=[
        {"src": str(tarea), "dest": str(uni / "Sexto_Semestre" / "Calidad_Software" / "Entregas"), "name": "tarea.pdf"},
        {"src": str(sexto), "dest": str(uni), "name": "Sexto_Semestre"},
    ])
    assert [(s["op"], Path(s["dst"]).name) for s in p["steps"]] == [
        ("crear", "10_Universidad"), ("mover", "Sexto_Semestre"), ("crear", "Entregas"), ("mover", "tarea.pdf"),
    ]
    assert apply(client, p)["done"] == 4
    assert (uni / "Sexto_Semestre" / "Calidad_Software" / "notas.pdf").exists()
    assert (uni / "Sexto_Semestre" / "Calidad_Software" / "Entregas" / "tarea.pdf").exists()


def test_undo_keeps_created_folder_with_new_content(client, home):
    view = client.get("/api/organizer").json()
    result = apply(client, plan(client, kind="organizar", moves=moves_of(view, "Curriculum_Rodri.pdf")))
    cv = home / "OneDrive" / "20_Carrera" / "CV_y_Perfil"
    write(cv / "otro.pdf")
    undo = plan(client, kind="deshacer", ids=[r["audit_id"] for r in result["results"]])
    assert undo["blocked"] and all("ya tiene contenido" in b["reason"] for b in undo["blocked"])
    apply(client, undo)
    assert (home / "Downloads" / "Curriculum_Rodri.pdf").exists() and (cv / "otro.pdf").exists()


def test_create_missing_structure_folders(client, home):
    view = client.get("/api/organizer").json()
    p = plan(client, kind="organizar", folders=[f["path"] for f in view["carpetas"]])
    assert p["confirm"].startswith("Crear ") and all(s["op"] == "crear" for s in p["steps"])
    apply(client, p)
    assert all(f["exists"] for f in client.get("/api/organizer").json()["carpetas"])


def test_organize_never_touches_protected_or_outside(client, home, tmp_path):
    f = write(home / "Downloads" / "a.pdf")
    p = plan(client, kind="organizar", moves=[
        {"src": str(f), "dest": str(home / "AppData" / "Roaming"), "name": "a.pdf"},
        {"src": str(f), "dest": str(tmp_path / "fuera"), "name": "a.pdf"},
        {"src": str(f), "dest": str(home / "OneDrive"), "name": "con?.pdf"},
        {"src": str(home / "AppData" / "Local" / "x.bin"), "dest": str(home / "OneDrive"), "name": "x.bin"},
    ])
    assert p["steps"] == [] and len(p["blocked"]) == 4


def test_organize_requires_edit_mode(client, home):
    view = client.get("/api/organizer").json()
    p = plan(client, kind="organizar", moves=moves_of(view, "random.txt") or moves_of(view, "ELAP_presentacion.pptx"))
    client.post("/api/session/edit-mode", json={"enabled": False}, headers=H)
    assert client.post(f"/api/ops/apply/{p['id']}", json={}, headers=H).status_code == 403
