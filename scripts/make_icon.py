#!/usr/bin/env python3
"""Генератор иконки приложения «Учёт личных финансов».

Иконка рисуется на чистом Python: сама графика, PNG-кодирование и
ICO-контейнер написаны на стандартной библиотеке (``struct``,
``zlib``) — без PIL и прочих зависимостей.

Дизайн (палитра — finance/ui/widgets/theme.py):

* скруглённый квадрат (сквиркл) с вертикальным градиентом
  ACCENT_HOVER ``#1D4ED8`` → ACCENT ``#2563EB``; углы за пределами
  скругления прозрачны, поэтому иконка читается и на светлом, и на
  тёмном рабочем столе;
* белая (ON_ACCENT) диаграмма-столбики из трёх столбцов;
* зелёный (SUCCESS ``#16A34A``) третий, самый высокий столбец —
  растущий тренд.

Края сглаживаются суперсэмплингом: каждый пиксель результата
усредняется по сетке ``SCALE × SCALE`` субсэмплов (цвет и альфа
считаются раздельно, поэтому прозрачные углы не затемняют край).

Запуск:  python3 scripts/make_icon.py

Создаёт:
    finance/ui/assets/icon.png  — 256×256, RGBA;
    finance/ui/assets/icon.ico  — кадры 16, 24, 32, 48, 64, 128, 256
                                  (каждый кадр — PNG).
"""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

#: Эталонный размер: вся геометрия задана в его единицах.
BASE = 256
#: Субсэмплов на пиксель по каждой оси (степень двойки — усреднение без остатка).
SCALE = 8
#: Радиус скругления сквиркла.
CORNER = 56

#: Верх и низ градиента фона (ACCENT_HOVER → ACCENT).
BG_TOP = (0x1D, 0x4E, 0xD8)
BG_BOTTOM = (0x25, 0x63, 0xEB)
#: Цвета столбиков: белый (ON_ACCENT) и зелёный (SUCCESS).
BAR_LIGHT = (0xFF, 0xFF, 0xFF)
BAR_GROW = (0x16, 0xA3, 0x4A)

#: Ширина столбца диаграммы и общая линия низа.
BAR_WIDTH = 36
BAR_BOTTOM = 192
#: Столбцы диаграммы: (левый край, верхний край, цвет).
#: Высоты 64 / 96 / 128 — восходящая прогрессия тренда.
BARS = (
    (56, 128, BAR_LIGHT),
    (110, 96, BAR_LIGHT),
    (164, 64, BAR_GROW),
)

#: Размеры кадров многоразмерного ICO.
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)


def _inside(x: float, y: float, x0: float, y0: float, x1: float, y1: float,
            r: float) -> bool:
    """Проверяет, попадает ли точка в прямоугольник со скруглением.

    Прямоугольник описан границами ``(x0, y0)``–``(x1, y1)`` и радиусом
    ``r`` в углах. Точка вне ограничивающего прямоугольника — сразу
    вне фигуры; иначе расстояние до прямоугольника, стянутого на ``r``,
    не должно превышать ``r``. Значение ``r = half ширины`` даёт
    «капсулу» — скругление верхнего и нижнего краёв столбца.
    """
    if not (x0 <= x <= x1 and y0 <= y <= y1):
        return False
    dx = 0.0
    if x < x0 + r:
        dx = x0 + r - x
    elif x > x1 - r:
        dx = x - (x1 - r)
    dy = 0.0
    if y < y0 + r:
        dy = y0 + r - y
    elif y > y1 - r:
        dy = y - (y1 - r)
    return dx * dx + dy * dy <= r * r


def render(size: int, scale: int = SCALE) -> bytes:
    """Рендерит RGBA-пиксели иконки заданного размера.

    Каждый пиксель результата усредняется по сетке ``scale × scale``
    субсэмплов (суперсэмплинг): цвет берётся как среднее по каналам,
    альфа — как среднее покрытие. Вне сквиркла альфа равна нулю,
    поэтому углы прозрачны.
    """
    n = size * scale
    unit = BASE / n  # сторона субсэмпла в единицах геометрии
    samples = scale * scale

    xs = [(sx + 0.5) * unit for sx in range(n)]
    ys = [(sy + 0.5) * unit for sy in range(n)]
    out_cols = [sx // scale for sx in range(n)]

    # Столбцы диаграммы заданы в единицах эталона; столбцы не перекрываются,
    # поэтому каждому столбцу субсэмпла соответствует не более один кандидат.
    bars = [
        (x0, y0, x0 + BAR_WIDTH, BAR_BOTTOM, BAR_WIDTH / 2, color)
        for x0, y0, color in BARS
    ]
    col_bar: list[int | None] = []
    for x in xs:
        hit = None
        for index, (bx0, _by0, bx1, _by1, _br, _color) in enumerate(bars):
            if bx0 <= x <= bx1:
                hit = index
                break
        col_bar.append(hit)

    # Градиент зависит только от y: цвет строки субсэмплов одинаков.
    row_rgb = [
        tuple(
            round(top + (bottom - top) * (y / BASE))
            for top, bottom in zip(BG_TOP, BG_BOTTOM)
        )
        for y in ys
    ]

    accum = [0] * (size * size * 4)
    for sy in range(n):
        y = ys[sy]
        rgb = row_rgb[sy]
        row_base = (sy // scale) * size * 4
        for sx in range(n):
            x = xs[sx]
            if _inside(x, y, 0.0, 0.0, BASE, BASE, CORNER):
                color = rgb
                alpha = 255
                bar_index = col_bar[sx]
                if bar_index is not None and y >= bars[bar_index][1]:
                    bx0, by0, bx1, by1, br, bar_color = bars[bar_index]
                    if _inside(x, y, bx0, by0, bx1, by1, br):
                        color = bar_color
            else:
                # Снаружи сквиркла цвет не виден (альфа 0), но берём
                # градиент, чтобы среднее на краю не темнело.
                color = rgb
                alpha = 0
            idx = row_base + out_cols[sx] * 4
            accum[idx] += color[0]
            accum[idx + 1] += color[1]
            accum[idx + 2] += color[2]
            accum[idx + 3] += alpha

    half = samples // 2
    rgba = bytearray(size * size * 4)
    for i, value in enumerate(accum):
        rgba[i] = (value + half) // samples
    return bytes(rgba)


def _chunk(tag: bytes, payload: bytes) -> bytes:
    """Собирает блок PNG: длина, тип, данные, CRC32."""
    return (
        struct.pack(">I", len(payload))
        + tag
        + payload
        + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
    )


def png_bytes(size: int, rgba: bytes) -> bytes:
    """Кодирует RGBA-пиксели в PNG (8 бит на канал, фильтр None)."""
    stride = size * 4
    raw = bytearray()
    for y in range(size):
        raw.append(0)  # фильтр None: строка без изменений
        raw += rgba[y * stride:(y + 1) * stride]
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + _chunk(b"IEND", b"")
    )


def ico_bytes(frames: dict[int, bytes]) -> bytes:
    """Собирает многоуровневый ICO из готовых PNG-кадров.

    Каждый кадр хранится в формате PNG: такой ICO понимают начиная
    с Windows Vista, его же использует PyInstaller для ресурса exe.
    """
    header = struct.pack("<HHH", 0, 1, len(frames))
    entries = bytearray()
    blobs = bytearray()
    offset = len(header) + 16 * len(frames)
    for size in sorted(frames):
        data = frames[size]
        edge = 0 if size >= 256 else size  # 256 в байте ICO записывается как 0
        entries += struct.pack(
            "<BBBBHHII", edge, edge, 0, 0, 1, 32, len(data), offset
        )
        blobs += data
        offset += len(data)
    return bytes(header + entries + blobs)


def main() -> int:
    """Генерирует icon.png и icon.ico в finance/ui/assets/."""
    assets = Path(__file__).resolve().parents[1] / "finance" / "ui" / "assets"
    assets.mkdir(parents=True, exist_ok=True)

    master = render(BASE)
    png_path = assets / "icon.png"
    png_path.write_bytes(png_bytes(BASE, master))

    frames = {
        size: png_bytes(size, master if size == BASE else render(size))
        for size in ICO_SIZES
    }
    ico_path = assets / "icon.ico"
    ico_path.write_bytes(ico_bytes(frames))

    print(f"{png_path}: {BASE}×{BASE}, {png_path.stat().st_size} байт")
    print(f"{ico_path}: кадры {', '.join(str(s) for s in ICO_SIZES)}, "
          f"{ico_path.stat().st_size} байт")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
