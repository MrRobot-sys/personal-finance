"""Диалоги работы с инвестициями."""
from __future__ import annotations

import threading
import time
import tkinter as tk
from datetime import date
from tkinter import ttk

from ....models import (
    CURRENCIES,
    MARKET_LABELS,
    MARKETS,
    ONLINE_MARKETS,
    ValidationError,
    categories_for,
    format_date,
    parse_date,
    parse_optional_number,
)
from ...widgets import FormDialog, theme
from ..common import _amount_text, _cache_search, _get_search_cache


_SEARCH_CACHE = _get_search_cache()


class AssetDialog(FormDialog):
    """Создание/редактирование актива портфеля или объекта имущества."""

    def __init__(self, parent, asset=None, default_market="manual"):
        self._asset = asset
        self._start_market = asset.market if asset else default_market
        title = "Редактировать актив" if asset else "Новый актив"
        super().__init__(parent, title, confirm_text="Сохранить")

    def build_body(self, parent) -> None:
        a = self._asset
        self._alive = True
        self._search_after_id: str | None = None
        self._search_token = 0
        self._matches: list = []
        self._pending = None
        self._poll_after_id: str | None = None
        self._poll_deadline = 0.0
        self.bind("<Destroy>", self._on_destroy, add="+")
        self.market_var = tk.StringVar(value=MARKET_LABELS[self._start_market])
        self.name_var = tk.StringVar(value=a.name if a else "")
        self.ticker_var = tk.StringVar(value=a.ticker if a else "")
        self.currency_var = tk.StringVar(value=a.currency if a else "RUB")
        self.category_var = tk.StringVar(
            value=(
                a.category if a and a.category
                else categories_for(self._start_market)[0]
            )
        )
        self.details_var = tk.StringVar(value=a.details if a else "")
        self.depreciation_var = tk.StringVar(
            value=_amount_text(a.depreciation_rate) if a else ""
        )
        self.note_var = tk.StringVar(value=a.note if a else "")

        row = 0
        ttk.Label(parent, text="Тип:").grid(row=row, column=0, sticky="w", pady=4)
        self.market_combo = ttk.Combobox(
            parent, textvariable=self.market_var,
            values=[MARKET_LABELS[m] for m in MARKETS], state="readonly", width=31,
        )
        self.market_combo.grid(row=row, column=1, columnspan=2, sticky="ew", pady=4)
        self.market_combo.bind("<<ComboboxSelected>>", lambda _e: self._sync_fields())
        row += 1

        ttk.Label(parent, text="Название:").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.name_var, width=33).grid(
            row=row, column=1, columnspan=2, sticky="ew", pady=4
        )
        row += 1

        self.ticker_label = ttk.Label(parent, text="Тикер:")
        self.ticker_label.grid(row=row, column=0, sticky="w", pady=4)
        self.ticker_entry = ttk.Entry(parent, textvariable=self.ticker_var, width=16)
        self.ticker_entry.grid(row=row, column=1, sticky="w", pady=4)
        self.ticker_hint = ttk.Label(
            parent, text="напр. SBER, AAPL", foreground="gray"
        )
        self.ticker_hint.grid(row=row, column=2, sticky="w", padx=(8, 0))
        row += 1

        # Список подсказок бумаг: накладывается поверх формы под полем тикера,
        # поэтому не влияет на раскладку и не конфликтует с модальным захватом.
        self.suggest_list = tk.Listbox(
            parent, height=6, activestyle="none", exportselection=False,
            highlightthickness=1, highlightbackground=theme.BORDER,
            background=theme.CARD, foreground=theme.TEXT,
            selectbackground=theme.SELECT_BG, selectforeground=theme.SELECT_FG,
            font=theme.make_font(11),
        )
        self.suggest_list.bind("<Return>", self._choose_from_list)
        self.suggest_list.bind("<KP_Enter>", self._choose_from_list)
        self.suggest_list.bind("<ButtonRelease-1>", self._choose_from_list)
        self.suggest_list.bind("<Escape>", self._suggest_escape)
        self.suggest_list.bind("<Up>", self._suggest_up)
        self.suggest_list.bind("<FocusOut>", self._maybe_hide_suggestions)

        self.ticker_entry.bind("<KeyRelease>", self._on_ticker_key)
        self.ticker_entry.bind("<Down>", self._suggest_down)
        self.ticker_entry.bind("<Return>", self._on_ticker_submit)
        self.ticker_entry.bind("<FocusOut>", self._maybe_hide_suggestions)

        ttk.Label(parent, text="Валюта:").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Combobox(
            parent, textvariable=self.currency_var,
            values=list(CURRENCIES), state="readonly", width=8,
        ).grid(row=row, column=1, sticky="w", pady=4)
        row += 1

        self.category_label = ttk.Label(parent, text="Категория:")
        self.category_label.grid(row=row, column=0, sticky="w", pady=4)
        self.category_combo = ttk.Combobox(
            parent, textvariable=self.category_var,
            values=list(categories_for(self._start_market)),
            state="readonly", width=20,
        )
        self.category_combo.grid(row=row, column=1, sticky="w", pady=4)
        row += 1

        self.details_label = ttk.Label(parent, text="Детали:")
        self.details_label.grid(row=row, column=0, sticky="w", pady=4)
        self.details_entry = ttk.Entry(parent, textvariable=self.details_var, width=33)
        self.details_entry.grid(row=row, column=1, columnspan=2, sticky="ew", pady=4)
        row += 1
        self.details_hint = ttk.Label(
            parent, text="адрес, серийный номер, состояние",
            foreground="gray",
        )
        self.details_hint.grid(row=row, column=1, columnspan=2, sticky="w", pady=(0, 4))
        row += 1

        self.depreciation_label = ttk.Label(parent, text="Износ, %/год:")
        self.depreciation_label.grid(row=row, column=0, sticky="w", pady=4)
        self.depreciation_entry = ttk.Entry(
            parent, textvariable=self.depreciation_var, width=10
        )
        self.depreciation_entry.grid(row=row, column=1, sticky="w", pady=4)
        row += 1

        ttk.Label(parent, text="Заметка:").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.note_var, width=33).grid(
            row=row, column=1, columnspan=2, sticky="ew", pady=4
        )
        row += 1

        if a is None:
            ttk.Separator(parent, orient="horizontal").grid(
                row=row, column=0, columnspan=3, sticky="ew", pady=8
            )
            row += 1
            ttk.Label(
                parent, text="Начальная покупка", style="CardTitle.TLabel"
            ).grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 4))
            row += 1

            self.quantity_var = tk.StringVar(value="")
            self.price_var = tk.StringVar(value="")
            self.buy_date_var = tk.StringVar(value=format_date(date.today()))
            self.fee_var = tk.StringVar(value="")

            ttk.Label(parent, text="Количество:").grid(
                row=row, column=0, sticky="w", pady=4
            )
            ttk.Entry(parent, textvariable=self.quantity_var, width=16).grid(
                row=row, column=1, columnspan=2, sticky="w", pady=4
            )
            row += 1
            ttk.Label(parent, text="Цена покупки:").grid(
                row=row, column=0, sticky="w", pady=4
            )
            ttk.Entry(parent, textvariable=self.price_var, width=16).grid(
                row=row, column=1, columnspan=2, sticky="w", pady=4
            )
            row += 1
            ttk.Label(parent, text="Дата покупки:").grid(
                row=row, column=0, sticky="w", pady=4
            )
            ttk.Entry(parent, textvariable=self.buy_date_var, width=14).grid(
                row=row, column=1, sticky="w", pady=4
            )
            row += 1
            ttk.Label(parent, text="Комиссия:").grid(
                row=row, column=0, sticky="w", pady=4
            )
            ttk.Entry(parent, textvariable=self.fee_var, width=16).grid(
                row=row, column=1, columnspan=2, sticky="w", pady=4
            )
            row += 1
            ttk.Label(
                parent,
                text="Пустое количество — актив без позиции (сделки добавите позже).",
                foreground="gray",
            ).grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 4))

        parent.columnconfigure(1, weight=1)
        self._sync_fields(initial=True)

    def _market_key(self) -> str:
        label = self.market_var.get()
        for key, name in MARKET_LABELS.items():
            if name == label:
                return key
        return "manual"

    def _sync_fields(self, initial: bool = False) -> None:
        market = self._market_key()
        online = market in ONLINE_MARKETS
        physical = market == "physical"
        self.ticker_entry.configure(state="normal" if online else "disabled")
        self.ticker_hint.configure(
            text="начните вводить — подскажем" if online else "только для MOEX/США"
        )

        options = list(categories_for(market))
        if self.category_var.get() not in options:
            self.category_var.set(options[0] if options else "")
        self.category_combo.configure(values=options)

        self.details_entry.configure(state="normal" if physical else "disabled")
        self.depreciation_entry.configure(state="normal" if physical else "disabled")

        if not initial and online and len(self.ticker_var.get().strip()) >= 2:
            self._schedule_search()
        else:
            self._hide_suggestions()

    def _on_ticker_key(self, event) -> None:
        if event.keysym in (
            "Up", "Down", "Left", "Right", "Tab", "Return", "KP_Enter",
            "Escape", "Shift_L", "Shift_R", "Control_L", "Control_R",
            "Alt_L", "Alt_R", "Meta_L", "Meta_R", "Caps_Lock",
        ):
            return
        self._schedule_search()

    def _schedule_search(self) -> None:
        if not self._alive:
            return
        if self._search_after_id is not None:
            try:
                self.after_cancel(self._search_after_id)
            except tk.TclError:
                pass
            self._search_after_id = None
        market = self._market_key()
        if market not in ONLINE_MARKETS:
            self._hide_suggestions()
            return
        query = self.ticker_var.get().strip()
        if len(query) < 2:
            self._hide_suggestions()
            return
        self._search_after_id = self.after(
            350, lambda: self._run_search(market, query)
        )

    def _run_search(self, market: str, query: str) -> None:
        self._search_after_id = None
        if not self._alive:
            return
        key = (market, query.lower())
        self._search_token += 1
        token = self._search_token
        cached = _SEARCH_CACHE.get(key)
        if cached is not None:
            self._matches = list(cached)
            self._show_suggestions()
            return

        from .... import quotes

        self._pending = None

        def worker() -> None:
            try:
                result = quotes.search_securities(market, query)
            except Exception:
                result = []
            self._pending = (token, key, result)

        threading.Thread(target=worker, daemon=True).start()
        self._poll_deadline = time.monotonic() + 10.0
        self._poll_results()

    def _poll_results(self) -> None:
        self._poll_after_id = None
        if not self._alive:
            return
        pending = self._pending
        if pending is not None:
            self._pending = None
            token, key, matches = pending
            if token == self._search_token:
                _cache_search(key, matches)
                self._matches = list(matches)
                self._show_suggestions()
            return
        if time.monotonic() < self._poll_deadline:
            self._poll_after_id = self.after(50, self._poll_results)

    def _show_suggestions(self) -> None:
        if not self._matches:
            self._hide_suggestions()
            return
        self.suggest_list.delete(0, tk.END)
        for match in self._matches:
            self.suggest_list.insert(tk.END, match.label)
        self.suggest_list.configure(height=min(len(self._matches), 6))
        entry = self.ticker_entry
        self.update_idletasks()
        width = max(entry.winfo_width(), 300)
        width = min(width, max(self.body.winfo_width() - entry.winfo_x(), 200))
        self.suggest_list.place(
            in_=entry, x=0, y=entry.winfo_height(), width=width,
        )
        self.suggest_list.lift()

    def _hide_suggestions(self) -> None:
        try:
            self.suggest_list.place_forget()
        except tk.TclError:
            pass

    def _choose_suggestion(self, index: int) -> None:
        if index < 0 or index >= len(self._matches):
            return
        match = self._matches[index]
        self.ticker_var.set(match.ticker)
        self.name_var.set(match.name)
        self.currency_var.set(match.currency)
        options = list(categories_for(self._market_key()))
        if match.category in options:
            self.category_var.set(match.category)
        self._matches = []
        self._hide_suggestions()
        self.ticker_entry.focus_set()

    def _choose_from_list(self, event=None):
        selection = self.suggest_list.curselection()
        index = int(selection[0]) if selection else -1
        if index < 0 and event is not None and hasattr(event, "y"):
            index = self.suggest_list.nearest(event.y)
        if index < 0 and self._matches:
            index = 0
        if index >= 0:
            self._choose_suggestion(index)
        return "break"

    def _suggest_down(self, _event=None):
        if self.suggest_list.winfo_ismapped() and self._matches:
            self.suggest_list.focus_set()
            self.suggest_list.selection_clear(0, tk.END)
            self.suggest_list.selection_set(0)
            self.suggest_list.activate(0)
            return "break"
        return None

    def _suggest_up(self, _event=None):
        selection = self.suggest_list.curselection()
        if selection and int(selection[0]) <= 0:
            self.ticker_entry.focus_set()
            return "break"
        return None

    def _suggest_escape(self, _event=None):
        self._hide_suggestions()
        return "break"

    def _on_ticker_submit(self, _event=None):
        if self.suggest_list.winfo_ismapped() and self._matches:
            selection = self.suggest_list.curselection()
            index = int(selection[0]) if selection else 0
            self._choose_suggestion(index)
            return "break"
        return None

    def _maybe_hide_suggestions(self, _event=None) -> None:
        if not self._alive:
            return
        self.after(120, self._hide_if_unfocused)

    def _hide_if_unfocused(self) -> None:
        if not self._alive:
            return
        if self.focus_get() is self.suggest_list:
            return
        pointer = self.winfo_containing(
            self.winfo_pointerx(), self.winfo_pointery()
        )
        if pointer is self.suggest_list:
            return
        self._hide_suggestions()

    def _on_destroy(self, event) -> None:
        if event.widget is not self:
            return
        self._alive = False
        for attr in ("_search_after_id", "_poll_after_id"):
            after_id = getattr(self, attr, None)
            if after_id is not None:
                try:
                    self.after_cancel(after_id)
                except tk.TclError:
                    pass
                setattr(self, attr, None)

    def on_ok(self) -> None:
        market = self._market_key()
        name = self.name_var.get().strip()
        ticker = self.ticker_var.get().strip().upper()
        if not name:
            self.show_error("Введите название актива")
            return
        if market in ONLINE_MARKETS and not ticker:
            self.show_error("Для биржевого актива укажите тикер")
            return
        physical = market == "physical"
        try:
            depreciation = (
                parse_optional_number(self.depreciation_var.get()) if physical else None
            )
        except ValidationError as exc:
            self.show_error(str(exc))
            return
        result = {
            "name": name,
            "market": market,
            "ticker": ticker if market in ONLINE_MARKETS else "",
            "currency": self.currency_var.get(),
            "category": self.category_var.get().strip(),
            "details": self.details_var.get().strip() if physical else "",
            "depreciation_rate": depreciation,
            "note": self.note_var.get().strip(),
        }
        if self._asset is None:
            try:
                quantity = parse_optional_number(self.quantity_var.get()) or 0.0
                price = parse_optional_number(self.price_var.get())
                buy_date = parse_date(self.buy_date_var.get())
                fee = parse_optional_number(self.fee_var.get()) or 0.0
            except ValidationError as exc:
                self.show_error(str(exc))
                return
            if quantity and price is None:
                self.show_error("Укажите цену покупки")
                return
            result.update({
                "quantity": quantity, "price": price or 0.0,
                "trade_date": buy_date, "fee": fee,
            })
        self.result = result
        self.destroy()


class ManualPriceDialog(FormDialog):
    """Ручная оценка актива (для имущества и «вручную»)."""

    def __init__(self, parent, asset):
        self._asset = asset
        super().__init__(parent, f"Оценка: {asset.name}", confirm_text="Сохранить")

    def build_body(self, parent) -> None:
        asset = self._asset
        self.price_var = tk.StringVar(
            value=_amount_text(asset.current_price) if asset.current_price else ""
        )
        self.date_var = tk.StringVar(value=format_date(date.today()))

        ttk.Label(
            parent,
            text="Текущая оценочная стоимость за единицу.",
            style="Muted.TLabel",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))

        ttk.Label(parent, text="Оценка:").grid(row=1, column=0, sticky="w", pady=4)
        entry = ttk.Entry(parent, textvariable=self.price_var, width=16)
        entry.grid(row=1, column=1, sticky="w", pady=4)

        ttk.Label(parent, text="Дата оценки:").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.date_var, width=14).grid(
            row=2, column=1, sticky="w", pady=4
        )
        parent.columnconfigure(1, weight=1)
        self.after(50, entry.focus_set)

    def on_ok(self) -> None:
        try:
            price = parse_optional_number(self.price_var.get())
            on_date = parse_date(self.date_var.get())
        except ValidationError as exc:
            self.show_error(str(exc))
            return
        if price is None:
            self.show_error("Укажите оценку")
            return
        self.result = {"price": price, "date": on_date}
        self.destroy()
