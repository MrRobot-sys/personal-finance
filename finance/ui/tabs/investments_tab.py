"""Вкладка «Инвестиции»: портфель активов, имущество, сделки и календарь выплат.

Вкладка состоит из двух подразделов: «Портфель» (активы, имущество, сделки,
график, пул «внесено/вложено/свободно») и «Календарь выплат» (дивиденды и
купоны: план, факт и онлайн-прогноз).

Биржевые активы (MOEX/США) обновляются онлайн, имущество и ручные активы —
только ручной оценкой. Сеть опциональна: при её отсутствии используются
сохранённые оценки, и вкладка продолжает работать.
"""
from __future__ import annotations

import calendar
import threading
import tkinter as tk
from datetime import date, datetime
from tkinter import messagebox, ttk

from ...models import (
    BUY,
    MARKET_LABELS,
    MARKET_MANUAL,
    MARKET_PHYSICAL,
    ONLINE_MARKETS,
    PAYOUT_EXPECTED,
    PAYOUT_KIND_LABELS,
    PAYOUT_RECEIVED,
    PAYOUT_STATUS_LABELS,
    SCOPE_LABELS,
    SCOPE_PROPERTY,
    SCOPE_SECURITIES,
    SELL,
    TRADE_LABELS,
    ValidationError,
    format_amount,
    format_currency_amount,
    format_date,
    format_quantity,
)
from ..widgets import theme
from ...services import PAYOUTS_SYNCED_KEY, PRICES_UPDATED_KEY
from ..dialogs import (
    AssetDialog,
    ManualPriceDialog,
    PayoutDialog,
    PayoutRuleDialog,
    ReceivePayoutsDialog,
    TradeDialog,
)
from ..widgets import CanvasTooltip, TreeTable, make_card, row, run_dialog

SCOPE_CHOICES = (
    (SCOPE_LABELS[None], None),
    (SCOPE_LABELS[SCOPE_SECURITIES], SCOPE_SECURITIES),
    (SCOPE_LABELS[SCOPE_PROPERTY], SCOPE_PROPERTY),
)
GRAPH_ACCENT = theme.ACCENT
WEEKDAYS = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
MONTH_NAMES_SHORT = (
    "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
)
PAYOUT_COLORS = {
    "dividend": theme.SUCCESS,
    "coupon": theme.ACCENT,
    "other": theme.MUTED,
}


def _short_money(value: float) -> str:
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.1f} млн".replace(".", ",")
    if abs(value) >= 1_000:
        return f"{value / 1_000:.0f} тыс"
    return f"{value:.0f}"


def _date_text(stamp: str) -> str:
    if not stamp:
        return "—"
    try:
        return format_date(date.fromisoformat(stamp[:10]))
    except ValueError:
        return stamp[:10]


class PortfolioView(ttk.Frame):
    def __init__(self, master, service, on_change):
        super().__init__(master, padding=12)
        self.service = service
        self.on_change = on_change
        self._selected_id: int | None = None
        self._graph: list[tuple[date, float]] = []
        self._graph_tips: dict[int, str] = {}
        self._status = tk.StringVar(value="")
        self._refreshing = False
        self.rowconfigure(2, weight=3)
        self.rowconfigure(3, weight=2)
        self.columnconfigure(0, weight=1)
        self._build_toolbar()
        self._build_summary()
        self._build_table()
        self._build_bottom()
        self.graph_tip = CanvasTooltip(self.graph_canvas, self._graph_tip_for)

    # --- построение ---

    def _build_toolbar(self) -> None:
        outer, card = make_card(self, padding=(14, 10))
        outer.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        bar = ttk.Frame(card)
        bar.pack(fill="x")

        ttk.Label(bar, text="Показывать:").pack(side="left")
        self.scope_combo = ttk.Combobox(
            bar, values=[label for label, _ in SCOPE_CHOICES],
            state="readonly", width=13,
        )
        self.scope_combo.set(SCOPE_CHOICES[0][0])
        self.scope_combo.pack(side="left", padx=8)
        self.scope_combo.bind("<<ComboboxSelected>>", lambda _e: self._render())

        ttk.Button(
            bar, text="Добавить", style="Accent.TButton", command=self._add
        ).pack(side="left", padx=(12, 0))

        self.refresh_btn = ttk.Button(
            bar, text="Обновить цены", command=self._refresh_prices
        )
        self.refresh_btn.pack(side="right")
        ttk.Button(bar, text="Оценить…", command=self._manual_price).pack(
            side="right", padx=(0, 8)
        )
        ttk.Button(bar, text="Удалить", command=self._delete).pack(
            side="right", padx=(0, 8)
        )
        ttk.Button(bar, text="Изменить", command=self._edit).pack(
            side="right", padx=(0, 8)
        )

        ttk.Label(card, textvariable=self._status, style="Muted.TLabel").pack(
            anchor="w", pady=(8, 0)
        )

    def _stat(self, parent, caption: str, variable: tk.StringVar, style: str):
        outer, card = make_card(parent, padding=(14, 9))
        ttk.Label(card, text=caption, style="StatLabel.TLabel").pack(anchor="w")
        ttk.Label(card, textvariable=variable, style=style).pack(anchor="w", pady=(3, 0))
        return outer

    def _build_summary(self) -> None:
        container = ttk.Frame(self)
        container.grid(row=1, column=0, sticky="ew", pady=(0, 10))

        frame = ttk.Frame(container)
        frame.pack(fill="x")
        self.securities_var = tk.StringVar(value=format_amount(0))
        self.property_var = tk.StringVar(value=format_amount(0))
        self.total_var = tk.StringVar(value=format_amount(0))
        self.profit_var = tk.StringVar(value=format_amount(0))
        self.rate_var = tk.StringVar(value="—")
        self._stat(frame, "Биржевые", self.securities_var, "StatIncome.TLabel").pack(
            side="left", fill="both", expand=True
        )
        self._stat(frame, "Имущество", self.property_var, "StatBalance.TLabel").pack(
            side="left", fill="both", expand=True, padx=(10, 0)
        )
        self._stat(frame, "Итого капитал", self.total_var, "StatValue.TLabel").pack(
            side="left", fill="both", expand=True, padx=(10, 0)
        )
        self._stat(frame, "Прибыль", self.profit_var, "StatValue.TLabel").pack(
            side="left", fill="both", expand=True, padx=(10, 0)
        )
        self._stat(frame, "USD/RUB", self.rate_var, "StatValue.TLabel").pack(
            side="left", fill="both", expand=True, padx=(10, 0)
        )

        pool = ttk.Frame(container)
        pool.pack(fill="x", pady=(10, 0))
        self.contributed_var = tk.StringVar(value=format_amount(0))
        self.deployed_var = tk.StringVar(value=format_amount(0))
        self.free_var = tk.StringVar(value=format_amount(0))
        self._stat(
            pool, "Внесено в пул", self.contributed_var, "StatBalance.TLabel"
        ).pack(side="left", fill="both", expand=True)
        self._stat(
            pool, "Вложено в активы", self.deployed_var, "StatValue.TLabel"
        ).pack(side="left", fill="both", expand=True, padx=(10, 0))
        free_outer, free_card = make_card(pool, padding=(14, 9))
        free_outer.pack(side="left", fill="both", expand=True, padx=(10, 0))
        ttk.Label(free_card, text="Свободно", style="StatLabel.TLabel").pack(anchor="w")
        self._free_value = ttk.Label(
            free_card, textvariable=self.free_var, style="StatValue.TLabel"
        )
        self._free_value.pack(anchor="w", pady=(3, 0))

    def _build_table(self) -> None:
        outer, card = make_card(self, title="Портфель", padding=8)
        outer.grid(row=2, column=0, sticky="nsew")
        self.table = TreeTable(
            card,
            columns=[
                ("market", "Тип", 85, "center", False),
                ("ticker", "Тикер / кат.", 100, "w", False),
                ("name", "Название", 190, "w", True),
                ("qty", "Кол-во", 90, "e", False),
                ("avg", "Ср. цена", 110, "e", False),
                ("price", "Текущая", 110, "e", False),
                ("value", "Стоимость", 130, "e", True),
                ("profit", "Прибыль", 120, "e", True),
                ("percent", "Доходн.", 80, "e", False),
                ("updated", "Оценено", 100, "center", False),
            ],
            height=9,
            on_double_click=self._edit,
            on_select=self._on_select,
        )
        self.table.frame.pack(fill="both", expand=True)
        self.table.tree.tag_configure("gain", foreground=theme.SUCCESS)
        self.table.tree.tag_configure("loss", foreground=theme.DANGER)

    def _build_bottom(self) -> None:
        frame = ttk.Frame(self)
        frame.grid(row=3, column=0, sticky="nsew", pady=(10, 0))
        frame.columnconfigure(0, weight=3)
        frame.columnconfigure(1, weight=2)
        frame.rowconfigure(0, weight=1)

        trades_outer, trades_card = make_card(frame, title="Сделки", padding=8)
        trades_outer.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        head = ttk.Frame(trades_card)
        head.pack(fill="x", pady=(0, 6))
        self.trades_title = tk.StringVar(value="Выберите актив")
        ttk.Label(head, textvariable=self.trades_title, style="CardTitle.TLabel").pack(
            side="left"
        )
        ttk.Button(head, text="Удалить сделку", command=self._delete_trade).pack(
            side="right"
        )
        ttk.Button(head, text="Продать…", command=self._sell).pack(
            side="right", padx=(0, 6)
        )
        ttk.Button(head, text="Купить…", command=self._buy).pack(
            side="right", padx=(0, 6)
        )

        self.trades_table = TreeTable(
            trades_card,
            columns=[
                ("date", "Дата", 95, "center", False),
                ("kind", "Тип", 80, "center", False),
                ("qty", "Кол-во", 85, "e", False),
                ("price", "Цена", 110, "e", False),
                ("total", "Сумма", 120, "e", True),
                ("fee", "Комис.", 80, "e", False),
                ("note", "Заметка", 140, "w", True),
            ],
            height=6,
        )
        self.trades_table.frame.pack(fill="both", expand=True)

        graph_outer, graph_card = make_card(
            frame, title="Стоимость портфеля", padding=8
        )
        graph_outer.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        self.graph_canvas = tk.Canvas(
            graph_card, background=theme.CARD, highlightthickness=0
        )
        self.graph_canvas.pack(fill="both", expand=True)
        self.graph_canvas.bind("<Configure>", lambda _e: self._draw_graph())

    # --- данные и отрисовка ---

    def _scope(self):
        label = self.scope_combo.get()
        for text, value in SCOPE_CHOICES:
            if text == label:
                return value
        return None

    def refresh(self) -> None:
        self._render()

    def _render(self) -> None:
        scope = self._scope()
        assets = self.service.assets(scope)
        self._fill_table(assets)

        summary = self.service.portfolio_summary()
        self.securities_var.set(format_amount(summary.securities.value))
        self.property_var.set(format_amount(summary.property.value))
        self.total_var.set(format_amount(summary.total.value))
        profit = summary.total.profit
        sign = "+" if profit >= 0 else ""
        self.profit_var.set(
            f"{sign}{format_amount(profit)} ({summary.total.profit_percent:+.1f}%)"
        )
        self.rate_var.set(
            f"{summary.usd_rub:,.2f}".replace(",", "\u00a0").replace(".", ",")
            if summary.usd_rub else "—"
        )

        self.contributed_var.set(format_amount(summary.contributed))
        self.deployed_var.set(format_amount(summary.deployed))
        self.free_var.set(format_amount(summary.free))
        self._free_value.configure(
            style="StatIncome.TLabel" if summary.free >= 0 else "StatExpense.TLabel"
        )

        self._graph = self.service.portfolio_history(scope)
        self._draw_graph()

        ids = [asset.id for asset in assets]
        if self._selected_id not in ids:
            self._selected_id = ids[0] if ids else None
        self._sync_selection()
        self._render_trades()

    def _fill_table(self, assets) -> None:
        rows = []
        for asset in assets:
            currency = asset.currency
            price_text = (
                format_currency_amount(asset.current_price, currency)
                if asset.has_price else "—"
            )
            profit = asset.profit
            tag = "gain" if profit > 1e-9 else ("loss" if profit < -1e-9 else None)
            tags = [tag] if tag else []
            rows.append(
                row(
                    asset.id,
                    [
                        MARKET_LABELS[asset.market],
                        asset.ticker or asset.category or "—",
                        asset.name,
                        format_quantity(asset.quantity),
                        format_currency_amount(asset.avg_price, currency)
                        if asset.quantity else "—",
                        price_text,
                        format_currency_amount(asset.market_value, currency),
                        format_currency_amount(profit, currency),
                        f"{asset.profit_percent:+.1f}%",
                        _date_text(asset.last_price_at),
                    ],
                    tags=tags,
                    sort=[
                        asset.market, asset.ticker or asset.category, asset.name.lower(),
                        asset.quantity, asset.avg_price, asset.current_price,
                        asset.market_value, profit, asset.profit_percent,
                        asset.last_price_at,
                    ],
                )
            )
        self.table.set_rows(rows)

    def _sync_selection(self) -> None:
        if self._selected_id is None:
            self.trades_title.set("Выберите актив")
            return
        iid = str(self._selected_id)
        if self.table.tree.exists(iid):
            self.table.tree.selection_set(iid)
            self.table.tree.see(iid)

    def _on_select(self) -> None:
        iid = self.table.selected_iid()
        if iid is not None:
            self._selected_id = int(iid)
        self._render_trades()

    def _selected_asset(self):
        if self._selected_id is None:
            return None
        return self.service.asset(self._selected_id)

    def _render_trades(self) -> None:
        asset = self._selected_asset()
        self.trades_table.clear()
        if asset is None:
            self.trades_title.set("Выберите актив")
            return
        self.trades_title.set(f"{asset.name}: сделки")
        rows = []
        for trade in self.service.trades(asset.id):
            rows.append(
                row(
                    trade.id,
                    [
                        format_date(trade.trade_date),
                        TRADE_LABELS[trade.kind],
                        format_quantity(trade.quantity),
                        format_currency_amount(trade.price, asset.currency),
                        format_currency_amount(trade.gross, asset.currency),
                        format_currency_amount(trade.fee, asset.currency)
                        if trade.fee else "—",
                        trade.note,
                    ],
                    tags=("income",) if trade.kind == BUY else ("expense",),
                    sort=[
                        trade.trade_date.toordinal(), trade.kind, trade.quantity,
                        trade.price, trade.gross, trade.fee, trade.note,
                    ],
                )
            )
        self.trades_table.set_rows(rows)

    def _draw_graph(self) -> None:
        canvas = self.graph_canvas
        self.graph_tip.hide()
        canvas.delete("all")
        self._graph_tips = {}
        width = max(canvas.winfo_width(), 100)
        height = max(canvas.winfo_height(), 100)
        points = self._graph
        if len(points) < 2:
            canvas.create_text(
                width / 2, height / 2, text="Нет истории оценок", fill=theme.MUTED
            )
            return

        pad_left, pad_right, pad_top, pad_bottom = 76, 14, 14, 26
        plot_w = width - pad_left - pad_right
        plot_h = height - pad_top - pad_bottom
        values = [value for _d, value in points]
        min_v, max_v = min(values), max(values)
        if max_v == min_v:
            max_v = min_v + 1

        for step in range(5):
            value = min_v + (max_v - min_v) * step / 4
            y = pad_top + plot_h - plot_h * step / 4
            canvas.create_line(pad_left, y, width - pad_right, y, fill="#EDEFF4")
            canvas.create_text(
                pad_left - 8, y, text=_short_money(value), anchor="e", fill=theme.MUTED
            )

        count = len(points)

        def coords(index: int, value: float) -> tuple[float, float]:
            x = pad_left + plot_w * index / (count - 1)
            y = pad_top + plot_h - plot_h * (value - min_v) / (max_v - min_v)
            return x, y

        flat: list[float] = []
        for index, (_day, value) in enumerate(points):
            flat.extend(coords(index, value))
        canvas.create_line(*flat, fill=GRAPH_ACCENT, width=2)

        for index, (day, value) in enumerate(points):
            x, y = coords(index, value)
            item = canvas.create_oval(x - 3, y - 3, x + 3, y + 3, fill=GRAPH_ACCENT,
                                      outline="")
            self._graph_tips[item] = f"{format_date(day)}: {format_amount(value)}"

        for index, anchor in ((0, "w"), (count - 1, "e")):
            x, _y = coords(index, points[index][1])
            canvas.create_text(
                x, height - pad_bottom + 15, text=format_date(points[index][0]),
                fill=theme.MUTED, anchor=anchor,
            )

    def _graph_tip_for(self, event, canvas) -> str | None:
        x = canvas.canvasx(event.x)
        y = canvas.canvasy(event.y)
        for item in canvas.find_overlapping(x - 1, y - 1, x + 1, y + 1):
            text = self._graph_tips.get(item)
            if text:
                return text
        return None

    def _set_status(self, text: str) -> None:
        self._status.set(text)

    # --- действия ---

    def _default_market(self) -> str:
        return MARKET_PHYSICAL if self._scope() == SCOPE_PROPERTY else MARKET_MANUAL

    def _add(self) -> None:
        result = run_dialog(
            AssetDialog, self, default_market=self._default_market()
        )
        if not result:
            return
        try:
            self.service.create_asset(**result)
        except ValidationError as exc:
            messagebox.showerror("Ошибка", str(exc), parent=self)
            return
        self.on_change()

    def _edit(self) -> None:
        asset = self._selected_asset()
        if asset is None:
            messagebox.showinfo("Изменить", "Выберите актив", parent=self)
            return
        result = run_dialog(AssetDialog, self, asset=asset)
        if not result:
            return
        allowed = {
            "name", "market", "ticker", "currency", "category",
            "details", "depreciation_rate", "note",
        }
        try:
            self.service.update_asset(
                asset.id, **{k: v for k, v in result.items() if k in allowed}
            )
        except ValidationError as exc:
            messagebox.showerror("Ошибка", str(exc), parent=self)
            return
        self.on_change()

    def _delete(self) -> None:
        asset = self._selected_asset()
        if asset is None:
            messagebox.showinfo("Удалить", "Выберите актив", parent=self)
            return
        if not messagebox.askyesno(
            "Удалить актив",
            f"Удалить «{asset.name}» вместе со сделками и оценками?",
            parent=self,
        ):
            return
        self.service.remove_asset(asset.id)
        self._selected_id = None
        self.on_change()

    def _buy(self) -> None:
        self._add_trade(BUY)

    def _sell(self) -> None:
        self._add_trade(SELL)

    def _add_trade(self, kind: str) -> None:
        asset = self._selected_asset()
        if asset is None:
            messagebox.showinfo(TRADE_LABELS[kind], "Выберите актив", parent=self)
            return
        result = run_dialog(TradeDialog, self, asset=asset, kind=kind)
        if not result:
            return
        try:
            self.service.add_trade(
                asset.id, kind, result["quantity"], result["price"],
                result["trade_date"], result["fee"], result["note"],
            )
        except ValidationError as exc:
            messagebox.showerror("Ошибка", str(exc), parent=self)
            return
        self.on_change()

    def _delete_trade(self) -> None:
        asset = self._selected_asset()
        iid = self.trades_table.selected_iid()
        if asset is None or iid is None:
            messagebox.showinfo("Удалить сделку", "Выберите сделку", parent=self)
            return
        if not messagebox.askyesno("Удалить", "Удалить выбранную сделку?", parent=self):
            return
        self.service.remove_trade(int(iid))
        self.on_change()

    def _manual_price(self) -> None:
        asset = self._selected_asset()
        if asset is None:
            messagebox.showinfo("Оценить", "Выберите актив", parent=self)
            return
        result = run_dialog(ManualPriceDialog, self, asset=asset)
        if not result:
            return
        try:
            self.service.set_manual_price(asset.id, result["price"], result["date"])
        except ValidationError as exc:
            messagebox.showerror("Ошибка", str(exc), parent=self)
            return
        self.on_change()

    def _refresh_prices(self) -> None:
        self.start_refresh()

    def start_refresh(self, silent: bool = False, on_done=None) -> bool:
        """Запустить обновление цен в фоне. False — уже идёт обновление."""
        if self._refreshing:
            return False
        online = [a for a in self.service.assets() if a.market in ONLINE_MARKETS]
        if not online:
            if on_done:
                on_done()
            return True
        self._refreshing = True
        if not silent:
            self.refresh_btn.configure(state="disabled")
            self._set_status("Обновление цен…")

        def worker() -> None:
            try:
                fetched = self.service.fetch_quotes(online)
            except Exception as exc:  # noqa: BLE001 — поток не должен падать молча
                message = str(exc)
                self.after(
                    0, lambda: self._after_refresh(None, message, silent, on_done)
                )
                return
            self.after(
                0, lambda: self._after_refresh(fetched, None, silent, on_done)
            )

        threading.Thread(target=worker, daemon=True).start()
        return True

    def _after_refresh(self, fetched, error, silent: bool = False, on_done=None) -> None:
        self._refreshing = False
        if not silent:
            self.refresh_btn.configure(state="normal")
        if fetched is None:
            self._set_status(f"Не удалось обновить: {error}")
            if on_done:
                on_done()
            return
        result = self.service.apply_fetch(fetched)
        self.service.mark_synced(PRICES_UPDATED_KEY)
        parts = []
        if result.updated:
            parts.append(f"Обновлено: {result.updated}")
        if fetched.rates:
            parts.append("курсы ЦБ обновлены")
        if not parts:
            parts.append("Нет данных для обновления")
        if result.failed:
            shown = "; ".join(result.failed[:2])
            if len(result.failed) > 2:
                shown += f" и ещё {len(result.failed) - 2}"
            parts.append(f"ошибки: {shown}")
        self._set_status(" · ".join(parts))
        self.on_change()
        if on_done:
            on_done()


class PayoutCalendarView(ttk.Frame):
    """Календарь выплат: план и факт по дивидендам и купонам.

    Ожидаемая сумма каждой выплаты считается как ставка на единицу,
    умноженная на текущее количество актива, поэтому она пересчитывается
    при изменении позиции. Повторяющиеся выплаты задаются правилами и
    разворачиваются в даты прямо здесь, без хранения лишних записей.
    """

    def __init__(self, master, service, on_change):
        super().__init__(master, padding=12)
        self.service = service
        self.on_change = on_change
        today = date.today()
        self._year = today.year
        self._month = today.month
        self._selected_day: date | None = None
        self._row_map: dict[str, object] = {}
        self._asset_map: dict[str, int | None] = {"Все активы": None}
        self._syncing = False
        self.rowconfigure(2, weight=1)
        self.columnconfigure(0, weight=1)
        self._build_toolbar()
        self._build_calendar()
        self._build_list()

    # --- построение ---

    def _build_toolbar(self) -> None:
        outer, card = make_card(self, padding=(14, 10))
        outer.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        bar = ttk.Frame(card)
        bar.pack(fill="x")

        ttk.Button(bar, text="◀", width=3, command=self._prev_month).pack(side="left")
        self.month_var = tk.StringVar(value="")
        ttk.Label(
            bar, textvariable=self.month_var, style="Value.TLabel",
            width=18, anchor="center",
        ).pack(side="left", padx=6)
        ttk.Button(bar, text="▶", width=3, command=self._next_month).pack(side="left")
        ttk.Button(bar, text="Сегодня", command=self._today).pack(side="left", padx=(8, 0))

        ttk.Label(bar, text="Актив:").pack(side="left", padx=(18, 4))
        self.asset_combo = ttk.Combobox(bar, state="readonly", width=22)
        self.asset_combo.pack(side="left")
        self.asset_combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh())

        ttk.Button(bar, text="Правило…", command=self._add_rule).pack(
            side="right", padx=(6, 0)
        )
        ttk.Button(
            bar, text="Добавить", style="Accent.TButton", command=self._add
        ).pack(side="right")
        ttk.Button(bar, text="Удалить", command=self._delete).pack(
            side="right", padx=(6, 0)
        )
        ttk.Button(bar, text="Изменить", command=self._edit).pack(
            side="right", padx=(6, 0)
        )
        self.refresh_btn = ttk.Button(
            bar, text="Обновить из сети", command=self._fetch_network
        )
        self.refresh_btn.pack(side="right", padx=(6, 0))

        self.status_var = tk.StringVar(value="")
        status_row = ttk.Frame(card)
        status_row.pack(fill="x", pady=(8, 0))
        ttk.Label(
            status_row, textvariable=self.status_var, style="Muted.TLabel"
        ).pack(side="left")
        self.due_var = tk.StringVar(value="")
        ttk.Label(
            status_row, textvariable=self.due_var, style="Accent.TLabel"
        ).pack(side="right")

    def _build_calendar(self) -> None:
        outer, card = make_card(self, title="Календарь", padding=8)
        outer.grid(row=1, column=0, sticky="ew")
        self.grid_frame = ttk.Frame(card)
        self.grid_frame.pack(fill="x")

    def _build_list(self) -> None:
        outer, card = make_card(self, title="Выплаты за месяц", padding=8)
        outer.grid(row=2, column=0, sticky="nsew", pady=(10, 0))
        self.table = TreeTable(
            card,
            columns=[
                ("date", "Дата", 95, "center", False),
                ("asset", "Актив", 175, "w", True),
                ("kind", "Тип", 95, "center", False),
                ("expected", "Ожидается", 120, "e", True),
                ("received", "Получено", 120, "e", True),
                ("status", "Статус", 95, "center", False),
                ("source", "Источник", 95, "center", False),
            ],
            height=8,
            on_double_click=self._edit,
        )
        self.table.frame.pack(fill="both", expand=True)
        self.total_var = tk.StringVar(value="")
        ttk.Label(card, textvariable=self.total_var, style="Muted.TLabel").pack(
            anchor="w", pady=(8, 0)
        )

    # --- данные ---

    def _selected_asset_id(self) -> int | None:
        return self._asset_map.get(self.asset_combo.get())

    def _sync_assets(self) -> None:
        labels = ["Все активы"]
        mapping: dict[str, int | None] = {"Все активы": None}
        seen: dict[str, int] = {}
        for asset in self.service.assets():
            base = f"{asset.name} ({asset.ticker})" if asset.ticker else asset.name
            count = seen.get(base, 0)
            seen[base] = count + 1
            label = base if not count else f"{base} #{count + 1}"
            labels.append(label)
            mapping[label] = asset.id
        current = self.asset_combo.get()
        self._asset_map = mapping
        self.asset_combo.configure(values=labels)
        self.asset_combo.set(current if current in labels else labels[0])

    def refresh(self) -> None:
        self._sync_assets()
        self._render()

    def _month_range(self) -> tuple[date, date]:
        last_day = calendar.monthrange(self._year, self._month)[1]
        return (
            date(self._year, self._month, 1),
            date(self._year, self._month, last_day),
        )

    def _render(self) -> None:
        self.month_var.set(
            f"{MONTH_NAMES_SHORT[self._month - 1].capitalize()} {self._year}"
        )
        self._draw_calendar()
        self._fill_list()
        due = len(self.service.due_past_payouts(self._selected_asset_id()))
        self.due_var.set(
            f"Не отмечено прошедших: {due}" if due else ""
        )

    def _draw_calendar(self) -> None:
        frame = self.grid_frame
        for child in frame.winfo_children():
            child.destroy()
        for index, name in enumerate(WEEKDAYS):
            ttk.Label(
                frame, text=name, style="CardTitle.TLabel", anchor="center"
            ).grid(row=0, column=index, sticky="ew", padx=1, pady=(0, 4))
            frame.columnconfigure(index, weight=1)

        date_from, date_to = self._month_range()
        entries = self.service.calendar_entries(
            date_from, date_to, self._selected_asset_id()
        )
        by_day: dict[int, list] = {}
        for entry in entries:
            by_day.setdefault(entry.date.day, []).append(entry)

        today = date.today()
        weeks = calendar.monthcalendar(self._year, self._month)
        for week_index, week in enumerate(weeks, start=1):
            frame.rowconfigure(week_index, weight=1)
            for column, day in enumerate(week):
                cell = tk.Frame(
                    frame, bg=theme.CARD, highlightthickness=1,
                    highlightbackground=theme.BORDER,
                )
                cell.grid(row=week_index, column=column, sticky="nsew", padx=1, pady=1)
                cell.configure(width=118, height=82)
                cell.grid_propagate(False)
                if not day:
                    continue
                picked = date(self._year, self._month, day)
                selected = self._selected_day == picked
                is_today = picked == today
                if selected:
                    cell.configure(highlightbackground="#6D28D9", highlightthickness=2)
                elif is_today:
                    cell.configure(highlightbackground=theme.ACCENT, highlightthickness=2)

                tk.Label(
                    cell, text=str(day), bg=theme.CARD, fg=theme.TEXT,
                    font=theme.make_font(10, "bold"),
                ).pack(anchor="nw", padx=4, pady=(2, 0))

                day_entries = by_day.get(day, [])
                if day_entries:
                    total = sum(e.expected for e in day_entries)
                    has_expected = any(not e.is_received for e in day_entries)
                    color = theme.ACCENT if has_expected else theme.MUTED
                    tk.Label(
                        cell, text=_short_money(total), bg=theme.CARD, fg=color,
                        font=theme.make_font(10),
                    ).pack(anchor="w", padx=4)
                    dots = tk.Frame(cell, bg=theme.CARD)
                    dots.pack(anchor="w", padx=4)
                    for entry in day_entries[:5]:
                        tk.Frame(
                            dots, bg=PAYOUT_COLORS.get(entry.kind, theme.MUTED),
                            width=6, height=6,
                        ).pack(side="left", padx=1)
                    due = [e for e in day_entries if e.is_due]
                    if due:
                        ttk.Button(
                            cell, text="Получить", style="Compact.TButton",
                            command=lambda d=day: self._receive_day(d),
                        ).pack(anchor="w", padx=4, pady=(2, 0))
                cell.bind("<Button-1>", lambda _e, d=day: self._select_day(d))

    def _fill_list(self) -> None:
        date_from, date_to = self._month_range()
        entries = self.service.calendar_entries(
            date_from, date_to, self._selected_asset_id()
        )
        if self._selected_day:
            entries = [e for e in entries if e.date == self._selected_day]

        rows = []
        self._row_map = {}
        for entry in entries:
            key = (
                f"p{entry.payout_id}" if entry.payout_id is not None
                else f"r{entry.rule_id}:{entry.date.isoformat()}"
            )
            self._row_map[key] = entry
            received = (
                format_currency_amount(entry.received, entry.currency)
                if entry.received is not None else "—"
            )
            source = {
                "rule": "Правило",
                "manual": "Вручную",
                "moex": "MOEX",
                "yahoo": "Yahoo",
                "smartlab": "smart-lab",
            }.get(entry.source, entry.source or "—")
            tags = ("income",) if entry.is_received else ("invest",)
            rows.append(
                row(
                    key,
                    [
                        format_date(entry.date),
                        entry.asset_name,
                        PAYOUT_KIND_LABELS[entry.kind],
                        format_currency_amount(entry.expected, entry.currency),
                        received,
                        PAYOUT_STATUS_LABELS[entry.status],
                        source,
                    ],
                    tags=tags,
                    sort=[
                        entry.date.toordinal(), entry.asset_name.lower(),
                        entry.kind, entry.expected,
                        entry.received or 0.0, entry.status, source,
                    ],
                )
            )
        self.table.set_rows(rows)

        expected_sum = sum(e.expected for e in entries if not e.is_received)
        received_sum = sum(
            (e.received if e.received is not None else e.expected)
            for e in entries if e.is_received
        )
        scope = self._selected_day.strftime("%d.%m.%Y") if self._selected_day else "месяц"
        self.total_var.set(
            f"{scope}: ожидается {format_amount(expected_sum)}"
            f"   ·   получено {format_amount(received_sum)}"
        )

    # --- навигация ---

    def _shift_month(self, delta: int) -> None:
        total = self._year * 12 + (self._month - 1) + delta
        self._year, month0 = divmod(total, 12)
        self._month = month0 + 1
        self._selected_day = None
        self._render()

    def _prev_month(self) -> None:
        self._shift_month(-1)

    def _next_month(self) -> None:
        self._shift_month(1)

    def _today(self) -> None:
        today = date.today()
        self._year, self._month = today.year, today.month
        self._selected_day = today
        self._render()

    def _select_day(self, day: int) -> None:
        picked = date(self._year, self._month, day)
        self._selected_day = None if self._selected_day == picked else picked
        self._draw_calendar()
        self._fill_list()

    def _receive_day(self, day: int) -> None:
        """Отметить прошедшие выплаты выбранного дня полученными."""
        picked = date(self._year, self._month, day)
        entries = [
            e for e in self.service.calendar_entries(
                picked, picked, self._selected_asset_id()
            ) if e.is_due
        ]
        if not entries:
            return
        result = run_dialog(ReceivePayoutsDialog, self, entries=entries)
        if not result:
            return
        try:
            for entry, amount in result["items"]:
                self.service.receive_entry(entry, amount, result["received_date"])
        except ValidationError as exc:
            messagebox.showerror("Ошибка", str(exc), parent=self)
            return
        self.on_change()

    # --- действия ---

    def _selected_entry(self):
        iid = self.table.selected_iid()
        if iid is None:
            return None
        return self._row_map.get(iid)

    def _add(self) -> None:
        assets = self.service.assets()
        if not assets:
            messagebox.showinfo("Выплаты", "Сначала добавьте актив", parent=self)
            return
        result = run_dialog(
            PayoutDialog, self, assets=assets,
            default_asset_id=self._selected_asset_id(),
        )
        if not result:
            return
        try:
            self.service.create_payout(
                result["asset_id"], result["kind"], result["date"],
                rate=result["rate"], amount=result["amount"],
                status=result["status"], received_date=result["received_date"],
                note=result["note"], source="manual",
            )
        except ValidationError as exc:
            messagebox.showerror("Ошибка", str(exc), parent=self)
            return
        self.on_change()

    def _add_rule(self) -> None:
        assets = self.service.assets()
        if not assets:
            messagebox.showinfo("Выплаты", "Сначала добавьте актив", parent=self)
            return
        result = run_dialog(
            PayoutRuleDialog, self, assets=assets,
            default_asset_id=self._selected_asset_id(),
        )
        if not result:
            return
        try:
            self.service.create_payout_rule(
                result["asset_id"], result["kind"], result["rate"],
                result["period"], result["anchor"], result["note"],
            )
        except ValidationError as exc:
            messagebox.showerror("Ошибка", str(exc), parent=self)
            return
        self.on_change()

    def _edit(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            messagebox.showinfo("Изменить", "Выберите выплату", parent=self)
            return
        if entry.payout_id is None:
            messagebox.showinfo(
                "Правило",
                "Эта выплата задана правилом. Чтобы изменить её, "
                "удалите правило и создайте новое.",
                parent=self,
            )
            return
        payout = self.service.payout(entry.payout_id)
        if payout is None:
            return
        result = run_dialog(
            PayoutDialog, self, assets=self.service.assets(), payout=payout
        )
        if not result:
            return
        try:
            self.service.update_payout(
                payout.id, result["kind"], result["date"],
                rate=result["rate"], amount=result["amount"],
                status=result["status"], received_date=result["received_date"],
                note=result["note"],
            )
        except ValidationError as exc:
            messagebox.showerror("Ошибка", str(exc), parent=self)
            return
        self.on_change()

    def _delete(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            messagebox.showinfo("Удалить", "Выберите выплату", parent=self)
            return
        if entry.payout_id is not None:
            if not messagebox.askyesno("Удалить", "Удалить выбранную выплату?", parent=self):
                return
            self.service.remove_payout(entry.payout_id)
        else:
            if not messagebox.askyesno(
                "Удалить правило",
                "Это плановая выплата по правилу. Удалить правило целиком?",
                parent=self,
            ):
                return
            self.service.remove_payout_rule(entry.rule_id)
        self.on_change()

    # --- сеть ---

    def _fetch_network(self) -> None:
        self.start_sync()

    def start_sync(self, silent: bool = False, on_done=None) -> bool:
        """Запустить поиск выплат в фоне. False — уже идёт синхронизация."""
        if self._syncing:
            return False
        online = [
            a for a in self.service.assets() if a.market in ONLINE_MARKETS
        ]
        if not online:
            if not silent:
                messagebox.showinfo(
                    "Выплаты", "Нет активов с онлайн-источником", parent=self
                )
            if on_done:
                on_done()
            return True
        self._syncing = True
        if not silent:
            self.refresh_btn.configure(state="disabled")
            self.status_var.set("Поиск выплат…")

        def worker() -> None:
            try:
                fetched = self.service.fetch_payouts(online, include_past=True)
            except Exception as exc:  # noqa: BLE001 — поток не должен падать молча
                message = str(exc)
                self.after(
                    0, lambda: self._after_fetch(None, message, silent, on_done)
                )
                return
            self.after(
                0, lambda: self._after_fetch(fetched, None, silent, on_done)
            )

        threading.Thread(target=worker, daemon=True).start()
        return True

    def _after_fetch(
        self, fetched, error: str | None, silent: bool = False, on_done=None
    ) -> None:
        self._syncing = False
        if not silent:
            self.refresh_btn.configure(state="normal")
        if error is not None:
            self.status_var.set(f"Ошибка: {error}")
            if on_done:
                on_done()
            return
        try:
            result = self.service.apply_payout_fetch(fetched, include_past=True)
        except Exception as exc:  # noqa: BLE001
            self.status_var.set(f"Ошибка: {exc}")
            if on_done:
                on_done()
            return
        self.service.mark_synced(PAYOUTS_SYNCED_KEY)
        parts = [f"добавлено выплат: {result.updated}"]
        if result.failed:
            shown = "; ".join(result.failed[:2])
            if len(result.failed) > 2:
                shown += f" и ещё {len(result.failed) - 2}"
            parts.append(f"нет данных: {shown}")
        self.status_var.set(" · ".join(parts))
        self.on_change()
        if on_done:
            on_done()


class InvestmentsTab(ttk.Frame):
    """Вкладка «Инвестиции»: портфель и календарь выплат."""

    def __init__(self, master, service, on_change):
        super().__init__(master)
        self.service = service
        self.on_change = on_change
        self._price_after: str | None = None
        self._payout_after: str | None = None
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)
        self.portfolio = PortfolioView(self.notebook, service, on_change)
        self.calendar = PayoutCalendarView(self.notebook, service, on_change)
        self.notebook.add(self.portfolio, text="Портфель")
        self.notebook.add(self.calendar, text="Календарь выплат")
        self.bind("<Destroy>", self._on_destroy, add="+")
        self.reschedule_auto()

    def refresh(self) -> None:
        self.portfolio.refresh()
        self.calendar.refresh()

    # --- автообновление ---

    def reschedule_auto(self) -> None:
        """Перечитать настройки и заново поставить таймеры (при старте)."""
        self._schedule_price(initial=True)
        self._schedule_payout(initial=True)

    def _cancel_timer(self, attr: str) -> None:
        after_id = getattr(self, attr, None)
        if after_id is not None:
            try:
                self.after_cancel(after_id)
            except tk.TclError:
                pass
            setattr(self, attr, None)

    @staticmethod
    def _delay_seconds(last_iso: str | None, interval: float) -> float:
        """Сколько ждать до следующего запуска с учётом прошлого успеха."""
        if not last_iso:
            return 2.0
        try:
            stamp = datetime.strptime(last_iso[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return 2.0
        remaining = interval - (datetime.now() - stamp).total_seconds()
        return 2.0 if remaining <= 0 else remaining

    def _schedule_price(self, initial: bool = False) -> None:
        self._cancel_timer("_price_after")
        settings = self.service.auto_settings()
        if not settings.price_enabled:
            return
        interval = settings.price_minutes * 60
        delay = (
            self._delay_seconds(self.service.last_sync(PRICES_UPDATED_KEY), interval)
            if initial else interval
        )
        self._price_after = self.after(
            int(delay * 1000), lambda: self._auto_price_tick()
        )

    def _schedule_payout(self, initial: bool = False) -> None:
        self._cancel_timer("_payout_after")
        settings = self.service.auto_settings()
        if not settings.payout_enabled:
            return
        interval = settings.payout_hours * 3600
        delay = (
            self._delay_seconds(self.service.last_sync(PAYOUTS_SYNCED_KEY), interval)
            if initial else interval
        )
        self._payout_after = self.after(
            int(delay * 1000), lambda: self._auto_payout_tick()
        )

    def _auto_price_tick(self) -> None:
        self._price_after = None
        if not self.service.auto_settings().price_enabled:
            return
        started = self.portfolio.start_refresh(
            silent=True, on_done=lambda: self._schedule_price()
        )
        if not started:
            self._price_after = self.after(
                60_000, lambda: self._auto_price_tick()
            )

    def _auto_payout_tick(self) -> None:
        self._payout_after = None
        if not self.service.auto_settings().payout_enabled:
            return
        started = self.calendar.start_sync(
            silent=True, on_done=lambda: self._schedule_payout()
        )
        if not started:
            self._payout_after = self.after(
                60_000, lambda: self._auto_payout_tick()
            )

    def _on_destroy(self, event) -> None:
        if event.widget is not self:
            return
        self._cancel_timer("_price_after")
        self._cancel_timer("_payout_after")
