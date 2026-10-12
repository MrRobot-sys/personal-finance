"""Бизнес-логика поверх репозитория."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from .models import (
    EXPENSE,
    INCOME,
    INVEST,
    BUY,
    SELL,
    MARKET_MOEX,
    MARKET_PHYSICAL,
    MARKET_US,
    ONLINE_MARKETS,
    PAYOUT_COUPON,
    PAYOUT_DIVIDEND,
    PAYOUT_EXPECTED,
    PAYOUT_KINDS,
    PAYOUT_RECEIVED,
    PERIOD_ONCE,
    PERIOD_MONTHS,
    Asset,
    Category,
    CategoryPlan,
    MonthSummary,
    Payout,
    PayoutRule,
    PortfolioSummary,
    PortfolioTotals,
    Trade,
    Transaction,
    ValidationError,
    add_months,
    parse_amount,
    parse_date,
    parse_optional_amount,
    validate_asset_name,
    validate_category_name,
    validate_currency,
    validate_kind,
    validate_market,
    validate_payout_kind,
    validate_period,
)
from .repository import Repository

RATE_USD_KEY = "rate_USD"
RATE_EUR_KEY = "rate_EUR"
RATES_UPDATED_KEY = "rates_updated"

# Метки времени последних успешных синхронизаций (ISO, для авто-таймеров).
PRICES_UPDATED_KEY = "prices_updated_at"
PAYOUTS_SYNCED_KEY = "payouts_synced_at"

# Настройки автообновления.
AUTO_PRICE_ENABLED_KEY = "auto_price_enabled"
AUTO_PRICE_MINUTES_KEY = "auto_price_minutes"
AUTO_PAYOUT_ENABLED_KEY = "auto_payout_enabled"
AUTO_PAYOUT_HOURS_KEY = "auto_payout_hours"
DEFAULT_PRICE_MINUTES = 30
DEFAULT_PAYOUT_HOURS = 24
MIN_PRICE_MINUTES = 5
MIN_PAYOUT_HOURS = 1

# Насколько глубоко искать пропущенные прошедшие выплаты (месяцев).
PAST_PAYOUT_MONTHS = 24


@dataclass
class AutoRefreshSettings:
    """Настройки фонового автообновления цен и поиска выплат."""
    price_enabled: bool = True
    price_minutes: int = DEFAULT_PRICE_MINUTES
    payout_enabled: bool = True
    payout_hours: int = DEFAULT_PAYOUT_HOURS


@dataclass
class ImportSummary:
    imported: int = 0
    skipped_duplicates: int = 0
    skipped_category: int = 0


@dataclass
class PriceFetch:
    """Результат сетевого обновления цен (без записи в базу)."""
    quotes: list = None       # [(asset_id, Quote), ...]
    failures: list = None     # ["SBER: нет соединения", ...]
    rates: dict = None        # {"USD": 84.9, "EUR": 94.97}

    def __post_init__(self):
        if self.quotes is None:
            self.quotes = []
        if self.failures is None:
            self.failures = []
        if self.rates is None:
            self.rates = {}


@dataclass
class RefreshResult:
    updated: int = 0
    failed: list = None

    def __post_init__(self):
        if self.failed is None:
            self.failed = []


@dataclass
class PayoutFetch:
    """Результат сетевого поиска будущих выплат (без записи в базу)."""
    payouts: list = None   # [{asset_id, kind, date, rate, source, note}, ...]
    failures: list = None  # ["SBER: нет соединения", ...]

    def __post_init__(self):
        if self.payouts is None:
            self.payouts = []
        if self.failures is None:
            self.failures = []


@dataclass
class PayoutEntry:
    """Строка календаря выплат: явная выплата или вхождение правила."""
    date: date
    asset_id: int
    asset_name: str
    kind: str
    currency: str
    expected: float
    status: str
    source: str
    payout_id: int | None = None
    rule_id: int | None = None
    received: float | None = None
    note: str = ""
    rate: float | None = None
    # Количество актива на дату выплаты (только для прошедших дат).
    quantity_at: float | None = None

    @property
    def is_received(self) -> bool:
        return self.status == PAYOUT_RECEIVED

    @property
    def expected_at_date(self) -> float:
        """Ожидаемая сумма по количеству на дату выплаты (для прошедших)."""
        if self.quantity_at is not None and self.rate is not None:
            return self.rate * self.quantity_at
        return self.expected

    @property
    def is_past_due(self) -> bool:
        """Прошедшая ожидаемая выплата: срок наступил, но она не отмечена."""
        return not self.is_received and self.date <= date.today()

    @property
    def is_due(self) -> bool:
        """Прошедшая ожидаемая выплата при бумаге, бывшей у нас на дату."""
        return self.is_past_due and (self.quantity_at or 0) > 0


class FinanceService:
    def __init__(self, repo: Repository):
        self.repo = repo

    # --- категории ---

    def categories(self, kind: str | None = None) -> list[Category]:
        return self.repo.list_categories(kind)

    def create_category(
        self, name: str, kind: str, monthly_limit: float | None = None
    ) -> int:
        name = validate_category_name(name)
        kind = validate_kind(kind)
        if self.repo.category_exists_name(name, kind):
            raise ValidationError(f"Категория «{name}» уже существует")
        return self.repo.add_category(name, kind, monthly_limit)

    def rename_category(
        self, category_id: int, name: str, kind: str,
        monthly_limit: float | None = None,
    ) -> None:
        name = validate_category_name(name)
        kind = validate_kind(kind)
        if self.repo.category_exists_name(name, kind, exclude_id=category_id):
            raise ValidationError(f"Категория «{name}» уже существует")
        self.repo.update_category(category_id, name, kind, monthly_limit)

    def remove_category(self, category_id: int, with_transactions: bool = False) -> int:
        try:
            return self.repo.delete_category(category_id, with_transactions)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

    def transaction(self, transaction_id: int) -> Transaction | None:
        return self.repo.get_transaction(transaction_id)

    def category_usage(self, category_id: int) -> tuple[int, float]:
        return self.repo.category_stats(category_id)

    # --- операции ---

    def transactions(
        self,
        kind: str | None = None,
        category_id: int | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        text: str | None = None,
    ) -> list[Transaction]:
        if date_from and date_to and date_from > date_to:
            date_from, date_to = date_to, date_from
        return self.repo.list_transactions(kind, category_id, date_from, date_to, text)

    def create_transaction(
        self, category_id: int, amount: float, txn_date: date, note: str = "",
        source: str = "",
    ) -> int:
        category = self.repo.get_category(category_id)
        if category is None:
            raise ValidationError("Категория не найдена")
        if amount <= 0:
            raise ValidationError("Сумма должна быть больше нуля")
        return self.repo.add_transaction(
            category_id, round(amount, 2), txn_date, note, source
        )

    def update_transaction(
        self, transaction_id: int, category_id: int, amount: float,
        txn_date: date, note: str = "",
    ) -> None:
        if self.repo.get_transaction(transaction_id) is None:
            raise ValidationError("Операция не найдена")
        if self.repo.get_category(category_id) is None:
            raise ValidationError("Категория не найдена")
        if amount <= 0:
            raise ValidationError("Сумма должна быть больше нуля")
        self.repo.update_transaction(transaction_id, category_id, round(amount, 2), txn_date, note)

    def remove_transaction(self, transaction_id: int) -> None:
        self.repo.delete_transaction(transaction_id)

    # --- планы по категориям ---

    def category_plans(self, year: int, month: int) -> list[CategoryPlan]:
        return self.repo.category_plans(year, month)

    def set_monthly_plan(self, category_id: int, raw_plan: str | None) -> None:
        if self.repo.get_category(category_id) is None:
            raise ValidationError("Категория не найдена")
        value = parse_optional_amount(raw_plan)
        self.repo.set_monthly_limit(category_id, round(value, 2) if value is not None else None)

    # --- статистика ---

    def month_summary(self, year: int, month: int) -> MonthSummary:
        return self.repo.monthly_totals(year, month)

    def month_breakdown(self, year: int, month: int) -> list[tuple[str, str, float]]:
        from .models import month_range

        start, end = month_range(year, month)
        return self.repo.category_totals(start, end)

    def dynamics(self, year: int, month: int, count: int = 12) -> list[MonthSummary]:
        return self.repo.monthly_series(year, month, count)

    def filtered_totals(self, transactions: list[Transaction]) -> tuple[float, float]:
        income = sum(t.amount for t in transactions if t.kind == INCOME)
        expense = sum(t.amount for t in transactions if t.kind == EXPENSE)
        return income, expense

    def invested_total(self) -> float:
        """Сумма всех инвестиционных операций (внесено в пул)."""
        return self.repo.invested_total()

    @staticmethod
    def amount_from_text(raw: str) -> float:
        return parse_amount(raw)

    @staticmethod
    def date_from_text(raw: str) -> date:
        return parse_date(raw)

    # --- импорт ---

    def operation_sources(self) -> set[str]:
        return set(self.repo.list_sources())

    def import_operations(
        self,
        operations: list,
        resolver: Callable[[str, str], int | None],
        skip_existing: bool = True,
    ) -> ImportSummary:
        """Импортирует операции. resolver(name, kind) возвращает category_id или None."""
        known = set(self.repo.list_sources())
        summary = ImportSummary()
        for op in operations:
            if skip_existing and op.fingerprint in known:
                summary.skipped_duplicates += 1
                continue
            category_id = resolver(op.category_name, op.kind)
            if category_id is None:
                summary.skipped_category += 1
                continue
            self.create_transaction(
                category_id, op.amount, op.txn_date, op.note,
                source=op.fingerprint,
            )
            known.add(op.fingerprint)
            summary.imported += 1
        return summary

    def get_or_create_category(self, name: str, kind: str) -> int:
        name = validate_category_name(name)
        kind = validate_kind(kind)
        existing = self.repo.category_by_name(name, kind)
        if existing is not None:
            return existing.id
        return self.create_category(name, kind)

    def import_category(
        self, name: str, kind: str, action: str,
        existing_id: int | None = None,
    ) -> int | None:
        """Разрешает категорию импорта по действию пользователя.
        action: 'existing' | 'create' | 'fallback'."""
        kind = validate_kind(kind)
        if action == "existing" and existing_id is not None:
            return existing_id
        if action == "create":
            existing = self.repo.category_by_name(name, kind)
            if existing is not None:
                return existing.id
            try:
                return self.create_category(name, kind)
            except ValidationError:
                pass
        return self._fallback_import_category(kind)

    def _fallback_import_category(self, kind: str) -> int | None:
        existing = self.repo.category_by_name("Прочее", kind)
        if existing is not None:
            return existing.id
        try:
            return self.create_category("Прочее", kind)
        except ValidationError:
            return None

    # --- инвестиции и имущество ---

    def assets(self, scope: str | None = None) -> list[Asset]:
        return self.repo.list_assets(scope)

    def asset(self, asset_id: int) -> Asset | None:
        return self.repo.get_asset(asset_id)

    def create_asset(
        self, name: str, market: str, ticker: str = "", currency: str = "RUB",
        category: str = "", details: str = "", depreciation_rate: float | None = None,
        note: str = "", quantity: float | None = None, price: float | None = None,
        trade_date: date | None = None, fee: float = 0.0,
    ) -> int:
        name, market, ticker, currency, category, depreciation_rate = (
            self._validate_asset_fields(
                name, market, ticker, currency, category, depreciation_rate
            )
        )
        if ticker and self.repo.asset_by_ticker(ticker, market) is not None:
            raise ValidationError(f"Актив «{ticker}» уже есть в портфеле")
        asset_id = self.repo.add_asset(
            name, market, ticker, currency, category, details,
            depreciation_rate, note.strip(),
        )
        if quantity:
            self.add_trade(
                asset_id, BUY, quantity, price or 0.0,
                trade_date or date.today(), fee,
            )
        return asset_id

    def update_asset(
        self, asset_id: int, name: str, market: str, ticker: str = "",
        currency: str = "RUB", category: str = "", details: str = "",
        depreciation_rate: float | None = None, note: str = "",
    ) -> None:
        if self.repo.get_asset(asset_id) is None:
            raise ValidationError("Актив не найден")
        name, market, ticker, currency, category, depreciation_rate = (
            self._validate_asset_fields(
                name, market, ticker, currency, category, depreciation_rate
            )
        )
        existing = self.repo.asset_by_ticker(ticker, market) if ticker else None
        if existing is not None and existing.id != asset_id:
            raise ValidationError(f"Актив «{ticker}» уже есть в портфеле")
        self.repo.update_asset(
            asset_id, name, market, ticker, currency, category, details,
            depreciation_rate, note.strip(),
        )

    @staticmethod
    def _validate_asset_fields(
        name, market, ticker, currency, category, depreciation_rate
    ):
        name = validate_asset_name(name)
        market = validate_market(market)
        currency = validate_currency(currency or "RUB")
        ticker = (ticker or "").strip().upper()
        if market in ONLINE_MARKETS and not ticker:
            raise ValidationError("Для биржевого актива укажите тикер")
        if market not in ONLINE_MARKETS:
            ticker = ""
        category = (category or "").strip()
        if market != MARKET_PHYSICAL:
            depreciation_rate = None
        elif depreciation_rate is not None and depreciation_rate < 0:
            raise ValidationError("Износ не может быть отрицательным")
        return name, market, ticker, currency, category, depreciation_rate

    def remove_asset(self, asset_id: int) -> None:
        self.repo.delete_asset(asset_id)

    def trades(self, asset_id: int) -> list[Trade]:
        return self.repo.list_trades(asset_id)

    def add_trade(
        self, asset_id: int, kind: str, quantity: float, price: float,
        trade_date: date, fee: float = 0.0, note: str = "",
    ) -> int:
        asset = self.repo.get_asset(asset_id)
        if asset is None:
            raise ValidationError("Актив не найден")
        if kind not in (BUY, SELL):
            raise ValidationError("Неизвестный тип сделки")
        if quantity is None or quantity <= 0:
            raise ValidationError("Количество должно быть больше нуля")
        if price is None or price < 0:
            raise ValidationError("Цена не может быть отрицательной")
        if fee is None or fee < 0:
            raise ValidationError("Комиссия не может быть отрицательной")
        if kind == SELL and quantity > asset.quantity + 1e-9:
            raise ValidationError("Недостаточно актива для продажи")
        return self.repo.add_trade(
            asset_id, kind, round(quantity, 6), round(price, 6),
            trade_date, round(fee, 2), note,
        )

    def remove_trade(self, trade_id: int) -> None:
        self.repo.delete_trade(trade_id)

    def set_manual_price(
        self, asset_id: int, price: float, on_date: date | None = None,
        source: str = "manual",
    ) -> None:
        asset = self.repo.get_asset(asset_id)
        if asset is None:
            raise ValidationError("Актив не найден")
        if price is None or price < 0:
            raise ValidationError("Оценка не может быть отрицательной")
        stamp = f"{on_date.isoformat()} 12:00:00" if on_date else None
        self.repo.add_price(
            asset_id, round(price, 6), asset.currency, source, stamp
        )

    # --- курсы валют ---

    def rates(self) -> dict[str, float]:
        result: dict[str, float] = {}
        for code in ("USD", "EUR"):
            raw = self.repo.get_setting(f"rate_{code}")
            if raw:
                try:
                    result[code] = float(raw)
                except ValueError:
                    pass
        return result

    def set_rates(self, rates: dict[str, float]) -> None:
        for code, value in (rates or {}).items():
            if value and value > 0:
                self.repo.set_setting(f"rate_{code}", f"{float(value):.6f}")
        from .quotes import now_iso

        self.repo.set_setting(RATES_UPDATED_KEY, now_iso())

    def rate_to_rub(self, currency: str) -> float:
        if currency == "RUB":
            return 1.0
        return self.rates().get(currency, 1.0)

    # --- обновление цен ---

    def fetch_quotes(self, assets: list[Asset] | None = None, opener=None) -> PriceFetch:
        """Только сеть, без записи в базу (можно вызывать из потока)."""
        from . import quotes

        assets = self.repo.list_assets() if assets is None else assets
        result = PriceFetch()
        for asset in assets:
            if asset.market not in ONLINE_MARKETS:
                continue
            try:
                quote = quotes.fetch_quote(asset, opener=opener)
            except quotes.QuoteError as exc:
                result.failures.append(f"{asset.ticker or asset.name}: {exc}")
                continue
            result.quotes.append((asset.id, quote))
        try:
            result.rates = quotes.fetch_rates(opener=opener)
        except quotes.QuoteError as exc:
            result.failures.append(f"Курсы ЦБ: {exc}")
        return result

    def apply_fetch(self, fetched: PriceFetch) -> RefreshResult:
        """Запись полученных цен и курсов в базу (в основном потоке)."""
        for asset_id, quote in fetched.quotes:
            self.repo.add_price(
                asset_id, quote.price, quote.currency, quote.source, quote.fetched_at
            )
        if fetched.rates:
            self.set_rates(fetched.rates)
        return RefreshResult(updated=len(fetched.quotes), failed=list(fetched.failures))

    def refresh_prices(self, opener=None) -> RefreshResult:
        return self.apply_fetch(self.fetch_quotes(opener=opener))

    # --- сводка портфеля ---

    def portfolio_summary(self, assets: list[Asset] | None = None) -> PortfolioSummary:
        assets = self.repo.list_assets() if assets is None else assets
        rates = self.rates()
        securities = PortfolioTotals()
        physical = PortfolioTotals()
        deployed = 0.0
        for asset in assets:
            rate = 1.0 if asset.currency == "RUB" else rates.get(asset.currency, 1.0)
            target = physical if asset.is_physical else securities
            target.invested += asset.cost_basis * rate
            target.value += asset.market_value * rate
            target.realized += asset.realized * rate
            # В пул вложены нетто-покупки: покупки с комиссией минус продажи за вычетом комиссии.
            deployed += (asset.invested - asset.proceeds) * rate
        total = PortfolioTotals(
            invested=securities.invested + physical.invested,
            value=securities.value + physical.value,
            realized=securities.realized + physical.realized,
        )
        return PortfolioSummary(
            securities, physical, total, "RUB",
            rates.get("USD"), rates.get("EUR"),
            contributed=self.repo.invested_total(),
            deployed=deployed,
        )

    def portfolio_history(self, scope: str | None = None) -> list[tuple[date, float]]:
        """Стоимость портфеля по датам оценок (в рублях, по текущему курсу)."""
        assets = {a.id: a for a in self.repo.list_assets(scope)}
        if not assets:
            return []
        rates = self.rates()
        series: dict[int, list[tuple[str, float]]] = {}
        days: set[str] = set()
        for point in self.repo.list_prices():
            if point.asset_id not in assets:
                continue
            series.setdefault(point.asset_id, []).append(
                (point.fetched_at, point.price)
            )
            days.add(point.fetched_at[:10])
        if not days:
            return []
        trades: dict[int, list[tuple[date, float]]] = {}
        for asset_id in assets:
            trades[asset_id] = [
                (t.trade_date, t.quantity if t.kind == BUY else -t.quantity)
                for t in self.repo.list_trades(asset_id)
            ]
        points: list[tuple[date, float]] = []
        for day in sorted(days):
            total = 0.0
            for asset_id, asset in assets.items():
                quantity = sum(
                    qty for when, qty in trades.get(asset_id, [])
                    if when.isoformat() <= day
                )
                if not quantity:
                    continue
                price = asset.avg_price
                for stamp, value in series.get(asset_id, []):
                    if stamp[:10] <= day:
                        price = value
                    else:
                        break
                rate = 1.0 if asset.currency == "RUB" else rates.get(asset.currency, 1.0)
                total += quantity * price * rate
            points.append((date.fromisoformat(day), total))
        return points

    # --- выплаты (дивиденды, купоны) ---

    def payouts(
        self, asset_id: int | None = None,
        date_from: date | None = None, date_to: date | None = None,
    ) -> list[Payout]:
        return self.repo.list_payouts(asset_id, date_from, date_to)

    def payout(self, payout_id: int) -> Payout | None:
        return self.repo.get_payout(payout_id)

    def create_payout(
        self, asset_id: int, kind: str, pay_date: date,
        rate: float | None = None, amount: float | None = None,
        status: str = PAYOUT_EXPECTED, received_date: date | None = None,
        note: str = "", source: str = "manual", rule_id: int | None = None,
    ) -> int:
        asset = self.repo.get_asset(asset_id)
        if asset is None:
            raise ValidationError("Актив не найден")
        kind = validate_payout_kind(kind)
        if status not in (PAYOUT_EXPECTED, PAYOUT_RECEIVED):
            raise ValidationError("Неизвестный статус выплаты")
        if status == PAYOUT_RECEIVED and (amount is None or amount < 0):
            raise ValidationError("Укажите полученную сумму")
        if status == PAYOUT_EXPECTED and rate is None and amount is None:
            raise ValidationError("Укажите ставку на единицу или ожидаемую сумму")
        if rate is not None and rate < 0:
            raise ValidationError("Ставка не может быть отрицательной")
        if amount is not None and amount < 0:
            raise ValidationError("Сумма не может быть отрицательной")
        if received_date is None and status == PAYOUT_RECEIVED:
            received_date = pay_date
        return self.repo.add_payout(
            asset_id, kind, pay_date,
            round(rate, 6) if rate is not None else None,
            round(amount, 2) if amount is not None else None,
            asset.currency, status, received_date, source, rule_id, note,
        )

    def update_payout(
        self, payout_id: int, kind: str, pay_date: date,
        rate: float | None = None, amount: float | None = None,
        status: str = PAYOUT_EXPECTED, received_date: date | None = None,
        note: str = "",
    ) -> None:
        existing = self.repo.get_payout(payout_id)
        if existing is None:
            raise ValidationError("Выплата не найдена")
        kind = validate_payout_kind(kind)
        if status not in (PAYOUT_EXPECTED, PAYOUT_RECEIVED):
            raise ValidationError("Неизвестный статус выплаты")
        if status == PAYOUT_RECEIVED and (amount is None or amount < 0):
            raise ValidationError("Укажите полученную сумму")
        if status == PAYOUT_EXPECTED and rate is None and amount is None:
            raise ValidationError("Укажите ставку на единицу или ожидаемую сумму")
        if rate is not None and rate < 0:
            raise ValidationError("Ставка не может быть отрицательной")
        if amount is not None and amount < 0:
            raise ValidationError("Сумма не может быть отрицательной")
        self.repo.update_payout(
            payout_id, kind, pay_date,
            round(rate, 6) if rate is not None else None,
            round(amount, 2) if amount is not None else None,
            existing.currency, status, received_date, note,
        )

    def remove_payout(self, payout_id: int) -> None:
        self.repo.delete_payout(payout_id)

    def mark_payout_received(
        self, payout_id: int, amount: float, received_date: date | None = None,
    ) -> None:
        payout = self.repo.get_payout(payout_id)
        if payout is None:
            raise ValidationError("Выплата не найдена")
        if amount is None or amount < 0:
            raise ValidationError("Сумма не может быть отрицательной")
        self.repo.update_payout(
            payout_id, payout.kind, payout.pay_date, payout.rate,
            round(amount, 2), payout.currency, PAYOUT_RECEIVED,
            received_date or date.today(), payout.note,
        )

    def receive_entry(
        self, entry: PayoutEntry, amount: float, received_date: date | None = None,
    ) -> None:
        """Отметить выплату календаря полученной.

        Для сохранённой выплаты меняет статус, для вхождения правила —
        материализует запись, которая перекроет вхождение в тот же день.
        """
        if amount is None or amount < 0:
            raise ValidationError("Сумма не может быть отрицательной")
        when = received_date or entry.date
        if entry.payout_id is not None:
            self.mark_payout_received(entry.payout_id, amount, when)
            return
        self.create_payout(
            entry.asset_id, entry.kind, entry.date, rate=entry.rate,
            amount=amount, status=PAYOUT_RECEIVED, received_date=when,
            note=entry.note, source=entry.source or "rule", rule_id=entry.rule_id,
        )

    def due_past_payouts(
        self, asset_id: int | None = None, months: int = PAST_PAYOUT_MONTHS,
    ) -> list[PayoutEntry]:
        """Прошедшие ожидаемые выплаты, которые ещё не отмечены полученными."""
        today = date.today()
        start = add_months(today, -months)
        entries = self.calendar_entries(start, today, asset_id)
        return [e for e in entries if e.is_due]

    def expected_payout_amount(self, payout: Payout) -> float:
        asset = self.repo.get_asset(payout.asset_id)
        quantity = asset.quantity if asset else 0.0
        return payout.expected(quantity)

    def holding_quantity_at(self, asset_id: int, day: date) -> float:
        """Количество актива на конец указанного дня по сделкам."""
        total = 0.0
        for trade in self.repo.list_trades(asset_id):
            if trade.trade_date <= day:
                total += trade.quantity if trade.kind == BUY else -trade.quantity
        return total

    # --- автообновление ---

    def auto_settings(self) -> AutoRefreshSettings:
        def flag(key: str, default: bool) -> bool:
            raw = self.repo.get_setting(key)
            if raw is None:
                return default
            return raw == "1"

        def number(key: str, default: int, minimum: int) -> int:
            raw = self.repo.get_setting(key)
            try:
                value = int(raw)
            except (TypeError, ValueError):
                return default
            return value if value >= minimum else default

        return AutoRefreshSettings(
            price_enabled=flag(AUTO_PRICE_ENABLED_KEY, True),
            price_minutes=number(
                AUTO_PRICE_MINUTES_KEY, DEFAULT_PRICE_MINUTES, MIN_PRICE_MINUTES
            ),
            payout_enabled=flag(AUTO_PAYOUT_ENABLED_KEY, True),
            payout_hours=number(
                AUTO_PAYOUT_HOURS_KEY, DEFAULT_PAYOUT_HOURS, MIN_PAYOUT_HOURS
            ),
        )

    def save_auto_settings(self, settings: AutoRefreshSettings) -> None:
        self.repo.set_setting(
            AUTO_PRICE_ENABLED_KEY, "1" if settings.price_enabled else "0"
        )
        self.repo.set_setting(
            AUTO_PRICE_MINUTES_KEY,
            str(max(MIN_PRICE_MINUTES, int(settings.price_minutes))),
        )
        self.repo.set_setting(
            AUTO_PAYOUT_ENABLED_KEY, "1" if settings.payout_enabled else "0"
        )
        self.repo.set_setting(
            AUTO_PAYOUT_HOURS_KEY,
            str(max(MIN_PAYOUT_HOURS, int(settings.payout_hours))),
        )

    def last_sync(self, key: str) -> str | None:
        return self.repo.get_setting(key)

    def mark_synced(self, key: str) -> None:
        from .quotes import now_iso

        self.repo.set_setting(key, now_iso())

    # --- правила выплат ---

    def payout_rules(self, asset_id: int | None = None) -> list[PayoutRule]:
        return self.repo.list_payout_rules(asset_id)

    def create_payout_rule(
        self, asset_id: int, kind: str, rate: float, period: str, anchor: date,
        note: str = "",
    ) -> int:
        asset = self.repo.get_asset(asset_id)
        if asset is None:
            raise ValidationError("Актив не найден")
        kind = validate_payout_kind(kind)
        period = validate_period(period)
        if rate is None or rate <= 0:
            raise ValidationError("Ставка должна быть больше нуля")
        return self.repo.add_payout_rule(
            asset_id, kind, round(rate, 6), period, anchor, asset.currency, note
        )

    def remove_payout_rule(self, rule_id: int) -> None:
        self.repo.delete_payout_rule(rule_id)

    @staticmethod
    def rule_dates(rule: PayoutRule, date_from: date, date_to: date) -> list[date]:
        anchor = rule.anchor
        if rule.period == PERIOD_ONCE:
            return [anchor] if date_from <= anchor <= date_to else []
        step = PERIOD_MONTHS.get(rule.period)
        if not step:
            return []
        current = anchor
        guard = 0
        while current < date_from and guard < 4000:
            current = add_months(current, step)
            guard += 1
        dates: list[date] = []
        while current <= date_to and guard < 8000:
            if current >= date_from:
                dates.append(current)
            current = add_months(current, step)
            guard += 1
        return dates

    def calendar_entries(
        self, date_from: date, date_to: date, asset_id: int | None = None,
    ) -> list[PayoutEntry]:
        assets = {a.id: a for a in self.repo.list_assets()}
        entries: list[PayoutEntry] = []
        taken: set[tuple[int, date]] = set()
        today = date.today()
        trades_cache: dict[int, list[Trade]] = {}

        def quantity_at(asset_id: int, day: date) -> float | None:
            """Количество на дату; None для будущих дат (не требуется)."""
            if day > today:
                return None
            trades = trades_cache.get(asset_id)
            if trades is None:
                trades = self.repo.list_trades(asset_id)
                trades_cache[asset_id] = trades
            return sum(
                t.quantity if t.kind == BUY else -t.quantity
                for t in trades
                if t.trade_date <= day
            )

        for payout in self.repo.list_payouts(asset_id, date_from, date_to):
            asset = assets.get(payout.asset_id)
            quantity = asset.quantity if asset else 0.0
            entries.append(
                PayoutEntry(
                    date=payout.pay_date,
                    asset_id=payout.asset_id,
                    asset_name=payout.asset_name,
                    kind=payout.kind,
                    currency=payout.currency,
                    expected=payout.expected(quantity),
                    status=payout.status,
                    source=payout.source,
                    payout_id=payout.id,
                    rule_id=payout.rule_id,
                    received=payout.amount,
                    note=payout.note,
                    rate=payout.rate,
                    quantity_at=quantity_at(payout.asset_id, payout.pay_date),
                )
            )
            taken.add((payout.asset_id, payout.pay_date))
        for rule in self.repo.list_payout_rules():
            if not rule.active:
                continue
            if asset_id is not None and rule.asset_id != asset_id:
                continue
            asset = assets.get(rule.asset_id)
            quantity = asset.quantity if asset else 0.0
            for day in self.rule_dates(rule, date_from, date_to):
                if (rule.asset_id, day) in taken:
                    continue
                entries.append(
                    PayoutEntry(
                        date=day,
                        asset_id=rule.asset_id,
                        asset_name=rule.asset_name,
                        kind=rule.kind,
                        currency=rule.currency,
                        expected=rule.rate * quantity,
                        status=PAYOUT_EXPECTED,
                        source="rule",
                        rule_id=rule.id,
                        note=rule.note,
                        rate=rule.rate,
                        quantity_at=quantity_at(rule.asset_id, day),
                    )
                )
        entries.sort(key=lambda e: (e.date, e.asset_name.lower()))
        return entries

    def payout_calendar_totals(
        self, date_from: date, date_to: date, asset_id: int | None = None,
    ) -> tuple[float, float]:
        """(ожидаемые, полученные) выплаты за период (в валюте активов)."""
        entries = self.calendar_entries(date_from, date_to, asset_id)
        expected = sum(
            e.expected for e in entries if not e.is_received
        )
        received = sum(
            (e.received if e.received is not None else e.expected)
            for e in entries if e.is_received
        )
        return expected, received

    # --- онлайн-выплаты ---

    @staticmethod
    def _project_dividends(
        history: list[tuple[date, float]], horizon_months: int = 12, limit: int = 12,
    ) -> list[tuple[date, float]]:
        """Оценка будущих дивидендов по истории (для акций США)."""
        if not history:
            return []
        history = sorted(history)
        last_date, last_amount = history[-1]
        if last_amount <= 0:
            return []
        gaps = [
            (history[i][0] - history[i - 1][0]).days
            for i in range(1, len(history))
        ][-4:]
        if gaps:
            average = sum(gaps) / len(gaps)
            step = 1 if average <= 45 else 3 if average <= 135 else 12
        else:
            step = 3
        today = date.today()
        horizon = add_months(today, horizon_months)
        out: list[tuple[date, float]] = []
        moment = add_months(last_date, step)
        while moment <= horizon and len(out) < limit:
            if moment >= today:
                out.append((moment, last_amount))
            moment = add_months(moment, step)
        return out

    def fetch_payouts(
        self, assets: list[Asset] | None = None, opener=None,
        include_past: bool = False,
    ) -> PayoutFetch:
        """Только сеть, без записи в базу (можно вызывать из потока).

        Для бумаг MOEX — график купонов с ISS и дивиденды со smart-lab,
        для бумаг США — прогноз по истории дивидендов Yahoo (а при
        include_past — ещё и прошедшие дивиденды из истории).
        """
        from . import quotes

        assets = self.repo.list_assets() if assets is None else assets
        result = PayoutFetch()
        ru_calendar: list[dict] | None = None
        for asset in assets:
            ticker = (asset.ticker or "").strip()
            if not ticker:
                continue
            if asset.market == MARKET_MOEX:
                try:
                    coupons = quotes.fetch_bond_coupons(ticker, opener=opener)
                except quotes.QuoteError as exc:
                    coupons = []
                    result.failures.append(f"{ticker} (купоны): {exc}")
                for when, value in coupons:
                    result.payouts.append({
                        "asset_id": asset.id, "kind": PAYOUT_COUPON,
                        "date": when, "rate": value, "source": "moex",
                        "note": "MOEX: купон",
                    })
                if ru_calendar is None:
                    try:
                        ru_calendar = quotes.fetch_smartlab_dividends(opener=opener)
                    except quotes.QuoteError as exc:
                        ru_calendar = []
                        result.failures.append(f"smart-lab: {exc}")
                for row in ru_calendar:
                    if row["ticker"] != ticker.upper():
                        continue
                    when = row.get("pay_date") or row.get("close_date")
                    if when is None:
                        continue
                    result.payouts.append({
                        "asset_id": asset.id, "kind": PAYOUT_DIVIDEND,
                        "date": when, "rate": row["amount"], "source": "smartlab",
                        "note": f"smart-lab: дивиденд, {row.get('period', '')}".strip(),
                    })
            elif asset.market == MARKET_US:
                try:
                    history = quotes.fetch_yahoo_dividends(ticker, opener=opener)
                except quotes.QuoteError as exc:
                    result.failures.append(f"{ticker}: {exc}")
                    continue
                for when, rate in self._project_dividends(history):
                    result.payouts.append({
                        "asset_id": asset.id, "kind": PAYOUT_DIVIDEND,
                        "date": when, "rate": rate, "source": "yahoo",
                        "note": "Yahoo: прогноз дивиденда",
                    })
                if include_past:
                    for when, rate in history:
                        result.payouts.append({
                            "asset_id": asset.id, "kind": PAYOUT_DIVIDEND,
                            "date": when, "rate": rate, "source": "yahoo",
                            "note": "Yahoo: дивиденд",
                        })
        return result

    def apply_payout_fetch(
        self, fetched: PayoutFetch, include_past: bool = False,
    ) -> RefreshResult:
        """Запись найденных выплат в базу (в основном потоке).

        При include_past дополнительно добавляются прошедшие выплаты, но
        только если бумага была в портфеле на дату выплаты и дата не старше
        окна PAST_PAYOUT_MONTHS (и не раньше даты первой покупки).
        """
        added = 0
        today = date.today()
        window_start = add_months(today, -PAST_PAYOUT_MONTHS)
        by_asset: dict[int, list[dict]] = {}
        for spec in fetched.payouts:
            by_asset.setdefault(spec["asset_id"], []).append(spec)
        for asset_id, specs in by_asset.items():
            asset = self.repo.get_asset(asset_id)
            if asset is None:
                continue
            existing = {
                (p.kind, p.pay_date) for p in self.repo.list_payouts(asset_id)
            }
            start = window_start
            if asset.first_buy is not None and asset.first_buy > start:
                start = asset.first_buy
            for spec in specs:
                when = spec.get("date")
                if when is None:
                    continue
                rate = spec.get("rate")
                if rate is None or rate <= 0:
                    continue
                if when < today:
                    if not include_past or when < start:
                        continue
                    if self.holding_quantity_at(asset_id, when) <= 0:
                        continue
                key = (spec["kind"], when)
                if key in existing:
                    continue
                self.repo.add_payout(
                    asset_id, spec["kind"], when, round(rate, 6), None,
                    asset.currency, PAYOUT_EXPECTED, None,
                    spec.get("source", ""), None, spec.get("note", ""),
                )
                existing.add(key)
                added += 1
        return RefreshResult(updated=added, failed=list(fetched.failures))

    def sync_payouts(self, opener=None, include_past: bool = False) -> RefreshResult:
        return self.apply_payout_fetch(
            self.fetch_payouts(opener=opener, include_past=include_past),
            include_past=include_past,
        )
