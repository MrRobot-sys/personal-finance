"""Вкладка статистики: итоги месяца, структура, план и факт, динамика."""
from __future__ import annotations

import tkinter as tk
from datetime import date
from tkinter import ttk

from ...models import (
    EXPENSE,
    INCOME,
    KIND_LABELS,
    MONTH_NAMES,
    MonthSummary,
    format_amount,
    previous_months,
)
from ..widgets import CanvasTooltip, TreeTable, charts, make_card, row, theme


class StatsTab(ttk.Frame):
    def __init__(self, master, service, on_change):
        super().__init__(master, padding=theme.SPACING["large"])
        self.service = service
        self.on_change = on_change
        self._breakdown: list[tuple[str, str, float]] = []
        self._donut_slices: list[tuple[str, float, str]] = []
        self._donut_caption = "Расходы"
        self._plan_rows: list[tuple[str, float, float]] = []
        self._dynamics: list[MonthSummary] = []
        self._colors: dict[str, str] = {}
        self._donut_tips: dict[int, str] = {}
        self._plan_tips: dict[int, str] = {}
        self._dynamics_tips: dict[int, str] = {}
        self._selected: tuple[int, int] = self._current_month()
        self._build()
        self.chart_tip = CanvasTooltip(self.donut_canvas, self._donut_tip_for)
        self.plan_tip = CanvasTooltip(self.plan_canvas, self._plan_tip_for)
        self.dyn_tip = CanvasTooltip(self.dynamics_canvas, self._dynamics_tip_for)

    @staticmethod
    def _current_month() -> tuple[int, int]:
        today = date.today()
        return today.year, today.month

    def _build(self) -> None:
        self.rowconfigure(1, weight=1, minsize=200)
        self.rowconfigure(2, weight=1, minsize=210)
        self.columnconfigure(0, weight=1)

        top = ttk.Frame(self)
        top.grid(row=0, column=0, sticky="ew")

        month_outer, month_card = make_card(
            top, title="Месяц", padding=theme.CARD_PADDING
        )
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
            side="left", fill="both", expand=True, padx=(theme.SPACING["large"], 0)
        )
        self._stat(top, "Расходы", self.expense_var, "StatExpense.TLabel").pack(
            side="left", fill="both", expand=True, padx=(theme.SPACING["large"], 0)
        )
        self._stat(top, "Баланс", self.balance_var, "StatBalance.TLabel").pack(
            side="left", fill="both", expand=True, padx=(theme.SPACING["large"], 0)
        )

        middle = ttk.Frame(self)
        middle.grid(row=1, column=0, sticky="nsew", pady=(theme.SPACING["large"], 0))
        middle.columnconfigure(0, weight=1)
        middle.columnconfigure(1, weight=1)
        middle.rowconfigure(0, weight=1)

        left_outer, left_card = make_card(
            middle, title="По категориям", padding=theme.CARD_PADDING_COMPACT
        )
        left_outer.grid(
            row=0, column=0, sticky="nsew", padx=(0, theme.SPACING["small"])
        )
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

        donut_outer, donut_card = make_card(
            middle,
            title="Структура месяца",
            padding=theme.CARD_PADDING_COMPACT,
        )
        donut_outer.grid(
            row=0, column=1, sticky="nsew", padx=(theme.SPACING["small"], 0)
        )
        self.donut_canvas = tk.Canvas(
            donut_card, background=theme.CARD, highlightthickness=0
        )
        self.donut_canvas.pack(fill="both", expand=True)
        self.donut_canvas.bind("<Configure>", lambda _e: self._draw_donut())

        bottom = ttk.Frame(self)
        bottom.grid(row=2, column=0, sticky="nsew", pady=(theme.SPACING["large"], 0))
        bottom.columnconfigure(0, weight=1)
        bottom.columnconfigure(1, weight=1)
        bottom.rowconfigure(0, weight=1)

        plan_outer, plan_card = make_card(
            bottom, title="План и факт (расходы)", padding=theme.CARD_PADDING_COMPACT
        )
        plan_outer.grid(
            row=0, column=0, sticky="nsew", padx=(0, theme.SPACING["small"])
        )
        self.plan_canvas = tk.Canvas(
            plan_card, background=theme.CARD, highlightthickness=0, height=150
        )
        self.plan_canvas.pack(fill="both", expand=True)
        self.plan_canvas.bind("<Configure>", lambda _e: self._draw_plans())

        dyn_outer, dyn_card = make_card(
            bottom, title="Динамика за 12 месяцев", padding=theme.CARD_PADDING
        )
        dyn_outer.grid(
            row=0, column=1, sticky="nsew", padx=(theme.SPACING["small"], 0)
        )
        self.dynamics_canvas = tk.Canvas(
            dyn_card, background=theme.CARD, highlightthickness=0, height=150
        )
        self.dynamics_canvas.pack(fill="both", expand=True)
        self.dynamics_canvas.bind("<Configure>", lambda _e: self._draw_dynamics())

        legend = ttk.Frame(dyn_card)
        legend.pack(fill="x", pady=(theme.SPACING["small"], 0))
        tk.Frame(legend, bg=theme.SUCCESS, width=12, height=12).pack(
            side="left", padx=(theme.SPACING["small"], 0)
        )
        ttk.Label(legend, text="Доходы", style="Muted.TLabel").pack(
            side="left", padx=(theme.SPACING["medium"], theme.SPACING["large"])
        )
        tk.Frame(legend, bg=theme.DANGER, width=12, height=12).pack(
            side="left", padx=(theme.SPACING["small"], 0)
        )
        ttk.Label(legend, text="Расходы", style="Muted.TLabel").pack(
            side="left", padx=(theme.SPACING["medium"], theme.SPACING["large"])
        )
        tk.Frame(legend, bg=theme.ACCENT, width=16, height=2).pack(
            side="left", padx=(theme.SPACING["small"], 0), pady=(5, 0)
        )
        ttk.Label(legend, text="Тренд расходов", style="Muted.TLabel").pack(
            side="left", padx=(theme.SPACING["medium"], 0)
        )

    def _stat(self, parent, caption: str, variable: tk.StringVar, style: str):
        outer, card = make_card(parent, padding=theme.CARD_PADDING)
        ttk.Label(card, text=caption, style="StatLabel.TLabel").pack(anchor="w")
        ttk.Label(card, textvariable=variable, style=style).pack(
            anchor="w", pady=(theme.SPACING["small"], 0)
        )
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

        self._colors = self._category_colors()
        slices = [(n, v) for n, k, v in self._breakdown if k == EXPENSE]
        self._donut_caption = "Расходы"
        if not slices:
            slices = [(n, v) for n, k, v in self._breakdown if k == INCOME]
            self._donut_caption = "Доходы"
        self._donut_slices = [
            (name, value, self._color_for(name, index))
            for index, (name, value) in enumerate(slices)
        ]

        self._plan_rows = sorted(
            (
                (plan.category.name, float(plan.limit or 0.0), float(plan.spent))
                for plan in self.service.category_plans(year, month)
                if plan.category.kind == EXPENSE and plan.has_limit
            ),
            key=lambda item: item[1],
            reverse=True,
        )
        self._dynamics = self.service.dynamics(year, month, 12)
        self._draw_donut()
        self._draw_plans()
        self._draw_dynamics()

    def _category_colors(self) -> dict[str, str]:
        """Устойчивый цвет категории независимо от месяца и суммы."""
        names = sorted(category.name for category in self.service.categories(EXPENSE))
        names += sorted(category.name for category in self.service.categories(INCOME))
        return {
            name: charts.PALETTE[index % len(charts.PALETTE)]
            for index, name in enumerate(names)
        }

    def _color_for(self, name: str, index: int) -> str:
        return self._colors.get(name, charts.PALETTE[index % len(charts.PALETTE)])

    def _month_note(self) -> str:
        year, month = self._selected
        return f"{MONTH_NAMES[month - 1].lower()} {year}"

    def _draw_donut(self) -> None:
        self.chart_tip.hide()
        self._donut_tips = charts.draw_donut(
            self.donut_canvas,
            self._donut_slices,
            caption=self._donut_caption,
            note=self._month_note(),
            empty_text=charts.EMPTY_MONTH,
        )

    def _draw_plans(self) -> None:
        self.plan_tip.hide()
        self._plan_tips = charts.draw_plan_fact(
            self.plan_canvas, self._plan_rows, empty_text=charts.EMPTY_PERIOD
        )

    def _draw_dynamics(self) -> None:
        self.dyn_tip.hide()
        self._dynamics_tips = charts.draw_dynamics(
            self.dynamics_canvas, self._dynamics, empty_text=charts.EMPTY_PERIOD
        )

    def _donut_tip_for(self, event, canvas) -> str | None:
        return _tip_at(canvas, self._donut_tips, event.x, event.y)

    def _plan_tip_for(self, event, canvas) -> str | None:
        return _tip_at(canvas, self._plan_tips, event.x, event.y)

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
