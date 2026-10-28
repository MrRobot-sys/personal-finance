"""Диалоги работы с инвестициями.

Реэкспортует публичный API для обратной совместимости:
``from finance.ui.dialogs.investments import AssetDialog`` и т.д.
"""
from __future__ import annotations

from .assets import AssetDialog, ManualPriceDialog
from .payouts import PayoutDialog, PayoutRuleDialog, ReceivePayoutsDialog
from .trades import TradeDialog

__all__ = [
    "AssetDialog",
    "ManualPriceDialog",
    "PayoutDialog",
    "PayoutRuleDialog",
    "ReceivePayoutsDialog",
    "TradeDialog",
]
