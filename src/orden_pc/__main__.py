"""`uv run orden-pc`: compila la interfaz si hace falta, levanta el servidor y abre el navegador."""

import os
import shutil
import socket
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

import uvicorn

from orden_pc.app import create_app

HOST = "127.0.0.1"  # nunca 0.0.0.0
DEFAULT_PORT = 8765
WEB_DIR = Path(__file__).resolve().parents[2] / "web"
DIST_DIR = WEB_DIR / "dist"


def pick_port(preferred: int = DEFAULT_PORT) -> int:
    with socket.socket() as s:
        try:
            s.bind((HOST, preferred))
            return preferred
        except OSError:
            s.bind((HOST, 0))
            return s.getsockname()[1]


def frontend_is_stale() -> bool:
    index = DIST_DIR / "index.html"
    if not index.exists():
        return True
    built = index.stat().st_mtime
    sources = [p for p in (WEB_DIR / "src").rglob("*") if p.is_file()]
    sources += [WEB_DIR / "index.html", WEB_DIR / "package.json"]
    return any(p.stat().st_mtime > built for p in sources if p.exists())


def ensure_frontend_built() -> None:
    if not frontend_is_stale():
        return
    npm = shutil.which("npm")
    if not npm:
        sys.exit("No encontré npm. Instala Node.js para compilar la interfaz.")
    installed = WEB_DIR / "node_modules" / ".package-lock.json"
    if not installed.exists() or (WEB_DIR / "package-lock.json").stat().st_mtime > installed.stat().st_mtime:
        print("Instalando dependencias de la interfaz...")
        subprocess.run([npm, "ci"], cwd=WEB_DIR, check=True)
    print("Compilando la interfaz...")
    subprocess.run([npm, "run", "build"], cwd=WEB_DIR, check=True)


def main() -> None:
    ensure_frontend_built()
    port = pick_port()
    url = f"http://{HOST}:{port}"
    app = create_app(port, static_dir=DIST_DIR)
    print(f"Orden PC en {url}  (Ctrl+C para cerrar)")
    if not os.environ.get("ORDEN_PC_NO_BROWSER"):
        threading.Timer(1.0, webbrowser.open, [url]).start()
    uvicorn.run(app, host=HOST, port=port, log_level="warning")


if __name__ == "__main__":
    main()
