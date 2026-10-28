"""Фасад сервисного слоя.

:class:`FinanceService` остаётся единственной точкой входа для интерфейса:
он собирает доменные сервисы и делегирует им каждый вызов с прежней
сигнатурой. Публичный API не менялся — UI и самопроверка работают без правок.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import date

from ..models import (
    PAYOUT_EXPECTED,
    Asset,
    Category,
    CategoryPlan,
    MonthSummary,
    Payout,
    PayoutRule,
    PortfolioSummary,
    Trade,
    Transaction,
)
from ..repository import Repository
from .constants import PAST_PAYOUT_MONTHS
from .dto import (
    AutoRefreshSettings,
    ImportSummary,
    PayoutEntry,
    PayoutFetch,
    PriceFetch,
    RefreshResult,
)
from .imports import ImportService
from .investments import InvestmentService
from .payouts import PayoutService
from .quotes import QuoteService
from .sync import SyncService
from .transactions import TransactionService


class FinanceService:
    """Бизнес-логика приложения, собранная из доменных сервисов."""

    def __init__(self, repo: Repository):
        self.repo = repo
        self.transactions_service = TransactionService(repo)
        self.imports_service = ImportService(repo, self.transactions_service)
        self.quotes_service = QuoteService(repo)
        self.investments_service = InvestmentService(repo, self.quotes_service)
        self.payouts_service = PayoutService(repo)
        self.sync_service = SyncService(repo)

    # --- категории ---

    def categories(self, kind: str | None = None) -> list[Category]:
        return self.transactions_service.categories(kind)

    def create_category(
        self, name: str, kind: str, monthly_limit: float | None = None
    ) -> int:
        return self.transactions_service.create_category(name, kind, monthly_limit)

    def rename_category(
        self, category_id: int, name: str, kind: str,
        monthly_limit: float | None = None,
    ) -> None:
        self.transactions_service.rename_category(
            category_id, name, kind, monthly_limit
        )

    def remove_category(self, category_id: int, with_transactions: bool = False) -> int:
        return self.transactions_service.remove_category(category_id, with_transactions)

    def transaction(self, transaction_id: int) -> Transaction | None:
        return self.transactions_service.transaction(transaction_id)

    def category_usage(self, category_id: int) -> tuple[int, float]:
        return self.transactions_service.category_usage(category_id)

    # --- операции ---

    def transactions(
        self,
        kind: str | None = None,
        category_id: int | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        text: str | None = None,
    ) -> list[Transaction]:
        return self.transactions_service.transactions(
            kind, category_id, date_from, date_to, text
        )

    def create_transaction(
        self, category_id: int, amount: float, txn_date: date, note: str = "",
        source: str = "",
    ) -> int:
        return self.transactions_service.create_transaction(
            category_id, amount, txn_date, note, source
        )

    def update_transaction(
        self, transaction_id: int, category_id: int, amount: float,
        txn_date: date, note: str = "",
    ) -> None:
        self.transactions_service.update_transaction(
            transaction_id, category_id, amount, txn_date, note
        )

    def remove_transaction(self, transaction_id: int) -> None:
        self.transactions_service.remove_transaction(transaction_id)

    # --- планы по категориям ---

    def category_plans(self, year: int, month: int) -> list[CategoryPlan]:
        return self.transactions_service.category_plans(year, month)

    def set_monthly_plan(self, category_id: int, raw_plan: str | None) -> None:
        self.transactions_service.set_monthly_plan(category_id, raw_plan)

    # --- статистика ---

    def month_summary(self, year: int, month: int) -> MonthSummary:
        return self.transactions_service.month_summary(year, month)

    def month_breakdown(self, year: int, month: int) -> list[tuple[str, str, float]]:
        return self.transactions_service.month_breakdown(year, month)

    def dynamics(self, year: int, month: int, count: int = 12) -> list[MonthSummary]:
        return self.transactions_service.dynamics(year, month, count)

    def filtered_totals(self, transactions: list[Transaction]) -> tuple[float, float]:
        return self.transactions_service.filtered_totals(transactions)

    def invested_total(self) -> float:
        """Сумма всех инвестиционных операций (внесено в пул)."""
        return self.transactions_service.invested_total()

    @staticmethod
    def amount_from_text(raw: str) -> float:
        return TransactionService.amount_from_text(raw)

    @staticmethod
    def date_from_text(raw: str) -> date:
        return TransactionService.date_from_text(raw)

    # --- импорт ---

    def operation_sources(self) -> set[str]:
        return self.imports_service.operation_sources()

    def parse_operations(self, path) -> list:
        """Читает файл выписки и возвращает операции для импорта."""
        return self.imports_service.parse_operations(path)

    def import_operations(
        self,
        operations: list,
        resolver: Callable[[str, str], int | None],
        skip_existing: bool = True,
    ) -> ImportSummary:
        """Импортирует операции. resolver(name, kind) возвращает category_id или None."""
        return self.imports_service.import_operations(
            operations, resolver, skip_existing
        )

    def get_or_create_category(self, name: str, kind: str) -> int:
        return self.imports_service.get_or_create_category(name, kind)

    def import_category(
        self, name: str, kind: str, action: str,
        existing_id: int | None = None,
    ) -> int | None:
        """Разрешает категорию импорта по действию пользователя.
        action: 'existing' | 'create' | 'fallback'."""
        return self.imports_service.import_category(name, kind, action, existing_id)

    def _fallback_import_category(self, kind: str) -> int | None:
        return self.imports_service._fallback_import_category(kind)

    # --- инвестиции и имущество ---

    def assets(self, scope: str | None = None) -> list[Asset]:
        return self.investments_service.assets(scope)

    def asset(self, asset_id: int) -> Asset | None:
        return self.investments_service.asset(asset_id)

    def create_asset(
        self, name: str, market: str, ticker: str = "", currency: str = "RUB",
        category: str = "", details: str = "", depreciation_rate: float | None = None,
        note: str = "", quantity: float | None = None, price: float | None = None,
        trade_date: date | None = None, fee: float = 0.0,
    ) -> int:
        return self.investments_service.create_asset(
            name, market, ticker, currency, category, details,
            depreciation_rate, note, quantity, price, trade_date, fee,
        )

    def update_asset(
        self, asset_id: int, name: str, market: str, ticker: str = "",
        currency: str = "RUB", category: str = "", details: str = "",
        depreciation_rate: float | None = None, note: str = "",
    ) -> None:
        self.investments_service.update_asset(
            asset_id, name, market, ticker, currency, category, details,
            depreciation_rate, note,
        )

    @staticmethod
    def _validate_asset_fields(
        name, market, ticker, currency, category, depreciation_rate
    ):
        return InvestmentService._validate_asset_fields(
            name, market, ticker, currency, category, depreciation_rate
        )

    def remove_asset(self, asset_id: int) -> None:
        self.investments_service.remove_asset(asset_id)

    def trades(self, asset_id: int) -> list[Trade]:
        return self.investments_service.trades(asset_id)

    def add_trade(
        self, asset_id: int, kind: str, quantity: float, price: float,
        trade_date: date, fee: float = 0.0, note: str = "",
    ) -> int:
        return self.investments_service.add_trade(
            asset_id, kind, quantity, price, trade_date, fee, note
        )

    def remove_trade(self, trade_id: int) -> None:
        self.investments_service.remove_trade(trade_id)

    def set_manual_price(
        self, asset_id: int, price: float, on_date: date | None = None,
        source: str = "manual",
    ) -> None:
        self.investments_service.set_manual_price(
            asset_id, price, on_date, source
        )

    # --- курсы валют ---

    def rates(self) -> dict[str, float]:
        return self.quotes_service.rates()

    def set_rates(self, rates: dict[str, float]) -> None:
        self.quotes_service.set_rates(rates)

    def rate_to_rub(self, currency: str) -> float:
        return self.quotes_service.rate_to_rub(currency)

    # --- обновление цен ---

    def fetch_quotes(
        self, assets: list[Asset] | None = None, opener=None
    ) -> PriceFetch:
        """Только сеть, без записи в базу (можно вызывать из потока)."""
        return self.quotes_service.fetch_quotes(assets, opener)

    def apply_fetch(self, fetched: PriceFetch) -> RefreshResult:
        """Запись полученных цен и курсов в базу (в основном потоке)."""
        return self.quotes_service.apply_fetch(fetched)

    def refresh_prices(self, opener=None) -> RefreshResult:
        return self.quotes_service.refresh_prices(opener)

    # --- сводка портфеля ---

    def portfolio_summary(
        self, assets: list[Asset] | None = None
    ) -> PortfolioSummary:
        return self.investments_service.portfolio_summary(assets)

    def portfolio_history(self, scope: str | None = None) -> list[tuple[date, float]]:
        """Стоимость портфеля по датам оценок (в рублях, по текущему курсу)."""
        return self.investments_service.portfolio_history(scope)

    # --- выплаты (дивиденды, купоны) ---

    def payouts(
        self, asset_id: int | None = None,
        date_from: date | None = None, date_to: date | None = None,
    ) -> list[Payout]:
        return self.payouts_service.payouts(asset_id, date_from, date_to)

    def payout(self, payout_id: int) -> Payout | None:
        return self.payouts_service.payout(payout_id)

    def create_payout(
        self, asset_id: int, kind: str, pay_date: date,
        rate: float | None = None, amount: float | None = None,
        status: str = PAYOUT_EXPECTED, received_date: date | None = None,
        note: str = "", source: str = "manual", rule_id: int | None = None,
    ) -> int:
        return self.payouts_service.create_payout(
            asset_id, kind, pay_date, rate, amount, status,
            received_date, note, source, rule_id,
        )

    def update_payout(
        self, payout_id: int, kind: str, pay_date: date,
        rate: float | None = None, amount: float | None = None,
        status: str = PAYOUT_EXPECTED, received_date: date | None = None,
        note: str = "",
    ) -> None:
        self.payouts_service.update_payout(
            payout_id, kind, pay_date, rate, amount, status, received_date, note
        )

    def remove_payout(self, payout_id: int) -> None:
        self.payouts_service.remove_payout(payout_id)

    def mark_payout_received(
        self, payout_id: int, amount: float, received_date: date | None = None,
    ) -> None:
        self.payouts_service.mark_payout_received(
            payout_id, amount, received_date
        )

    def receive_entry(
        self, entry: PayoutEntry, amount: float, received_date: date | None = None,
    ) -> None:
        """Отметить выплату календаря полученной."""
        self.payouts_service.receive_entry(entry, amount, received_date)

    def due_past_payouts(
        self, asset_id: int | None = None, months: int = PAST_PAYOUT_MONTHS,
    ) -> list[PayoutEntry]:
        """Прошедшие ожидаемые выплаты, которые ещё не отмечены полученными."""
        return self.payouts_service.due_past_payouts(asset_id, months)

    def expected_payout_amount(self, payout: Payout) -> float:
        return self.payouts_service.expected_payout_amount(payout)

    def holding_quantity_at(self, asset_id: int, day: date) -> float:
        """Количество актива на конец указанного дня по сделкам."""
        return self.payouts_service.holding_quantity_at(asset_id, day)

    # --- автообновление ---

    def auto_settings(self) -> AutoRefreshSettings:
        return self.sync_service.auto_settings()

    def save_auto_settings(self, settings: AutoRefreshSettings) -> None:
        self.sync_service.save_auto_settings(settings)

    def last_sync(self, key: str) -> str | None:
        return self.sync_service.last_sync(key)

    def mark_synced(self, key: str) -> None:
        self.sync_service.mark_synced(key)

    # --- правила выплат ---

    def payout_rules(self, asset_id: int | None = None) -> list[PayoutRule]:
        return self.payouts_service.payout_rules(asset_id)

    def create_payout_rule(
        self, asset_id: int, kind: str, rate: float, period: str, anchor: date,
        note: str = "",
    ) -> int:
        return self.payouts_service.create_payout_rule(
            asset_id, kind, rate, period, anchor, note
        )

    def remove_payout_rule(self, rule_id: int) -> None:
        self.payouts_service.remove_payout_rule(rule_id)

    @staticmethod
    def rule_dates(rule: PayoutRule, date_from: date, date_to: date) -> list[date]:
        return PayoutService.rule_dates(rule, date_from, date_to)

    def calendar_entries(
        self, date_from: date, date_to: date, asset_id: int | None = None,
    ) -> list[PayoutEntry]:
        return self.payouts_service.calendar_entries(date_from, date_to, asset_id)

    def payout_calendar_totals(
        self, date_from: date, date_to: date, asset_id: int | None = None,
    ) -> tuple[float, float]:
        """(ожидаемые, полученные) выплаты за период (в валюте активов)."""
        return self.payouts_service.payout_calendar_totals(
            date_from, date_to, asset_id
        )

    # --- онлайн-выплаты ---

    @staticmethod
    def _project_dividends(
        history: list[tuple[date, float]], horizon_months: int = 12, limit: int = 12,
    ) -> list[tuple[date, float]]:
        """Оценка будущих дивидендов по истории (для акций США)."""
        return PayoutService._project_dividends(history, horizon_months, limit)

    def fetch_payouts(
        self, assets: list[Asset] | None = None, opener=None,
        include_past: bool = False,
    ) -> PayoutFetch:
        """Только сеть, без записи в базу (можно вызывать из потока)."""
        return self.payouts_service.fetch_payouts(assets, opener, include_past)

    def apply_payout_fetch(
        self, fetched: PayoutFetch, include_past: bool = False,
    ) -> RefreshResult:
        """Запись найденных выплат в базу (в основном потоке)."""
        return self.payouts_service.apply_payout_fetch(fetched, include_past)

    def sync_payouts(self, opener=None, include_past: bool = False) -> RefreshResult:
        return self.payouts_service.sync_payouts(opener, include_past)
