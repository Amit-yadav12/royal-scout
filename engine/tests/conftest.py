"""Shared test helpers. All data is synthetic and clearly labelled."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ENGINE_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ENGINE_ROOT / "tests" / "fixtures" / "generated"


@pytest.fixture(scope="session", autouse=True)
def fixtures_generated() -> None:
    if not (FIXTURES / "batting_innings.csv").exists():
        subprocess.run([sys.executable, str(ENGINE_ROOT / "tests" / "fixtures" / "make_fixtures.py")],
                       check=True, capture_output=True)


@pytest.fixture()
def tmp_storage(tmp_path: Path) -> Path:
    return tmp_path / "storage"


@pytest.fixture()
def bat_csv() -> Path:
    return FIXTURES / "batting_innings.csv"


@pytest.fixture()
def bowl_csv() -> Path:
    return FIXTURES / "bowling_innings.csv"


@pytest.fixture()
def bbb_csv() -> Path:
    return FIXTURES / "ball_by_ball.csv"


@pytest.fixture()
def archive_zip() -> Path:
    return FIXTURES / "dataset_bundle.zip"
