"""Структуры данных сервисного слоя.

Здесь собраны настройки, результаты сетевых обновлений и строки календаря
выплат — объекты, которыми доменные сервисы обмениваются с интерфейсом.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..models import PAYOUT_RECEIVED
from .constants import DEFAULT_PAYOUT_HOURS, DEFAULT_PRICE_MINUTES


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
