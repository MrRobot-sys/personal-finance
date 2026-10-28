"""Общие хелперы для диалогов."""
from __future__ import annotations

import tkinter as tk

from ...models import format_amount


# Кэш результатов поиска бумаг на время работы окна: (market, query) -> matches.
_SEARCH_CACHE: dict[tuple[str, str], list] = {}
_SEARCH_CACHE_LIMIT = 64


def _cache_search(key: tuple[str, str], matches: list) -> None:
    if key in _SEARCH_CACHE:
        return
    if len(_SEARCH_CACHE) >= _SEARCH_CACHE_LIMIT:
        _SEARCH_CACHE.pop(next(iter(_SEARCH_CACHE)))
    _SEARCH_CACHE[key] = matches


def _get_search_cache() -> dict[tuple[str, str], list]:
    return _SEARCH_CACHE


# Пустые обязательные поля сервисного слоя сериализуются в человеко-понятные тексты.
_EMPTY_VALIDATION_TEXTS: dict[str, str] = {
    "Введите сумму": "Сумма не может быть пустой — укажите число, например 1500 или 1500,50",
    "Введите дату": "Дата не может быть пустой — укажите дату в формате ДД.ММ.ГГГГ",
}


def _validation_text(raw: str) -> str:
    """Человеко-понятный текст ошибки валидации (пустые поля — по словарю выше)."""
    text = (raw or "").strip()
    return _EMPTY_VALIDATION_TEXTS.get(text, text)


def _amount_text(value: float | None) -> str:
    if value is None:
        return ""
    return str(value).replace(".00", "").replace(".", ",")


def _asset_choices(assets) -> tuple[list[str], dict[str, object]]:
    labels: list[str] = []
    mapping: dict[str, object] = {}
    seen: dict[str, int] = {}
    for asset in assets:
        base = asset.ticker or asset.name
        label = f"{asset.name} ({base})" if asset.ticker else asset.name
        count = seen.get(label, 0)
        seen[label] = count + 1
        if count:
            label = f"{label} #{count + 1}"
        labels.append(label)
        mapping[label] = asset
    return labels, mapping
