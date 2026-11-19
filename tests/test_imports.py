import sys

import pytest

from testmon.imports import STAR, ImportGraph, parse_imports


def test_parse_imports():
    imports, exports = parse_imports(
        "import a.b\n"
        "import c as d\n"
        "from .m import x as y, z\n"
        "from .. import n\n"
        "from p import *\n"
        "def f():\n"
        "    import lazy\n"
    )
    assert imports == [
        ("a.b", 0, None),
        ("c", 0, None),
        ("m", 1, "x"),
        ("m", 1, "z"),
        ("", 2, "n"),
        ("p", 0, STAR),
        ("lazy", 0, None),
    ]
    assert exports == {
        "y": ("m", 1, "x"),
        "z": ("m", 1, "z"),
        "n": ("", 2, "n"),
        STAR: [("p", 0, STAR)],
    }


def test_parse_imports_syntax_error():
    assert parse_imports("def (:") == ([], {})


def test_installed_packages_are_not_project_files():
    graph = ImportGraph(sys.prefix)
    graph._index_modules()
    assert "pytest" in sys.modules
    assert pytest.__name__ not in graph._files
