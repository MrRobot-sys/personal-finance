"""Диалоги работы с инвестициями."""
from __future__ import annotations

import tkinter as tk
from datetime import date
from tkinter import ttk

from ....models import (
    TRADE_LABELS,
    ValidationError,
    format_currency_amount,
    format_date,
    format_quantity,
    parse_amount,
    parse_optional_number,
)
from ...widgets import FormDialog
from ..common import _amount_text


class TradeDialog(FormDialog):
    """Сделка купли/продажи по выбранному активу."""

    def __init__(self, parent, asset, kind: str):
        self._asset = asset
        self._kind = kind
        super().__init__(
            parent, f"{TRADE_LABELS[kind]}: {asset.name}", confirm_text="Сохранить"
        )

    def build_body(self, parent) -> None:
        asset = self._asset
        self.quantity_var = tk.StringVar(value="")
        self.price_var = tk.StringVar(
            value=_amount_text(asset.current_price) if asset.current_price else ""
        )
        self.date_var = tk.StringVar(value=format_date(date.today()))
        self.fee_var = tk.StringVar(value="")
        self.note_var = tk.StringVar(value="")

        holder = (
            f"В портфеле: {format_quantity(asset.quantity)} ед. · "
            f"средняя {format_currency_amount(asset.avg_price, asset.currency)}"
        )
        ttk.Label(parent, text=holder, style="Muted.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 6)
        )

        ttk.Label(parent, text="Количество:").grid(row=1, column=0, sticky="w", pady=4)
        self.quantity_entry = ttk.Entry(parent, textvariable=self.quantity_var, width=16)
        self.quantity_entry.grid(row=1, column=1, sticky="w", pady=4)

        ttk.Label(parent, text="Цена за единицу:").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.price_var, width=16).grid(
            row=2, column=1, sticky="w", pady=4
        )

        ttk.Label(parent, text="Дата:").grid(row=3, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.date_var, width=14).grid(
            row=3, column=1, sticky="w", pady=4
        )

        ttk.Label(parent, text="Комиссия:").grid(row=4, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.fee_var, width=16).grid(
            row=4, column=1, sticky="w", pady=4
        )

        ttk.Label(parent, text="Заметка:").grid(row=5, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.note_var, width=31).grid(
            row=5, column=1, columnspan=2, sticky="ew", pady=4
        )
        parent.columnconfigure(1, weight=1)
        self.after(50, self.quantity_entry.focus_set)

    def on_ok(self) -> None:
        try:
            quantity = parse_amount(self.quantity_var.get())
            price = parse_optional_number(self.price_var.get())
            trade_date = parse_date(self.date_var.get())
            fee = parse_optional_number(self.fee_var.get()) or 0.0
        except ValidationError as exc:
            self.show_error(str(exc))
            return
        if price is None:
            self.show_error("Укажите цену сделки")
            return
        self.result = {
            "quantity": quantity,
            "price": price,
            "trade_date": trade_date,
            "fee": fee,
            "note": self.note_var.get().strip(),
        }
        self.destroy()
