"""Разбор банковских выписок (CSV/OFX/XLSX) в операции для импорта.

Поддерживаются выгрузки Т-Банка: CSV и XLSX одной структуры, а также
стандартный формат OFX. Используется только стандартная библиотека.
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from .models import EXPENSE, INCOME

EXCEL_EPOCH = date(1899, 12, 30)

_XLSX_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


class ImportFormatError(ValueError):
    """Файл не распознан, повреждён или не содержит операций."""


@dataclass(frozen=True)
class ImportedOperation:
    txn_date: date
    amount: float
    kind: str
    category_name: str
    note: str
    fingerprint: str

    @property
    def signed_amount(self) -> float:
        return self.amount if self.kind == INCOME else -self.amount


def read_operations(path: str | Path) -> list[ImportedOperation]:
    """Читает файл выписки и возвращает операции для импорта."""
    data = Path(path).read_bytes()
    return parse_bytes(data, Path(path).suffix.lower())


def parse_bytes(data: bytes, suffix: str = "") -> list[ImportedOperation]:
    if data.startswith(b"PK\x03\x04") or suffix == ".xlsx":
        return _parse_xlsx(data)
    stripped = data.lstrip()
    if b"<OFX" in stripped or b"OFXHEADER" in stripped[:200]:
        return _parse_ofx(data)
    try:
        return _parse_csv(data)
    except _CsvError as exc:
        raise ImportFormatError(str(exc)) from exc


def _clean(value: str) -> str:
    return (value or "").replace("\u00a0", " ").strip()


def _parse_tbank_date(raw: str) -> date:
    text = _clean(raw)
    for fmt in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ImportFormatError(
        f"Не удалось разобрать дату «{raw}». Ожидается формат ДД.ММ.ГГГГ."
    )


def _parse_signed_amount(raw: str) -> float:
    text = _clean(raw).replace("₽", "").replace(",", ".").replace(" ", "")
    try:
        value = float(text)
    except ValueError as exc:
        raise ImportFormatError(f"Не удалось разобрать сумму «{raw}».") from exc
    return value


def _fingerprint(prefix: str, *parts: object) -> str:
    raw = "|".join(str(p).strip().lower() for p in parts)
    return f"{prefix}:{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:24]}"


def _make_operation(
    txn_date: date, amount: float, category_name: str,
    note: str, fingerprint: str,
) -> ImportedOperation | None:
    if amount == 0 or not category_name:
        return None
    kind = EXPENSE if amount < 0 else INCOME
    clean_category = _clean(category_name)
    if not clean_category:
        return None
    return ImportedOperation(
        txn_date=txn_date,
        amount=round(abs(amount), 2),
        kind=kind,
        category_name=clean_category,
        note=_clean(note),
        fingerprint=fingerprint,
    )


# --- CSV ---

DEFAULT_CSV_ENCODINGS = ("utf-8-sig", "utf-8", "cp1251")


class _CsvError(Exception):
    pass


def _parse_csv(data: bytes) -> list[ImportedOperation]:
    text = None
    for encoding in DEFAULT_CSV_ENCODINGS:
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise _CsvError("Не удалось распознать кодировку файла.")
    rows = [
        r for r in csv.reader(io.StringIO(text), delimiter=";")
        if any(cell.strip() for cell in r)
    ]
    if not rows:
        raise _CsvError("Файл CSV пуст.")
    header = [_clean(c) for c in rows[0]]
    indices = _csv_columns(header)
    operations: list[ImportedOperation] = []
    for row in rows[1:]:
        if len(row) <= indices["date"]:
            continue
        if "analytics" in indices and _clean(row[indices["analytics"]]).lower() == "нет":
            continue
        operations.extend(_row_to_operations(row, indices))
    if not operations:
        raise _CsvError("В файле не найдено операций для импорта.")
    return operations


def _csv_columns(header: list[str]) -> dict[str, int]:
    required = ("Дата операции", "Сумма в валюте счёта")
    found = {}
    for index, name in enumerate(header):
        low = name.lower()
        if low == "дата операции":
            found["date"] = index
        elif low == "сумма в валюте счёта":
            found["amount"] = index
        elif low == "категория по-умолчанию":
            found["default_category"] = index
        elif low in ("ваша категория", "категория"):
            found["user_category"] = index
        elif low == "описание":
            found["description"] = index
        elif low == "сообщение":
            found["message"] = index
        elif low == "учёт в аналитике":
            found["analytics"] = index
    for name in required:
        if name == "Дата операции" and "date" not in found:
            raise _CsvError(f"Не найдена колонка «{name}».")
        if name == "Сумма в валюте счёта" and "amount" not in found:
            raise _CsvError(f"Не найдена колонка «{name}».")
    found["kind"] = found.get("user_category") or found.get("default_category")
    if "kind" not in found:
        raise _CsvError("Не найдена колонка категории операции.")
    return found


def _row_to_operations(row: list[str], idx: dict[str, int]) -> list[ImportedOperation]:
    date_text = row[idx["date"]]
    try:
        txn_date = _parse_tbank_date(date_text)
        amount = _parse_signed_amount(row[idx["amount"]])
    except ImportFormatError:
        return []
    if amount == 0:
        return []

    category = _clean(row[idx.get("user_category")]) or _clean(row[idx.get("default_category")])
    note_parts = []
    if idx.get("description") and _clean(row[idx["description"]]):
        note_parts.append(_clean(row[idx["description"]]))
    if idx.get("message") and _clean(row[idx["message"]]):
        message = _clean(row[idx["message"]])
        if message not in note_parts:
            note_parts.append(message)
    note = " — ".join(p for p in note_parts if p)

    operation = _make_operation(
        txn_date, amount, category, note,
        _fingerprint("csv", date_text.strip(), str(amount), category, note),
    )
    return [operation] if operation else []


# --- OFX ---

def _parse_ofx(data: bytes) -> list[ImportedOperation]:
    text = data.decode("utf-8", errors="replace")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ImportFormatError("OFX: повреждённый XML.") from exc

    operations: list[ImportedOperation] = []
    for trn in root.iter("STMTTRN"):
        amount_text = _child_text(trn, "TRNAMT")
        if amount_text is None:
            continue
        try:
            amount = float(amount_text.replace(",", "."))
        except ValueError:
            continue
        if amount == 0:
            continue
        date_text = _child_text(trn, "DTPOSTED") or _child_text(trn, "DTUSER")
        txn_date = _parse_ofx_date(date_text) if date_text else date.today()
        category = _clean(_child_text(trn, "MEMO") or _child_text(trn, "NAME"))
        note = _clean(_child_text(trn, "NAME") or "")
        fitid = _clean(_child_text(trn, "FITID") or "")
        fingerprint = (
            f"ofx:{fitid}" if fitid
            else _fingerprint("ofx", txn_date.isoformat(), round(abs(amount), 2), category, note)
        )
        operation = _make_operation(txn_date, amount, category, note or category, fingerprint)
        if operation:
            operations.append(operation)
    if not operations:
        raise ImportFormatError("OFX: не найдено операций в выписке.")
    return operations


def _parse_ofx_date(raw: str) -> date:
    digits = re.sub(r"\D", "", raw)[:14]
    if len(digits) == 8:
        digits += "000000"
    if len(digits) != 14:
        raise ImportFormatError(f"OFX: некорректная дата «{raw}».")
    try:
        return datetime.strptime(digits, "%Y%m%d%H%M%S").date()
    except ValueError as exc:
        raise ImportFormatError(f"OFX: некорректная дата «{raw}».") from exc


def _child_text(parent: ET.Element, tag: str) -> str | None:
    child = parent.find(tag)
    if child is None or child.text is None:
        return None
    return child.text


# --- XLSX ---

def _parse_xlsx(data: bytes) -> list[ImportedOperation]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ImportFormatError("XLSX: повреждённый файл.") from exc

    shared = _read_shared_strings(archive)
    sheet_path = _first_sheet_path(archive)
    if sheet_path is None:
        raise ImportFormatError("XLSX: не найдено листа с данными.")
    try:
        sheet_xml = archive.read(sheet_path)
    except KeyError as exc:
        raise ImportFormatError("XLSX: не найден лист с данными.") from exc

    root = ET.fromstring(sheet_xml)
    namespace = _XLSX_NS
    rows = root.findall(f"{namespace}sheetData/{namespace}row")
    matrix: list[list[tuple[str, object]]] = []
    for row in rows:
        cells: list[tuple[str, object]] = []
        for cell in row.findall(f"{namespace}c"):
            ref = cell.get("r") or ""
            m = re.match(r"([A-Z]+)\d+", ref)
            col = m.group(1) if m else ""
            value = _cell_value(cell, namespace, shared)
            cells.append((col, value))
        matrix.append(cells)

    header = {col: _clean(str(value)) for col, value in matrix[0]}
    cols = _xlsx_columns(header)
    operations: list[ImportedOperation] = []
    for cells in matrix[1:]:
        values = {col: value for col, value in cells if col}
        if "date" not in cols or cols["date"] not in values:
            continue
        if "analytics" in cols and _clean(str(values.get(cols["analytics"], ""))).lower() == "нет":
            continue
        operation = _xlsx_row_to_operation(values, cols)
        if operation:
            operations.append(operation)
    if not operations:
        raise ImportFormatError("XLSX: не найдено операций для импорта.")
    return operations


def _cell_value(cell: ET.Element, namespace: str, shared: list[str]) -> object:
    cell_type = cell.get("t")
    if cell_type == "s":
        try:
            return shared[int(cell.findtext(f"{namespace}v"))]
        except (TypeError, ValueError, IndexError):
            return ""
    if cell_type == "inlineStr":
        return "".join(
            t.text or "" for t in cell.iter(f"{namespace}t")
        )
    if cell_type == "str":
        return cell.findtext(f"{namespace}v") or ""
    raw = cell.findtext(f"{namespace}v")
    if raw is None:
        return ""
    try:
        return float(raw)
    except ValueError:
        return raw


def _cell_number(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _excel_serial_to_date(serial: float) -> date:
    return EXCEL_EPOCH + timedelta(days=int(serial))


def _xlsx_row_to_operation(
    values: dict[str, object], cols: dict[str, str]
) -> ImportedOperation | None:
    serial = _cell_number(values.get(cols["date"]))
    if serial is None:
        return None
    txn_date = _excel_serial_to_date(serial)

    amount_value = values.get(cols["amount"])
    amount = _cell_number(amount_value)
    if amount is None and isinstance(amount_value, str):
        try:
            amount = _parse_signed_amount(amount_value)
        except ImportFormatError:
            return None
    if amount is None or amount == 0:
        return None

    category = _clean(str(values.get(cols.get("user_category", ""), "")))
    if not category:
        category = _clean(str(values.get(cols.get("default_category", ""), "")))
    note_parts = []
    if "description" in cols:
        description = _clean(str(values.get(cols["description"], "")))
        if description:
            note_parts.append(description)
    if "message" in cols:
        message = _clean(str(values.get(cols["message"], "")))
        if message and message not in note_parts:
            note_parts.append(message)

    operation = _make_operation(
        txn_date, amount, category, " — ".join(note_parts),
        _fingerprint("xlsx", str(serial), str(amount), category, " — ".join(note_parts)),
    )
    return operation


def _xlsx_columns(header: dict[str, str]) -> dict[str, str]:
    def find(*names: str) -> str | None:
        lowered = {name.lower(): name for name in names}
        for col, value in header.items():
            if value.lower() in lowered:
                return col
        return None

    cols: dict[str, str] = {}
    date_col = find("дата операции")
    amount_col = find("сумма в валюте счёта")
    if date_col is None or amount_col is None:
        raise ImportFormatError("XLSX: не найдены колонки «Дата операции» и «Сумма в валюте счёта».")
    cols["date"] = date_col
    cols["amount"] = amount_col
    for key, names in (
        ("default_category", ("категория по-умолчанию",)),
        ("user_category", ("ваша категория", "категория")),
        ("description", ("описание",)),
        ("message", ("сообщение",)),
        ("analytics", ("учёт в аналитике",)),
    ):
        col = find(*names)
        if col is not None:
            cols[key] = col
    if "user_category" not in cols and "default_category" not in cols:
        raise ImportFormatError("XLSX: не найдена колонка категории операции.")
    cols["kind"] = cols.get("user_category") or cols.get("default_category")
    return cols


def _read_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        xml_bytes = archive.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ET.fromstring(xml_bytes)
    result = []
    for si in root.findall(f"{_XLSX_NS}si"):
        result.append("".join(t.text or "" for t in si.iter(f"{_XLSX_NS}t")))
    return result


def _first_sheet_path(archive: zipfile.ZipFile) -> str | None:
    candidates = [
        name for name in archive.namelist()
        if name.startswith("xl/worksheets/")
        and name.endswith(".xml")
        and "/_rels/" not in name
    ]
    return candidates[0] if candidates else None