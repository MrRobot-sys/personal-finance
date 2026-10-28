"""Диалоги работы с инвестициями."""
from __future__ import annotations

import tkinter as tk
from datetime import date
from tkinter import ttk

from ....models import (
    PAYOUT_KINDS,
    PAYOUT_KIND_LABELS,
    PAYOUT_EXPECTED,
    PAYOUT_RECEIVED,
    PAYOUT_STATUS_LABELS,
    PERIODS,
    PERIOD_LABELS,
    ValidationError,
    format_date,
    parse_amount,
    parse_date,
    parse_optional_number,
)
from ...widgets import FormDialog
from ..common import _amount_text, _asset_choices


class PayoutDialog(FormDialog):
    """Плановая или полученная выплата по активу."""

    def __init__(self, parent, assets, payout=None, default_asset_id=None):
        self._assets = list(assets)
        self._payout = payout
        self._default_asset_id = default_asset_id
        title = "Редактировать выплату" if payout else "Новая выплата"
        super().__init__(parent, title, confirm_text="Сохранить")

    def build_body(self, parent) -> None:
        p = self._payout
        labels, mapping = _asset_choices(self._assets)
        self._mapping = mapping
        current_label = ""
        target_id = p.asset_id if p else self._default_asset_id
        for label, asset in mapping.items():
            if asset.id == target_id:
                current_label = label
                break
        if not current_label and labels:
            current_label = labels[0]

        self.asset_var = tk.StringVar(value=current_label)
        kind = p.kind if p else PAYOUT_KINDS[0]
        self.kind_var = tk.StringVar(value=PAYOUT_KIND_LABELS[kind])
        self.date_var = tk.StringVar(
            value=format_date(p.pay_date) if p else format_date(date.today())
        )
        self.rate_var = tk.StringVar(
            value=_amount_text(p.rate) if p and p.rate is not None else ""
        )
        self.amount_var = tk.StringVar(
            value=_amount_text(p.amount) if p and p.amount is not None else ""
        )
        self.status_var = tk.StringVar(
            value=p.status if p else PAYOUT_EXPECTED
        )
        self.received_var = tk.StringVar(
            value=format_date(p.received_date) if p and p.received_date
            else format_date(date.today())
        )
        self.note_var = tk.StringVar(value=p.note if p else "")

        ttk.Label(parent, text="Актив:").grid(row=0, column=0, sticky="w", pady=4)
        self.asset_combo = ttk.Combobox(
            parent, textvariable=self.asset_var, values=labels,
            state="readonly", width=33,
        )
        self.asset_combo.grid(row=0, column=1, columnspan=2, sticky="ew", pady=4)

        ttk.Label(parent, text="Тип:").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Combobox(
            parent, textvariable=self.kind_var,
            values=[PAYOUT_KIND_LABELS[k] for k in PAYOUT_KINDS],
            state="readonly", width=16,
        ).grid(row=1, column=1, sticky="w", pady=4)

        ttk.Label(parent, text="Дата выплаты:").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.date_var, width=14).grid(
            row=2, column=1, sticky="w", pady=4
        )

        ttk.Label(parent, text="Ставка на единицу:").grid(
            row=3, column=0, sticky="w", pady=4
        )
        ttk.Entry(parent, textvariable=self.rate_var, width=16).grid(
            row=3, column=1, sticky="w", pady=4
        )
        ttk.Label(
            parent, text="напр. дивиденд/купон на акцию", foreground="gray"
        ).grid(row=3, column=2, sticky="w", padx=(8, 0))

        ttk.Label(parent, text="Сумма:").grid(row=4, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.amount_var, width=16).grid(
            row=4, column=1, sticky="w", pady=4
        )
        ttk.Label(
            parent,
            text="ожидаемая (если нет ставки) или фактически полученная",
            foreground="gray",
        ).grid(row=4, column=2, sticky="w", padx=(8, 0))

        ttk.Label(parent, text="Статус:").grid(row=5, column=0, sticky="w", pady=4)
        statuses = ttk.Frame(parent)
        statuses.grid(row=5, column=1, columnspan=2, sticky="w", pady=4)
        ttk.Radiobutton(
            statuses, text=PAYOUT_STATUS_LABELS[PAYOUT_EXPECTED],
            value=PAYOUT_EXPECTED, variable=self.status_var,
            command=self._sync_status,
        ).pack(side="left")
        ttk.Radiobutton(
            statuses, text=PAYOUT_STATUS_LABELS[PAYOUT_RECEIVED],
            value=PAYOUT_RECEIVED, variable=self.status_var,
            command=self._sync_status,
        ).pack(side="left", padx=(12, 0))

        ttk.Label(parent, text="Дата получения:").grid(
            row=6, column=0, sticky="w", pady=4
        )
        self.received_entry = ttk.Entry(
            parent, textvariable=self.received_var, width=14
        )
        self.received_entry.grid(row=6, column=1, sticky="w", pady=4)

        ttk.Label(parent, text="Заметка:").grid(row=7, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.note_var, width=33).grid(
            row=7, column=1, columnspan=2, sticky="ew", pady=4
        )

        parent.columnconfigure(1, weight=1)
        self._sync_status()

    def _sync_status(self) -> None:
        received = self.status_var.get() == PAYOUT_RECEIVED
        self.received_entry.configure(state="normal" if received else "disabled")

    def on_ok(self) -> None:
        asset = self._mapping.get(self.asset_var.get())
        if asset is None:
            self.show_error("Выберите актив")
            return
        try:
            pay_date = parse_date(self.date_var.get())
            rate = parse_optional_number(self.rate_var.get())
            amount = parse_optional_number(self.amount_var.get())
        except ValidationError as exc:
            self.show_error(str(exc))
            return
        status = self.status_var.get()
        received_date = None
        if status == PAYOUT_RECEIVED:
            if amount is None:
                self.show_error("Укажите полученную сумму")
                return
            try:
                received_date = parse_date(self.received_var.get())
            except ValidationError as exc:
                self.show_error(str(exc))
                return
        elif rate is None and amount is None:
            self.show_error("Укажите ставку на единицу или ожидаемую сумму")
            return
        kind = next(
            (k for k, label in PAYOUT_KIND_LABELS.items() if label == self.kind_var.get()),
            PAYOUT_KINDS[0],
        )
        self.result = {
            "asset_id": asset.id,
            "kind": kind,
            "date": pay_date,
            "rate": rate,
            "amount": amount,
            "status": status,
            "received_date": received_date,
            "note": self.note_var.get().strip(),
        }
        self.destroy()


class PayoutRuleDialog(FormDialog):
    """Правило повторяющихся выплат (дивиденды/купоны)."""

    def __init__(self, parent, assets, rule=None, default_asset_id=None):
        self._assets = list(assets)
        self._rule = rule
        self._default_asset_id = default_asset_id
        super().__init__(parent, "Правило выплат", confirm_text="Сохранить")

    def build_body(self, parent) -> None:
        r = self._rule
        labels, mapping = _asset_choices(self._assets)
        self._mapping = mapping
        current_label = ""
        target_id = r.asset_id if r else self._default_asset_id
        for label, asset in mapping.items():
            if asset.id == target_id:
                current_label = label
                break
        if not current_label and labels:
            current_label = labels[0]

        self.asset_var = tk.StringVar(value=current_label)
        kind = r.kind if r else PAYOUT_KINDS[0]
        self.kind_var = tk.StringVar(value=PAYOUT_KIND_LABELS[kind])
        self.rate_var = tk.StringVar(
            value=_amount_text(r.rate) if r else ""
        )
        period = r.period if r else PERIODS[1]
        self.period_var = tk.StringVar(value=PERIOD_LABELS[period])
        self.anchor_var = tk.StringVar(
            value=format_date(r.anchor) if r else format_date(date.today())
        )
        self.note_var = tk.StringVar(value=r.note if r else "")

        ttk.Label(parent, text="Актив:").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Combobox(
            parent, textvariable=self.asset_var, values=labels,
            state="readonly", width=33,
        ).grid(row=0, column=1, columnspan=2, sticky="ew", pady=4)

        ttk.Label(parent, text="Тип:").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Combobox(
            parent, textvariable=self.kind_var,
            values=[PAYOUT_KIND_LABELS[k] for k in PAYOUT_KINDS],
            state="readonly", width=16,
        ).grid(row=1, column=1, sticky="w", pady=4)

        ttk.Label(parent, text="Ставка на единицу:").grid(
            row=2, column=0, sticky="w", pady=4
        )
        ttk.Entry(parent, textvariable=self.rate_var, width=16).grid(
            row=2, column=1, sticky="w", pady=4
        )

        ttk.Label(parent, text="Периодичность:").grid(
            row=3, column=0, sticky="w", pady=4
        )
        ttk.Combobox(
            parent, textvariable=self.period_var,
            values=[PERIOD_LABELS[p] for p in PERIODS],
            state="readonly", width=16,
        ).grid(row=3, column=1, sticky="w", pady=4)

        ttk.Label(parent, text="Первая дата:").grid(row=4, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.anchor_var, width=14).grid(
            row=4, column=1, sticky="w", pady=4
        )

        ttk.Label(parent, text="Заметка:").grid(row=5, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.note_var, width=33).grid(
            row=5, column=1, columnspan=2, sticky="ew", pady=4
        )

        parent.columnconfigure(1, weight=1)

    def on_ok(self) -> None:
        asset = self._mapping.get(self.asset_var.get())
        if asset is None:
            self.show_error("Выберите актив")
            return
        try:
            rate = parse_amount(self.rate_var.get())
            anchor = parse_date(self.anchor_var.get())
        except ValidationError as exc:
            self.show_error(str(exc))
            return
        kind = next(
            (k for k, label in PAYOUT_KIND_LABELS.items() if label == self.kind_var.get()),
            PAYOUT_KINDS[0],
        )
        period = next(
            (p for p, label in PERIOD_LABELS.items() if label == self.period_var.get()),
            PERIODS[1],
        )
        self.result = {
            "asset_id": asset.id,
            "kind": kind,
            "rate": rate,
            "period": period,
            "anchor": anchor,
            "note": self.note_var.get().strip(),
        }
        self.destroy()


class ReceivePayoutsDialog(FormDialog):
    """Отметить прошедшие выплаты полученными с фактическими суммами."""

    def __init__(self, parent, entries):
        self._entries = list(entries)
        super().__init__(parent, "Получить выплаты", confirm_text="Отметить полученными")

    def build_body(self, parent) -> None:
        ttk.Label(
            parent,
            text="Проверьте фактически полученные суммы по каждой выплате.",
            style="Muted.TLabel",
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 8))

        self._amount_vars: list[tk.StringVar] = []
        for index, entry in enumerate(self._entries, start=1):
            amount = entry.expected_at_date
            if amount <= 0 and entry.expected > 0:
                amount = entry.expected
            ttk.Label(
                parent,
                text=(
                    f"{entry.asset_name} · "
                    f"{PAYOUT_KIND_LABELS[entry.kind]} · "
                    f"{format_date(entry.date)}"
                ),
            ).grid(row=index, column=0, sticky="w", pady=4)
            var = tk.StringVar(value=_amount_text(amount))
            ttk.Entry(parent, textvariable=var, width=14).grid(
                row=index, column=1, sticky="w", pady=4
            )
            ttk.Label(parent, text=entry.currency, style="Muted.TLabel").grid(
                row=index, column=2, sticky="w", padx=(6, 0)
            )
            self._amount_vars.append(var)

        row = len(self._entries) + 1
        ttk.Label(parent, text="Дата получения:").grid(
            row=row, column=0, sticky="w", pady=(10, 4)
        )
        self.received_var = tk.StringVar(
            value=format_date(self._entries[0].date) if self._entries
            else format_date(date.today())
        )
        ttk.Entry(parent, textvariable=self.received_var, width=14).grid(
            row=row, column=1, sticky="w", pady=(10, 4)
        )
        parent.columnconfigure(0, weight=1)

    def on_ok(self) -> None:
        try:
            received_date = parse_date(self.received_var.get())
        except ValidationError as exc:
            self.show_error(str(exc))
            return
        items = []
        for entry, var in zip(self._entries, self._amount_vars):
            try:
                amount = parse_optional_number(var.get())
            except ValidationError as exc:
                self.show_error(f"{entry.asset_name}: {exc}")
                return
            if amount is None:
                self.show_error(f"{entry.asset_name}: укажите сумму")
                return
            items.append((entry, amount))
        self.result = {"items": items, "received_date": received_date}
        self.destroy()
