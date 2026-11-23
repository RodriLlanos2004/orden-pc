"""Lo que lee el asistente: el texto de tus documentos, en trozos, buscable con FTS5.

Reglas:
- solo lee cuando se lo pides ("Preparar"), en segundo plano y de forma incremental (tamaño y fecha);
- solo dentro de tus carpetas (fuera de AppData, carpetas ocultas y rutas protegidas);
- nunca abre un archivo de OneDrive que está solo en la nube: lo comprueba justo antes de abrirlo;
- todo queda en la base de datos local. Nada sale del equipo.
"""

import json
import os
import re
import sqlite3
import threading
import time
import unicodedata
from dataclasses import asdict, dataclass

from orden_pc import db, insights, safety, winfs

TEXTO = {"txt", "md", "csv", "json", "log", "py", "js", "ts", "tsx", "jsx", "java", "c", "cpp", "h", "cs", "dart", "kt", "swift",
         "html", "css", "sql", "yaml", "yml", "xml", "toml", "ini", "ps1", "sh", "bat", "r", "go", "rs", "php", "rb", "tex"}
TIPOS = TEXTO | {"pdf", "docx", "pptx", "xlsx", "ipynb"}
MAX_BYTES = 30 * 2**20
MAX_TEXTO = 300_000  # caracteres por archivo
TROZO = 1100
SOLAPE = 160


# ---------------------------------------------------------------------- extracción


def _texto_plano(path: str) -> str:
    with open(path, "rb") as f:
        crudo = f.read(MAX_TEXTO * 2)
    for codec in ("utf-8", "cp1252"):
        try:
            return crudo.decode(codec)
        except UnicodeDecodeError:
            continue
    return crudo.decode("utf-8", "replace")


def extraer(path: str, ext: str) -> str:
    """Texto legible de un archivo. Lanza excepción si no se puede leer (protegido con contraseña, dañado)."""
    if ext == "pdf":
        from pypdf import PdfReader

        lector = PdfReader(path)
        partes = []
        for i, pagina in enumerate(lector.pages[:300]):
            t = (pagina.extract_text() or "").strip()
            if t:
                partes.append(f"[Página {i + 1}]\n{t}")
            if sum(map(len, partes)) > MAX_TEXTO:
                break
        return "\n\n".join(partes)
    if ext == "docx":
        import docx

        d = docx.Document(path)
        partes = [p.text for p in d.paragraphs if p.text.strip()]
        for tabla in d.tables:
            for fila in tabla.rows:
                partes.append(" | ".join(c.text.strip() for c in fila.cells))
        return "\n".join(partes)
    if ext == "pptx":
        from pptx import Presentation

        partes = []
        for i, diapositiva in enumerate(Presentation(path).slides):
            textos = [s.text_frame.text.strip() for s in diapositiva.shapes if s.has_text_frame and s.text_frame.text.strip()]
            if textos:
                partes.append(f"[Diapositiva {i + 1}]\n" + "\n".join(textos))
        return "\n\n".join(partes)
    if ext == "xlsx":
        from openpyxl import load_workbook

        libro = load_workbook(path, read_only=True, data_only=True)
        partes = []
        for hoja in libro.worksheets[:6]:
            filas = []
            for fila in hoja.iter_rows(max_row=1500, values_only=True):
                valores = [str(v) for v in fila if v is not None and str(v).strip()]
                if valores:
                    filas.append(" | ".join(valores))
            if filas:
                partes.append(f"[Hoja {hoja.title}]\n" + "\n".join(filas))
        libro.close()
        return "\n\n".join(partes)
    if ext == "ipynb":
        cuaderno = json.loads(_texto_plano(path))
        return "\n\n".join("".join(c.get("source", [])) for c in cuaderno.get("cells", []))
    return _texto_plano(path)


def trocear(texto: str) -> list[str]:
    """Trozos de unos 1100 caracteres que respetan párrafos y se solapan un poco para no cortar ideas."""
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto).strip()[:MAX_TEXTO]
    if not texto:
        return []
    parrafos = [p.strip() for p in re.split(r"\n\s*\n", texto) if p.strip()]
    trozos, actual = [], ""
    for p in parrafos:
        if len(p) > TROZO and actual:
            trozos.append(actual.strip())
            actual = ""
        while len(p) > TROZO:  # párrafo enorme: se parte en cortes de frase
            corte = p.rfind(". ", 0, TROZO)
            corte = corte + 1 if corte > TROZO // 2 else TROZO
            trozos.append(p[:corte].strip())
            p = p[max(0, corte - SOLAPE):].strip()
        if len(actual) + len(p) + 2 > TROZO and actual:
            trozos.append(actual.strip())
            actual = actual[-SOLAPE:]
        actual = f"{actual}\n\n{p}" if actual else p
    if actual.strip():
        trozos.append(actual.strip())
    return trozos


# ---------------------------------------------------------------------- qué se lee


def _oculto(path: str, h: str) -> bool:
    return any(parte.startswith(".") or parte.lower() == "node_modules" for parte in path[len(h):].split("\\") if parte)


def candidatos(conn: sqlite3.Connection, h: str | None = None) -> list[sqlite3.Row]:
    """Documentos de tus carpetas que el asistente puede leer, según el índice."""
    h = h or insights.home()
    donde, params = insights.user_scope_sql(h)
    marcas = ",".join("?" * len(TIPOS))
    filas = conn.execute(
        f"SELECT path, ext, size, mtime, cloud FROM entries WHERE is_dir = 0 AND {donde} AND ext IN ({marcas}) AND size > 0 AND size <= ?",
        [*params, *sorted(TIPOS), MAX_BYTES],
    ).fetchall()
    extra = db.get_setting(conn, "rutas_protegidas", [])
    return [f for f in filas if f["cloud"] != "solo_nube" and not _oculto(f["path"], h) and not safety.protected_reason(f["path"], extra)]


# ---------------------------------------------------------------------- lector en segundo plano


@dataclass
class Avance:
    estado: str = "inactivo"  # inactivo | leyendo | listo | detenido | error
    total: int = 0
    hechos: int = 0
    leidos: int = 0
    trozos: int = 0
    omitidos: int = 0
    actual: str = ""
    error: str | None = None
    terminado: float | None = None


class Lector:
    def __init__(self, db_path):
        self.db_path = db_path
        self.avance = Avance()
        self._hilo: threading.Thread | None = None
        self._parar = threading.Event()
        self._lock = threading.Lock()

    @property
    def leyendo(self) -> bool:
        return bool(self._hilo and self._hilo.is_alive())

    def snapshot(self) -> dict:
        return asdict(self.avance)

    def start(self, home: str | None = None) -> bool:
        with self._lock:
            if self.leyendo:
                return False
            self._parar.clear()
            self.avance = Avance(estado="leyendo")
            self._hilo = threading.Thread(target=self._correr, args=(home,), daemon=True)
            self._hilo.start()
            return True

    def stop(self) -> None:
        self._parar.set()

    def _correr(self, home: str | None) -> None:
        conn = db.connect(self.db_path)
        try:
            self.run(conn, home)
            self.avance.estado = "detenido" if self._parar.is_set() else "listo"
        except Exception as e:  # el error se muestra; el índice conserva lo leído
            self.avance.estado, self.avance.error = "error", str(e)
        finally:
            self.avance.terminado = time.time()
            conn.close()

    def run(self, conn: sqlite3.Connection, home: str | None = None) -> None:
        archivos = candidatos(conn, home)
        self.avance.total = len(archivos)
        vistos = set()
        for i, f in enumerate(archivos):
            if self._parar.is_set():
                return
            path = f["path"]
            vistos.add(path.lower())
            self.avance.hechos, self.avance.actual = i + 1, path
            previo = conn.execute("SELECT mtime, size FROM doc_archivos WHERE path = ?", (path,)).fetchone()
            if previo and previo["mtime"] == f["mtime"] and previo["size"] == f["size"]:
                continue
            # Justo antes de abrir: OneDrive pudo liberar el archivo después del escaneo.
            if not winfs.safe_to_read(path):
                self._guardar(conn, f, [], "Está solo en la nube: no se descarga para leerlo.")
                self.avance.omitidos += 1
                continue
            try:
                trozos = trocear(extraer(path, f["ext"]))
                error = None if trozos else "No tiene texto legible."
            except Exception as e:
                trozos, error = [], f"No se pudo leer: {e.__class__.__name__}"
            self._guardar(conn, f, trozos, error)
            self.avance.leidos += 1
            self.avance.trozos += len(trozos)
            if i % 20 == 0:
                conn.commit()
        # Lo que ya no está (se movió fuera, se borró, quedó solo en la nube) deja de estar en el índice.
        if not self._parar.is_set():
            for (path,) in conn.execute("SELECT path FROM doc_archivos").fetchall():
                if path.lower() not in vistos:
                    conn.execute("DELETE FROM doc_trozos WHERE path = ?", (path,))
                    conn.execute("DELETE FROM doc_archivos WHERE path = ?", (path,))
        conn.commit()

    @staticmethod
    def _guardar(conn, f, trozos: list[str], error: str | None) -> None:
        path = f["path"]
        nombre = os.path.basename(path)
        conn.execute("DELETE FROM doc_trozos WHERE path = ?", (path,))
        conn.executemany("INSERT INTO doc_trozos(path, ord, nombre, texto) VALUES (?, ?, ?, ?)", [(path, i, nombre, t) for i, t in enumerate(trozos)])
        conn.execute(
            "INSERT INTO doc_archivos(path, mtime, size, trozos, error, leido) VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(path) DO UPDATE SET mtime = excluded.mtime, size = excluded.size, trozos = excluded.trozos, error = excluded.error, leido = excluded.leido",
            (path, f["mtime"], f["size"], len(trozos), error, time.time()),
        )


# ---------------------------------------------------------------------- búsqueda

VACIAS = set(
    "a al algo algun alguna algunas alguno algunos ante antes aqui asi aun cada como con contra cual cuales cuando de del desde "
    "donde dos el ella ellas ellos en entre era eres es esa esas ese eso esos esta estan estas este esto estos fue fueron ha han "
    "hay la las le les lo los mas me mi mis mucho muy nada ni no nos o otra otro para pero poco por porque que quien se sea "
    "segun ser si sin sobre son su sus tambien te tengo tiene tienen todo todos tu tus un una uno unos y ya yo "
    "dime dame explica explicame busca buscame encuentra encuentrame archivo archivos documento documentos mis tengo hablan habla "
    "sobre acerca cual cuales donde esta estan que dice dicen".split()
)


def _plano(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))


# Abreviaturas y equivalencias comunes en nombres de archivo. La forma larga va primero: es la que menos falsos aciertos da.
SINONIMOS = {
    "cv": ["curriculum", "resume", "cv"],
    "curriculum": ["curriculum", "cv", "resume"],
    "resume": ["resume", "curriculum", "cv"],
    "hw": ["tarea", "hw"],
    "tarea": ["tarea", "hw"],
}


def palabras(consulta: str) -> list[str]:
    """Términos de búsqueda: sin acentos, sin palabras vacías, sin repetir, con sus equivalencias."""
    vistos, out = set(), []
    for w in re.findall(r"[0-9a-zA-ZÀ-ÿ_]{2,}", consulta):
        p = _plano(w)
        if p in VACIAS or (len(p) < 3 and not p.isdigit() and p not in SINONIMOS):
            continue
        for t in SINONIMOS.get(p, [p]):
            if t not in vistos:
                vistos.add(t)
                out.append(t)
    return out[:12]


def buscar(conn: sqlite3.Connection, consulta: str, limite: int = 8, por_archivo: int = 3, dentro: str | None = None) -> list[dict]:
    """Los trozos que mejor responden (BM25, el nombre pesa más que el texto). Como mucho `por_archivo` de cada archivo."""
    terminos = palabras(consulta)
    if not terminos:
        return []
    fts = " OR ".join(f'"{t}"*' for t in terminos)
    filtro, params = "", []
    if dentro:
        filtro, params = " AND (t.path > ? AND t.path < ?)", list(insights.inside(dentro))
    filas = conn.execute(
        f"""SELECT t.id, t.path, t.nombre, t.ord, t.texto, bm25(doc_fts, 3.0, 1.0) AS rango
            FROM doc_fts JOIN doc_trozos t ON t.id = doc_fts.rowid
            WHERE doc_fts MATCH ?{filtro} ORDER BY rango LIMIT 80""",
        [fts, *params],
    ).fetchall()
    out, cuenta = [], {}
    for f in filas:
        if cuenta.get(f["path"], 0) >= por_archivo:
            continue
        cuenta[f["path"]] = cuenta.get(f["path"], 0) + 1
        out.append(dict(f))
        if len(out) >= limite:
            break
    return out


def por_nombre(conn: sqlite3.Connection, consulta: str, limite: int = 6) -> list[dict]:
    """Archivos cuyo nombre coincide, aunque no tengan texto (fotos, instaladores): sirven para encontrarlos e identificarlos."""
    h = insights.home()
    donde, params = insights.user_scope_sql(h)
    out = []
    for t in palabras(consulta)[:4]:
        for f in conn.execute(
            f"SELECT path, name, size, mtime, ext FROM entries WHERE is_dir = 0 AND {donde} AND name LIKE ? ORDER BY mtime DESC LIMIT ?",
            [*params, f"%{t}%", limite],
        ):
            if not _oculto(f["path"], h) and all(o["path"] != f["path"] for o in out):
                out.append(dict(f))
    return out[:limite]


def del_archivo(conn: sqlite3.Connection, path: str, max_chars: int = 9000) -> list[dict]:
    """Los primeros trozos de un archivo, para explicarlo entero."""
    out, total = [], 0
    for f in conn.execute("SELECT id, path, nombre, ord, texto FROM doc_trozos WHERE path = ? ORDER BY ord", (path,)):
        if total + len(f["texto"]) > max_chars and out:
            break
        out.append(dict(f))
        total += len(f["texto"])
    return out


def resumen(conn: sqlite3.Connection) -> dict:
    fila = conn.execute("SELECT count(*) AS archivos, coalesce(sum(trozos), 0) AS trozos, max(leido) AS leido, sum(trozos > 0) AS con_texto FROM doc_archivos").fetchone()
    return {"archivos": fila["archivos"], "con_texto": fila["con_texto"] or 0, "trozos": fila["trozos"], "leido": fila["leido"]}
