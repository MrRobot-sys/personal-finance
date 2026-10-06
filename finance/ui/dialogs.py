"""Модальные окна добавления и редактирования."""
from __future__ import annotations

import tkinter as tk
from datetime import date
from tkinter import ttk

from ..models import (
    EXPENSE,
    INCOME,
    KIND_LABELS,
    Category,
    Transaction,
    ValidationError,
    format_amount,
    format_date,
    parse_amount,
    parse_date,
    parse_optional_amount,
)
from .widgets import FormDialog


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
            types, text=KIND_LABELS[EXPENSE], value=EXPENSE, variable=self.kind_var
        ).pack(side="left")
        ttk.Radiobutton(
            types, text=KIND_LABELS[INCOME], value=INCOME, variable=self.kind_var
        ).pack(side="left", padx=(12, 0))

        ttk.Label(parent, text="План в месяц:").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.plan_var, width=16).grid(
            row=2, column=1, sticky="w", pady=4
        )
        ttk.Label(
            parent, text="Сколько обычно поступает/тратится в месяц.\nПусто — без плана.",
            foreground="gray", justify="left",
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(0, 4))

    def on_ok(self) -> None:
        name = self.name_var.get().strip()
        if not name:
            self.show_error("Введите название категории")
            return
        if len(name) > 60:
            self.show_error("Название слишком длинное (макс. 60)")
            return
        try:
            plan = parse_optional_amount(self.plan_var.get())
        except ValidationError as exc:
            self.show_error(str(exc))
            return
        self.result = (name, self.kind_var.get(), plan)
        self.destroy()


def _amount_text(value: float | None) -> str:
    if value is None:
        return ""
    return str(value).replace(".00", "").replace(".", ",")


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


class TransactionDialog(FormDialog):
    def __init__(
        self,
        parent,
        categories: list[Category],
        transaction: Transaction | None = None,
        default_kind: str = EXPENSE,
    ):
        self._categories = categories
        self._transaction = transaction
        self._default_kind = transaction.kind if transaction else default_kind
        title = "Редактировать операцию" if transaction else "Новая операция"
        super().__init__(parent, title, confirm_text="Сохранить")

    def build_body(self, parent) -> None:
        tr = self._transaction
        self.kind_var = tk.StringVar(value=self._default_kind)
        self.category_var = tk.StringVar()
        self.amount_var = tk.StringVar(
            value=format_amount(tr.amount).replace("\u00a0₽", "").strip()
            .replace("\u00a0", "").replace(" ", "") if tr else ""
        )
        self.date_var = tk.StringVar(value=format_date(tr.txn_date) if tr else format_date(date.today()))
        self.note_var = tk.StringVar(value=tr.note if tr else "")

        ttk.Label(parent, text="Тип:").grid(row=0, column=0, sticky="w", pady=4)
        kinds = ttk.Frame(parent)
        kinds.grid(row=0, column=1, columnspan=2, sticky="w", pady=4)
        ttk.Radiobutton(
            kinds, text=KIND_LABELS[EXPENSE], value=EXPENSE, variable=self.kind_var,
            command=self._sync_categories,
        ).pack(side="left")
        ttk.Radiobutton(
            kinds, text=KIND_LABELS[INCOME], value=INCOME, variable=self.kind_var,
            command=self._sync_categories,
        ).pack(side="left", padx=(12, 0))

        ttk.Label(parent, text="Категория:").grid(row=1, column=0, sticky="w", pady=4)
        self.category_combo = ttk.Combobox(
            parent, textvariable=self.category_var, state="readonly", width=31
        )
        self.category_combo.grid(row=1, column=1, columnspan=2, sticky="ew", pady=4)

        ttk.Label(parent, text="Сумма:").grid(row=2, column=0, sticky="w", pady=4)
        self.amount_entry = ttk.Entry(parent, textvariable=self.amount_var, width=16)
        self.amount_entry.grid(row=2, column=1, columnspan=2, sticky="w", pady=4)

        ttk.Label(parent, text="Дата:").grid(row=3, column=0, sticky="w", pady=4)
        date_frame = ttk.Frame(parent)
        date_frame.grid(row=3, column=1, columnspan=2, sticky="w", pady=4)
        ttk.Entry(date_frame, textvariable=self.date_var, width=14).pack(side="left")
        ttk.Button(
            date_frame, text="Сегодня",
            command=lambda: self.date_var.set(format_date(date.today())),
        ).pack(side="left", padx=(8, 0))

        ttk.Label(parent, text="Заметка:").grid(row=4, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.note_var, width=33).grid(
            row=4, column=1, columnspan=2, sticky="ew", pady=4
        )

        parent.columnconfigure(1, weight=1)
        self._sync_categories()

    def _sync_categories(self) -> None:
        kind = self.kind_var.get()
        names = [c.name for c in self._categories if c.kind == kind]
        self.category_combo.configure(values=names)
        current = self.category_var.get()
        if current not in names:
            self.category_var.set(names[0] if names else "")

    def on_ok(self) -> None:
        kind = self.kind_var.get()
        name = self.category_var.get()
        if not self._categories:
            self.show_error("Сначала создайте категории на вкладке «Категории»")
            return
        match = next((c for c in self._categories if c.name == name and c.kind == kind), None)
        if match is None:
            self.show_error("Выберите категорию")
            return
        amount_text = self.amount_var.get()
        date_text = self.date_var.get()
        try:
            from ..models import parse_amount, parse_date

            amount = parse_amount(amount_text)
            txn_date = parse_date(date_text)
        except ValidationError as exc:
            self.show_error(str(exc))
            return
        self.result = {
            "category_id": match.id,
            "amount": amount,
            "date": txn_date,
            "note": self.note_var.get().strip(),
        }
        self.destroy()
