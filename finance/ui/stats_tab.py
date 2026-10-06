"""Вкладка статистики: итоги месяца, диаграммы по категориям и за 12 месяцев."""
from __future__ import annotations

import tkinter as tk
from datetime import date
from tkinter import ttk

from ..models import (
    INCOME,
    KIND_LABELS,
    MONTH_NAMES,
    MonthSummary,
    format_amount,
    previous_months,
)
from . import theme
from .widgets import CanvasTooltip, TreeTable, make_card, row

PALETTE = (
    "#e53935", "#fb8c00", "#fdd835", "#43a047", "#1e88e5",
    "#8e24aa", "#00acc1", "#6d4c41", "#d81b60", "#7cb342",
)
INCOME_COLOR = "#16a34a"
EXPENSE_COLOR = "#dc2626"
MONTH_SHORT = ("янв", "фев", "мар", "апр", "май", "июн",
               "июл", "авг", "сен", "окт", "ноя", "дек")


class StatsTab(ttk.Frame):
    def __init__(self, master, service, on_change):
        super().__init__(master, padding=12)
        self.service = service
        self.on_change = on_change
        self._breakdown: list[tuple[str, str, float]] = []
        self._dynamics: list[MonthSummary] = []
        self._breakdown_tips: dict[int, str] = {}
        self._dynamics_tips: dict[int, str] = {}
        self._selected: tuple[int, int] = self._current_month()
        self._build()
        self.chart_tip = CanvasTooltip(self.chart, self._chart_tip_for)
        self.dyn_tip = CanvasTooltip(self.dynamics_canvas, self._dynamics_tip_for)

    @staticmethod
    def _current_month() -> tuple[int, int]:
        today = date.today()
        return today.year, today.month

    def _build(self) -> None:
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        top = ttk.Frame(self)
        top.grid(row=0, column=0, sticky="ew")

        month_outer, month_card = make_card(top, title="Месяц", padding=(14, 10))
        month_outer.pack(side="left", fill="y")
        self.months = previous_months(*self._current_month(), 24)
        labels = [f"{MONTH_NAMES[m - 1]} {y}" for y, m in self.months]
        self.month_combo = ttk.Combobox(
            month_card, values=labels, state="readonly", width=16
        )
        self.month_combo.current(len(labels) - 1)
        self.month_combo.pack(fill="x")
        self.month_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_month())

        self.income_var = tk.StringVar(value=format_amount(0))
        self.expense_var = tk.StringVar(value=format_amount(0))
        self.balance_var = tk.StringVar(value=format_amount(0))
        self._stat(top, "Доходы", self.income_var, "StatIncome.TLabel").pack(
            side="left", fill="both", expand=True, padx=(12, 0)
        )
        self._stat(top, "Расходы", self.expense_var, "StatExpense.TLabel").pack(
            side="left", fill="both", expand=True, padx=(12, 0)
        )
        self._stat(top, "Баланс", self.balance_var, "StatBalance.TLabel").pack(
            side="left", fill="both", expand=True, padx=(12, 0)
        )

        middle = ttk.Frame(self)
        middle.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        middle.columnconfigure(0, weight=1)
        middle.columnconfigure(1, weight=1)
        middle.rowconfigure(0, weight=1)

        left_outer, left_card = make_card(middle, title="По категориям", padding=8)
        left_outer.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self.table = TreeTable(
            left_card,
            columns=[
                ("name", "Категория", 150, "w", True),
                ("kind", "Тип", 80, "center", False),
                ("amount", "Сумма", 115, "e", True),
                ("share", "Доля", 75, "e", True),
            ],
            height=9,
        )
        self.table.frame.pack(fill="both", expand=True)

        right_outer, right_card = make_card(middle, title="Диаграмма по категориям", padding=8)
        right_outer.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        self.chart = tk.Canvas(right_card, background=theme.CARD, highlightthickness=0)
        self.chart.pack(fill="both", expand=True)
        self.chart.bind("<Configure>", lambda _e: self._draw_breakdown())

        bottom_outer, bottom_card = make_card(
            self, title="Динамика за 12 месяцев", padding=(10, 8)
        )
        bottom_outer.grid(row=2, column=0, sticky="nsew", pady=(12, 0))
        self.dynamics_canvas = tk.Canvas(
            bottom_card, background=theme.CARD, highlightthickness=0, height=170
        )
        self.dynamics_canvas.pack(fill="both", expand=True)
        self.dynamics_canvas.bind("<Configure>", lambda _e: self._draw_dynamics())

        legend = ttk.Frame(bottom_card)
        legend.pack(fill="x", pady=(8, 0))
        tk.Frame(legend, bg=INCOME_COLOR, width=12, height=12).pack(
            side="left", padx=(2, 0)
        )
        ttk.Label(legend, text="Доходы", style="Muted.TLabel").pack(
            side="left", padx=(6, 18)
        )
        tk.Frame(legend, bg=EXPENSE_COLOR, width=12, height=12).pack(
            side="left", padx=(2, 0)
        )
        ttk.Label(legend, text="Расходы", style="Muted.TLabel").pack(
            side="left", padx=(6, 0)
        )

    def _stat(self, parent, caption: str, variable: tk.StringVar, style: str):
        outer, card = make_card(parent, padding=(16, 10))
        ttk.Label(card, text=caption, style="StatLabel.TLabel").pack(anchor="w")
        ttk.Label(card, textvariable=variable, style=style).pack(anchor="w", pady=(3, 0))
        return outer

    def refresh(self) -> None:
        self._on_month()

    def _on_month(self) -> None:
        index = self.month_combo.current()
        if index < 0 or index >= len(self.months):
            index = len(self.months) - 1
        self._selected = self.months[index]
        year, month = self._selected

        summary = self.service.month_summary(year, month)
        self.income_var.set(format_amount(summary.income))
        self.expense_var.set(format_amount(summary.expense))
        self.balance_var.set(format_amount(summary.balance))

        self._breakdown = self.service.month_breakdown(year, month)
        total = sum(v for _n, _k, v in self._breakdown)
        rows = []
        for name, kind, value in self._breakdown:
            share = (value / total * 100) if total else 0.0
            rows.append(
                row(
                    f"{kind}:{name}",
                    [name, KIND_LABELS[kind], format_amount(value), f"{share:.1f}%"],
                    tags=(kind,),
                    sort=[name, kind, value, share],
                )
            )
        self.table.set_rows(rows)

        self._dynamics = self.service.dynamics(year, month, 12)
        self._draw_breakdown()
        self._draw_dynamics()

    def _draw_breakdown(self) -> None:
        canvas = self.chart
        self.chart_tip.hide()
        canvas.delete("all")
        self._breakdown_tips = {}
        width = max(canvas.winfo_width(), 100)
        height = max(canvas.winfo_height(), 100)
        items = self._breakdown
        if not items:
            canvas.create_text(
                width / 2, height / 2, text="Нет данных за месяц", fill=theme.MUTED
            )
            return

        pad_left = min(150, max(90, width // 4))
        pad_right = 115
        row_h = max(20, min(34, (height - 12) // len(items)))
        bar_max = max(40, width - pad_left - pad_right)
        max_value = max(v for _n, _k, v in items) or 1

        expense_index = 0
        for i, (name, kind, value) in enumerate(items):
            y = 6 + i * row_h
            if kind == INCOME:
                color = INCOME_COLOR
            else:
                color = PALETTE[expense_index % len(PALETTE)]
                expense_index += 1
            length = max(2, int(bar_max * value / max_value))
            label = name if len(name) <= 16 else name[:15] + "…"
            canvas.create_text(pad_left - 8, y + row_h / 2, text=label, anchor="e")
            item = canvas.create_rectangle(
                pad_left, y + 4, pad_left + length, y + row_h - 4,
                fill=color, outline="",
            )
            self._breakdown_tips[item] = (
                f"{KIND_LABELS[kind]}: {name} — {format_amount(value)}"
            )
            canvas.create_text(
                pad_left + length + 8, y + row_h / 2,
                text=format_amount(value), anchor="w",
            )

    def _chart_tip_for(self, event, canvas) -> str | None:
        return _tip_at(canvas, self._breakdown_tips, event.x, event.y)

    def _draw_dynamics(self) -> None:
        canvas = self.dynamics_canvas
        self.dyn_tip.hide()
        canvas.delete("all")
        self._dynamics_tips = {}
        width = max(canvas.winfo_width(), 100)
        height = max(canvas.winfo_height(), 100)
        series = self._dynamics
        if not series:
            return

        pad_top = 14
        pad_bottom = 26
        pad_left = 74
        pad_right = 12
        plot_w = width - pad_left - pad_right
        plot_h = height - pad_top - pad_bottom
        max_value = max(
            [s.income for s in series] + [s.expense for s in series] + [1]
        )

        for step in range(5):
            value = max_value * step / 4
            y = pad_top + plot_h - plot_h * step / 4
            canvas.create_line(pad_left, y, width - pad_right, y, fill="#EDEFF4")
            text = f"{value:,.0f}".replace(",", "\u00a0")
            canvas.create_text(pad_left - 8, y, text=text, anchor="e", fill=theme.MUTED)

        slot = plot_w / len(series)
        bar_w = max(4, min(18, slot / 2.6))
        for i, s in enumerate(series):
            cx = pad_left + slot * i + slot / 2
            month = f"{MONTH_NAMES[s.month - 1]} {s.year}"
            for offset, value, color, caption in (
                (-bar_w / 2 - 1, s.income, INCOME_COLOR, "Доходы"),
                (bar_w / 2 + 1, s.expense, EXPENSE_COLOR, "Расходы"),
            ):
                h = plot_h * value / max_value if max_value else 0
                if h > 0:
                    item = canvas.create_rectangle(
                        cx + offset - bar_w / 2,
                        pad_top + plot_h - h,
                        cx + offset + bar_w / 2,
                        pad_top + plot_h,
                        fill=color, outline="",
                    )
                    self._dynamics_tips[item] = (
                        f"{caption}, {month}: {format_amount(value)}"
                    )
            canvas.create_text(
                cx, height - pad_bottom + 15,
                text=MONTH_SHORT[s.month - 1], fill=theme.MUTED,
            )

    def _dynamics_tip_for(self, event, canvas) -> str | None:
        return _tip_at(canvas, self._dynamics_tips, event.x, event.y)


def _tip_at(canvas: tk.Canvas, tips: dict[int, str], x: int, y: int) -> str | None:
    canvas_x = canvas.canvasx(x)
    canvas_y = canvas.canvasy(y)
    for item in canvas.find_overlapping(
        canvas_x - 1, canvas_y - 1, canvas_x + 1, canvas_y + 1
    ):
        text = tips.get(item)
        if text:
            return text
    return None
