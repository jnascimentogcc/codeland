import pytest

from codeland_analyzer.gitrepo import is_source, is_test, language_of
from codeland_analyzer.parse import ImportRef, analyze_python
from codeland_analyzer.resolve import PythonIndex

SOURCE = b'''"""Module docstring
over two lines."""
import os, a.b as c
from . import x, y as z
from ..pkg.mod import (q, r)
from app.core import *
import importlib

# a comment
def f(a, b):
    """doc"""
    if a and b:        # +1 if, +1 and
        return 1
    elif b:            # +1
        return 2
    for i in a:        # +1
        pass
    try:
        pass
    except ValueError:  # +1
        pass
    return [i for i in a if i]  # +2 comprehension clauses


class K:
    def m(self):
        return 1 if self else 2  # +1


g = lambda: importlib.import_module("plug.in")
'''


def test_metrics_of_python_source():
    metrics = analyze_python(SOURCE)
    assert metrics.functions == 3  # f, K.m and the lambda
    assert metrics.complexity == 3 + 7 + 1
    assert metrics.max_function_complexity == 8
    # docstrings and comments are not code lines
    assert metrics.loc == 21


def test_python_imports():
    imports = analyze_python(SOURCE).imports
    assert sorted(imports) == sorted(
        [
            ImportRef("os", "import"),
            ImportRef("a.b", "import"),
            ImportRef(".", "import", ("x", "y")),
            ImportRef("..pkg.mod", "import", ("q", "r")),
            ImportRef("app.core", "import", ()),
            ImportRef("importlib", "import"),
            ImportRef("plug.in", "dynamic-import"),
        ]
    )


@pytest.mark.parametrize(
    ("path", "language", "test"),
    [
        ("app/main.py", "python", False),
        ("tests/test_x.py", "python", True),
        ("app/test_utils.py", "python", True),
        ("app/utils_test.py", "python", True),
        ("app/conftest.py", "python", True),
        ("app/stubs.pyi", None, False),
        ("web/a.ts", "typescript", False),
        ("web/a.d.ts", None, False),
    ],
)
def test_language_and_test_detection(path, language, test):
    assert language_of(path) == language
    assert is_source(path) == (language is not None)
    if language:
        assert is_test(path) == test


KNOWN = {
    "backend/app/__init__.py",
    "backend/app/main.py",
    "backend/app/services/__init__.py",
    "backend/app/services/billing.py",
    "backend/app/models.py",
    "backend/tests/test_billing.py",
    "tools/gen.py",
    "scripts/models.py",
}


def resolve(importer, specifier, *names):
    return PythonIndex(KNOWN).resolve(importer, ImportRef(specifier, "import", names))


def test_absolute_imports_use_the_source_root_above_the_importer():
    assert resolve("backend/app/main.py", "app.services.billing") == [
        "backend/app/services/billing.py"
    ]
    assert resolve("backend/tests/test_billing.py", "app.models") == ["backend/app/models.py"]
    assert resolve("backend/app/main.py", "app.services") == ["backend/app/services/__init__.py"]
    # a module with the same name elsewhere is not picked over the one the importer can see
    assert resolve("backend/app/main.py", "models") == ["backend/app/models.py"]
    assert resolve("backend/app/main.py", "os") == []
    assert resolve("backend/app/main.py", "requests.adapters") == []


def test_from_imports_include_submodules_but_not_attributes():
    assert resolve("backend/app/main.py", "app.services", "billing", "helper") == [
        "backend/app/services/__init__.py",
        "backend/app/services/billing.py",
    ]


def test_relative_imports():
    importer = "backend/app/services/billing.py"
    assert resolve(importer, ".") == ["backend/app/services/__init__.py"]
    assert resolve(importer, "..", "models") == ["backend/app/__init__.py", "backend/app/models.py"]
    assert resolve(importer, "..models") == ["backend/app/models.py"]
    assert resolve(importer, ".missing") == []


def test_unique_match_outside_the_importer_roots_is_accepted():
    assert resolve("tools/gen.py", "app.services.billing") == ["backend/app/services/billing.py"]
    # ambiguous outside the importer's roots: refuse to guess
    assert resolve("tools/gen.py", "models") == []
