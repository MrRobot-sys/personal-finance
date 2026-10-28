"""Диалоги работы с категориями."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..models import (
    EXPENSE,
    INCOME,
    INVEST,
    KIND_LABELS,
    Category,
    ValidationError,
    parse_optional_amount,
)
from .widgets import FormDialog
from .dialogs_common import _amount_text


class CategoryDialog(FormDialog):
    def __init__(self, parent, category: Category | None = None):
        self._category = category
        title = "Редактировать категорию" if category else "Новая категория"
        super().__init__(parent, title, confirm_text="Сохранить")

    def build_body(self, parent) -> None:
        cat = self._category
        self.name_var = tk.StringVar(value=cat.name if cat else "")
        kind = cat.kind if cat else EXPENSE
        self.kind_var = tk.StringVar(value=kind)
        self.plan_var = tk.StringVar(
            value=_amount_text(cat.monthly_limit) if cat else ""
        )

        ttk.Label(parent, text="Название:").grid(row=0, column=0, sticky="w", pady=4)
        entry = ttk.Entry(parent, textvariable=self.name_var, width=34)
        entry.grid(row=0, column=1, columnspan=2, sticky="ew", pady=4)

        ttk.Label(parent, text="Тип:").grid(row=1, column=0, sticky="w", pady=4)
        types = ttk.Frame(parent)
        types.grid(row=1, column=1, columnspan=2, sticky="w", pady=4)
        ttk.Radiobutton(
            types, text=KIND_LABELS[EXPENSE], value=EXPENSE, variable=self.kind_var,
            command=self._sync_plan,
        ).pack(side="left")
        ttk.Radiobutton(
            types, text=KIND_LABELS[INCOME], value=INCOME, variable=self.kind_var,
            command=self._sync_plan,
        ).pack(side="left", padx=(12, 0))
        ttk.Radiobutton(
            types, text=KIND_LABELS[INVEST], value=INVEST, variable=self.kind_var,
            command=self._sync_plan,
        ).pack(side="left", padx=(12, 0))

        ttk.Label(parent, text="План в месяц:").grid(row=2, column=0, sticky="w", pady=4)
        self.plan_entry = ttk.Entry(parent, textvariable=self.plan_var, width=16)
        self.plan_entry.grid(row=2, column=1, sticky="w", pady=4)
        ttk.Label(
            parent, text="Сколько обычно поступает/тратится в месяц.\nПусто — без плана. "
            "Для инвестиций план не задаётся.",
            foreground="gray", justify="left",
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(0, 4))
        self._sync_plan()

    def _sync_plan(self) -> None:
        state = "disabled" if self.kind_var.get() == INVEST else "normal"
        self.plan_entry.configure(state=state)

    def on_ok(self) -> None:
        name = self.name_var.get().strip()
        if not name:
            self.show_error("Введите название категории")
            return
        if len(name) > 60:
            self.show_error("Название слишком длинное (макс. 60)")
            return
        if self.kind_var.get() == INVEST:
            plan = None
        else:
            try:
                plan = parse_optional_amount(self.plan_var.get())
            except ValidationError as exc:
                self.show_error(str(exc))
                return
        self.result = (name, self.kind_var.get(), plan)
        self.destroy()


class PlanDialog(FormDialog):
    """Задание ожидаемой суммы в месяц для выбранной категории."""

    def __init__(self, parent, categories: list[Category]):
        self._categories = categories
        super().__init__(parent, "План в месяц", confirm_text="Сохранить")

    def build_body(self, parent) -> None:
        names = [c.name for c in self._categories]
        selected = next((c for c in self._categories if c.monthly_limit), None)
        self.plan_var = tk.StringVar(value=_amount_text(selected.monthly_limit) if selected else "")

        ttk.Label(parent, text="Категория:").grid(row=0, column=0, sticky="w", pady=4)
        self.category_var = tk.StringVar(value=selected.name if selected else (names[0] if names else ""))
        combo = ttk.Combobox(
            parent, textvariable=self.category_var, values=names,
            state="readonly", width=31,
        )
        combo.grid(row=0, column=1, columnspan=2, sticky="ew", pady=4)

        ttk.Label(parent, text="Сумма в месяц:").grid(row=1, column=0, sticky="w", pady=4)
        self.amount_entry = ttk.Entry(parent, textvariable=self.plan_var, width=16)
        self.amount_entry.grid(row=1, column=1, columnspan=2, sticky="w", pady=4)
        ttk.Label(
            parent, text="Пусто — убрать план для категории.", foreground="gray"
        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(0, 4))

        parent.columnconfigure(1, weight=1)
        combo.bind("<<ComboboxSelected>>", lambda _e: self._on_category())
        self.after(50, self.amount_entry.focus_set)

    def _on_category(self) -> None:
        match = next((c for c in self._categories if c.name == self.category_var.get()), None)
        if match is not None:
            self.plan_var.set(_amount_text(match.monthly_limit))

    def on_ok(self) -> None:
        name = self.category_var.get()
        match = next((c for c in self._categories if c.name == name), None)
        if match is None:
            self.show_error("Выберите категорию")
            return
        try:
            plan = parse_optional_amount(self.plan_var.get())
        except ValidationError as exc:
            self.show_error(str(exc))
            return
        self.result = (match, plan)
        self.destroy()
