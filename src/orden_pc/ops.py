"""Acciones de escritura. Todo cambio en disco pasa por aquí: plan (vista previa), aplicar, auditoría.

Reglas que este módulo garantiza (docs/adr/002 y 003):
- cada ruta se valida con safety.resolve_target al planear y otra vez al aplicar;
- nunca se sobrescribe: os.rename falla en Windows si el destino existe, y además se comprueba antes;
- nunca se borra de forma permanente: eliminar es trash.send, solo si el elemento cabe en la Papelera;
- si algo cambió entre la vista previa y la confirmación, ese paso se omite;
- si un paso falla, los siguientes no se hacen;
- cada paso, hecho, fallido u omitido, queda en audit_log.
"""

import csv
import io
import json
import os
import re
import sqlite3
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field

from orden_pc import db, safety, scanner, trash

PLAN_TTL = 600  # segundos que vive una vista previa
RESERVED = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?$", re.I)
BAD_NAME_CHARS = set('<>:"/\\|?*') | {chr(c) for c in range(32)}
REVERSIBLE = {"crear", "renombrar", "mover", "papelera"}


class PlanError(ValueError):
    """No se puede planear o aplicar. El mensaje se muestra tal cual."""


@dataclass
class Step:
    op: str  # crear | renombrar | mover | papelera | restaurar
    src: str | None
    dst: str | None
    is_dir: bool = False
    size: int = 0
    files: int = 0
    fingerprint: list | None = None  # del origen al planear
    undo_of: int | None = None
    deleted_after: float | None = None  # restaurar: ventana de tiempo en la que se envió a la Papelera
    deleted_before: float | None = None


@dataclass
class Plan:
    id: str
    kind: str
    title: str
    confirm: str  # texto del botón: nombra la acción, nunca "Aceptar"
    created: float
    steps: list[Step] = field(default_factory=list)
    blocked: list[dict] = field(default_factory=list)  # {path, reason}
    warnings: list[dict] = field(default_factory=list)  # {text, level: info|aviso|peligro}
    needs_ack: bool = False

    @property
    def total(self) -> int:
        return sum(s.size for s in self.steps)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["total"] = self.total
        d["expires"] = self.created + PLAN_TTL
        return d


# ---------------------------------------------------------------------- utilidades


def check_name(name: str) -> str:
    if not isinstance(name, str) or not name:
        raise PlanError("Escribe un nombre.")
    if name != name.strip():
        raise PlanError("El nombre no puede empezar ni terminar con espacios.")
    if len(name) > 200:
        raise PlanError("El nombre es demasiado largo (máximo 200 caracteres).")
    if set(name) & BAD_NAME_CHARS:
        raise PlanError('El nombre no puede llevar estos caracteres: < > : " / \\ | ? *')
    if name in (".", "..") or name.endswith("."):
        raise PlanError("El nombre no puede terminar en punto.")
    if RESERVED.match(name):
        raise PlanError(f"«{name}» es un nombre reservado por Windows.")
    return name


def fingerprint(path: str) -> list:
    st = os.stat(path, follow_symlinks=False)
    return [int(os.path.isdir(path)), 0 if os.path.isdir(path) else st.st_size, st.st_mtime_ns]


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _short(path: str) -> str:
    """Rutas largas en la confirmación: primera parte, …, las dos últimas carpetas."""
    parts = path.split("\\")
    return path if len(parts) <= 5 else "\\".join([*parts[:2], "…", *parts[-2:]])


def _in_onedrive(path: str) -> bool:
    od = os.environ.get("OneDrive")
    return bool(od) and (path.lower() == od.lower() or path.lower().startswith(od.lower() + "\\"))


def _inside(path: str, base: str) -> bool:
    return path.lower() == base.lower() or path.lower().startswith(base.lower().rstrip("\\") + "\\")


class Ops:
    def __init__(self, db_path, scan: scanner.Scanner):
        self.db_path = db_path
        self.scanner = scan
        self.plans: dict[str, Plan] = {}
        self.lock = threading.Lock()

    # ------------------------------------------------------------------ validación

    def _resolve(self, conn: sqlite3.Connection, raw: str) -> str:
        roots = [r["path"] for r in scanner.configured_roots(conn)]
        extra = db.get_setting(conn, "rutas_protegidas", [])
        return str(safety.resolve_target(raw, roots, extra))

    def _measure(self, conn: sqlite3.Connection, path: str) -> tuple[int, int]:
        if not os.path.isdir(path):
            return os.stat(path, follow_symlinks=False).st_size, 1
        row = conn.execute("SELECT size, files FROM entries WHERE path = ?", (path,)).fetchone()
        if row:
            return row["size"], row["files"]
        total = n = 0
        for d, _, fs in os.walk(path):
            for f in fs:
                try:
                    total += os.stat(os.path.join(d, f), follow_symlinks=False).st_size
                    n += 1
                except OSError:
                    pass
        return total, n

    def _git_warnings(self, conn, path: str, plan: Plan, verb: str) -> None:
        """Avisa si se mueve o elimina un repo (o una carpeta que contiene repos) con cambios sin commit."""
        if not os.path.isdir(path):
            return
        repos = [r["path"] for r in conn.execute("SELECT path FROM projects WHERE kinds LIKE '%git%'") if _inside(r["path"], path)]
        if os.path.isdir(os.path.join(path, ".git")) and path not in repos:
            repos.append(path)
        for repo in repos[:20]:
            branch, dirty = scanner.git_status(repo)
            if dirty:
                plan.warnings.append({
                    "level": "peligro",
                    "text": f"El repo «{os.path.basename(repo)}» tiene cambios sin commit (rama {branch or 'desconocida'}). "
                            f"Haz commit antes o confirma que quieres {verb} igual.",
                })
                plan.needs_ack = True

    def _new_plan(self, kind: str, title: str, confirm: str) -> Plan:
        self.plans = {k: p for k, p in self.plans.items() if time.time() - p.created < PLAN_TTL}
        plan = Plan(id=uuid.uuid4().hex, kind=kind, title=title, confirm=confirm, created=time.time())
        self.plans[plan.id] = plan
        return plan

    def _source(self, conn, raw: str, plan: Plan) -> str | None:
        try:
            src = self._resolve(conn, raw)
        except safety.UnsafePath as e:
            plan.blocked.append({"path": raw, "reason": str(e)})
            return None
        if not os.path.lexists(src):
            plan.blocked.append({"path": raw, "reason": "Ya no existe en esa ubicación. Vuelve a escanear."})
            return None
        return src

    def _add_move(self, conn, plan: Plan, src: str, dst: str, taken: set[str], cloud: list[int], dst_now: str | None = None) -> bool:
        """Valida un movimiento (con nombre nuevo o no) y lo agrega al plan. `taken`: destinos ya usados en este plan.
        `dst_now`: dónde está hoy ese destino, si queda dentro de una carpeta que el mismo plan mueve antes."""
        dest, name = os.path.split(dst)
        exists = os.path.lexists(dst_now or dst)
        if os.path.dirname(src).lower() == dest.lower() and os.path.basename(src) == name:
            reason = "Ya está en esa carpeta."
        elif os.path.isdir(src) and _inside(dest, src):
            reason = "No se puede mover una carpeta dentro de sí misma."
        elif os.path.splitdrive(src)[0].lower() != os.path.splitdrive(dest)[0].lower():
            reason = "Mover entre discos distintos todavía no está disponible."
        elif (exists and dst.lower() != src.lower()) or dst.lower() in taken:
            reason = f"Ya existe «{name}» en el destino. Orden PC nunca sobrescribe."
        else:
            try:
                self._resolve(conn, dst)
                reason = None
            except safety.UnsafePath as e:
                reason = f"No se puede mover ahí: {e}"
        if reason:
            plan.blocked.append({"path": src, "reason": reason})
            return False
        taken.add(dst.lower())
        size, files = self._measure(conn, src)
        plan.steps.append(Step("mover", src, dst, os.path.isdir(src), size, files, fingerprint(src)))
        self._git_warnings(conn, src, plan, "moverlo")
        if _in_onedrive(src) and not _in_onedrive(dest):
            row = conn.execute(
                "SELECT count(*), coalesce(sum(size), 0) FROM entries WHERE cloud = 'solo_nube' AND (path = ? OR (path > ? AND path < ?))",
                (src, src + "\\", src + "]"),
            ).fetchone()
            cloud[0] += row[0]
            cloud[1] += row[1]
        return True

    @staticmethod
    def _cloud_warning(plan: Plan, cloud: list[int]) -> None:
        if cloud[0]:
            plan.warnings.append({
                "level": "aviso",
                "text": f"{_plural(cloud[0], 'archivo está', 'archivos están')} solo en la nube ({cloud[1] / 2**20:,.1f} MB). "
                        "Al sacarlos de OneDrive, Windows los descargará.",
            })

    # ------------------------------------------------------------------ planes

    def plan_create(self, conn, parent: str, name: str) -> Plan:
        name = check_name(name)
        try:
            parent = self._resolve(conn, parent)
        except safety.UnsafePath as e:
            raise PlanError(str(e))
        if not os.path.isdir(parent):
            raise PlanError("La carpeta donde quieres crearla ya no existe.")
        dst = os.path.join(parent, name)
        plan = self._new_plan("crear", f"Crear la carpeta «{name}» en {_short(parent)}", "Crear carpeta")
        if os.path.lexists(dst):
            plan.blocked.append({"path": dst, "reason": f"Ya existe «{name}» en esa carpeta."})
        else:
            plan.steps.append(Step("crear", None, dst, is_dir=True))
        return plan

    def plan_rename(self, conn, path: str, new_name: str) -> Plan:
        new_name = check_name(new_name)
        plan = self._new_plan("renombrar", "", "Renombrar")
        src = self._source(conn, path, plan)
        if src:
            dst = os.path.join(os.path.dirname(src), new_name)
            plan.title = f"Renombrar «{os.path.basename(src)}» como «{new_name}»"
            if dst == src:
                raise PlanError("El nombre nuevo es igual al actual.")
            try:
                self._resolve(conn, dst)
            except safety.UnsafePath as e:
                plan.blocked.append({"path": dst, "reason": str(e)})
                return plan
            if os.path.lexists(dst) and dst.lower() != src.lower():
                plan.blocked.append({"path": src, "reason": f"Ya existe «{new_name}» en esa carpeta."})
            else:
                size, files = self._measure(conn, src)
                plan.steps.append(Step("renombrar", src, dst, os.path.isdir(src), size, files, fingerprint(src)))
                self._git_warnings(conn, src, plan, "renombrarlo")
        return plan

    def plan_move(self, conn, paths: list[str], dest: str) -> Plan:
        try:
            dest = self._resolve(conn, dest)
        except safety.UnsafePath as e:
            raise PlanError(f"No se puede mover ahí: {e}")
        if not os.path.isdir(dest):
            raise PlanError("La carpeta de destino ya no existe.")
        plan = self._new_plan("mover", "", "")
        taken: set[str] = set()
        cloud = [0, 0]
        for raw in paths:
            src = self._source(conn, raw, plan)
            if src:
                self._add_move(conn, plan, src, os.path.join(dest, os.path.basename(src)), taken, cloud)
        self._cloud_warning(plan, cloud)
        n = len(plan.steps)
        what = _plural(n, "elemento", "elementos")
        plan.title = f"Mover {what} a {_short(dest)}"
        plan.confirm = f"Mover {what}"
        return plan

    def plan_organize(self, conn, moves: list[dict], folders: list[str] = ()) -> Plan:
        """Organizador: crear las carpetas que falten y mover (quizá con nombre nuevo) varios elementos.

        Orden de los pasos: carpetas nuevas; movimientos, lo más profundo primero (un proyecto anidado sale
        antes que su carpeta padre); y al final, lo que va dentro de una carpeta que este mismo plan acaba de mover.
        """
        plan = self._new_plan("organizar", "", "")
        items: list[tuple[str, str, str]] = []  # (origen, carpeta destino, nombre)
        for m in moves:
            src = self._source(conn, m.get("src") or "", plan)
            if not src:
                continue
            try:
                items.append((src, self._resolve(conn, m.get("dest") or ""), check_name(m.get("name") or os.path.basename(src))))
            except (PlanError, safety.UnsafePath) as e:
                plan.blocked.append({"path": src, "reason": str(e)})
        wanted = []
        for f in folders:
            try:
                wanted.append(self._resolve(conn, f))
            except safety.UnsafePath as e:
                plan.blocked.append({"path": f, "reason": str(e)})

        dir_moves = [(s, os.path.join(d, n)) for s, d, n in items if os.path.isdir(s)]

        def now(path: str) -> tuple[str, bool]:
            """Dónde está hoy lo que, tras mover las carpetas, estará en `path`."""
            for s, d in dir_moves:
                if _inside(path, d):
                    return s + path[len(d):], True
            return path, False

        first, second = [], []
        for src, dest, name in items:
            if any(_inside(dest, s) for s, _ in dir_moves if s.lower() != src.lower()):
                plan.blocked.append({"path": src, "reason": "Su carpeta de destino también se mueve en este plan. Hazlo en dos pasos."})
            elif now(dest)[1]:
                if any(_inside(src, s) and s.lower() != src.lower() for s, _ in dir_moves):
                    plan.blocked.append({"path": src, "reason": "Su carpeta también se mueve en este plan. Hazlo en dos pasos."})
                else:
                    second.append((src, dest, name))
            else:
                first.append((src, dest, name))

        taken, cloud = set(), [0, 0]
        for src, dest, name in sorted(first, key=lambda t: -t[0].count("\\")):
            self._add_move(conn, plan, src, os.path.join(dest, name), taken, cloud)
        split = len(plan.steps)
        for src, dest, name in second:
            dst = os.path.join(dest, name)
            self._add_move(conn, plan, src, dst, taken, cloud, dst_now=now(dst)[0])
        self._cloud_warning(plan, cloud)

        # Solo se crean las carpetas pedidas y las de los movimientos que sí van.
        early: dict[str, None] = {}
        late: dict[str, None] = {}
        for folder in [*wanted, *(os.path.dirname(s.dst) for s in plan.steps)]:
            p = folder
            while True:
                cur, later = now(p)
                if os.path.isdir(cur):
                    break
                if os.path.lexists(cur):
                    raise PlanError(f"Hay un archivo llamado «{os.path.basename(cur)}» donde iría una carpeta: {cur}")
                (late if later else early)[p] = None
                up = os.path.dirname(p)
                if up == p:
                    break
                p = up

        create = lambda ps: [Step("crear", None, p, is_dir=True) for p in sorted(ps, key=len)]
        plan.steps = [*create(early), *plan.steps[:split], *create(late), *plan.steps[split:]]

        # Una carpeta que pierde un elemento en este mismo plan cambia de fecha: su huella ya no sirve.
        srcs = [s.src for s in plan.steps if s.op == "mover"]
        for s in plan.steps:
            if s.op == "mover" and s.is_dir and any(o.lower() != s.src.lower() and _inside(o, s.src) for o in srcs):
                s.fingerprint = None

        n_new = sum(s.op == "crear" for s in plan.steps)
        n_move = len(srcs)
        dests = {os.path.dirname(s.dst) for s in plan.steps if s.op == "mover"}
        what = _plural(n_move, "elemento", "elementos")
        if n_move and len(dests) == 1:
            plan.title = f"Mover {what} a {_short(dests.pop())}"
        elif n_move:
            plan.title = f"Organizar {what} en {len(dests)} carpetas"
        else:
            plan.title = f"Crear {_plural(n_new, 'carpeta', 'carpetas')}"
        parts = ([f"crear {_plural(n_new, 'carpeta', 'carpetas')}"] if n_new else []) + ([f"mover {what}"] if n_move else [])
        plan.confirm = " y ".join(parts).capitalize() if parts else "Nada que hacer"
        return plan

    def plan_trash(self, conn, paths: list[str]) -> Plan:
        plan = self._new_plan("papelera", "", "")
        bins: dict[str, dict] = {}
        onedrive = 0
        for raw in paths:
            src = self._source(conn, raw, plan)
            if not src:
                continue
            drive = os.path.splitdrive(src)[0].upper()
            if drive not in bins:
                bins[drive] = trash.limits(src)
            b = bins[drive]
            size, files = self._measure(conn, src)
            if not b["enabled"]:
                plan.blocked.append({"path": src, "reason": f"La Papelera de {drive} está desactivada: Windows borraría para siempre. Actívala en sus propiedades."})
            elif size > b["max_bytes"]:
                plan.blocked.append({
                    "path": src,
                    "reason": f"No cabe en la Papelera ({size / 2**30:,.1f} GB de {b['max_bytes'] / 2**30:,.1f} GB). "
                              "Windows lo borraría para siempre, así que Orden PC no lo hace.",
                })
            else:
                plan.steps.append(Step("papelera", src, None, os.path.isdir(src), size, files, fingerprint(src)))
                self._git_warnings(conn, src, plan, "enviarlo a la Papelera")
                onedrive += _in_onedrive(src)
        for drive, b in bins.items():
            total = sum(s.size for s in plan.steps if s.src.upper().startswith(drive))
            if total and total + b["used_bytes"] > b["max_bytes"]:
                plan.warnings.append({"level": "aviso", "text": f"Para hacer espacio, Windows quitará de la Papelera de {drive} lo más antiguo."})
        if onedrive:
            plan.warnings.append({
                "level": "info",
                "text": f"{_plural(onedrive, 'elemento es', 'elementos son')} de OneDrive: también se quitan de la nube. "
                        "OneDrive los guarda en su propia papelera en línea.",
            })
        n = len(plan.steps)
        what = _plural(n, "elemento", "elementos")
        plan.title = f"Enviar {what} a la Papelera"
        plan.confirm = f"Enviar {what} a la Papelera"
        return plan

    def plan_undo(self, conn, ids: list[int]) -> Plan:
        plan = self._new_plan("deshacer", "", "")
        rows = conn.execute(
            f"SELECT * FROM audit_log WHERE id IN ({','.join('?' * len(ids))}) ORDER BY id DESC", ids
        ).fetchall()
        if not rows:
            raise PlanError("No encontré esos cambios en el historial.")
        leaving: set[str] = set()  # lo que este mismo deshacer saca de su lugar antes (para vaciar carpetas creadas)
        for r in rows:
            label = r["dst"] or r["src"]
            if r["result"] != "hecho" or not r["reversible"]:
                plan.blocked.append({"path": label, "reason": "Este cambio no se puede deshacer."})
                continue
            if r["undone_by"]:
                plan.blocked.append({"path": label, "reason": "Ya se deshizo."})
                continue
            try:
                if r["op"] in ("mover", "renombrar"):
                    current, original = self._resolve(conn, r["dst"]), self._resolve(conn, r["src"])
                    if not os.path.lexists(current):
                        raise PlanError(f"Ya no está en {current}.")
                    if os.path.lexists(original) and original.lower() != current.lower():
                        raise PlanError(f"Ya hay algo en {original}. Orden PC nunca sobrescribe.")
                    fp = fingerprint(current)
                    if not r["is_dir"] and r["fingerprint"] and json.loads(r["fingerprint"]) != fp:
                        raise PlanError("El archivo cambió después de moverlo. Muévelo a mano si aún lo quieres de vuelta.")
                    size, files = self._measure(conn, current)
                    plan.steps.append(Step(r["op"], current, original, bool(r["is_dir"]), size, files, fp, undo_of=r["id"]))
                    leaving.add(current.lower())
                elif r["op"] == "papelera":
                    original = self._resolve(conn, r["src"])
                    if os.path.lexists(original):
                        raise PlanError(f"Ya hay algo en {original}. Orden PC nunca sobrescribe.")
                    after, before = r["ts"] - 60, r["ts"] + 5  # el envío ocurre justo antes de registrarlo
                    if not trash.in_bin(original, after, before):
                        raise PlanError("Ya no está en la Papelera: quizá se vació o se restauró a mano.")
                    plan.steps.append(Step("restaurar", None, original, bool(r["is_dir"]), r["size"], r["files"],
                                           undo_of=r["id"], deleted_after=after, deleted_before=before))
                elif r["op"] == "crear":
                    folder = self._resolve(conn, r["dst"])
                    if not os.path.isdir(folder):
                        raise PlanError("La carpeta ya no existe.")
                    if any(os.path.join(folder, c).lower() not in leaving for c in os.listdir(folder)):
                        raise PlanError("La carpeta ya tiene contenido. Si quieres eliminarla, envíala a la Papelera desde el Explorador.")
                    # Sin huella: se vacía en este mismo deshacer y su fecha cambia. Al aplicar se exige que esté vacía.
                    plan.steps.append(Step("papelera", folder, None, True, 0, 0, None, undo_of=r["id"]))
                    leaving.add(folder.lower())
            except (PlanError, safety.UnsafePath, OSError) as e:
                plan.blocked.append({"path": label, "reason": str(e)})
        what = _plural(len(plan.steps), "cambio", "cambios")
        plan.title = f"Deshacer {what}"
        plan.confirm = f"Deshacer {what}"
        return plan

    # ------------------------------------------------------------------ aplicar

    def apply(self, conn: sqlite3.Connection, plan_id: str, ack: bool) -> dict:
        with self.lock:
            plan = self.plans.get(plan_id)
            if plan is None or time.time() - plan.created > PLAN_TTL:
                self.plans.pop(plan_id, None)
                raise PlanError("La vista previa caducó o ya se usó. Ábrela de nuevo para revisar los cambios.")
            if plan.needs_ack and not ack:
                raise PlanError("Confirma que leíste el aviso sobre los cambios sin commit.")
            if self.scanner.running:
                raise PlanError("Hay un escaneo en curso. Espera a que termine para hacer cambios.")
            del self.plans[plan_id]

            results, stopped = [], False
            roots = scanner.configured_roots(conn)
            for step in plan.steps:
                if stopped:
                    result, message = "omitido", "No se hizo porque un paso anterior falló."
                else:
                    try:
                        self._recheck(conn, step)
                        self._execute(step)
                        result, message = "hecho", None
                    except PlanError as e:
                        result, message, stopped = "omitido", str(e), True
                    except OSError as e:
                        result, message, stopped = "error", str(e), True
                audit_id = self._audit(conn, plan, step, result, message)
                if result == "hecho":
                    self._update_index(conn, step, roots)
                    if step.undo_of:
                        conn.execute("UPDATE audit_log SET undone_by = ? WHERE id = ?", (audit_id, step.undo_of))
                conn.commit()
                results.append({**asdict(step), "audit_id": audit_id, "result": result, "message": message})
            done = sum(r["result"] == "hecho" for r in results)
            return {"batch": plan.id, "title": plan.title, "results": results, "done": done, "total": len(results)}

    def _recheck(self, conn, step: Step) -> None:
        """Lo mismo que al planear, otra vez, justo antes de tocar el disco."""
        try:
            for p in (step.src, step.dst):
                if p:
                    self._resolve(conn, p)
        except safety.UnsafePath as e:
            raise PlanError(str(e))
        if step.src:
            if not os.path.lexists(step.src):
                raise PlanError("Ya no existe en esa ubicación.")
            if step.fingerprint and fingerprint(step.src) != step.fingerprint:
                raise PlanError("Cambió desde la vista previa. Revisa y vuelve a intentarlo.")
        if step.dst and step.op != "renombrar" and os.path.lexists(step.dst):
            raise PlanError(f"Ya existe algo en {step.dst}. Orden PC nunca sobrescribe.")
        if step.op == "renombrar" and os.path.lexists(step.dst) and step.dst.lower() != step.src.lower():
            raise PlanError(f"Ya existe algo en {step.dst}. Orden PC nunca sobrescribe.")
        if step.op == "papelera" and step.undo_of and os.listdir(step.src):
            raise PlanError("La carpeta ya tiene contenido. Si quieres eliminarla, envíala a la Papelera desde el Explorador.")
        if step.op == "papelera":
            b = trash.limits(step.src)
            if not b["enabled"] or step.size > b["max_bytes"]:
                raise PlanError("Ya no cabe en la Papelera. No se elimina.")

    def _execute(self, step: Step) -> None:
        if step.op == "crear":
            os.mkdir(step.dst)
        elif step.op in ("renombrar", "mover"):
            os.rename(step.src, step.dst)  # en Windows falla si el destino existe: nunca sobrescribe
        elif step.op == "papelera":
            t0 = time.time() - 2
            trash.send(step.src)
            if os.path.lexists(step.src):
                raise OSError("Windows no lo movió: sigue en su lugar.")
            if not trash.in_bin(step.src, t0):
                raise OSError("No aparece en la Papelera. Revísala antes de seguir.")
        elif step.op == "restaurar":
            trash.restore(step.dst, step.deleted_after, step.deleted_before)
        else:
            raise PlanError(f"Operación desconocida: {step.op}")

    def _audit(self, conn, plan: Plan, step: Step, result: str, message: str | None) -> int:
        fp = None
        if result == "hecho" and step.op in ("mover", "renombrar") and os.path.lexists(step.dst):
            fp = json.dumps(fingerprint(step.dst))
        reversible = int(result == "hecho" and step.op in REVERSIBLE and step.undo_of is None)
        return conn.execute(
            """INSERT INTO audit_log(ts, batch, title, op, src, dst, is_dir, size, files, result, message, fingerprint, reversible, undo_of)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (time.time(), plan.id, plan.title, step.op, step.src, step.dst, int(step.is_dir), step.size, step.files,
             result, message, fp, reversible, step.undo_of),
        ).lastrowid

    # ------------------------------------------------------------------ índice

    def _update_index(self, conn, step: Step, roots: list[dict]) -> None:
        if step.op in ("mover", "renombrar"):
            self._move_index(conn, step.src, step.dst)
        elif step.op == "papelera":
            self._remove_index(conn, step.src)
        elif step.op in ("crear", "restaurar"):
            root = scanner.root_for(step.dst, roots)
            if root:
                size, files = scanner.Scanner(self.db_path).index_one(conn, step.dst, root)
                self._bump(conn, step.dst, size, files)

    @staticmethod
    def _bump(conn, path: str, size: int, files: int) -> None:
        """Ajusta el tamaño acumulado de todas las carpetas que contienen `path`."""
        p = os.path.dirname(path)
        while True:
            conn.execute("UPDATE entries SET size = max(0, size + ?), files = max(0, files + ?) WHERE path = ?", (size, files, p))
            up = os.path.dirname(p)
            if up == p:
                break
            p = up

    def _move_index(self, conn, src: str, dst: str) -> None:
        row = conn.execute("SELECT size, files FROM entries WHERE path = ?", (src,)).fetchone()
        n = len(src) + 1
        lo, hi = src + "\\", src + "]"
        conn.execute("UPDATE entries SET path = ? || substr(path, ?), parent = ? || substr(parent, ?) WHERE path > ? AND path < ?",
                     (dst, n, dst, n, lo, hi))
        name = os.path.basename(dst)
        ext = None if os.path.isdir(dst) else (os.path.splitext(name)[1].lower().lstrip(".") or None)
        conn.execute("UPDATE entries SET path = ?, parent = ?, name = ?, ext = ? WHERE path = ?", (dst, os.path.dirname(dst), name, ext, src))
        for table in ("projects", "user_meta", "rec_marks", "doc_archivos", "doc_trozos"):
            conn.execute(f"UPDATE {table} SET path = ? || substr(path, ?) WHERE path = ? OR (path > ? AND path < ?)", (dst, n, src, lo, hi))
        conn.execute("UPDATE doc_trozos SET nombre = ? WHERE path = ?", (name, dst))  # lo que leyó el asistente sigue al archivo
        if row:
            self._bump(conn, src, -row["size"], -row["files"])
            self._bump(conn, dst, row["size"], row["files"])

    def _remove_index(self, conn, src: str) -> None:
        row = conn.execute("SELECT size, files FROM entries WHERE path = ?", (src,)).fetchone()
        lo, hi = src + "\\", src + "]"
        for table in ("entries", "projects", "rec_marks", "doc_trozos", "doc_archivos"):
            conn.execute(f"DELETE FROM {table} WHERE path = ? OR (path > ? AND path < ?)", (src, lo, hi))
        if row:
            self._bump(conn, src, -row["size"], -row["files"])


# ---------------------------------------------------------------------- historial


def history(conn: sqlite3.Connection, op: str | None = None, result: str | None = None, q: str | None = None, limit: int = 1000) -> list[dict]:
    where, params = ["1 = 1"], []
    if op:
        where.append("op = ?")
        params.append(op)
    if result:
        where.append("result = ?")
        params.append(result)
    if q:
        where.append("(coalesce(src, '') LIKE ? OR coalesce(dst, '') LIKE ? OR title LIKE ?)")
        params += [f"%{q}%"] * 3
    rows = conn.execute(f"SELECT * FROM audit_log WHERE {' AND '.join(where)} ORDER BY id DESC LIMIT ?", [*params, limit]).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["can_undo"] = bool(r["reversible"] and r["result"] == "hecho" and not r["undone_by"])
        out.append(d)
    return out


CSV_COLUMNS = ["id", "ts", "batch", "title", "op", "src", "dst", "is_dir", "size", "files", "result", "message", "undo_of", "undone_by"]
CSV_HEADERS = ["id", "fecha", "lote", "acción", "operación", "origen", "destino", "es_carpeta", "bytes", "archivos", "resultado", "detalle", "deshace_a", "deshecho_por"]


def history_csv(conn: sqlite3.Connection) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_HEADERS)
    for r in conn.execute(f"SELECT {', '.join(CSV_COLUMNS)} FROM audit_log ORDER BY id"):
        row = list(r)
        row[1] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(row[1]))
        w.writerow(row)
    return "﻿" + buf.getvalue()  # BOM: Excel abre los acentos bien
