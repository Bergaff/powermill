"""Тесты пункта 23: макрос разведки должен быть СВЕЖИМ и с абсолютным путём.

Причина: путь к файлу снимка вписан внутрь макроса. Если в папке PowerMill
осталась старая копия (или файл в output от прежней версии), макрос пишет не
туда — и выглядит это как «макрос ничего не делает». Поэтому пункт 23 каждый
раз пересобирает PM_PROBE.mac под этот компьютер.
"""
from __future__ import annotations

import config

from scripts import check_pm_api
from src import pml_files, pm_macro


def test_install_probe_macro_regenerates_stale_copy(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path)
    pm_folder = tmp_path / "pm_macros"
    pm_folder.mkdir()
    monkeypatch.setattr(pm_macro, "power_mill_macro_folders", lambda: [pm_folder])

    # заведомо устаревшая копия: только печать, без записи файла
    stale = tmp_path / "PM_PROBE.mac"
    stale.write_text("// старая версия\nPRINT \"старый макрос\"\n", encoding="utf-8")

    copied = check_pm_api.install_probe_macro()

    assert copied == [pm_folder / "PM_PROBE.mac"]
    fresh = pml_files.read(stale)
    assert "FILE OPEN" in fresh                      # макрос пересобран
    assert "RESET LOCALVARS" in fresh
    assert "старый макрос" not in fresh
    # путь к снимку — абсолютный и с прямыми слэшами
    assert str(tmp_path / "pm_project.txt").replace("\\", "/") in fresh
    assert pml_files.read(pm_folder / "PM_PROBE.mac") == fresh


def test_install_probe_macro_survives_no_folders(tmp_path, monkeypatch):
    """Если папок PowerMill нет — просто ничего не копируем, но файл создаём."""
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(pm_macro, "power_mill_macro_folders", lambda: [])

    assert check_pm_api.install_probe_macro() == []
    assert (tmp_path / "PM_PROBE.mac").exists()
