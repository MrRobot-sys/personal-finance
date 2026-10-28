"""Диаграммы на tkinter Canvas: кольцевая, «план и факт», динамика.

Модуль не использует сторонних библиотек и не знает о слое данных: функции
получают готовые числа и рисуют их по текущему размеру холста. Цвета берутся
только из семантических ролей темы (:mod:`.theme`) и категориальной палитры
:data:`PALETTE`, поэтому обе темы остаются читаемыми.

Каждая функция очищает холст и возвращает словарь подсказок
``{id элемента: текст}`` для :class:`~.widgets.CanvasTooltip`.
"""
from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING, Sequence

from ...models import MONTH_NAMES, format_amount
from . import theme

if TYPE_CHECKING:  # pragma: no cover - только для аннотаций
    from ...models import MonthSummary

# Категориальная палитра: устойчивые цвета для категорий в обеих темах.
PALETTE = (
    "#e53935", "#fb8c00", "#fdd835", "#43a047", "#1e88e5",
    "#8e24aa", "#00acc1", "#6d4c41", "#d81b60", "#7cb342",
)
MONTH_SHORT = ("янв", "фев", "мар", "апр", "май", "июн",
               "июл", "авг", "сен", "окт", "ноя", "дек")

EMPTY_MONTH = "Нет данных за месяц"
EMPTY_PERIOD = "Нет данных за период"

Tips = dict[int, str]

_font_family: str | None = None


def _family() -> str:
    """Семейство шрифта темы; вычисляется лениво (нужен уже созданный Tk)."""
    global _font_family
    if _font_family is None:
        _font_family = theme.font_family()
    return _font_family


def _font(size: int, weight: str = "normal") -> tuple[str, int, str]:
    return (_family(), size, weight)


def _axis(value: float) -> str:
    """Подпись оси: целые рубли без символа валюты."""
    return f"{value:,.0f}".replace(",", "\u00a0")


def _rub(value: float) -> str:
    """Короткая сумма для центра кольца и подписей."""
    return f"{_axis(value)}\u00a0₽"


def _percent(part: float, whole: float) -> str:
    if whole <= 0:
        return "0,0%"
    return f"{part / whole * 100:.1f}%".replace(".", ",")


def _measure(canvas: tk.Canvas, text: str, size: int, weight: str = "normal") -> int:
    """Ширина строки в пикселях для шрифта диаграмм."""
    return int(canvas.tk.call("font", "measure", _font(size, weight), text))


def _fit(
    canvas: tk.Canvas, text: str, width: float,
    size: int, weight: str = "normal",
) -> str:
    """Обрезать подпись по фактической ширине с многоточием."""
    if width <= 0 or _measure(canvas, text, size, weight) <= width:
        return text
    shortened = text
    while shortened and _measure(canvas, shortened + "…", size, weight) > width:
        shortened = shortened[:-1]
    return f"{shortened}…" if shortened else "…"


def _compact_rub(value: float) -> str:
    """Короткая сумма для центра кольца: миллионы — в «млн»."""
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.2f} млн\u00a0₽".replace(".", ",")
    return _rub(value)


def _center_text(
    canvas: tk.Canvas, cx: float, cy: float, text: str,
    color: str, size: int, weight: str = "normal",
) -> None:
    canvas.create_text(cx, cy, text=text, fill=color, font=_font(size, weight))


def draw_donut(
    canvas: tk.Canvas,
    slices: Sequence[tuple[str, float, str]],
    *,
    caption: str = "Расходы",
    note: str = "",
    empty_text: str = EMPTY_MONTH,
) -> Tips:
    """Кольцевая диаграмма структуры месяца.

    :param slices: ``[(подпись, сумма, цвет)]``; сумма — положительное число;
    :param caption: подпись в центре над суммой («Расходы»/«Доходы»);
    :param note: дополнительная строка в центре (например, «октябрь 2026»);
    :param empty_text: текст пустого состояния.
    :return: подсказки для сегментов кольца.
    """
    canvas.delete("all")
    tips: Tips = {}
    width = max(canvas.winfo_width(), 120)
    height = max(canvas.winfo_height(), 100)
    items = [
        (str(name), float(value), color)
        for name, value, color in slices
        if value > 0
    ]
    if not items:
        _center_text(canvas, width / 2, height / 2, empty_text, theme.MUTED, 11)
        return tips

    total = sum(value for _name, value, _color in items)
    items.sort(key=lambda item: item[1], reverse=True)

    ring = min(height - 10, max(60, int(width * 0.44)), 260)
    left = 4.0
    top = (height - ring) / 2
    cx = left + ring / 2
    cy = height / 2

    angle = 90.0
    for name, value, color in items:
        extent = -360.0 * value / total
        # create_arc не рисует полный круг одним сегментом.
        extent = max(extent, -359.9)
        item = canvas.create_arc(
            left, top, left + ring, top + ring,
            start=angle, extent=extent, fill=color,
            outline=theme.CARD, width=1, style=tk.PIESLICE,
        )
        tips[item] = f"{name}: {format_amount(value)} ({_percent(value, total)})"
        angle += extent

    hole = ring * 0.58
    canvas.create_oval(
        cx - hole / 2, cy - hole / 2, cx + hole / 2, cy + hole / 2,
        fill=theme.CARD, outline="",
    )
    sum_size = 14 if hole >= 120 else 12 if hole >= 95 else 10
    total_text = _compact_rub(total)
    while sum_size > 8 and _measure(canvas, total_text, sum_size, "bold") > hole - 10:
        sum_size -= 1
    paragraph = [
        (caption, 9, theme.MUTED, "normal"),
        (total_text, sum_size, theme.TEXT, "bold"),
    ]
    if note:
        paragraph.append((note, 8, theme.MUTED, "normal"))
    gap = sum_size + 8
    start = cy - (len(paragraph) - 1) * gap / 2
    for index, (text, size, color, weight) in enumerate(paragraph):
        _center_text(canvas, cx, start + index * gap, text, color, size, weight)

    legend_x = left + ring + 18
    legend_w = width - legend_x - 8
    if legend_w < 120:
        return tips

    max_rows = max(1, int((height - 8) // 18))
    hidden = max(0, len(items) - max_rows)
    shown = items[: max_rows - 1] if hidden else items
    row_count = len(shown) + (1 if hidden else 0)
    row_h = min(24.0, (height - 8) / max(row_count, 1))
    y = (height - row_h * row_count) / 2 + row_h / 2
    for name, value, color in shown:
        square = canvas.create_rectangle(
            legend_x, y - 5, legend_x + 10, y + 5, fill=color, outline=""
        )
        label = canvas.create_text(
            legend_x + 16, y,
            text=_fit(canvas, name, legend_w - 52, 10), anchor="w",
            fill=theme.TEXT, font=_font(10),
        )
        percent = canvas.create_text(
            width - 8, y, text=_percent(value, total), anchor="e",
            fill=theme.MUTED, font=_font(10),
        )
        tips[square] = tips[label] = tips[percent] = (
            f"{name}: {format_amount(value)} ({_percent(value, total)})"
        )
        y += row_h
    if hidden:
        canvas.create_text(
            legend_x + 16, y, text=f"ещё {hidden}", anchor="w",
            fill=theme.MUTED, font=_font(9),
        )
    return tips


def draw_plan_fact(
    canvas: tk.Canvas,
    rows: Sequence[tuple[str, float, float]],
    *,
    empty_text: str = EMPTY_PERIOD,
) -> Tips:
    """Столбики «план и факт» по категориям с месячным планом.

    План рисуется светлой колонкой с меткой уровня, факт — узкой колонкой
    поверх: :data:`theme.SUCCESS` в пределах плана, :data:`theme.DANGER`
    при перерасходе.

    :param rows: ``[(категория, план, факт)]``; строки без плана отбрасываются;
    :return: подсказки для колонок.
    """
    canvas.delete("all")
    tips: Tips = {}
    width = max(canvas.winfo_width(), 120)
    height = max(canvas.winfo_height(), 110)
    items = [
        (str(name), float(plan), float(fact))
        for name, plan, fact in rows
        if plan > 0
    ]
    if not items:
        _center_text(canvas, width / 2, height / 2, empty_text, theme.MUTED, 11)
        return tips

    pad_top = 24
    pad_bottom = 30
    pad_left = 56
    pad_right = 10
    plot_w = max(40, width - pad_left - pad_right)
    plot_h = max(30, height - pad_top - pad_bottom)

    hidden = 0
    max_slots = max(1, int(plot_w // 34))
    if len(items) > max_slots:
        hidden = len(items) - max_slots
        items = items[:max_slots]

    max_value = max(max(plan, fact) for _name, plan, fact in items) or 1.0
    steps = 4 if plot_h >= 70 else 2
    for step in range(steps + 1):
        value = max_value * step / steps
        y = pad_top + plot_h - plot_h * step / steps
        canvas.create_line(pad_left, y, width - pad_right, y, fill=theme.GRID)
        canvas.create_text(
            pad_left - 8, y, text=_axis(value), anchor="e",
            fill=theme.MUTED, font=_font(9),
        )

    if width >= pad_left + 240:
        legend = (
            (theme.STRIP, theme.BORDER, "план"),
            (theme.SUCCESS, "", "в норме"),
            (theme.DANGER, "", "перерасход"),
        )
        x = float(pad_left)
        for fill, outline, text in legend:
            canvas.create_rectangle(
                x, 8, x + 9, 17, fill=fill, outline=outline or ""
            )
            canvas.create_text(
                x + 13, 12.5, text=text, anchor="w",
                fill=theme.MUTED, font=_font(9),
            )
            x += 23 + _measure(canvas, text, 9)
    if hidden:
        canvas.create_text(
            width - pad_right, 12.5, text=f"ещё {hidden}", anchor="e",
            fill=theme.MUTED, font=_font(9),
        )

    slot = plot_w / len(items)
    bar_w = max(8, min(30, slot * 0.56))
    baseline = pad_top + plot_h
    label_width = slot - 6
    show_labels = label_width >= 24
    for index, (name, plan, fact) in enumerate(items):
        cx = pad_left + slot * index + slot / 2
        plan_h = plot_h * plan / max_value
        fact_h = plot_h * fact / max_value
        plan_y = baseline - plan_h
        fact_y = baseline - fact_h
        over = fact > plan

        plan_item = canvas.create_rectangle(
            cx - bar_w / 2, plan_y, cx + bar_w / 2, baseline,
            fill=theme.STRIP, outline=theme.BORDER,
        )
        fact_item = None
        if fact_h >= 1:
            fact_item = canvas.create_rectangle(
                cx - bar_w * 0.28, fact_y, cx + bar_w * 0.28, baseline,
                fill=theme.DANGER if over else theme.SUCCESS, outline="",
            )
        canvas.create_line(
            cx - bar_w / 2, plan_y, cx + bar_w / 2, plan_y,
            fill=theme.MUTED, width=1,
        )

        percent = f"{round(fact / plan * 100)}%"
        top = min(plan_y, fact_y)
        if top - pad_top >= 14:
            canvas.create_text(
                cx, top - 6, text=percent, anchor="s",
                fill=theme.DANGER if over else theme.SUCCESS,
                font=_font(9, "bold"),
            )
        canvas.create_text(
            cx, baseline + 6,
            text=_fit(canvas, name, label_width, 9) if show_labels else "…",
            anchor="n", fill=theme.MUTED, font=_font(9),
        )

        tip = f"{name}: {format_amount(fact)} из {format_amount(plan)} ({percent})"
        if over:
            tip += " — перерасход"
        tips[plan_item] = tip
        if fact_item is not None:
            tips[fact_item] = tip
    return tips


def draw_dynamics(
    canvas: tk.Canvas,
    series: Sequence[MonthSummary],
    *,
    empty_text: str = EMPTY_PERIOD,
) -> Tips:
    """Динамика доходов и расходов по месяцам с линией тренда расходов.

    :param series: месячные итоги (``MonthSummary``) в хронологическом порядке;
    :return: подсказки для столбиков и точек тренда.
    """
    canvas.delete("all")
    tips: Tips = {}
    width = max(canvas.winfo_width(), 100)
    height = max(canvas.winfo_height(), 100)
    if not series or not any(s.income or s.expense for s in series):
        _center_text(canvas, width / 2, height / 2, empty_text, theme.MUTED, 11)
        return tips

    pad_top = 16
    pad_bottom = 26
    pad_left = 66
    pad_right = 14
    plot_w = max(30, width - pad_left - pad_right)
    plot_h = max(20, height - pad_top - pad_bottom)
    max_value = max(
        [s.income for s in series] + [s.expense for s in series] + [1]
    )
    baseline = pad_top + plot_h

    steps = 4 if plot_h >= 80 else 2
    for step in range(steps + 1):
        value = max_value * step / steps
        y = baseline - plot_h * step / steps
        canvas.create_line(pad_left, y, width - pad_right, y, fill=theme.GRID)
        canvas.create_text(
            pad_left - 8, y, text=_axis(value), anchor="e",
            fill=theme.MUTED, font=_font(9),
        )

    slot = plot_w / len(series)
    bar_w = max(3, min(16, slot / 2.8))
    points: list[tuple[float, float, float]] = []
    for index, summary in enumerate(series):
        cx = pad_left + slot * index + slot / 2
        month = MONTH_SHORT[summary.month - 1]
        for offset, value, color, caption in (
            (-bar_w / 2 - 1, summary.income, theme.SUCCESS, "Доходы"),
            (bar_w / 2 + 1, summary.expense, theme.DANGER, "Расходы"),
        ):
            bar_h = plot_h * value / max_value if max_value else 0
            if bar_h > 0:
                item = canvas.create_rectangle(
                    cx + offset - bar_w / 2, baseline - bar_h,
                    cx + offset + bar_w / 2, baseline,
                    fill=color, outline="",
                )
                tips[item] = (
                    f"{caption}, {MONTH_NAMES[summary.month - 1]} "
                    f"{summary.year}: {format_amount(value)}"
                )
        points.append(
            (
                cx + bar_w / 2 + 1,
                baseline - plot_h * summary.expense / max_value,
                summary.expense,
            )
        )

    if len(points) > 1:
        coords: list[float] = []
        for x, y, _value in points:
            coords.extend((x, y))
        canvas.create_line(*coords, fill=theme.ACCENT, width=2)

    for index, (x, y, value) in enumerate(points):
        summary = series[index]
        item = canvas.create_oval(
            x - 3.5, y - 3.5, x + 3.5, y + 3.5,
            fill=theme.ACCENT, outline=theme.CARD, width=1.5,
        )
        tips[item] = (
            f"Расходы (тренд), {MONTH_SHORT[summary.month - 1]} "
            f"{summary.year}: {format_amount(value)}"
        )

    label_step = 1 if slot >= 28 else 2
    for index, summary in enumerate(series):
        if index % label_step:
            continue
        canvas.create_text(
            pad_left + slot * index + slot / 2, height - pad_bottom + 14,
            text=MONTH_SHORT[summary.month - 1], fill=theme.MUTED,
            font=_font(9),
        )
    return tips
