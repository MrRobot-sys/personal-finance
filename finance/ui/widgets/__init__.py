"""Базовые виджеты, диаграммы и тема оформления интерфейса.

Реэкспортует публичный API модулей ``widgets`` и ``charts``, подмодуль
``theme`` для обратной совместимости: ``from finance.ui.widgets import X``.
"""
from __future__ import annotations

from . import charts, theme
from .charts import draw_donut, draw_dynamics, draw_plan_fact
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
    "charts",
    "draw_donut",
    "draw_dynamics",
    "draw_plan_fact",
    "make_card",
    "row",
    "run_dialog",
    "theme",
]
