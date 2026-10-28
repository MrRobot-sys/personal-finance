"""Базовые виджеты и тема оформления интерфейса.

Реэкспортует публичный API модуля ``widgets`` и подмодуль ``theme``
для обратной совместимости: ``from finance.ui.widgets import X``.
"""
from __future__ import annotations

from . import theme
from .widgets import (
    CanvasTooltip,
    FormDialog,
    PlaceholderEntry,
    ScrollableFrame,
    TreeTable,
    add_divider,
    make_card,
    row,
    run_dialog,
)

__all__ = [
    "CanvasTooltip",
    "FormDialog",
    "PlaceholderEntry",
    "ScrollableFrame",
    "TreeTable",
    "add_divider",
    "make_card",
    "row",
    "run_dialog",
    "theme",
]
