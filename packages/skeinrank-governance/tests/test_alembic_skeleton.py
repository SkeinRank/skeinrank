from __future__ import annotations

from pathlib import Path


def test_alembic_skeleton_files_exist():
    package_root = Path(__file__).resolve().parents[1]

    assert (package_root / "alembic.ini").exists()
    assert (package_root / "alembic" / "env.py").exists()
    assert (package_root / "alembic" / "script.py.mako").exists()
    assert any((package_root / "alembic" / "versions").glob("*.py"))
