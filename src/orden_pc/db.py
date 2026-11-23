"""SQLite: esquema, migraciones por PRAGMA user_version y ajustes en JSON."""

import json
import os
import sqlite3
import time
from pathlib import Path

MIGRATIONS = [
    """
    CREATE TABLE entries (
        id INTEGER PRIMARY KEY,
        path TEXT NOT NULL UNIQUE COLLATE NOCASE,
        parent TEXT COLLATE NOCASE,
        name TEXT NOT NULL,
        ext TEXT,
        is_dir INTEGER NOT NULL,
        size INTEGER NOT NULL DEFAULT 0,      -- carpetas: total de todo lo que contienen
        files INTEGER NOT NULL DEFAULT 0,     -- carpetas: archivos que contienen
        ctime REAL, mtime REAL, atime REAL,
        attrs INTEGER,
        cloud TEXT,                           -- solo_nube | siempre_local | local | NULL (fuera de OneDrive)
        owner TEXT,
        hash_partial TEXT,
        hash_full TEXT,
        tags TEXT NOT NULL DEFAULT '',        -- etiquetas detectadas separadas por coma
        collapsed INTEGER NOT NULL DEFAULT 0  -- 1: carpeta sumada sin indexar su contenido
    );
    CREATE INDEX entries_parent ON entries(parent);
    CREATE INDEX entries_file_size ON entries(size) WHERE is_dir = 0;

    CREATE VIRTUAL TABLE entries_fts USING fts5(name, path, content='entries', content_rowid='id', tokenize='trigram');
    CREATE TRIGGER entries_ai AFTER INSERT ON entries BEGIN
        INSERT INTO entries_fts(rowid, name, path) VALUES (new.id, new.name, new.path);
    END;
    CREATE TRIGGER entries_ad AFTER DELETE ON entries BEGIN
        INSERT INTO entries_fts(entries_fts, rowid, name, path) VALUES ('delete', old.id, old.name, old.path);
    END;

    CREATE TABLE projects (
        path TEXT PRIMARY KEY COLLATE NOCASE,
        kinds TEXT NOT NULL,                  -- git,node,python,flutter
        git_branch TEXT,
        git_dirty INTEGER,                    -- 1 con cambios, 0 limpio, NULL desconocido
        last_activity REAL
    );

    CREATE TABLE scans (
        id INTEGER PRIMARY KEY,
        started REAL NOT NULL,
        finished REAL,
        status TEXT NOT NULL,
        files INTEGER NOT NULL DEFAULT 0,
        dirs INTEGER NOT NULL DEFAULT 0,
        bytes INTEGER NOT NULL DEFAULT 0,
        error TEXT
    );

    CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated REAL NOT NULL);
    """,
    # 2: índice de búsqueda sin posiciones (detail=none). Se consulta con LIKE, que usa los
    # trigramas igual. En un índice real bajó de 139 MB a 28 MB y responde en menos de 1 ms.
    """
    DROP TRIGGER entries_ai;
    DROP TRIGGER entries_ad;
    DROP TABLE entries_fts;
    CREATE VIRTUAL TABLE entries_fts USING fts5(
        name, path, content='entries', content_rowid='id', tokenize='trigram', detail=none);
    CREATE TRIGGER entries_ai AFTER INSERT ON entries BEGIN
        INSERT INTO entries_fts(rowid, name, path) VALUES (new.id, new.name, new.path);
    END;
    CREATE TRIGGER entries_ad AFTER DELETE ON entries BEGIN
        INSERT INTO entries_fts(entries_fts, rowid, name, path) VALUES ('delete', old.id, old.name, old.path);
    END;
    INSERT INTO entries_fts(entries_fts) VALUES ('rebuild');
    """,
    # 3: etiquetas y notas personales. Viven solo aquí: nunca tocan el archivo.
    """
    CREATE TABLE user_meta (
        path TEXT PRIMARY KEY COLLATE NOCASE,
        tags TEXT NOT NULL DEFAULT '',
        note TEXT NOT NULL DEFAULT '',
        updated REAL NOT NULL
    );
    """,
    # 4: recomendaciones que marcaste como aceptadas. Marcar no ejecuta nada.
    """
    CREATE TABLE rec_marks (
        path TEXT PRIMARY KEY COLLATE NOCASE,
        rule TEXT NOT NULL,
        marked REAL NOT NULL
    );
    """,
    # 5: registro de auditoría y búsqueda al día cuando una ruta cambia de nombre o lugar.
    """
    CREATE TABLE audit_log (
        id INTEGER PRIMARY KEY,
        ts REAL NOT NULL,
        batch TEXT NOT NULL,          -- un plan aplicado = un lote
        title TEXT NOT NULL,          -- lo que decía la confirmación
        op TEXT NOT NULL,             -- crear | renombrar | mover | papelera | restaurar
        src TEXT,
        dst TEXT,
        is_dir INTEGER NOT NULL DEFAULT 0,
        size INTEGER NOT NULL DEFAULT 0,
        files INTEGER NOT NULL DEFAULT 0,
        result TEXT NOT NULL,         -- hecho | error | omitido
        message TEXT,
        fingerprint TEXT,             -- tamaño y fecha del elemento ya movido, para deshacer con seguridad
        reversible INTEGER NOT NULL DEFAULT 0,
        undo_of INTEGER REFERENCES audit_log(id),
        undone_by INTEGER REFERENCES audit_log(id)
    );
    CREATE INDEX audit_batch ON audit_log(batch);
    CREATE TRIGGER entries_au AFTER UPDATE OF path, name ON entries BEGIN
        INSERT INTO entries_fts(entries_fts, rowid, name, path) VALUES ('delete', old.id, old.name, old.path);
        INSERT INTO entries_fts(rowid, name, path) VALUES (new.id, new.name, new.path);
    END;
    """,
    # 6: lo que cambias de cada app: categoría y marca de revisión (1 marcada, 0 descartada, NULL automática).
    """
    CREATE TABLE app_meta (
        key TEXT PRIMARY KEY,
        category TEXT,
        review INTEGER,
        note TEXT NOT NULL DEFAULT '',
        updated REAL NOT NULL
    );
    """,
    # 7: lo que leyó el asistente: el texto de tus documentos en trozos, buscable sin acentos ni mayúsculas.
    # Solo se llena cuando pides "Preparar"; nunca con archivos solo en la nube ni rutas protegidas.
    """
    CREATE TABLE doc_archivos (
        path TEXT PRIMARY KEY,
        mtime REAL NOT NULL,
        size INTEGER NOT NULL,
        trozos INTEGER NOT NULL DEFAULT 0,
        error TEXT,
        leido REAL NOT NULL
    );
    CREATE TABLE doc_trozos (
        id INTEGER PRIMARY KEY,
        path TEXT NOT NULL,
        ord INTEGER NOT NULL,
        nombre TEXT NOT NULL,
        texto TEXT NOT NULL
    );
    CREATE INDEX doc_trozos_path ON doc_trozos(path);
    CREATE VIRTUAL TABLE doc_fts USING fts5(nombre, texto, content='doc_trozos', content_rowid='id', tokenize='unicode61 remove_diacritics 2');
    CREATE TRIGGER doc_trozos_ai AFTER INSERT ON doc_trozos BEGIN
        INSERT INTO doc_fts(rowid, nombre, texto) VALUES (new.id, new.nombre, new.texto);
    END;
    CREATE TRIGGER doc_trozos_ad AFTER DELETE ON doc_trozos BEGIN
        INSERT INTO doc_fts(doc_fts, rowid, nombre, texto) VALUES ('delete', old.id, old.nombre, old.texto);
    END;
    CREATE TRIGGER doc_trozos_au AFTER UPDATE OF nombre, texto ON doc_trozos BEGIN
        INSERT INTO doc_fts(doc_fts, rowid, nombre, texto) VALUES ('delete', old.id, old.nombre, old.texto);
        INSERT INTO doc_fts(rowid, nombre, texto) VALUES (new.id, new.nombre, new.texto);
    END;
    """,
]


def default_db_path() -> Path:
    if env := os.environ.get("ORDEN_PC_DB"):
        return Path(env)
    return Path(os.environ["LOCALAPPDATA"]) / "OrdenPC" / "orden.db"


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    for i, sql in enumerate(MIGRATIONS[version:], start=version + 1):
        with conn:
            conn.executescript(sql)
            conn.execute(f"PRAGMA user_version = {i}")
    if 0 < version < 2:
        conn.execute("VACUUM")  # la migración 2 reemplazó el índice de búsqueda: recupera ese espacio
    return conn


def get_setting(conn: sqlite3.Connection, key: str, default):
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return json.loads(row["value"]) if row else default


def set_setting(conn: sqlite3.Connection, key: str, value) -> None:
    with conn:
        conn.execute(
            "INSERT INTO settings(key, value, updated) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated = excluded.updated",
            (key, json.dumps(value, ensure_ascii=False), time.time()),
        )
