"""Диалоги работы с транзакциями."""
from __future__ import annotations

import tkinter as tk
from datetime import date
from tkinter import ttk

from ..models import (
    EXPENSE,
    INCOME,
    INVEST,
    KIND_LABELS,
    Category,
    Transaction,
    ValidationError,
    format_amount,
    format_date,
    parse_amount,
    parse_date,
)
from .widgets import FormDialog


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
        ttk.Radiobutton(
            kinds, text=KIND_LABELS[INVEST], value=INVEST, variable=self.kind_var,
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
