import pytest
from fastapi.testclient import TestClient

from orden_pc import apps, db
from orden_pc.app import create_app
from orden_pc.apps import App

PORT, TOKEN = 8765, "t"
H = {"X-Orden-Token": TOKEN}

def table(header: list[str], widths: list[int], rows: list[list[str]], prefix: str = "", suffix: str = "") -> str:
    """Tabla con columnas de ancho fijo, como la imprime winget."""
    line = lambda cells: "".join(c.ljust(w) for c, w in zip(cells, widths)).rstrip()
    return prefix + "\n".join([line(header), "-" * sum(widths), *(line(r) for r in rows)]) + "\n" + suffix


W = [29, 56, 13, 11, 8]
LIST_EN = table(
    ["Name", "Id", "Version", "Available", "Source"],
    W,
    [
        ["Docker Desktop", "Docker.DockerDesktop", "4.93.0", "4.94.0", "winget"],
        ["Noticias", r"MSIX\Microsoft.BingNews_4.55.1.0_x64__8wekyb3d8bbwe", "4.55.1.0"],
        ["Dropbox - promoción", r"MSIX\C27EB4BA.DropboxOEM_24.4.16.0_x64__xbfy0k16fey96", "24.4.16.0"],
        ["McAfee", r"ARP\Machine\X64\McAfee.wps", "1.0"],
        ["Herramienta suelta", "Vendor.Tool", "2.0", "", "winget"],
    ],
    prefix="   - \\ |\r",
    suffix="2 upgrades available.\n",
)
LIST_ES = table(["Nombre", "Id", "Versión", "Disponible", "Origen"], [12, 14, 9, 12, 8], [["Git", "Git.Git", "2.55.0", "2.55.1", "winget"]])
SEARCH = table(
    ["Name", "Id", "Version", "Match", "Source"],
    [20, 28, 10, 15, 8],
    [["Visual Studio Code", "Microsoft.VisualStudioCode", "1.99.0", "Tag: vscode", "winget"], ["Obsidian", "Obsidian.Obsidian", "1.8.0", "", "winget"]],
)


def test_parse_table_any_language_and_skips_summary():
    rows = apps.parse_table(LIST_EN, has_available=True)
    assert [r["id"] for r in rows] == [
        "Docker.DockerDesktop",
        "MSIX\\Microsoft.BingNews_4.55.1.0_x64__8wekyb3d8bbwe",
        "MSIX\\C27EB4BA.DropboxOEM_24.4.16.0_x64__xbfy0k16fey96",
        "ARP\\Machine\\X64\\McAfee.wps",
        "Vendor.Tool",
    ]
    assert rows[0]["available"] == "4.94.0" and rows[0]["source"] == "winget"
    assert rows[1]["available"] == "" and rows[2]["name"] == "Dropbox - promoción"
    es = apps.parse_table(LIST_ES, has_available=True)
    assert es == [{"name": "Git", "id": "Git.Git", "version": "2.55.0", "available": "2.55.1", "source": "winget"}]
    assert apps.parse_table("Ningún paquete instalado coincide", True) == []


def test_parse_search_ignores_match_column():
    rows = apps.parse_table(SEARCH, has_available=False)
    assert rows[1] == {"name": "Obsidian", "id": "Obsidian.Obsidian", "version": "1.8.0", "available": "", "source": "winget"}


def reg(name, sub, **kw):
    return App(key=f"reg:HKLM:{sub}", name=name, sources=["registro"], **kw)


def store(name, family, **kw):
    return App(key=f"store:{family}", name=name, sources=["store"], **kw)


def test_merge_sources():
    regs = [reg("Docker Desktop", "Docker Desktop", uninstall='"C:\\Program Files\\Docker\\uninst.exe"'), reg("McAfee", "McAfee.wps")]
    stores = [store("Microsoft.BingNews", "Microsoft.BingNews_8wekyb3d8bbwe"), store("C27EB4BA.DropboxOEM", "C27EB4BA.DropboxOEM_xbfy0k16fey96")]
    wl = apps.parse_table(LIST_EN, True)
    up = [{"id": "Docker.DockerDesktop", "available": "4.94.0"}]
    merged = {a.key: a for a in apps.merge(regs, stores, wl, up)}
    docker = merged["reg:HKLM:Docker Desktop"]
    assert docker.winget_id == "Docker.DockerDesktop" and docker.available == "4.94.0" and docker.sources == ["registro", "winget"]
    news = merged["store:Microsoft.BingNews_8wekyb3d8bbwe"]
    assert news.name == "Noticias" and news.winget_id.startswith("MSIX\\")  # nombre amigable de winget
    assert merged["reg:HKLM:McAfee.wps"].winget_id == "ARP\\Machine\\X64\\McAfee.wps"
    assert merged["winget:Vendor.Tool"].sources == ["winget"]


def test_merge_sparse_package_into_registry_app():
    sparse = store("McAfeeWPSSparsePackage", "McAfeeWPSSparsePackage_0j6k21vdgrmfw")
    sparse.name = "McAfee"
    merged = {a.key: a for a in apps.merge([reg("McAfee", "McAfee.wps")], [sparse], [], [])}
    assert list(merged) == ["reg:HKLM:McAfee.wps"] and merged["reg:HKLM:McAfee.wps"].sources == ["registro", "store"]


@pytest.mark.parametrize(
    "name,key,category",
    [
        ("Python 3.12.10 (64-bit)", "reg:HKLM:x", "Desarrollo"),
        ("MSTeams", "store:MSTeams_8wekyb3d8bbwe", "Productividad"),  # "msteams" contiene "steam"
        ("Steam", "reg:HKLM:Steam", "Juegos"),
        ("VALORANT", "reg:HKCU:x", "Juegos"),
        ("NVIDIA Controlador de gráficos 595.95", "reg:HKLM:x", "Hardware y drivers"),
        ("McAfee", "reg:HKLM:McAfee.wps", "Seguridad"),
        ("Noticias", "store:Microsoft.BingNews_8wekyb3d8bbwe", "Relleno"),
        ("Microsoft Visual C++ 2022 X64 Minimum Runtime", "reg:HKLM:x", "Sistema"),
        ("TranslucentTB", "store:TranslucentTB_x", "Sin categoría"),
    ],
)
def test_auto_category(name, key, category):
    assert apps.auto_category(App(key=key, name=name)) == category


def test_review_marks_from_the_brief():
    flagged = lambda name, key="reg:HKLM:x": apps.auto_review(App(key=key, name=name))
    for name in ["McAfee", "WebAdvisor de McAfee", "SENetFilter version 1.0.0.1", "Intel(R) Computing Improvement Program", "Lenovo Now", "Lenovo AI Now 1.3"]:
        assert flagged(name), name
    assert "OneDrive" in flagged("Dropbox - promoción", "store:C27EB4BA.DropboxOEM_x")
    assert "Defender" in flagged("McAfee")
    assert flagged("Lenovo Vantage", "store:E046963F.LenovoCompanion_k1") is None
    assert flagged("Docker Desktop") is None


def test_user_overrides(tmp_path):
    conn = db.connect(tmp_path / "prueba.db")
    a = [App(key="reg:HKLM:McAfee.wps", name="McAfee"), App(key="reg:HKLM:docker", name="Docker Desktop")]
    apps.save_meta(conn, "reg:HKLM:McAfee.wps", review=0)  # descartar la marca automática
    apps.save_meta(conn, "reg:HKLM:docker", review=1, note="Solo la uso en clase")
    apps.save_meta(conn, "reg:HKLM:docker", category="Productividad")  # no borra la marca ni la nota
    out = {x.key: x for x in apps.apply_meta(a, conn)}
    assert out["reg:HKLM:McAfee.wps"].review is None and out["reg:HKLM:McAfee.wps"].category == "Seguridad"
    d = out["reg:HKLM:docker"]
    assert (d.category, d.category_auto, d.review) == ("Productividad", "Desarrollo", "Solo la uso en clase")
    with pytest.raises(ValueError):
        apps.save_meta(conn, "x", category="Inventada")
    conn.close()


@pytest.mark.parametrize(
    "cmd,exe,params",
    [
        ('"C:\\Program Files\\Docker\\Docker Desktop Installer.exe" uninstall', "C:\\Program Files\\Docker\\Docker Desktop Installer.exe", "uninstall"),
        ("MsiExec.exe /X{35ED3F83-4BDC-4c44-8EC6-6A8301C7413A}", "MsiExec.exe", "/X{35ED3F83-4BDC-4c44-8EC6-6A8301C7413A}"),
        ("C:\\Program Files\\SENetFilter\\unins000.exe", "C:\\Program Files\\SENetFilter\\unins000.exe", ""),
    ],
)
def test_split_command(cmd, exe, params):
    assert apps.split_command(cmd) == (exe, params)


SILENT = ["/quiet", "/qn", "/s", "/S", "/silent", "/VERYSILENT", "--silent", "-silent"]


def test_uninstall_plans_are_never_silent():
    ops = apps.AppOps()
    cases = [
        App(key="a", name="Docker Desktop", uninstall='"C:\\Docker\\uninst.exe" uninstall'),
        App(key="b", name="Herramienta", winget_id="Vendor.Tool"),
        App(key="c", name="Noticias", winget_id="MSIX\\Microsoft.BingNews_4.5_x64__8wekyb3d8bbwe"),
        App(key="d", name="Silenciosa", uninstall='"C:\\x\\unins.exe" /VERYSILENT'),
        App(key="e", name="Sin desinstalador"),
    ]
    plans = {c.key: ops.plan(cases, "desinstalar", c.key) for c in cases}
    assert plans["a"].launch == ["shell", "C:\\Docker\\uninst.exe", "uninstall"]
    assert plans["b"].launch == ["console", "winget", "uninstall", "--id", "Vendor.Tool", "--exact", "--interactive"]
    assert plans["d"].launch == ["settings"] and "silencioso" in plans["d"].warnings[-1]["text"]
    assert plans["e"].launch == ["settings"]
    for p in plans.values():
        launched = " ".join(str(x) for x in p.launch)
        assert p.launch == ["settings"] or not any(f" {flag}" in f" {launched} " for flag in SILENT), launched
        assert "silencio" in p.warnings[0]["text"]


def test_uninstall_blocked_or_guarded():
    ops = apps.AppOps()
    locked = App(key="x", name="Seguridad de Windows", removable=False)
    driver = App(key="y", name="NVIDIA Controlador de gráficos", uninstall="C:\\nv\\setup.exe -uninstall", category="Hardware y drivers")
    system = App(key="z", name="Componente", uninstall="MsiExec.exe /X{1}", system=True)
    assert ops.plan([locked], "desinstalar", "x").blocked
    for a in (driver, system):
        p = ops.plan([a], "desinstalar", a.key)
        assert p.needs_ack and any(w["level"] == "peligro" for w in p.warnings)
        with pytest.raises(ValueError, match="aviso"):
            ops.run(p.id, ack=False)


def test_update_and_install_plans():
    ops = apps.AppOps()
    git = App(key="g", name="Git", version="2.55.0", available="2.55.1", winget_id="Git.Git")
    p = ops.plan([git], "actualizar", "g")
    assert p.launch == ["console", "winget", "upgrade", "--id", "Git.Git", "--exact", "--interactive"] and "2.55.1" in p.title
    with pytest.raises(ValueError):
        ops.plan([App(key="n", name="Sin update")], "actualizar", "n")
    i = ops.plan([], "instalar", winget_id="Obsidian.Obsidian", name="Obsidian")
    assert i.launch[:3] == ["console", "winget", "install"] and "--interactive" in i.launch
    for bad in ["x & calc", "a|b", '"a"', ""]:
        with pytest.raises(ValueError):
            ops.plan([], "instalar", winget_id=bad)


def test_search_validation():
    for q in ["a", "x" * 61, "a&b", "a|b", 'a"b', "--accept-source-agreements"]:
        with pytest.raises(ValueError):
            apps.search(q)


# ------------------------------------------------------------------------ API


@pytest.fixture
def client(tmp_path, monkeypatch):
    fake = [
        App(key="reg:HKLM:McAfee.wps", name="McAfee", publisher="McAfee, LLC", uninstall='"C:\\McAfee\\uninst.exe"', sources=["registro"]),
        App(key="reg:HKLM:docker", name="Docker Desktop", version="4.93.0", available="4.94.0", winget_id="Docker.DockerDesktop", sources=["registro", "winget"]),
        App(key="store:x", name="Componente", system=True, sources=["store"]),
    ]
    monkeypatch.setattr(apps.inventory, "raw", lambda refresh=False: [App(**a.__dict__) for a in fake])
    c = TestClient(create_app(PORT, token=TOKEN, db_path=tmp_path / "prueba.db"), base_url=f"http://127.0.0.1:{PORT}")
    return c


def test_api_list_and_meta(client):
    r = client.get("/api/apps").json()
    assert r["summary"] == {"count": 3, "updates": 1, "review": 1, "by_category": r["summary"]["by_category"]}
    mc = next(a for a in r["apps"] if a["name"] == "McAfee")
    assert mc["category"] == "Seguridad" and "Defender" in mc["review"] and mc["review_auto"]
    assert client.post("/api/apps/meta", json={"key": mc["key"], "review": 0}).status_code == 403  # sin token
    assert client.post("/api/apps/meta", json={"key": mc["key"], "review": 0}, headers=H).status_code == 200
    assert next(a for a in client.get("/api/apps").json()["apps"] if a["name"] == "McAfee")["review"] is None
    assert client.post("/api/apps/meta", json={"key": mc["key"], "category": "Juegos raros"}, headers=H).status_code == 422


def test_api_uninstall_needs_edit_mode_and_is_audited(client, monkeypatch):
    launched = []
    monkeypatch.setattr(apps, "launch", lambda spec: launched.append(spec))
    p = client.post("/api/apps/plan", json={"action": "desinstalar", "key": "reg:HKLM:McAfee.wps"}, headers=H).json()
    assert p["confirm"] == "Abrir el desinstalador de McAfee" and p["command"] == '"C:\\McAfee\\uninst.exe"'
    assert client.post(f"/api/apps/run/{p['id']}", json={}, headers=H).status_code == 403  # modo edición apagado
    client.post("/api/session/edit-mode", json={"enabled": True}, headers=H)
    assert client.post(f"/api/apps/run/{p['id']}", json={}, headers=H).status_code == 200
    assert launched == [["shell", "C:\\McAfee\\uninst.exe", ""]]
    assert client.post(f"/api/apps/run/{p['id']}", json={}, headers=H).status_code == 409  # se usa una vez
    h = client.get("/api/history").json()["items"][0]
    assert (h["op"], h["result"], h["src"], h["can_undo"]) == ("app_desinstalar", "iniciado", "McAfee", False)


def test_api_search_rejects_symbols(client):
    assert client.get("/api/apps/search", params={"q": "a&calc"}).status_code == 422
