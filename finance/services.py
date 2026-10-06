"""Бизнес-логика поверх репозитория."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from .models import (
    EXPENSE,
    INCOME,
    Category,
    CategoryPlan,
    MonthSummary,
    Transaction,
    ValidationError,
    parse_amount,
    parse_date,
    parse_optional_amount,
    validate_category_name,
    validate_kind,
)
from .repository import Repository


@dataclass
class ImportSummary:
    imported: int = 0
    skipped_duplicates: int = 0
    skipped_category: int = 0


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
