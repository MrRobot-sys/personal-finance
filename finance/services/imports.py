"""Домен импорта: источники операций и разрешение категорий."""
from __future__ import annotations

from collections.abc import Callable

from ..importers import ImportFormatError, ImportedOperation, read_operations
from ..models import ValidationError, validate_category_name, validate_kind
from ..repository import Repository
from .core import ServiceBase
from .dto import ImportSummary
from .transactions import TransactionService


class ImportService(ServiceBase):
    """Импорт банковских операций поверх домена транзакций.

    Категории создаются и находятся через :class:`TransactionService`,
    чтобы правила валидации оставались в одном месте.
    """

    def __init__(self, repo: Repository, transactions: TransactionService):
        super().__init__(repo)
        self.transactions = transactions

    def operation_sources(self) -> set[str]:
        return set(self.repo.list_sources())

    def parse_operations(self, path: str) -> list[ImportedOperation]:
        """Читает файл выписки и возвращает операции для импорта."""
        return read_operations(path)

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
            self.transactions.create_transaction(
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
        return self.transactions.create_category(name, kind)

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
                return self.transactions.create_category(name, kind)
            except ValidationError:
                pass
        return self._fallback_import_category(kind)

    def _fallback_import_category(self, kind: str) -> int | None:
        existing = self.repo.category_by_name("Прочее", kind)
        if existing is not None:
            return existing.id
        try:
            return self.transactions.create_category("Прочее", kind)
        except ValidationError:
            return None
