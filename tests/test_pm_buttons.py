"""
Тесты единого списка действий (src\\pm_buttons.py).

Смысл файла в том, что лента и панель плагина берут кнопки из **одного** места.
Поэтому проверяем: список целый, цели кнопок существуют, лента и панель не
расходятся, а батники, которые спрашивают технолога, помечены как «отдельное
окно».
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src import pm_buttons

PROJECT = Path(__file__).resolve().parent.parent


def test_registry_validates():
    assert pm_buttons.validate() == []


def test_keys_labels_and_launchers_are_unique():
    for field in ("key", "label", "launcher"):
        values = [getattr(action, field) for action in pm_buttons.ACTIONS]
        assert len(values) == len(set(values)), field


def test_macro_actions_point_to_macros_and_others_to_scenarios():
    for action in pm_buttons.ACTIONS:
        if action.kind == "macro":
            assert action.target.endswith(".mac"), action.key
            assert not action.asks, action.key
        elif action.kind == "bat":
            assert action.target.endswith(".bat"), action.key
            assert (PROJECT / action.target.replace("\\", "/")).exists(), action.target
            assert action.asks, action.key
        else:
            module = PROJECT / (action.target.replace(".", "/") + ".py")
            package = PROJECT / action.target.replace(".", "/") / "__init__.py"
            assert module.exists() or package.exists(), action.target
            assert not action.asks, action.key


def test_ribbon_uses_the_same_list():
    buttons = pm_buttons.ribbon_buttons()
    assert len(buttons) == len(pm_buttons.ribbon_actions())
    labels = [button[0] for button in buttons]
    assert labels == [action.label for action in pm_buttons.ribbon_actions()]
    # каждая кнопка ленты запускает наш макрос-запускатель или сам макрос
    for _label, launcher, target, _hint in buttons:
        assert launcher.endswith(".mac")
        assert target, launcher


def test_ribbon_now_has_the_new_scenarios():
    """Раньше лента отставала от пунктов — теперь берёт всё из списка."""
    labels = "\n".join(action.label for action in pm_buttons.ribbon_actions())
    for expected in ("Проверки (3.4)", "NC-программа (3.5)", "СДЕЛАЙ (3.6)"):
        assert expected in labels


def test_pane_groups_cover_every_pane_action():
    groups = pm_buttons.pane_groups()
    assert groups, "панель не может быть пустой"
    total = sum(len(items) for _name, items in groups)
    assert total == len(pm_buttons.pane_actions())
    names = [name for name, _items in groups]
    assert len(names) == len(set(names))
    assert pm_buttons.GROUP_MACROS in names       # макросы — отдельной группой


def test_macros_group_contains_macro_actions_only():
    macros = dict(pm_buttons.pane_groups())[pm_buttons.GROUP_MACROS]
    assert macros, "в группе макросов должны быть кнопки"
    assert all(action.kind == "macro" for action in macros)


def test_by_key_finds_and_misses():
    assert pm_buttons.by_key("flow") is not None
    assert pm_buttons.by_key("нет_такого") is None


def test_windows_targets_are_relative_to_project():
    for action in pm_buttons.ACTIONS:
        if action.kind == "bat":
            assert not action.target.startswith(("/", "\\")), action.target
            assert ":" not in action.target, action.target
