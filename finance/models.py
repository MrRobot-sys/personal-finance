"""Модели данных, валидация и форматирование."""
from __future__ import annotations

import math
import re
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime

INCOME = "income"
EXPENSE = "expense"
INVEST = "invest"
KIND_LABELS = {INCOME: "Доход", EXPENSE: "Расход", INVEST: "Инвестировано"}
# Планы и статистика доходов/расходов не учитывают инвестиционные операции.
PLAN_KINDS = (INCOME, EXPENSE)
ALL_KINDS = (INCOME, EXPENSE, INVEST)

# --- инвестиции и имущество ---

BUY = "buy"
SELL = "sell"
TRADE_LABELS = {BUY: "Покупка", SELL: "Продажа"}

MARKET_MOEX = "moex"
MARKET_US = "us"
MARKET_MANUAL = "manual"
MARKET_PHYSICAL = "physical"
MARKET_LABELS = {
    MARKET_MOEX: "MOEX",
    MARKET_US: "США",
    MARKET_MANUAL: "Вручную",
    MARKET_PHYSICAL: "Имущество",
}
MARKETS = tuple(MARKET_LABELS)
# Биржевые активы обновляются онлайн, имущество и «вручную» — только оценкой.
ONLINE_MARKETS = (MARKET_MOEX, MARKET_US)

CURRENCIES = ("RUB", "USD", "EUR")
CURRENCY_SYMBOLS = {"RUB": "₽", "USD": "$", "EUR": "€"}

PHYSICAL_CATEGORIES = (
    "Недвижимость", "Транспорт", "Техника",
    "Драгметаллы", "Коллекции", "Прочее",
)
SECURITY_CATEGORIES = ("Акции", "Фонды/ETF", "Облигации", "Прочее")
MANUAL_CATEGORIES = ("Вклады", "Наличные", "Прочее")

# Набор категорий зависит от типа актива.
MARKET_CATEGORIES = {
    MARKET_MOEX: SECURITY_CATEGORIES,
    MARKET_US: SECURITY_CATEGORIES,
    MARKET_MANUAL: MANUAL_CATEGORIES,
    MARKET_PHYSICAL: PHYSICAL_CATEGORIES,
}


def categories_for(market: str) -> tuple[str, ...]:
    return MARKET_CATEGORIES.get(market, ())


# --- подсказки бумаг при добавлении актива (онлайн-поиск) ---

SECURITY_AKTSII = "Акции"
SECURITY_FUNDS = "Фонды/ETF"
SECURITY_BONDS = "Облигации"
SECURITY_OTHER = "Прочее"

_MOEX_SHARE_TYPES = ("common_share", "preferred_share", "depositary_receipt")
_MOEX_FUND_TYPES = ("ppif", "etf", "fund")
_MOEX_SHARE_GROUPS = ("stock_shares", "stock_dr")
_MOEX_FUND_GROUPS = ("stock_ppif",)


@dataclass(frozen=True)
class SecurityMatch:
    """Бумага, найденная онлайн, для подсказки в диалоге актива."""

    ticker: str
    name: str
    currency: str
    category: str
    market: str
    detail: str = ""

    @property
    def label(self) -> str:
        text = f"{self.ticker} — {self.name}" if self.name else self.ticker
        return f"{text} ({self.detail})" if self.detail else text


def category_for_moex(type_: str | None, group: str | None) -> str:
    """Категория портфеля по типу/группе бумаги MOEX ISS."""
    kind = (type_ or "").lower()
    grp = (group or "").lower()
    if "bond" in kind or grp == "stock_bonds":
        return SECURITY_BONDS
    if any(token in kind for token in _MOEX_FUND_TYPES) or grp in _MOEX_FUND_GROUPS:
        return SECURITY_FUNDS
    if any(token in kind for token in _MOEX_SHARE_TYPES) or grp in _MOEX_SHARE_GROUPS:
        return SECURITY_AKTSII
    return SECURITY_OTHER


def category_for_yahoo(quote_type: str | None) -> str:
    """Категория портфеля по quoteType из Yahoo Finance search."""
    kind = (quote_type or "").upper()
    if kind == "EQUITY":
        return SECURITY_AKTSII
    if kind in ("ETF", "MUTUALFUND"):
        return SECURITY_FUNDS
    return SECURITY_OTHER


SCOPE_SECURITIES = "securities"
SCOPE_PROPERTY = "property"
SCOPE_LABELS = {None: "Все активы", SCOPE_SECURITIES: "Биржевые", SCOPE_PROPERTY: "Имущество"}

# --- выплаты (дивиденды, купоны) ---

PAYOUT_DIVIDEND = "dividend"
PAYOUT_COUPON = "coupon"
PAYOUT_OTHER = "other"
PAYOUT_KINDS = (PAYOUT_DIVIDEND, PAYOUT_COUPON, PAYOUT_OTHER)
PAYOUT_KIND_LABELS = {
    PAYOUT_DIVIDEND: "Дивиденд",
    PAYOUT_COUPON: "Купон",
    PAYOUT_OTHER: "Выплата",
}

PAYOUT_EXPECTED = "expected"
PAYOUT_RECEIVED = "received"
PAYOUT_STATUS_LABELS = {
    PAYOUT_EXPECTED: "Ожидается",
    PAYOUT_RECEIVED: "Получено",
}

PERIOD_ONCE = "once"
PERIOD_MONTHLY = "monthly"
PERIOD_QUARTERLY = "quarterly"
PERIOD_YEARLY = "yearly"
PERIODS = (PERIOD_ONCE, PERIOD_MONTHLY, PERIOD_QUARTERLY, PERIOD_YEARLY)
PERIOD_LABELS = {
    PERIOD_ONCE: "Разово",
    PERIOD_MONTHLY: "Ежемесячно",
    PERIOD_QUARTERLY: "Ежеквартально",
    PERIOD_YEARLY: "Ежегодно",
}
PERIOD_MONTHS = {
    PERIOD_MONTHLY: 1,
    PERIOD_QUARTERLY: 3,
    PERIOD_YEARLY: 12,
}

MONTH_NAMES = (
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
)


class ValidationError(ValueError):
    """Некорректные данные формы."""


@dataclass(frozen=True)
class Category:
    id: int
    name: str
    kind: str
    monthly_limit: float | None = None


@dataclass(frozen=True)
class Transaction:
    id: int
    category_id: int
    amount: float
    txn_date: date
    note: str = ""
    category_name: str = ""
    kind: str = EXPENSE


@dataclass
class CategoryPlan:
    """Среднее за 3 месяца, факт и план по категории."""
    category: Category
    spent: float = 0.0
    avg_3: float | None = None

    @property
    def limit(self) -> float | None:
        return self.category.monthly_limit

    @property
    def ratio(self) -> float:
        if self.limit is None or self.limit <= 0:
            return 0.0
        return self.spent / self.limit

    @property
    def percent(self) -> int:
        return round(self.ratio * 100)

    @property
    def has_limit(self) -> bool:
        return self.limit is not None and self.limit > 0

    @property
    def is_over(self) -> bool:
        """Перерасход: у расходной категории факт превысил план."""
        return self.category.kind == EXPENSE and self.has_limit and self.spent > self.limit

    @property
    def status(self) -> str:
        """Хорошо/плохо по сравнению среднего за 3 месяца с планом."""
        if self.avg_3 is None or not self.has_limit:
            return "neutral"
        if self.category.kind == INCOME:
            return "good" if self.avg_3 >= self.limit else "bad"
        return "good" if self.avg_3 <= self.limit else "bad"


@dataclass
class MonthSummary:
    year: int
    month: int
    income: float = 0.0
    expense: float = 0.0
    invested: float = 0.0

    @property
    def balance(self) -> float:
        return self.income - self.expense

    @property
    def label(self) -> str:
        return f"{MONTH_NAMES[self.month - 1]} {self.year}"


@dataclass(frozen=True)
class Trade:
    """Сделка купли/продажи актива."""
    id: int
    asset_id: int
    kind: str
    quantity: float
    price: float
    trade_date: date
    fee: float = 0.0
    note: str = ""

    @property
    def gross(self) -> float:
        return self.quantity * self.price


@dataclass(frozen=True)
class PricePoint:
    """Сохранённая цена/оценка актива на дату."""
    asset_id: int
    price: float
    currency: str
    source: str
    fetched_at: str


@dataclass(frozen=True)
class Asset:
    """Позиция портфеля: инструмент или объект имущества."""
    id: int
    name: str
    market: str
    ticker: str = ""
    currency: str = "RUB"
    category: str = ""
    details: str = ""
    depreciation_rate: float | None = None
    note: str = ""
    quantity: float = 0.0
    avg_price: float = 0.0
    invested: float = 0.0
    proceeds: float = 0.0
    realized: float = 0.0
    first_buy: date | None = None
    last_price: float | None = None
    last_price_at: str = ""
    price_source: str = ""

    @property
    def is_physical(self) -> bool:
        return self.market == MARKET_PHYSICAL

    @property
    def cost_basis(self) -> float:
        """Стоимость приобретения остатка позиции."""
        return self.quantity * self.avg_price

    @property
    def current_price(self) -> float:
        return self.last_price if self.last_price is not None else self.avg_price

    @property
    def market_value(self) -> float:
        return self.quantity * self.current_price

    @property
    def profit(self) -> float:
        """Нереализованная прибыль (стоимость минус вложения)."""
        return self.market_value - self.cost_basis

    @property
    def profit_percent(self) -> float:
        if not self.cost_basis:
            return 0.0
        return self.profit / self.cost_basis * 100

    @property
    def has_price(self) -> bool:
        return self.last_price is not None

    @property
    def years_held(self) -> float:
        if self.first_buy is None:
            return 0.0
        return max(0.0, (date.today() - self.first_buy).days / 365.25)

    @property
    def residual_value(self) -> float | None:
        """Оценка с учётом годового износа (справочно, для имущества)."""
        if self.depreciation_rate is None:
            return None
        factor = 1 - self.depreciation_rate / 100 * self.years_held
        return max(0.0, self.cost_basis * factor)


@dataclass
class PortfolioTotals:
    invested: float = 0.0
    value: float = 0.0
    realized: float = 0.0

    @property
    def profit(self) -> float:
        return self.value - self.invested

    @property
    def profit_percent(self) -> float:
        if not self.invested:
            return 0.0
        return self.profit / self.invested * 100


@dataclass
class PortfolioSummary:
    """Сводка портфеля: биржевые, имущество и итог (в рублях).

    Пул: ``contributed`` — сколько внесено инвестиционными операциями,
    ``deployed`` — сколько вложено в активы (покупки минус продажи),
    ``free`` — свободный остаток пула.
    """
    securities: PortfolioTotals
    property: PortfolioTotals
    total: PortfolioTotals
    currency: str = "RUB"
    usd_rub: float | None = None
    eur_rub: float | None = None
    contributed: float = 0.0
    deployed: float = 0.0

    @property
    def free(self) -> float:
        return self.contributed - self.deployed


@dataclass(frozen=True)
class Payout:
    """Плановая или полученная выплата по активу.

    ``rate`` — сумма на единицу актива (за акцию/облигацию), ``amount`` —
    фактически полученная сумма. Ожидаемая сумма считается как
    ``rate * текущее количество``, поэтому она автоматически меняется
    при изменении позиции.
    """
    id: int
    asset_id: int
    kind: str
    pay_date: date
    rate: float | None = None
    amount: float | None = None
    currency: str = "RUB"
    status: str = PAYOUT_EXPECTED
    received_date: date | None = None
    source: str = ""
    rule_id: int | None = None
    note: str = ""
    asset_name: str = ""

    @property
    def is_received(self) -> bool:
        return self.status == PAYOUT_RECEIVED

    def expected(self, quantity: float) -> float:
        """Ожидаемая сумма с учётом текущего количества актива."""
        if self.rate is not None:
            return self.rate * quantity
        return self.amount or 0.0


@dataclass(frozen=True)
class PayoutRule:
    """Правило повторяющихся выплат: купон или дивиденд с периодичностью."""
    id: int
    asset_id: int
    kind: str
    rate: float
    period: str
    anchor: date
    currency: str = "RUB"
    note: str = ""
    active: bool = True
    asset_name: str = ""


def add_months(value: date, months: int) -> date:
    """Сдвигает дату на месяцы вперёд, сохраняя день (с поправкой на конец месяца)."""
    total = value.year * 12 + (value.month - 1) + months
    year, month0 = divmod(total, 12)
    month = month0 + 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


def validate_market(market: str) -> str:
    if market not in MARKETS:
        raise ValidationError("Неизвестный тип актива")
    return market


def validate_currency(currency: str) -> str:
    if currency not in CURRENCIES:
        raise ValidationError("Неизвестная валюта")
    return currency


def validate_asset_name(name: str) -> str:
    text = (name or "").strip()
    if not text:
        raise ValidationError("Введите название актива")
    if len(text) > 80:
        raise ValidationError("Название актива слишком длинное (макс. 80)")
    return text


def parse_optional_number(raw: str | None) -> float | None:
    """Необязательное неотрицательное число (например, годовой износ)."""
    if raw is None or not str(raw).strip():
        return None
    cleaned = str(raw).strip().replace("\u00a0", "").replace(" ", "").replace(",", ".")
    cleaned = cleaned.replace("%", "")
    if not re.fullmatch(r"\d+(\.\d+)?", cleaned):
        raise ValidationError("Значение должно быть числом, например 2 или 2,5")
    value = float(cleaned)
    if not math.isfinite(value) or value < 0:
        raise ValidationError("Значение не может быть отрицательным")
    return round(value, 2)


def format_amount(value: float) -> str:
    text = f"{value:,.2f}".replace(",", "\u00a0").replace(".", ",")
    return f"{text}\u00a0₽"


def format_currency_amount(value: float, currency: str = "RUB") -> str:
    """Сумма с символом нужной валюты (₽/$/€)."""
    symbol = CURRENCY_SYMBOLS.get(currency, currency)
    text = f"{value:,.2f}".replace(",", "\u00a0").replace(".", ",")
    return f"{text}\u00a0{symbol}"


def format_quantity(value: float) -> str:
    """Число без символа валюты, без лишних нулей (для количества и цен)."""
    text = f"{value:,.4f}".replace(",", "\u00a0").replace(".", ",")
    if "," in text:
        text = text.rstrip("0").rstrip(",")
    return text


def parse_optional_amount(raw: str | None) -> float | None:
    """Пустая строка — «нет плана», иначе обязательная положительная сумма."""
    if raw is None:
        return None
    if not raw.strip():
        return None
    return parse_amount(raw)


def parse_amount(raw: str) -> float:
    if raw is None:
        raise ValidationError("Введите сумму")
    cleaned = raw.strip().replace("\u00a0", "").replace(" ", "").replace("₽", "")
    if not cleaned:
        raise ValidationError("Введите сумму")
    cleaned = cleaned.replace(",", ".")
    if not re.fullmatch(r"\d+(\.\d+)?", cleaned):
        raise ValidationError("Сумма должна быть числом, например 1500 или 1500,50")
    value = float(cleaned)
    if not math.isfinite(value) or value <= 0:
        raise ValidationError("Сумма должна быть больше нуля")
    return round(value, 2)


def format_date(value: date) -> str:
    return value.strftime("%d.%m.%Y")


def parse_date(raw: str) -> date:
    text = (raw or "").strip()
    if not text:
        raise ValidationError("Введите дату")
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValidationError("Дата в формате ДД.ММ.ГГГГ, например 06.10.2026")


def month_key(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def month_range(year: int, month: int) -> tuple[date, date]:
    first = date(year, month, 1)
    if month == 12:
        nxt = date(year + 1, 1, 1)
    else:
        nxt = date(year, month + 1, 1)
    return first, nxt.fromordinal(nxt.toordinal() - 1)


def previous_months(year: int, month: int, count: int) -> list[tuple[int, int]]:
    result = []
    cy, cm = year, month
    for _ in range(count):
        result.append((cy, cm))
        cm -= 1
        if cm == 0:
            cy, cm = cy - 1, 12
    result.reverse()
    return result


def validate_category_name(name: str) -> str:
    text = (name or "").strip()
    if not text:
        raise ValidationError("Введите название категории")
    if len(text) > 60:
        raise ValidationError("Название категории слишком длинное (макс. 60)")
    return text


def validate_kind(kind: str) -> str:
    if kind not in ALL_KINDS:
        raise ValidationError("Выберите тип: доход, расход или инвестиции")
    return kind


def validate_payout_kind(kind: str) -> str:
    if kind not in PAYOUT_KINDS:
        raise ValidationError("Выберите тип выплаты")
    return kind


def validate_period(period: str) -> str:
    if period not in PERIODS:
        raise ValidationError("Выберите периодичность")
    return period
