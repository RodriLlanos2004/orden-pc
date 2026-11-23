import os
import time
import zipfile

import pytest
from fastapi.testclient import TestClient

from orden_pc import apps, db, recommend
from orden_pc.app import create_app
from orden_pc.scanner import Scanner

PORT, TOKEN = 8765, "t"
DAY = 86400
OLD = time.time() - 400 * DAY


def write(path, size=0, data=None, mtime=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if data is not None else b"x" * size)
    if mtime:
        os.utime(path, (mtime, mtime))
    return path


INSTALLED = [
    {"name": "Python 3.12.10 (64-bit)"},
    {"name": "Git"},
    {"name": "GitHub Desktop"},
    {"name": "Docker Desktop"},
]
PRODUCTS = {"Docker Desktop Installer.exe": "Docker Desktop Installer"}


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "rodri"
    dl = h / "Downloads"
    # Instaladores
    write(dl / "python-3.12.10-amd64.exe", 900)
    write(dl / "python-3.13.0-amd64.exe", 900)  # otra versión: no se recomienda
    write(dl / "GitHubDesktopSetup-x64.exe", 800)
    write(dl / "Docker Desktop Installer.exe", 700)
    write(dl / "herramienta-portable.exe", 600)
    write(h / ".cache" / "chrome" / "setup.exe", 500)  # carpeta oculta de herramientas: fuera
    # Copias exactas
    write(dl / "CV.pdf", data=b"C" * 6000)
    write(dl / "CV (1).pdf", data=b"C" * 6000)
    write(dl / "Caso.pdf", data=b"K" * 7000)
    write(h / "OneDrive" / "10_Universidad" / "Caso.pdf", data=b"K" * 7000)
    write(h / "Proyectos" / "package.json", 10)
    write(h / "Proyectos" / "LICENSE.txt", data=b"L" * 5000)
    write(dl / "LICENSE.txt", data=b"L" * 5000)  # su gemelo vive en un proyecto: no se toca ninguno
    write(h / "AppData" / "a.bin", data=b"A" * 5000)
    write(h / "AppData" / "b.bin", data=b"A" * 5000)
    # Posibles copias por nombre
    write(dl / "Informe.docx", data=b"I" * 100)
    write(dl / "Informe (1).docx", data=b"J" * 120)
    write(dl / "datos - Copy.csv", 30)
    write(dl / "datos.csv", 31)
    write(dl / "Solo (1).txt", 10)  # sin original: no es copia de nada
    # Regenerables
    write(h / "Viejo" / "package.json", 10, mtime=OLD)
    write(h / "Viejo" / "index.js", 10, mtime=OLD)
    write(h / "Viejo" / "node_modules" / "lib" / "x.js", 3000, mtime=OLD)
    write(h / "Activo" / "package.json", 10)
    write(h / "Activo" / "node_modules" / "y.js", 3000)
    # Zip ya extraído
    with zipfile.ZipFile(dl / "Tarea.zip", "w") as z:
        z.writestr("Tarea/a.txt", "aaaa")
        z.writestr("Tarea/b.txt", "bbbbbb")
    write(dl / "Tarea" / "a.txt", data=b"aaaa")
    write(dl / "Tarea" / "b.txt", data=b"bbbbbb")
    with zipfile.ZipFile(dl / "Mitad.zip", "w") as z:
        z.writestr("a.txt", "aaaa")
        z.writestr("b.txt", "bbbbbb")
    write(dl / "Mitad" / "a.txt", data=b"aaaa")
    # Capturas
    write(h / "Pictures" / "Captura de pantalla 2025-01-01.png", 50, mtime=OLD)
    write(h / "Pictures" / "Captura de pantalla hoy.png", 50)
    write(h / "Pictures" / "Screenshots" / "img001.png", 60, mtime=OLD)
    # Grande sin abrir
    write(h / "Videos" / "clase.mp4", 11 * 1024 * 1024, mtime=OLD)

    monkeypatch.setenv("USERPROFILE", str(h))
    monkeypatch.setattr(apps, "installed_apps", lambda refresh=False: INSTALLED)
    monkeypatch.setattr(recommend, "product_name", lambda p: PRODUCTS.get(os.path.basename(p)))
    conn = db.connect(tmp_path / "prueba.db")
    db.set_setting(conn, "scan_roots", [{"path": str(h), "mode": "completo"}])
    db.set_setting(conn, "reglas_recomendacion", {"grandes": {"mb": 10}})
    s = Scanner(tmp_path / "prueba.db")
    s.run([{"path": str(h), "mode": "completo"}])
    assert s.progress.status == "terminado", s.progress.error
    yield h, conn
    conn.close()


def by_rule(result, rule):
    return {os.path.relpath(i["path"], os.environ["USERPROFILE"]): i for i in result["items"] if i["rule"] == rule}


def test_installers(home):
    h, conn = home
    got = by_rule(recommend.analyze(conn), "instaladores")
    assert set(got) == {
        "Downloads\\python-3.12.10-amd64.exe",
        "Downloads\\GitHubDesktopSetup-x64.exe",
        "Downloads\\Docker Desktop Installer.exe",
    }
    assert got["Downloads\\GitHubDesktopSetup-x64.exe"]["detail"]["app"] == "GitHub Desktop"  # no "Git"
    assert got["Downloads\\Docker Desktop Installer.exe"]["confidence"] == "alta"


def test_exact_duplicates_keep_the_right_one(home):
    h, conn = home
    got = by_rule(recommend.analyze(conn), "duplicados")
    assert set(got) == {"Downloads\\CV (1).pdf", "Downloads\\Caso.pdf"}
    assert "no tiene marca de copia" in got["Downloads\\CV (1).pdf"]["reason"]
    assert got["Downloads\\Caso.pdf"]["detail"]["keep"]["path"] == str(h / "OneDrive" / "10_Universidad" / "Caso.pdf")
    assert "estructura" in got["Downloads\\Caso.pdf"]["reason"]


def test_near_duplicates_by_name(home):
    h, conn = home
    got = by_rule(recommend.analyze(conn), "casi_duplicados")
    # CV (1).pdf ya salió como copia exacta: cada ruta aparece una sola vez, con su motivo más fuerte.
    assert set(got) == {"Downloads\\Informe (1).docx", "Downloads\\datos - Copy.csv"}
    assert got["Downloads\\Informe (1).docx"]["detail"]["original"]["size"] == 100
    assert "pesa distinto" in got["Downloads\\Informe (1).docx"]["reason"]


def test_regenerable_only_in_inactive_projects(home):
    h, conn = home
    got = by_rule(recommend.analyze(conn), "regenerables")
    assert set(got) == {"Viejo\\node_modules"}
    assert got["Viejo\\node_modules"]["size"] == 3000
    assert "npm install" in got["Viejo\\node_modules"]["reason"]


def test_extracted_zip(home):
    h, conn = home
    got = by_rule(recommend.analyze(conn), "zip_descomprimido")
    assert set(got) == {"Downloads\\Tarea.zip"}  # Mitad.zip solo coincide al 50 %
    assert got["Downloads\\Tarea.zip"]["detail"]["match_pct"] == 100


def test_old_screenshots_and_big_files(home):
    h, conn = home
    r = recommend.analyze(conn)
    assert set(by_rule(r, "capturas")) == {"Pictures\\Captura de pantalla 2025-01-01.png", "Pictures\\Screenshots\\img001.png"}
    assert set(by_rule(r, "grandes")) == {"Videos\\clase.mp4"}


def test_never_recommends_protected_or_hidden_tool_folders(home):
    h, conn = home
    paths = [i["path"].lower() for i in recommend.analyze(conn)["items"]]
    assert not any("\\appdata\\" in p or "\\.cache\\" in p or "\\proyectos\\" in p for p in paths)


def test_files_freed_by_onedrive_after_scan_are_not_read(home, monkeypatch):
    """El índice dice 'local', pero OneDrive liberó los archivos después: no se leen (no se descargan)."""
    from orden_pc import winfs

    h, conn = home
    read = []
    monkeypatch.setattr(recommend, "product_name", lambda p: read.append(p))
    monkeypatch.setattr(recommend.zipfile, "ZipFile", lambda p: read.append(p) or (_ for _ in ()).throw(OSError()))
    monkeypatch.setattr(winfs, "file_attrs", lambda p: winfs.RECALL_ON_DATA_ACCESS)
    recommend.analyze(conn)
    assert read == []


def test_summary_and_order(home):
    h, conn = home
    r = recommend.analyze(conn)
    s = r["summary"]
    assert s["count"] == len(r["items"]) and s["total"] == sum(i["size"] for i in r["items"])
    assert [i["confidence"] for i in r["items"]] == sorted((i["confidence"] for i in r["items"]), key=recommend.CONFIDENCES.index)


def test_disabled_rule_and_thresholds(home):
    h, conn = home
    db.set_setting(conn, "reglas_recomendacion", {"instaladores": {"enabled": False}, "capturas": {"dias": 1000}, "grandes": {"mb": 10}})
    r = recommend.analyze(conn)
    assert not by_rule(r, "instaladores") and not by_rule(r, "capturas")


@pytest.mark.parametrize(
    "body",
    [
        {"inventada": {"enabled": True}},
        {"capturas": {"confianza": "altísima"}},
        {"capturas": {"dias": 0}},
        {"grandes": {"mb": "500"}},
        {"duplicados": {"dias": 10}},
        {"zip_descomprimido": {"enabled": "sí"}},
    ],
)
def test_rule_validation(body):
    with pytest.raises(ValueError):
        recommend.validate_rules(body)


def test_name_tokens():
    assert {"git", "hub", "github", "desktop"} <= recommend.name_tokens("GitHubDesktopSetup-x64")
    assert recommend.app_key("Microsoft Visual Studio Code (User)") == ["visual", "studio", "code"]
    assert recommend.app_key("Node.js") == ["node"]


# ------------------------------------------------------------------------ API


@pytest.fixture
def client(tmp_path, home):
    return TestClient(create_app(PORT, token=TOKEN, db_path=tmp_path / "prueba.db"), base_url=f"http://127.0.0.1:{PORT}")


def snapshot(h):
    return sorted((str(p), p.stat().st_size, p.stat().st_mtime_ns) for p in h.rglob("*"))


def test_api_is_analysis_only(client, home):
    h, _ = home
    before = snapshot(h)
    r = client.get("/api/recommendations").json()
    assert r["summary"]["count"] > 0 and len(r["rules"]) == 7
    target = next(i["path"] for i in r["items"] if i["rule"] == "instaladores")

    assert client.post("/api/recommendations/marks", json={"paths": [target], "marked": True}).status_code == 403
    hdr = {"X-Orden-Token": TOKEN}
    assert client.post("/api/recommendations/marks", json={"paths": [target], "marked": True, "rule": "instaladores"}, headers=hdr).status_code == 200
    again = client.get("/api/recommendations").json()
    assert next(i for i in again["items"] if i["path"] == target)["marked"] is True
    assert again["summary"]["marked"]["count"] == 1
    assert client.post("/api/recommendations/marks", json={"paths": ["C:\\no\\existe.exe"], "marked": True}, headers=hdr).status_code == 404
    client.post("/api/recommendations/marks", json={"paths": [target], "marked": False}, headers=hdr)
    assert client.get("/api/recommendations").json()["summary"]["marked"]["count"] == 0

    assert snapshot(h) == before, "Analizar o marcar no debe cambiar ningún archivo"


def test_api_rules(client):
    hdr = {"X-Orden-Token": TOKEN}
    assert client.put("/api/recommendations/rules", json={"rules": {"capturas": {"dias": 30}}}).status_code == 403
    r = client.put("/api/recommendations/rules", json={"rules": {"capturas": {"dias": 30, "confianza": "media"}}}, headers=hdr)
    assert r.json()["rules"]["capturas"] == {"enabled": True, "confianza": "media", "dias": 30}
    bad = client.put("/api/recommendations/rules", json={"rules": {"capturas": {"dias": -1}}}, headers=hdr)
    assert bad.status_code == 422 and "entre" in bad.json()["detail"]
