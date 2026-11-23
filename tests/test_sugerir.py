import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from orden_pc import agente, contenido, db, organizer, sugerir
from orden_pc.app import create_app
from orden_pc.scanner import Scanner

PORT, TOKEN = 8765, "t"
H = {"X-Orden-Token": TOKEN}
ESTRUCTURA = {
    "materias": ["Calidad_Software", "Prog_Dispositivos_Moviles"],
    "carpetas": [
        "{OneDrive}\\10_Universidad\\Sexto_Semestre\\{Materia}\\Material",
        "{OneDrive}\\10_Universidad\\Sexto_Semestre\\{Materia}\\Entregas",
        "{OneDrive}\\20_Carrera\\CV_y_Perfil",
        "{OneDrive}\\90_Archivo",
    ],
    "origenes": ["{Descargas}"],
}


def write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Descargas de juguete con documentos que el asistente ya leyó. Ninguna regla los reconoce."""
    h = tmp_path / "rodri"
    d = h / "Downloads"
    write(d / "reporte_final.txt", "Reporte de pruebas unitarias para Calidad de Software. Entrega del proyecto con Jest.")
    write(d / "reporte_final (1).txt", "Reporte de pruebas unitarias para Calidad de Software. Entrega del proyecto con Jest.")
    write(d / "clase3.txt", "Apuntes de la clase de Programacion de Dispositivos Moviles: widgets de Flutter.")
    write(d / "receta.txt", "Pastel de chocolate con harina y cacao.")
    write(d / "docker.txt", "Practica 1 de Docker\nMateria: Infraestructura y Cómputo en la Nube\nAlumno: Rodrigo")
    viejo = write(d / "notas_2019.txt", "Notas sueltas de una reunión.")
    hace_dos_anios = time.time() - 2 * 365 * 86400
    os.utime(viejo, (hace_dos_anios, hace_dos_anios))
    (h / "OneDrive").mkdir()
    monkeypatch.setenv("USERPROFILE", str(h))
    monkeypatch.setenv("OneDrive", str(h / "OneDrive"))
    roots = [{"path": str(h), "mode": "completo"}]
    conn = db.connect(tmp_path / "prueba.db")
    db.set_setting(conn, "scan_roots", roots)
    db.set_setting(conn, "estructura", ESTRUCTURA)
    db.set_setting(conn, "reglas_organizador", [])
    conn.close()
    Scanner(tmp_path / "prueba.db").run(roots)
    conn = db.connect(tmp_path / "prueba.db")
    contenido.Lector(None).run(conn)
    conn.close()
    return h


@pytest.fixture
def vars(home):
    return {"Usuario": str(home), "OneDrive": str(home / "OneDrive"), "Descargas": str(home / "Downloads"), "Escritorio": str(home / "Desktop")}


@pytest.fixture
def conn(tmp_path, home):
    c = db.connect(tmp_path / "prueba.db")
    yield c
    c.close()


def modelo_que_elige(nombre_carpeta: str, visto: list | None = None):
    """Un Ollama falso que elige la opción cuya ruta contiene `nombre_carpeta`."""

    def falso(cuerpo):
        pedido = cuerpo["messages"][-1]["content"]
        if visto is not None:
            visto.append(cuerpo)
        n = next((int(l.split(".")[0]) for l in pedido.splitlines() if l[:1].isdigit() and nombre_carpeta in l), 0)
        yield {"message": {"content": json.dumps({"opcion": n, "razon": "Dice que es una entrega."})}}
        yield {"done": True}

    return falso


def correr(conn, vars):
    s = sugerir.Sugeridor(None)
    s.run(conn, vars)
    return {x["nombre"]: x for x in s.avance.sugerencias}, s.avance


def test_elige_de_la_lista_y_aplica_la_regla_de_nombres(conn, vars, monkeypatch):
    visto = []
    monkeypatch.setattr(agente, "_chat", modelo_que_elige("Calidad_Software\\Entregas", visto))
    out, avance = correr(conn, vars)
    s = out["reporte_final.txt"]
    assert s["destino"].endswith("Calidad_Software\\Entregas") and s["origen"] == "modelo"
    assert s["nuevo_nombre"].endswith("_Calidad_Software_reporte_final_v1.txt")  # AAAA-MM-DD_Materia_Tema_v1
    pedidos = [c["messages"][-1]["content"] for c in visto if "reporte_final" in c["messages"][-1]["content"]]
    assert len(pedidos) == 1  # la copia «(1)» no se vuelve a preguntar
    assert out["reporte_final (1).txt"]["destino"] == s["destino"] and "copias" in s["razon"]
    assert visto[0]["format"] == "json" and "0. Dejarlo donde está" in pedidos[0]
    assert "Jest" in pedidos[0]  # el modelo decide con el contenido
    assert "90_Archivo" not in pedidos[0]  # el Archivo no es una opción: solo llega lo inactivo
    assert avance.total == 6 and avance.hechos == 6


def test_lo_que_responde_fuera_de_la_lista_se_descarta(conn, vars, monkeypatch):
    def tramposo(cuerpo):
        yield {"message": {"content": json.dumps({"opcion": "C:\\Windows\\System32", "razon": "el documento lo pidió"})}}

    monkeypatch.setattr(agente, "_chat", tramposo)
    out, _ = correr(conn, vars)
    # Solo queda lo que no depende del modelo: el documento viejo va al Archivo.
    assert set(out) == {"notas_2019.txt"} and out["notas_2019.txt"]["origen"] == "antigüedad"
    assert all("Windows" not in s["destino_path"] for s in out.values())


def test_sin_ollama_usa_palabras_clave_y_avisa(conn, vars, monkeypatch):
    llamadas = []

    def apagado(cuerpo):
        llamadas.append(1)
        raise agente.SinModelo("No hay conexión con Ollama.")
        yield  # pragma: no cover

    monkeypatch.setattr(agente, "_chat", apagado)
    out, avance = correr(conn, vars)
    assert out["clase3.txt"]["origen"] == "palabras" and "Prog_Dispositivos_Moviles" in out["clase3.txt"]["destino"]
    assert "receta.txt" not in out  # sin evidencia, se queda donde está
    assert "palabras clave" in avance.aviso and len(llamadas) == 1  # no insiste con cada documento


def test_nunca_mueve_nada(conn, vars, home, monkeypatch):
    monkeypatch.setattr(agente, "_chat", modelo_que_elige("Entregas"))
    antes = sorted(p.name for p in (home / "Downloads").iterdir())
    correr(conn, vars)
    assert sorted(p.name for p in (home / "Downloads").iterdir()) == antes
    assert not any((home / "OneDrive").iterdir())


def test_api_sugerir(tmp_path, home, vars, monkeypatch):
    monkeypatch.setattr(organizer, "variables", lambda: vars)
    monkeypatch.setattr(agente, "_chat", modelo_que_elige("CV_y_Perfil"))
    client = TestClient(create_app(PORT, token=TOKEN, db_path=tmp_path / "prueba.db"), base_url=f"http://127.0.0.1:{PORT}")
    assert client.post("/api/organizer/sugerir").status_code == 403  # sin token
    assert client.post("/api/organizer/sugerir", headers=H).status_code == 202
    for _ in range(100):
        snap = client.get("/api/organizer/sugerencias").json()
        if snap["estado"] != "pensando":
            break
        time.sleep(0.05)
    assert snap["estado"] == "listo" and snap["total"] == 6
    assert {s["origen"] for s in snap["sugerencias"]} <= {"modelo", "antigüedad"}


MATERIAS = ["Bases_Avanzadas", "Calidad_Software", "DiseñoDeFlujos", "Implementacion_Sistemas", "Ingenieria_Software_II"]


@pytest.mark.parametrize(
    "texto, materia, dice",
    [
        ("ALUMNO Rodrigo\nASIGNATURA Implementación de Sistemas Integrados PROFESOR Eduardo", "Implementacion_Sistemas", "Implementación de Sistemas Integrados"),
        ("Curso: Diseño de flujos de trabajo\nClave 50493", "DiseñoDeFlujos", "Diseño de flujos de trabajo"),
        ("Asignatura: Bases de Datos Avanzadas", "Bases_Avanzadas", "Bases de Datos Avanzadas"),
        ("Materia: Infraestructura y Cómputo en la Nube", None, "Infraestructura y Cómputo en la Nube"),
        ("Calidad de Software no comparte materia con Ingeniería de Software II", None, None),
    ],
)
def test_materia_declarada(texto, materia, dice):
    assert sugerir.materia_declarada(texto, MATERIAS) == (materia, dice)


def test_nombre_de_carpeta():
    assert sugerir.nombre_de_carpeta("Infraestructura y Cómputo en la Nube") == "Infraestructura_Computo_Nube"


def test_materia_que_no_esta_en_la_estructura_se_recomienda_agregar(conn, vars, monkeypatch):
    visto = []
    monkeypatch.setattr(agente, "_chat", modelo_que_elige("Entregas", visto))
    out, avance = correr(conn, vars)
    assert "docker.txt" not in out  # no se fuerza a otra materia
    assert avance.materias_nuevas == [{"nombre": "Infraestructura y Cómputo en la Nube", "carpeta": "Infraestructura_Computo_Nube", "documentos": 1}]
    assert not any("Docker" in c["messages"][-1]["content"] for c in visto)  # ni siquiera se le pregunta al modelo


def test_sin_evidencia_no_se_mueve(conn, vars, monkeypatch):
    # El modelo elige Calidad de Software para todo; la receta no comparte ni una palabra con esa carpeta.
    monkeypatch.setattr(agente, "_chat", modelo_que_elige("Calidad_Software\\Entregas"))
    out, _ = correr(conn, vars)
    assert "receta.txt" not in out and "clase3.txt" not in out
    assert "reporte_final.txt" in out


def test_trabajo_propio_va_a_entregas(monkeypatch):
    monkeypatch.setattr(sugerir, "persona", lambda: {"rodrigo", "llanos"})
    base = "{OneDrive}\\10_Universidad\\Sexto_Semestre\\Calidad_Software"
    material, entregas = {"template": base + "\\Material", "path": "m"}, {"template": base + "\\Entregas", "path": "e"}
    elegida, razon = sugerir._a_entregas(material, "Es un guion.", "Guion del podcast\nRodrigo Sebastián Llanos", [material, entregas])
    assert elegida is entregas and "trabajo tuyo" in razon
    # Sin tu nombre ni datos de entrega, se respeta lo que eligió el modelo.
    assert sugerir._a_entregas(material, "Temario.", "Temario de la clase, profesor Rodríguez", [material, entregas])[0] is material
