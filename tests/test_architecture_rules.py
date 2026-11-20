"""Architecture & syntax enforcement tests (Rule D5 + Zero-Qt Domain)."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = PROJECT_ROOT / "src" / "kazu"


def _iter_imported_modules(py_file: Path) -> set[str]:
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


class ArchitectureRulesTests(unittest.TestCase):
    def test_all_python_files_parse_cleanly(self) -> None:
        py_files = list((PROJECT_ROOT / "src").rglob("*.py")) + list(
            (PROJECT_ROOT / "scripts").rglob("*.py")
        )
        self.assertGreaterEqual(len(py_files), 20)
        for py_file in py_files:
            ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))

    def test_domain_has_zero_qt_imports(self) -> None:
        domain_dir = SRC_ROOT / "domain"
        for py_file in domain_dir.rglob("*.py"):
            imports = _iter_imported_modules(py_file)
            qt_imports = [m for m in imports if "PySide6" in m or "PyQt" in m]
            self.assertEqual(
                qt_imports,
                [],
                f"{py_file.name} must not import Qt: {qt_imports}",
            )

    def test_only_engine_qt_imports_webengine(self) -> None:
        allowed_file = (SRC_ROOT / "ui" / "engine_qt.py").resolve()
        for py_file in SRC_ROOT.rglob("*.py"):
            imports = _iter_imported_modules(py_file)
            webengine_imports = [m for m in imports if "QtWebEngine" in m]
            if py_file.resolve() == allowed_file:
                self.assertTrue(
                    webengine_imports,
                    "engine_qt.py should import QtWebEngine modules",
                )
            else:
                self.assertEqual(
                    webengine_imports,
                    [],
                    f"{py_file} violated Rule D5 by importing {webengine_imports}",
                )


if __name__ == "__main__":
    unittest.main()
