"""Сервисный слой: фасад :class:`FinanceService` и доменные сервисы.

Пакет заменяет прежний модуль ``finance/services.py`` и полностью сохраняет
его публичный API: сюда реэкспортированы фасад, структуры данных и константы
настроек, поэтому внешние импорты продолжают работать без изменений.
"""
from __future__ import annotations

from .constants import (
    AUTO_PAYOUT_ENABLED_KEY,
    AUTO_PAYOUT_HOURS_KEY,
    AUTO_PRICE_ENABLED_KEY,
    AUTO_PRICE_MINUTES_KEY,
    DEFAULT_PAYOUT_HOURS,
    DEFAULT_PRICE_MINUTES,
    MIN_PAYOUT_HOURS,
    MIN_PRICE_MINUTES,
    PAST_PAYOUT_MONTHS,
    PAYOUTS_SYNCED_KEY,
    PRICES_UPDATED_KEY,
    RATES_UPDATED_KEY,
    RATE_EUR_KEY,
    RATE_USD_KEY,
)
from .core import ServiceBase
from .dto import (
    AutoRefreshSettings,
    ImportSummary,
    PayoutEntry,
    PayoutFetch,
    PriceFetch,
    RefreshResult,
)
from .facade import FinanceService
from .imports import ImportFormatError, ImportedOperation, ImportService
from .investments import InvestmentService
from .payouts import PayoutService
from .quotes import QuoteService
from .sync import SyncService
from .transactions import TransactionService

__all__ = [
    # фасад и доменные сервисы
    "FinanceService",
    "ServiceBase",
    "TransactionService",
    "ImportService",
    "ImportedOperation",
    "ImportFormatError",
    "InvestmentService",
    "QuoteService",
    "PayoutService",
    "SyncService",
    # структуры данных
    "AutoRefreshSettings",
    "ImportSummary",
    "PriceFetch",
    "RefreshResult",
    "PayoutFetch",
    "PayoutEntry",
    # ключи и параметры настроек
    "RATE_USD_KEY",
    "RATE_EUR_KEY",
    "RATES_UPDATED_KEY",
    "PRICES_UPDATED_KEY",
    "PAYOUTS_SYNCED_KEY",
    "AUTO_PRICE_ENABLED_KEY",
    "AUTO_PRICE_MINUTES_KEY",
    "AUTO_PAYOUT_ENABLED_KEY",
    "AUTO_PAYOUT_HOURS_KEY",
    "DEFAULT_PRICE_MINUTES",
    "DEFAULT_PAYOUT_HOURS",
    "MIN_PRICE_MINUTES",
    "MIN_PAYOUT_HOURS",
    "PAST_PAYOUT_MONTHS",
]
