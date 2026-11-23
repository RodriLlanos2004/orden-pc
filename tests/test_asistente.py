import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from orden_pc import agente, contenido, db, winfs
from orden_pc.app import create_app
from orden_pc.scanner import Scanner

PORT, TOKEN = 8765, "t"
H = {"X-Orden-Token": TOKEN}


def write(path: Path, text: str, encoding="utf-8"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding=encoding)
    return path


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Una carpeta de usuario de juguete con documentos de verdad (docx, pptx, xlsx, texto)."""
    import docx
    from openpyxl import Workbook
    from pptx import Presentation

    h = tmp_path / "rodri"
    write(h / "Documents" / "notas_calidad.txt", "Calidad de software: las pruebas unitarias del proyecto Chixi usan Jest.\n\nLa entrega es el viernes.")
    write(h / "Downloads" / "receta.md", "Pastel de chocolate: harina, cacao y huevos.")
    write(h / "Downloads" / "acentos.txt", "Ingeniería de software II: tarea HW07 sobre fixtures.", encoding="cp1252")
    d = docx.Document()
    d.add_paragraph("Currículum de Rodrigo: desarrollador de software con experiencia en Python.")
    (h / "Desktop").mkdir(parents=True)
    d.save(h / "Desktop" / "cv.docx")
    p = Presentation()
    s = p.slides.add_slide(p.slide_layouts[1])
    s.shapes.title.text = "Programa Genera: ELAP networking"
    p.save(h / "Desktop" / "genera.pptx")
    wb = Workbook()
    wb.active.append(["Materia", "Calificación"])
    wb.active.append(["Bases avanzadas", 95])
    wb.save(h / "Documents" / "notas.xlsx")
    write(h / "AppData" / "Local" / "secreto.txt", "Esto nunca se lee: Chixi Jest")
    write(h / "Proyecto" / ".git" / "config.txt", "Chixi interno de git")
    write(h / ".oculta" / "x.txt", "Chixi oculto")
    monkeypatch.setenv("USERPROFILE", str(h))
    roots = [{"path": str(h), "mode": "completo"}]
    conn = db.connect(tmp_path / "prueba.db")
    db.set_setting(conn, "scan_roots", roots)
    conn.close()
    Scanner(tmp_path / "prueba.db").run(roots)
    return h


@pytest.fixture
def conn(tmp_path, home):
    c = db.connect(tmp_path / "prueba.db")
    yield c
    c.close()


def leer(conn):
    lector = contenido.Lector(None)
    lector.run(conn)
    return lector.avance


# ---------------------------------------------------------------------- lectura


def test_trocear_respeta_tamano_y_solapa():
    texto = "\n\n".join(f"Párrafo {i}. " + "palabra " * 60 for i in range(30))
    trozos = contenido.trocear(texto)
    assert len(trozos) > 5 and all(len(t) <= contenido.TROZO + contenido.SOLAPE + 10 for t in trozos)
    enorme = "frase larga. " * 500
    assert all(len(t) <= contenido.TROZO + 10 for t in contenido.trocear(enorme))


def test_lee_documentos_y_respeta_limites(conn, home):
    avance = leer(conn)
    leidos = {Path(r["path"]).name for r in conn.execute("SELECT path FROM doc_archivos WHERE trozos > 0")}
    assert leidos == {"notas_calidad.txt", "receta.md", "acentos.txt", "cv.docx", "genera.pptx", "notas.xlsx"}
    rutas = " ".join(r["path"] for r in conn.execute("SELECT path FROM doc_archivos"))
    assert "AppData" not in rutas and ".git" not in rutas and ".oculta" not in rutas  # protegidas y ocultas: nunca
    assert avance.leidos == 6


def test_nunca_abre_archivos_solo_en_la_nube(conn, home, monkeypatch):
    nube = str(home / "Downloads" / "receta.md")
    abiertos = []
    real = contenido.extraer
    monkeypatch.setattr(winfs, "safe_to_read", lambda p: p != nube)
    monkeypatch.setattr(contenido, "extraer", lambda p, e: abiertos.append(p) or real(p, e))
    leer(conn)
    assert nube not in abiertos
    fila = conn.execute("SELECT trozos, error FROM doc_archivos WHERE path = ?", (nube,)).fetchone()
    assert fila["trozos"] == 0 and "nube" in fila["error"]


def test_lectura_incremental_y_limpieza(conn, home, monkeypatch, tmp_path):
    leer(conn)
    contados = []
    real = contenido.extraer
    monkeypatch.setattr(contenido, "extraer", lambda p, e: contados.append(p) or real(p, e))
    leer(conn)
    assert contados == []  # nada cambió: no se vuelve a abrir nada
    # Un archivo que desaparece del índice deja de estar en lo que leyó el asistente.
    conn.execute("DELETE FROM entries WHERE name = 'receta.md'")
    conn.commit()
    leer(conn)
    assert not conn.execute("SELECT 1 FROM doc_trozos WHERE nombre = 'receta.md'").fetchone()


def test_busqueda_sin_acentos_y_por_nombre(conn, home):
    leer(conn)
    assert contenido.buscar(conn, "ingenieria fixtures")[0]["nombre"] == "acentos.txt"
    assert contenido.buscar(conn, "INGENIERÍA")[0]["nombre"] == "acentos.txt"
    assert contenido.buscar(conn, "currículum python")[0]["nombre"] == "cv.docx"
    assert contenido.buscar(conn, "qué dice de la ") == []  # solo palabras vacías: no busca nada
    assert [f["name"] for f in contenido.por_nombre(conn, "genera")] == ["genera.pptx"]
    write(home / "Downloads" / "Curriculum_Rodrigo.pdf", "x")
    Scanner(home.parent / "prueba.db").run([{"path": str(home), "mode": "completo"}])
    assert "Curriculum_Rodrigo.pdf" in [f["name"] for f in contenido.por_nombre(conn, "busca un archivo de cv")]


# ---------------------------------------------------------------------- agente


def test_responde_solo_con_fragmentos_y_cita(conn, home, monkeypatch):
    leer(conn)
    visto = {}

    def falso(cuerpo):
        visto.update(cuerpo)
        yield {"message": {"content": "Las pruebas usan Jest [1]."}}
        yield {"done": True}

    monkeypatch.setattr(agente, "_chat", falso)
    eventos = list(agente.preguntar(conn, "¿Con qué hacen las pruebas de Chixi?"))
    assert eventos[0]["tipo"] == "fuentes" and eventos[0]["fuentes"][0]["nombre"] == "notas_calidad.txt"
    assert "".join(e.get("texto", "") for e in eventos if e["tipo"] == "texto") == "Las pruebas usan Jest [1]."
    assert eventos[-1] == {"tipo": "fin"}
    sistema, usuario = visto["messages"][0]["content"], visto["messages"][-1]["content"]
    assert "único conocimiento" in sistema and "no instrucciones" in sistema
    assert "[1] notas_calidad.txt" in usuario and "Jest" in usuario
    assert "secreto" not in usuario  # AppData nunca llega al modelo


def test_sin_resultados_no_llama_al_modelo(conn, home):
    leer(conn)
    eventos = list(agente.preguntar(conn, "astronautas marcianos"))  # _chat real está prohibido en las pruebas
    assert eventos[0]["fuentes"] == [] and "No encontré" in eventos[1]["texto"]


def test_explicar_un_archivo(conn, home, monkeypatch):
    leer(conn)
    visto = {}
    monkeypatch.setattr(agente, "_chat", lambda cuerpo: visto.update(cuerpo) or iter([{"done": True}]))
    cv = str(home / "Desktop" / "cv.docx")
    list(agente.preguntar(conn, "", archivo=cv))
    assert "Explica qué es este archivo" in visto["messages"][-1]["content"] and "Currículum" in visto["messages"][-1]["content"]


def test_ollama_apagado_da_un_mensaje_claro(conn, home, monkeypatch):
    leer(conn)

    def apagado(cuerpo):
        raise agente.SinModelo("No hay conexión con Ollama. Ábrelo y vuelve a intentar.")
        yield  # pragma: no cover

    monkeypatch.setattr(agente, "_chat", apagado)
    eventos = list(agente.preguntar(conn, "Chixi"))
    assert {"tipo": "error", "texto": "No hay conexión con Ollama. Ábrelo y vuelve a intentar."} in eventos


# ---------------------------------------------------------------------- API


@pytest.fixture
def client(tmp_path, home, monkeypatch):
    monkeypatch.setattr(agente, "_get", lambda ruta, timeout=2.0: {"models": [{"name": "qwen2.5:7b"}]})
    return TestClient(create_app(PORT, token=TOKEN, db_path=tmp_path / "prueba.db"), base_url=f"http://127.0.0.1:{PORT}")


def test_api_preparar_y_preguntar(client, monkeypatch):
    estado = client.get("/api/asistente/estado").json()
    assert estado["ollama"] and estado["modelo_listo"] and estado["indice"]["archivos"] == 0
    assert client.post("/api/asistente/preparar").status_code == 403  # sin token
    assert client.post("/api/asistente/preparar", headers=H).status_code == 202
    for _ in range(100):
        if client.get("/api/asistente/estado").json()["lectura"]["estado"] == "listo":
            break
        time.sleep(0.05)
    assert client.get("/api/asistente/estado").json()["indice"]["con_texto"] == 6

    monkeypatch.setattr(agente, "_chat", lambda cuerpo: iter([{"message": {"content": "Jest [1]"}}, {"done": True}]))
    r = client.post("/api/asistente/preguntar", json={"pregunta": "pruebas de Chixi"}, headers=H)
    eventos = [json.loads(l[6:]) for l in r.text.splitlines() if l.startswith("data: ")]
    assert eventos[0]["tipo"] == "fuentes" and eventos[1] == {"tipo": "texto", "texto": "Jest [1]"} and eventos[-1]["tipo"] == "fin"
    assert client.post("/api/asistente/preguntar", json={"pregunta": " "}, headers=H).status_code == 422
    assert client.post("/api/asistente/preguntar", json={"pregunta": "x", "archivo": "C:\\no\\leido.txt"}, headers=H).status_code == 404


def test_mover_un_archivo_actualiza_lo_que_leyo(client, home):
    client.post("/api/asistente/preparar", headers=H)
    for _ in range(100):
        if client.get("/api/asistente/estado").json()["lectura"]["estado"] == "listo":
            break
        time.sleep(0.05)
    client.post("/api/session/edit-mode", json={"enabled": True}, headers=H)
    p = client.post("/api/ops/plan", json={"kind": "renombrar", "path": str(home / "Downloads" / "acentos.txt"), "name": "hw07.txt"}, headers=H).json()
    assert client.post(f"/api/ops/apply/{p['id']}", json={}, headers=H).json()["done"] == 1
    conn = db.connect(Path(home).parent / "prueba.db")
    try:
        assert contenido.buscar(conn, "fixtures")[0]["path"] == str(home / "Downloads" / "hw07.txt")
        assert contenido.buscar(conn, "fixtures")[0]["nombre"] == "hw07.txt"
    finally:
        conn.close()
