"""Модальные окна добавления и редактирования.

Содержит только re-export для сохранения обратной совместимости.
Реализация разнесена по доменным модулям.
"""
from __future__ import annotations

from .category_dialogs import CategoryDialog, PlanDialog
from .transaction_dialogs import TransactionDialog
from .investment_dialogs import (
    AssetDialog,
    TradeDialog,
    ManualPriceDialog,
    PayoutDialog,
    PayoutRuleDialog,
    ReceivePayoutsDialog,
)
from .settings_dialog import SettingsDialog

__all__ = [
    "CategoryDialog",
    "PlanDialog",
    "TransactionDialog",
    "AssetDialog",
    "TradeDialog",
    "ManualPriceDialog",
    "PayoutDialog",
    "PayoutRuleDialog",
    "ReceivePayoutsDialog",
    "SettingsDialog",
]
