"""Модальные окна добавления и редактирования.

Реэкспортует публичный API прежнего модуля ``dialogs`` по доменным
подпакетам и модулям для обратной совместимости.
"""
from __future__ import annotations

from .category import CategoryDialog, PlanDialog
from .import_dialog import CategoryMapDialog, ImportDialog
from .investments import (
    AssetDialog,
    ManualPriceDialog,
    PayoutDialog,
    PayoutRuleDialog,
    ReceivePayoutsDialog,
    TradeDialog,
)
from .settings import SettingsDialog
from .transaction import TransactionDialog

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
    "ImportDialog",
    "CategoryMapDialog",
]
