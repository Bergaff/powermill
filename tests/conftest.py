"""
Общая настройка тестов.

ВАЖНО: переменные окружения выставляются ДО импорта config — config.py читает их
на этапе импорта и создаёт папки. Тесты пишут в tests/_data, не в E:\\.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent
FIXTURE_HELP = TESTS_DIR / "fixture_help"
TEST_DATA = TESTS_DIR / "_data"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ["POWERMILL_DATA_ROOT"] = str(TEST_DATA)
os.environ["POWERMILL_HELP_DIR"] = str(FIXTURE_HELP)
os.environ["POWERMILL_HELP_DIR_EXTRA"] = ""
os.environ["POWERMILL_HELP_LANG"] = "rus"

import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _clean_test_data():
    """Чистые выходные папки на время тестов."""
    if TEST_DATA.exists():
        shutil.rmtree(TEST_DATA.parent / "_data", ignore_errors=True)
    (TEST_DATA / "output").mkdir(parents=True, exist_ok=True)
    yield TEST_DATA
    shutil.rmtree(TEST_DATA, ignore_errors=True)


@pytest.fixture(scope="session")
def parsed_pages(_clean_test_data):
    """Один раз парсим фикстуру справки — из результата живут все тесты."""
    from src.html_parser import parse_all_help

    return parse_all_help(roots=[FIXTURE_HELP])
