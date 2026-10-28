"""Домен автообновления: настройки таймеров и метки последней синхронизации."""
from __future__ import annotations

from ..quotes import now_iso
from .constants import (
    AUTO_PAYOUT_ENABLED_KEY,
    AUTO_PAYOUT_HOURS_KEY,
    AUTO_PRICE_ENABLED_KEY,
    AUTO_PRICE_MINUTES_KEY,
    DEFAULT_PAYOUT_HOURS,
    DEFAULT_PRICE_MINUTES,
    MIN_PAYOUT_HOURS,
    MIN_PRICE_MINUTES,
)
from .core import ServiceBase
from .dto import AutoRefreshSettings


class SyncService(ServiceBase):
    """Настройки фонового обновления цен и поиска выплат.

    Ключи настроек общие для обоих таймеров, поэтому домен вынесен отдельно
    от котировок и выплат.
    """

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
        self.repo.set_setting(key, now_iso())
