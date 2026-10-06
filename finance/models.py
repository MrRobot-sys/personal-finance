"""Модели данных, валидация и форматирование."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, datetime

INCOME = "income"
EXPENSE = "expense"
KIND_LABELS = {INCOME: "Доход", EXPENSE: "Расход"}

MONTH_NAMES = (
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
)


class ValidationError(ValueError):
    """Некорректные данные формы."""


@dataclass(frozen=True)
class Category:
    id: int
    name: str
    kind: str
    monthly_limit: float | None = None


@dataclass(frozen=True)
class Transaction:
    id: int
    category_id: int
    amount: float
    txn_date: date
    note: str = ""
    category_name: str = ""
    kind: str = EXPENSE


@dataclass
class CategoryPlan:
    """Среднее за 3 месяца, факт и план по категории."""
    category: Category
    spent: float = 0.0
    avg_3: float | None = None

    @property
    def limit(self) -> float | None:
        return self.category.monthly_limit

    @property
    def ratio(self) -> float:
        if self.limit is None or self.limit <= 0:
            return 0.0
        return self.spent / self.limit

    @property
    def percent(self) -> int:
        return round(self.ratio * 100)

    @property
    def has_limit(self) -> bool:
        return self.limit is not None and self.limit > 0

    @property
    def is_over(self) -> bool:
        """Перерасход: у расходной категории факт превысил план."""
        return self.category.kind == EXPENSE and self.has_limit and self.spent > self.limit

    @property
    def status(self) -> str:
        """Хорошо/плохо по сравнению среднего за 3 месяца с планом."""
        if self.avg_3 is None or not self.has_limit:
            return "neutral"
        if self.category.kind == INCOME:
            return "good" if self.avg_3 >= self.limit else "bad"
        return "good" if self.avg_3 <= self.limit else "bad"


@dataclass
class MonthSummary:
    year: int
    month: int
    income: float = 0.0
    expense: float = 0.0

    @property
    def balance(self) -> float:
        return self.income - self.expense

    @property
    def label(self) -> str:
        return f"{MONTH_NAMES[self.month - 1]} {self.year}"


def format_amount(value: float) -> str:
    text = f"{value:,.2f}".replace(",", "\u00a0").replace(".", ",")
    return f"{text}\u00a0₽"


def parse_optional_amount(raw: str | None) -> float | None:
    """Пустая строка — «нет плана», иначе обязательная положительная сумма."""
    if raw is None:
        return None
    if not raw.strip():
        return None
    return parse_amount(raw)


def parse_amount(raw: str) -> float:
    if raw is None:
        raise ValidationError("Введите сумму")
    cleaned = raw.strip().replace("\u00a0", "").replace(" ", "").replace("₽", "")
    if not cleaned:
        raise ValidationError("Введите сумму")
    cleaned = cleaned.replace(",", ".")
    if not re.fullmatch(r"\d+(\.\d+)?", cleaned):
        raise ValidationError("Сумма должна быть числом, например 1500 или 1500,50")
    value = float(cleaned)
    if not math.isfinite(value) or value <= 0:
        raise ValidationError("Сумма должна быть больше нуля")
    return round(value, 2)


def format_date(value: date) -> str:
    return value.strftime("%d.%m.%Y")


def parse_date(raw: str) -> date:
    text = (raw or "").strip()
    if not text:
        raise ValidationError("Введите дату")
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValidationError("Дата в формате ДД.ММ.ГГГГ, например 06.10.2026")


def month_key(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def month_range(year: int, month: int) -> tuple[date, date]:
    first = date(year, month, 1)
    if month == 12:
        nxt = date(year + 1, 1, 1)
    else:
        nxt = date(year, month + 1, 1)
    return first, nxt.fromordinal(nxt.toordinal() - 1)


def previous_months(year: int, month: int, count: int) -> list[tuple[int, int]]:
    result = []
    cy, cm = year, month
    for _ in range(count):
        result.append((cy, cm))
        cm -= 1
        if cm == 0:
            cy, cm = cy - 1, 12
    result.reverse()
    return result


def validate_category_name(name: str) -> str:
    text = (name or "").strip()
    if not text:
        raise ValidationError("Введите название категории")
    if len(text) > 60:
        raise ValidationError("Название категории слишком длинное (макс. 60)")
    return text


def validate_kind(kind: str) -> str:
    if kind not in (INCOME, EXPENSE):
        raise ValidationError("Выберите тип: доход или расход")
    return kind
