"""Inventario de apps (registro, Microsoft Store y winget), categorías, marcas de revisión y acciones.

Leer es seguro. Instalar, actualizar y desinstalar nunca se hace en silencio: se abre el instalador o
desinstalador oficial en una ventana visible y tú terminas el proceso ahí (regla 7 del brief).
"""

import json
import os
import re
import sqlite3
import subprocess
import threading
import time
import uuid
import winreg
from dataclasses import asdict, dataclass, field

UNINSTALL_KEYS = [
    (winreg.HKEY_LOCAL_MACHINE, "HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", "Machine"),
    (winreg.HKEY_LOCAL_MACHINE, "HKLM32", r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall", "Machine"),
    (winreg.HKEY_CURRENT_USER, "HKCU", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", "User"),
]
CACHE_SECONDS = 600
PLAN_TTL = 600
CATEGORIES = ["Desarrollo", "Productividad", "Juegos", "Hardware y drivers", "Seguridad", "Sistema", "Relleno", "Sin categoría"]

# Primera regla que coincide (nombre o editor). Editable por app desde la interfaz.
CATEGORY_RULES: list[tuple[str, str]] = [
    ("Relleno", r"bing|get ?help|gethelp|feedback ?hub|feedbackhub|mixed ?reality|microsoft ?family|"
                r"microsoftfamily|solitaire|clipchamp|lenovo ?now|lenovo ?ai ?now|ainowcontext|dropbox|"
                r"getstarted|\bnoticias\b|\bnews\b|el tiempo|ofertas|offers"),
    ("Seguridad", r"mcafee|webadvisor|defender|norton|avast|kaspersky|bitdefender|senetfilter|malwarebytes|vpn"),
    ("Juegos", r"riot|valorant|league of legends|teamfight|epic ?games|\bsteam\b|xbox|gaming|game ?bar|wallpaper engine|bioshock|minecraft"),
    ("Desarrollo", r"python|\bgit\b|github|node\.?js|docker|visual studio|vs ?code|postman|\buv\b|ffmpeg|terminal|wsl|"
                   r"subsystem for linux|jetbrains|android studio|flutter|java|jdk|\.net sdk|postgres|mysql|mongo|oneapi"),
    ("Hardware y drivers", r"intel|nvidia|amd|realtek|lenovo|legion|razer|logi|synaptics|elan|bluetooth|controlador|driver|"
                           r"smart connect|motorola|dolby|audio|chroma|vantage|qualcomm"),
    ("Productividad", r"office|microsoft 365|word|excel|powerpoint|outlook|onenote|teams|onedrive|claude|copilot|notion|"
                      r"zoom|slack|discord|chrome|firefox|edge|opera|brave|adobe|acrobat|spotify|whatsapp|telegram|obsidian|7-zip|winrar|"
                      r"powertoys|snipping|recortes|grabadora|paint|photos|fotos|calculadora|calculator|notepad|bloc de notas|clock|reloj|"
                      r"camera|cámara|to ?do|journal|whiteboard|power automate|notas rápidas|sticky|linkedin|reproductor|media player|zune"),
    ("Sistema", r"\.net|visual c\+\+|runtime|webview|windows|microsoft|app installer|vclibs|framework|gameinput|compatibility|"
                r"store|tienda|experiencias|quick ?assist|asistencia"),
]

# Punto de partida de la sección 2 del brief. Cada marca se puede quitar o agregar desde la interfaz.
REVIEW_RULES: list[tuple[str, str]] = [
    (r"mcafee|webadvisor", "Duplica a Microsoft Defender, que ya protege tu equipo. Dos antivirus consumen recursos y pueden chocar entre sí."),
    (r"dropbox", "Vino preinstalado con el equipo y duplica a OneDrive, que ya usas para tus documentos."),
    (r"senetfilter", "No declara editor. Es un filtro de red: averigua qué programa lo instaló antes de decidir."),
    (r"computing improvement", "Envía datos de uso a Intel. No hace falta para que el equipo funcione."),
    (r"lenovo ?ai ?now|lenovo ?now|ainowcontext", "App preinstalada de Lenovo. Revisa si de verdad la usas."),
    (r"bing ?news|bingnews", "App de noticias preinstalada con Windows."),
    (r"bing ?weather|bingweather", "App del clima preinstalada con Windows."),
    (r"get ?help|gethelp", "App de ayuda preinstalada con Windows."),
    (r"feedback ?hub|feedbackhub", "Sirve para enviar comentarios a Microsoft. Preinstalada con Windows."),
    (r"mixed ?reality", "Para visores de realidad mixta. Preinstalada con Windows."),
    (r"microsoft ?family|microsoftfamily", "Control parental de Microsoft. Preinstalada con Windows."),
]

SILENT_FLAGS = re.compile(r"(^|\s)(/quiet|/qn|/qb-?|/passive|/s|/silent|/verysilent|-silent|--silent|-q|/norestart\s+/quiet)(\s|$)", re.I)
WINGET_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._\-+\\{}()]{0,250}$")


@dataclass
class App:
    key: str
    name: str
    publisher: str | None = None
    version: str | None = None
    size: int | None = None
    installed: str | None = None
    location: str | None = None
    sources: list[str] = field(default_factory=list)  # registro | store | winget
    winget_id: str | None = None
    available: str | None = None
    system: bool = False
    removable: bool = True
    uninstall: str | None = None
    category: str = "Sin categoría"
    category_auto: str = "Sin categoría"
    review: str | None = None  # motivo, si está marcada para revisar
    review_auto: bool = False
    note: str = ""


# ---------------------------------------------------------------------- lectura de fuentes


def _value(key, name: str):
    try:
        return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return None


def registry_apps() -> list[App]:
    out = []
    for hive, hive_name, path, scope in UNINSTALL_KEYS:
        try:
            root = winreg.OpenKey(hive, path)
        except OSError:
            continue
        with root:
            for i in range(winreg.QueryInfoKey(root)[0]):
                sub_name = winreg.EnumKey(root, i)
                try:
                    sub = winreg.OpenKey(root, sub_name)
                except OSError:
                    continue
                with sub:
                    name = _value(sub, "DisplayName")
                    if not name or _value(sub, "ParentKeyName"):  # actualizaciones de otra app
                        continue
                    size_kb = _value(sub, "EstimatedSize")
                    date = str(_value(sub, "InstallDate") or "")
                    out.append(App(
                        key=f"reg:{hive_name}:{sub_name}",
                        name=str(name).strip(),
                        publisher=(str(_value(sub, "Publisher")).strip() or None) if _value(sub, "Publisher") else None,
                        version=_value(sub, "DisplayVersion"),
                        size=int(size_kb) * 1024 if isinstance(size_kb, int) else None,
                        installed=f"{date[:4]}-{date[4:6]}-{date[6:8]}" if re.fullmatch(r"\d{8}", date) else None,
                        location=(_value(sub, "InstallLocation") or None),
                        sources=["registro"],
                        system=_value(sub, "SystemComponent") == 1,
                        removable=_value(sub, "NoRemove") != 1,
                        uninstall=_value(sub, "UninstallString"),
                    ))
    return out


def _run(args: list[str], timeout: int = 120) -> str:
    """Ejecuta una herramienta de solo lectura y devuelve su salida (UTF-8)."""
    try:
        r = subprocess.run(args, capture_output=True, timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return r.stdout.decode("utf-8", "replace")


def store_apps() -> list[App]:
    raw = _run([
        "powershell", "-NoProfile", "-NonInteractive", "-Command",
        "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-AppxPackage -PackageTypeFilter Main | "
        "Select-Object Name, Publisher, Version, PackageFamilyName, InstallLocation, SignatureKind, NonRemovable, IsFramework | "
        "ConvertTo-Json -Compress",
    ])
    try:
        data = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        data = [data]
    out = []
    for d in data:
        if d.get("IsFramework"):
            continue
        publisher = re.search(r"CN=([^,]+)", d.get("Publisher") or "")
        kind = d.get("SignatureKind")
        out.append(App(
            key=f"store:{d['PackageFamilyName']}",
            name=d["Name"],
            publisher=publisher[1].strip('"') if publisher else None,
            version=d.get("Version"),
            location=d.get("InstallLocation"),
            sources=["store"],
            system=kind in (4, "System"),  # SignatureKind llega como número: 4 = System
            removable=not d.get("NonRemovable"),
        ))
    return out


def parse_table(text: str, has_available: bool) -> list[dict]:
    """Tabla de winget. Las columnas salen de la posición de las palabras del encabezado, así que sirve
    en cualquier idioma. `list` y `upgrade` traen Nombre, Id, Versión, [Disponible], Origen; `search`
    trae Nombre, Id, Versión, [Coincidencia], Origen."""
    lines = [line for line in text.replace("\r", "\n").split("\n") if line.strip()]
    sep = next((i for i, line in enumerate(lines) if set(line.strip()) == {"-"}), None)
    if not sep:
        return []
    header = lines[sep - 1]
    starts = sorted({0, *(m.start() for m in re.finditer(r"(?<= )\S", header))})
    if len(starts) < 3:
        return []
    rows = []
    for line in lines[sep + 1:]:
        if len(line) < starts[1]:
            continue  # resumen al final ("17 upgrades available.")
        cells = [line[a:b].strip() for a, b in zip(starts, [*starts[1:], None])]
        if not cells[1]:
            continue
        extra = cells[3:-1]
        rows.append({
            "name": cells[0],
            "id": cells[1],
            "version": cells[2],
            "available": extra[0] if has_available and extra else "",
            "source": cells[-1] if len(cells) > 3 else "",
        })
    return rows


def winget_rows(command: str) -> list[dict]:
    return parse_table(_run(["winget", command, "--disable-interactivity"]), has_available=True)


# ---------------------------------------------------------------------- unión, categorías y marcas


def _norm(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def merge(reg: list[App], store: list[App], wlist: list[dict], wupgrade: list[dict]) -> list[App]:
    apps = {a.key: a for a in [*reg, *store]}
    by_subkey = {(a.key.split(":")[1].replace("32", ""), a.key.split(":", 2)[2].lower()): a for a in reg}
    by_family = {a.key[6:].lower(): a for a in store}
    by_name = {}
    for a in reg:
        by_name.setdefault(_norm(a.name), a)
    available = {r["id"]: r.get("available") or None for r in wupgrade}

    for row in wlist:
        wid, name = row["id"], row["name"]
        app = None
        if wid.startswith("MSIX\\"):
            parts = wid[5:].split("_")
            app = by_family.get(f"{parts[0]}_{parts[-1]}".lower())
            if app and name:
                app.name = name  # winget trae el nombre amigable
        elif wid.startswith("ARP\\"):
            _, scope, _arch, sub = (wid.split("\\", 3) + ["", "", ""])[:4]
            hive = "HKCU" if scope == "User" else "HKLM"
            app = by_subkey.get((hive, sub.lower()))
        else:
            app = by_name.get(_norm(name))
        if app is None:
            origin = "store" if wid.startswith("MSIX\\") else "registro" if wid.startswith("ARP\\") else "winget"
            app = App(key=f"winget:{wid}", name=name, version=row.get("version") or None, sources=[origin])
            apps[app.key] = app
        app.winget_id = wid
        if "winget" not in app.sources and not wid.startswith(("MSIX\\", "ARP\\")):
            app.sources.append("winget")
        app.available = available.get(wid) or (row.get("available") or None) or app.available

    # Programas clásicos que registran un paquete "sparse" de la Store para tener identidad (McAfee):
    # es la misma app, y su desinstalador real es el del registro.
    for s in store:
        twin = by_name.get(_norm(s.name))
        if twin and not s.system:
            apps.pop(s.key, None)
            twin.sources.append("store")
            twin.available = twin.available or s.available
    return sorted(apps.values(), key=lambda a: a.name.lower())


def auto_category(app: App) -> str:
    # La clave sin su prefijo ("store:", "reg:HKLM:"): el prefijo no dice nada de la app.
    text = f"{app.name} {app.publisher or ''} {app.key.split(':')[-1]}".lower()
    for cat, pattern in CATEGORY_RULES:
        if re.search(pattern, text):
            return cat
    return "Sin categoría"


def auto_review(app: App) -> str | None:
    text = f"{app.name} {app.key}".lower()
    return next((reason for pattern, reason in REVIEW_RULES if re.search(pattern, text)), None)


def apply_meta(apps: list[App], conn: sqlite3.Connection) -> list[App]:
    meta = {r["key"]: r for r in conn.execute("SELECT * FROM app_meta")}
    for a in apps:
        a.category_auto = auto_category(a)
        a.category = a.category_auto
        auto = auto_review(a)
        a.review, a.review_auto = auto, auto is not None
        m = meta.get(a.key)
        if m:
            if m["category"]:
                a.category = m["category"]
            if m["review"] == 1:
                a.review, a.review_auto = m["note"] or auto or "La marcaste para revisar.", False
            elif m["review"] == 0:
                a.review, a.review_auto = None, False
            a.note = m["note"] or ""
    return apps


def sizes_from_index(apps: list[App], conn: sqlite3.Connection) -> None:
    """Si la carpeta de instalación está en el índice, su tamaño real gana a la estimación del registro."""
    for a in apps:
        if a.location:
            row = conn.execute("SELECT size FROM entries WHERE path = ?", (os.path.normpath(a.location),)).fetchone()
            if row and row["size"]:
                a.size = row["size"]


class Inventory:
    def __init__(self):
        self._cache: tuple[float, list[App]] | None = None
        self._lock = threading.Lock()

    def raw(self, refresh: bool = False) -> list[App]:
        with self._lock:
            if refresh or self._cache is None or time.time() - self._cache[0] > CACHE_SECONDS:
                self._cache = (time.time(), merge(registry_apps(), store_apps(), winget_rows("list"), winget_rows("upgrade")))
            return [App(**asdict(a)) for a in self._cache[1]]

    def list(self, conn: sqlite3.Connection, refresh: bool = False) -> list[App]:
        apps = self.raw(refresh)
        sizes_from_index(apps, conn)
        return apply_meta(apps, conn)


inventory = Inventory()


def installed_apps(refresh: bool = False) -> list[dict]:
    """Para la regla de instaladores de Recomendaciones: solo nombres."""
    return [{"name": a.name} for a in inventory.raw(refresh)]


_UNSET = object()


def save_meta(conn: sqlite3.Connection, key: str, category=_UNSET, review=_UNSET, note=_UNSET) -> None:
    """Guarda solo lo que se pasa: cambiar la categoría no borra la marca ni la nota."""
    if category not in (_UNSET, None) and category not in CATEGORIES:
        raise ValueError("Esa categoría no existe.")
    row = conn.execute("SELECT category, review, note FROM app_meta WHERE key = ?", (key,)).fetchone()
    cur = dict(row) if row else {"category": None, "review": None, "note": ""}
    for name, value in (("category", category), ("review", review), ("note", note)):
        if value is not _UNSET:
            cur[name] = value
    with conn:
        conn.execute(
            "INSERT INTO app_meta(key, category, review, note, updated) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET category = excluded.category, review = excluded.review, note = excluded.note, updated = excluded.updated",
            (key, cur["category"], cur["review"], cur["note"] or "", time.time()),
        )


# ---------------------------------------------------------------------- acciones (nunca en silencio)


def split_command(cmd: str) -> tuple[str, str]:
    """Separa un UninstallString en ejecutable y parámetros, sin pasar por cmd.exe."""
    cmd = cmd.strip()
    if cmd.startswith('"'):
        end = cmd.find('"', 1)
        return cmd[1:end], cmd[end + 1:].strip()
    m = re.match(r"(?i)^(.+?\.exe)(\s+.*)?$", cmd)
    if m:
        return m[1], (m[2] or "").strip()
    exe, _, params = cmd.partition(" ")
    return exe, params


@dataclass
class AppPlan:
    id: str
    action: str  # desinstalar | actualizar | instalar
    app: str
    title: str
    confirm: str
    command: str  # lo que se va a abrir, para que lo veas
    warnings: list[dict] = field(default_factory=list)
    blocked: str | None = None
    needs_ack: bool = False
    launch: list | None = None  # ["shell", exe, params] | ["console", *args] | ["settings"]
    created: float = field(default_factory=time.time)


class AppOps:
    def __init__(self):
        self.plans: dict[str, AppPlan] = {}

    def _new(self, **kw) -> AppPlan:
        self.plans = {k: p for k, p in self.plans.items() if time.time() - p.created < PLAN_TTL}
        p = AppPlan(id=uuid.uuid4().hex, **kw)
        self.plans[p.id] = p
        return p

    def plan(self, apps: list[App], action: str, key: str | None = None, winget_id: str | None = None, name: str | None = None) -> AppPlan:
        if action == "instalar":
            if not winget_id or not WINGET_ID.match(winget_id):
                raise ValueError("Identificador de winget no válido.")
            label = name or winget_id
            return self._new(
                action=action, app=label, title=f"Instalar {label}", confirm=f"Abrir el instalador de {label}",
                command=f"winget install --id {winget_id} --exact --interactive",
                launch=["console", "winget", "install", "--id", winget_id, "--exact", "--interactive"],
                warnings=[{"level": "info", "text": "Se abre una ventana de winget y el instalador oficial. Si te pide aceptar términos o permisos, decides tú ahí."}],
            )

        app = next((a for a in apps if a.key == key), None)
        if app is None:
            raise ValueError("Esa app ya no está en el inventario. Vuelve a leerlo.")

        if action == "actualizar":
            if not app.winget_id or not app.available or not WINGET_ID.match(app.winget_id):
                raise ValueError("winget no tiene una actualización para esta app.")
            return self._new(
                action=action, app=app.name, title=f"Actualizar {app.name} de {app.version} a {app.available}",
                confirm=f"Abrir la actualización de {app.name}",
                command=f"winget upgrade --id {app.winget_id} --exact --interactive",
                launch=["console", "winget", "upgrade", "--id", app.winget_id, "--exact", "--interactive"],
                warnings=[{"level": "info", "text": "Se abre una ventana de winget y el instalador oficial; tú terminas el proceso ahí."}],
            )

        if action != "desinstalar":
            raise ValueError("Acción desconocida.")
        p = self._new(action=action, app=app.name, title=f"Desinstalar {app.name}", confirm=f"Abrir el desinstalador de {app.name}", command="")
        if not app.removable:
            p.blocked = "Windows marca esta app como no desinstalable."
            return p
        if app.uninstall and SILENT_FLAGS.search(app.uninstall):
            # Su comando registrado es silencioso: no se ejecuta. Lo haces tú desde Configuración.
            p.launch, p.command = ["settings"], "Configuración > Aplicaciones > Aplicaciones instaladas"
            p.warnings.append({"level": "aviso", "text": "Su desinstalador registrado es silencioso, así que se abrirá Configuración de Windows para que lo hagas tú."})
        elif app.uninstall:
            exe, params = split_command(app.uninstall)
            p.launch, p.command = ["shell", exe, params], app.uninstall
        elif app.winget_id and WINGET_ID.match(app.winget_id):
            p.launch = ["console", "winget", "uninstall", "--id", app.winget_id, "--exact", "--interactive"]
            p.command = f"winget uninstall --id {app.winget_id} --exact --interactive"
        else:
            p.launch, p.command = ["settings"], "Configuración > Aplicaciones > Aplicaciones instaladas"
            p.warnings.append({"level": "aviso", "text": "No tiene desinstalador registrado: se abrirá Configuración de Windows para que lo busques ahí."})

        p.warnings.insert(0, {"level": "info", "text": "Se abre el desinstalador oficial. Tú decides en su ventana; Orden PC no desinstala en silencio. Windows puede pedirte permiso de administrador."})
        if app.system or app.category in ("Sistema", "Hardware y drivers"):
            p.needs_ack = True
            p.warnings.append({
                "level": "peligro",
                "text": "Es un componente del sistema o un controlador. Quitarlo puede hacer que algo deje de funcionar (imagen, audio, Wi-Fi, teclado). "
                        "Hazlo solo si sabes para qué sirve.",
            })
        if app.review:
            p.warnings.append({"level": "info", "text": f"Marcada para revisar: {app.review}"})
        return p

    def run(self, plan_id: str, ack: bool) -> AppPlan:
        p = self.plans.get(plan_id)
        if p is None or time.time() - p.created > PLAN_TTL:
            self.plans.pop(plan_id, None)
            raise ValueError("La confirmación caducó o ya se usó. Ábrela de nuevo.")
        if p.blocked:
            raise ValueError(p.blocked)
        if p.needs_ack and not ack:
            raise ValueError("Confirma que leíste el aviso.")
        del self.plans[plan_id]
        launch(p.launch)
        return p


def launch(spec: list) -> None:
    """Abre algo visible para el usuario. Nunca con shell=True ni a través de cmd.exe."""
    kind = spec[0]
    if kind == "shell":
        import win32api

        # ShellExecute respeta el manifiesto del desinstalador: si necesita permisos, Windows muestra UAC.
        win32api.ShellExecute(0, "open", spec[1], spec[2] or None, None, 1)
    elif kind == "console":
        subprocess.Popen(spec[1:], creationflags=subprocess.CREATE_NEW_CONSOLE)
    elif kind == "settings":
        os.startfile("ms-settings:appsfeatures")
    else:
        raise ValueError(f"Forma de abrir desconocida: {kind}")


def search(q: str) -> list[dict]:
    q = q.strip()
    # Sin guion inicial: winget lo tomaría como opción (por ejemplo, aceptar términos por ti).
    if not 2 <= len(q) <= 60 or q.startswith("-") or any(c in q for c in '"&|<>^%\r\n'):
        raise ValueError("Escribe entre 2 y 60 caracteres, sin símbolos especiales.")
    rows = parse_table(_run(["winget", "search", q, "--disable-interactivity"], timeout=60), has_available=False)
    return [r for r in rows if WINGET_ID.match(r["id"])][:50]
