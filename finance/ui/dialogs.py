"""Модальные окна добавления и редактирования."""
from __future__ import annotations

import threading
import time
import tkinter as tk
from datetime import date
from tkinter import ttk

from ..models import (
    EXPENSE,
    INCOME,
    INVEST,
    KIND_LABELS,
    MARKET_LABELS,
    MARKETS,
    ONLINE_MARKETS,
    PAYOUT_KINDS,
    PAYOUT_KIND_LABELS,
    PAYOUT_EXPECTED,
    PAYOUT_RECEIVED,
    PAYOUT_STATUS_LABELS,
    PERIODS,
    PERIOD_LABELS,
    categories_for,
    CURRENCIES,
    TRADE_LABELS,
    Category,
    Transaction,
    ValidationError,
    format_amount,
    format_currency_amount,
    format_date,
    format_quantity,
    parse_amount,
    parse_date,
    parse_optional_amount,
    parse_optional_number,
)
from .widgets import FormDialog
from . import theme
from ..services import (
    DEFAULT_PAYOUT_HOURS,
    DEFAULT_PRICE_MINUTES,
    MIN_PAYOUT_HOURS,
    MIN_PRICE_MINUTES,
    AutoRefreshSettings,
)


# Кэш результатов поиска бумаг на время работы окна: (market, query) -> matches.
_SEARCH_CACHE: dict[tuple[str, str], list] = {}
_SEARCH_CACHE_LIMIT = 64


def _cache_search(key: tuple[str, str], matches: list) -> None:
    if key in _SEARCH_CACHE:
        return
    if len(_SEARCH_CACHE) >= _SEARCH_CACHE_LIMIT:
        _SEARCH_CACHE.pop(next(iter(_SEARCH_CACHE)))
    _SEARCH_CACHE[key] = matches


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

        # Список категорий зависит от типа актива. Если текущая категория
        # не подходит новому типу — сбрасываем на первую подходящую.
        options = list(categories_for(market))
        if self.category_var.get() not in options:
            self.category_var.set(options[0] if options else "")
        self.category_combo.configure(values=options)

        self.details_entry.configure(state="normal" if physical else "disabled")
        self.depreciation_entry.configure(state="normal" if physical else "disabled")

        # Подсказки ищем только по действию пользователя, не при открытии окна.
        if not initial and online and len(self.ticker_var.get().strip()) >= 2:
            self._schedule_search()
        else:
            self._hide_suggestions()

    # --- поиск бумаг (подсказки при вводе тикера) ---

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

        from .. import quotes

        self._pending = None

        def worker() -> None:
            # Только сетевая работа; результат кладём в поле, а Tk трогаем
            # исключительно из главного потока (см. _poll_results).
            try:
                result = quotes.search_securities(market, query)
            except Exception:  # сеть недоступна — просто без подсказок
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
        # Привязываем список к полю тикера: place(in_=...) не зависит от того,
        # как пересчиталась раскладка формы.
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


def _asset_choices(assets) -> tuple[list[str], dict[str, object]]:
    labels: list[str] = []
    mapping: dict[str, object] = {}
    seen: dict[str, int] = {}
    for asset in assets:
        base = asset.ticker or asset.name
        label = f"{asset.name} ({base})" if asset.ticker else asset.name
        count = seen.get(label, 0)
        seen[label] = count + 1
        if count:
            label = f"{label} #{count + 1}"
        labels.append(label)
        mapping[label] = asset
    return labels, mapping


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


class SettingsDialog(FormDialog):
    """Настройки автообновления цен и автопоиска выплат."""

    def __init__(self, parent, settings: AutoRefreshSettings):
        self._settings = settings
        super().__init__(parent, "Настройки", confirm_text="Сохранить")

    def build_body(self, parent) -> None:
        s = self._settings
        self.price_enabled_var = tk.BooleanVar(value=s.price_enabled)
        self.price_minutes_var = tk.StringVar(value=str(s.price_minutes))
        self.payout_enabled_var = tk.BooleanVar(value=s.payout_enabled)
        self.payout_hours_var = tk.StringVar(value=str(s.payout_hours))

        ttk.Checkbutton(
            parent, text="Автообновление цен", variable=self.price_enabled_var
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))

        ttk.Label(parent, text="Интервал, минут:").grid(
            row=1, column=0, sticky="w", pady=4, padx=(18, 0)
        )
        price_entry = ttk.Entry(parent, textvariable=self.price_minutes_var, width=8)
        price_entry.grid(row=1, column=1, sticky="w", pady=4)
        ttk.Label(
            parent, text=f"не менее {MIN_PRICE_MINUTES}", style="Muted.TLabel"
        ).grid(row=1, column=2, sticky="w", padx=(8, 0))

        ttk.Checkbutton(
            parent, text="Автопоиск выплат", variable=self.payout_enabled_var
        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(12, 4))

        ttk.Label(parent, text="Интервал, часов:").grid(
            row=3, column=0, sticky="w", pady=4, padx=(18, 0)
        )
        ttk.Entry(parent, textvariable=self.payout_hours_var, width=8).grid(
            row=3, column=1, sticky="w", pady=4
        )
        ttk.Label(
            parent, text=f"не менее {MIN_PAYOUT_HOURS}", style="Muted.TLabel"
        ).grid(row=3, column=2, sticky="w", padx=(8, 0))

        ttk.Label(
            parent,
            text="При отсутствии сети обновление просто пропускается.",
            style="Muted.TLabel",
        ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(12, 0))
        parent.columnconfigure(1, weight=1)

    def on_ok(self) -> None:
        try:
            minutes = int(self.price_minutes_var.get().strip())
            hours = int(self.payout_hours_var.get().strip())
        except ValueError:
            self.show_error("Интервалы должны быть целыми числами")
            return
        if minutes < MIN_PRICE_MINUTES:
            self.show_error(f"Интервал цен — не менее {MIN_PRICE_MINUTES} мин")
            return
        if hours < MIN_PAYOUT_HOURS:
            self.show_error(f"Интервал выплат — не менее {MIN_PAYOUT_HOURS} ч")
            return
        self.result = AutoRefreshSettings(
            price_enabled=bool(self.price_enabled_var.get()),
            price_minutes=minutes,
            payout_enabled=bool(self.payout_enabled_var.get()),
            payout_hours=hours,
        )
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
