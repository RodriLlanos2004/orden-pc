import os

import pytest

from orden_pc.safety import UnsafePath, protected_reason, resolve_target


@pytest.fixture
def root(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.txt").write_text("a")
    return tmp_path


def ok(raw, root, **kw):
    return resolve_target(raw, [str(root)], **kw)


def test_valid_paths_resolve(root):
    assert ok(str(root / "docs" / "a.txt"), root) == root / "docs" / "a.txt"
    assert ok(str(root / "docs" / "nuevo"), root) == root / "docs" / "nuevo"  # aún no existe
    assert ok(str(root).replace("\\", "/") + "/docs", root) == root / "docs"
    assert ok(str(root / "docs").upper(), root).name.lower() == "docs"


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "docs\\a.txt",
        "\\docs",
        "\\\\servidor\\recurso\\a.txt",
        "//servidor/recurso",
        "\\\\?\\C:\\Windows",
        "\\\\.\\C:\\Windows",
    ],
)
def test_rejects_relative_unc_and_device_paths(root, raw):
    with pytest.raises(UnsafePath):
        ok(raw, root)


@pytest.mark.parametrize("suffix", ["..\\..\\Windows", "docs\\..\\..\\x", "docs/../../x"])
def test_rejects_dotdot(root, suffix):
    with pytest.raises(UnsafePath, match=r"\.\."):
        ok(str(root) + "\\" + suffix, root)


@pytest.mark.parametrize("name", ["a.txt:oculto", "a.txt::$DATA", "a<b", "a|b", "a?b", "a*b", 'a"b', "a\x00b"])
def test_rejects_bad_chars_and_ads(root, name):
    with pytest.raises(UnsafePath):
        ok(str(root / "docs") + "\\" + name, root)


@pytest.mark.parametrize("name", ["carpeta.", "carpeta ", "docs.\\a.txt"])
def test_rejects_trailing_dot_or_space(root, name):
    with pytest.raises(UnsafePath, match="punto o espacio"):
        ok(str(root) + "\\" + name, root)


def test_rejects_outside_roots(root, tmp_path_factory):
    other = tmp_path_factory.mktemp("otra")
    with pytest.raises(UnsafePath, match="fuera"):
        ok(str(other), root)
    # Prefijo engañoso: C:\raiz-mala no está dentro de C:\raiz
    with pytest.raises(UnsafePath, match="fuera"):
        ok(str(root) + "-mala\\x", root)


@pytest.mark.parametrize(
    "path",
    [
        "C:\\",
        "C:\\Windows\\System32",
        "c:\\windows",
        "C:\\Program Files\\App",
        "C:\\Program Files (x86)",
        "C:\\ProgramData\\x",
        "C:\\$Recycle.Bin\\S-1-5",
        "C:\\System Volume Information",
        "C:\\Recovery\\x",
        "C:\\Users\\rodri\\AppData\\Local\\x",
        "C:\\Users\\rodri\\Dev\\repo\\.git\\config",
        "C:\\Users\\rodri\\Dev\\repo\\.GIT",
    ],
)
def test_protected_paths(path):
    assert protected_reason(path) is not None


def test_not_protected():
    for p in ["C:\\Users\\rodri\\Downloads\\a.pdf", "C:\\Users\\rodri\\Dev\\repo\\.gitignore", "C:\\Users\\rodri\\Recovery"]:
        assert protected_reason(p) is None, p


def test_protected_even_if_root_allows_it():
    with pytest.raises(UnsafePath, match="protegida"):
        resolve_target("C:\\Windows\\System32", ["C:\\"])
    with pytest.raises(UnsafePath, match="raíz"):
        resolve_target("C:\\", ["C:\\"])


def test_extra_protected_adds_to_defaults(root):
    with pytest.raises(UnsafePath, match="protegida"):
        ok(str(root / "docs" / "a.txt"), root, extra_protected=[str(root / "docs")])
    # Agregar una lista extra no quita las de fábrica.
    assert protected_reason("C:\\Windows", extra=[str(root)]) is not None


def test_git_internals_inside_root(root):
    (root / "repo" / ".git").mkdir(parents=True)
    with pytest.raises(UnsafePath, match="Git"):
        ok(str(root / "repo" / ".git" / "HEAD"), root)
    assert ok(str(root / "repo"), root) == root / "repo"


def test_junction_to_protected_path_is_rejected(root, junction):
    link = junction(os.environ.get("SystemRoot", "C:\\Windows"), root / "atajo")
    with pytest.raises(UnsafePath, match="protegida"):
        ok(str(link / "System32"), root)


def test_junction_escaping_root_is_rejected(root, tmp_path_factory, junction):
    outside = tmp_path_factory.mktemp("afuera")
    junction(outside, root / "salida")
    with pytest.raises(UnsafePath, match="fuera"):
        ok(str(root / "salida"), root)


def test_short_name_is_expanded():
    short = "C:\\PROGRA~1"
    if not os.path.exists(short):
        pytest.skip("Este volumen no tiene nombres cortos 8.3")
    with pytest.raises(UnsafePath, match="protegida"):
        resolve_target(short + "\\x", ["C:\\"])
