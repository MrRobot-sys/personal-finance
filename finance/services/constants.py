"""Константы сервисного слоя: ключи настроек и параметры автообновления."""
from __future__ import annotations

RATE_USD_KEY = "rate_USD"
RATE_EUR_KEY = "rate_EUR"
RATES_UPDATED_KEY = "rates_updated"

# Метки времени последних успешных синхронизаций (ISO, для авто-таймеров).
PRICES_UPDATED_KEY = "prices_updated_at"
PAYOUTS_SYNCED_KEY = "payouts_synced_at"

# Настройки автообновления.
AUTO_PRICE_ENABLED_KEY = "auto_price_enabled"
AUTO_PRICE_MINUTES_KEY = "auto_price_minutes"
AUTO_PAYOUT_ENABLED_KEY = "auto_payout_enabled"
AUTO_PAYOUT_HOURS_KEY = "auto_payout_hours"
DEFAULT_PRICE_MINUTES = 30
DEFAULT_PAYOUT_HOURS = 24
MIN_PRICE_MINUTES = 5
MIN_PAYOUT_HOURS = 1

# Насколько глубоко искать пропущенные прошедшие выплаты (месяцев).
PAST_PAYOUT_MONTHS = 24
