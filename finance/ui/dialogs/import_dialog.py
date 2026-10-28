"""Диалоги импорта операций из банковских выписок."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ...models import (
    EXPENSE,
    INCOME,
    KIND_LABELS,
    Category,
    format_amount,
    format_date,
)
from ...services import ImportedOperation
from ..widgets import FormDialog, ScrollableFrame, TreeTable, row

CREATE = "create"
EXISTING = "existing"
FALLBACK = "fallback"


class ImportDialog(FormDialog):
    """Предпросмотр операций из файла: клик по строке включает/исключает её."""

    def __init__(
        self, parent, file_name: str,
        operations: list[ImportedOperation], known_sources: set[str],
    ):
        self._file_name = file_name
        self._ops = list(operations)
        self._known = known_sources
        self.result = None
        super().__init__(parent, "Импорт операций", confirm_text="Импортировать")
        self.geometry("860x560")
        self.minsize(620, 400)
        self._center_over(self.master)

    def build_body(self, parent) -> None:
        ttk.Label(
            parent,
            text=(
                f"Файл: {self._file_name} · найдено операций: {len(self._ops)}\n"
                "Клик по строке включает или исключает операцию из импорта."
            ),
            style="CardTitle.TLabel", justify="left", wraplength=760,
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))

        controls = ttk.Frame(parent)
        controls.grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 8))
        self.all_var = tk.BooleanVar(value=False)
        self.new_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            controls, text="Добавить все операции из файла",
            variable=self.all_var, command=lambda: self._toggle_mode(True),
        ).pack(side="left")
        ttk.Checkbutton(
            controls, text="Добавить только новые (ещё не импортированные)",
            variable=self.new_var, command=lambda: self._toggle_mode(False),
        ).pack(side="left", padx=(14, 0))

        table_holder = ttk.Frame(parent)
        table_holder.grid(row=2, column=0, columnspan=3, sticky="nsew")
        parent.rowconfigure(2, weight=1)
        parent.columnconfigure(0, weight=1)

        self.table = TreeTable(
            table_holder,
            columns=[
                ("date", "Дата", 95, "center", False),
                ("kind", "Тип", 75, "center", False),
                ("category", "Категория", 220, "w", True),
                ("amount", "Сумма", 110, "e", True),
                ("note", "Описание", 300, "w", True),
            ],
            height=18,
        )
        self.table.frame.pack(fill="both", expand=True)
        self.table.tree.tag_configure("muted", foreground="#9CA3AF")

        self.status_var = tk.StringVar(value="")
        ttk.Label(parent, textvariable=self.status_var, style="Value.TLabel").grid(
            row=3, column=0, columnspan=3, sticky="w", pady=(8, 0)
        )

        self.table.tree.bind(
            "<ButtonRelease-1>", self._on_click, add="+"
        )
        self._included: set[str] = set()
        self._locked: set[str] = set()
        self.table.set_rows([
            row(
                index,
                [
                    format_date(op.txn_date),
                    KIND_LABELS[op.kind],
                    op.category_name,
                    ("+" if op.kind == INCOME else "−") + format_amount(op.amount),
                    op.note,
                ],
                tags=(),
                sort=[op.txn_date.toordinal(), op.kind, op.category_name, op.amount, op.note],
            )
            for index, op in enumerate(self._ops)
        ])
        self._apply_mode()

    def _toggle_mode(self, is_all: bool) -> None:
        if is_all:
            self.new_var.set(False)
        else:
            self.all_var.set(False)
        self._apply_mode()

    def _apply_mode(self) -> None:
        total = len(self._ops)
        is_all = self.all_var.get()
        self._included = {
            str(i) for i in range(total)
        } if is_all else {
            str(i) for i, op in enumerate(self._ops)
            if op.fingerprint not in self._known
        }
        self._locked = set() if is_all else {
            str(i) for i, op in enumerate(self._ops)
            if op.fingerprint in self._known
        }
        for index, op in enumerate(self._ops):
            iid = str(index)
            iid_tags = self._tags_for(iid)
            self.table.tree.item(iid, tags=iid_tags)
        self._update_status()

    def _tags_for(self, iid: str) -> tuple[str, ...]:
        if iid in self._locked or iid not in self._included:
            return ("muted",)
        kind = self._ops[int(iid)].kind
        return ("income" if kind == INCOME else "expense",)

    def _on_click(self, _event) -> None:
        row_id = self.table.tree.identify_row(_event.y)
        if not row_id:
            return
        column = self.table.tree.identify_column(_event.x)
        if column == "#0":
            return
        if row_id in self._locked:
            return
        if row_id in self._included:
            self._included.discard(row_id)
        else:
            self._included.add(row_id)
        self.table.tree.item(row_id, tags=self._tags_for(row_id))
        self._update_status()

    def _update_status(self) -> None:
        count = len(self._included)
        total = len(self._ops)
        self.status_var.set(f"Выбрано к импорту: {count} из {total}")
        if hasattr(self, "_ok_button"):
            self._ok_button.configure(text=f"Импортировать ({count})")

    def on_ok(self) -> None:
        selected = [
            op for index, op in enumerate(self._ops)
            if str(index) in self._included
        ]
        self.result = {
            "operations": selected,
            "skip_existing": not self.all_var.get(),
        }
        self.destroy()


class CategoryMapDialog(FormDialog):
    """Сопоставление новых категорий банка с категориями приложения."""

    def __init__(
        self, parent,
        new_categories: list[tuple[str, str]],
        categories: list[Category],
    ):
        self._new = list(new_categories)
        self._categories = list(categories)
        self.result = None
        super().__init__(parent, "Новые категории из файла", confirm_text="Продолжить")
        self.resizable(True, True)
        self.geometry("520x440")
        self.minsize(460, 320)
        self._center_over(self.master)

    def build_body(self, parent) -> None:
        ttk.Label(
            parent,
            text=(
                "В файле есть категории, которых нет в приложении. "
                "Укажите, как их обработать."
            ),
            style="CardTitle.TLabel", justify="left", wraplength=460,
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))

        self.for_all_var = tk.BooleanVar(value=True)
        ttk.Label(parent, text="Действие для всех новых:").grid(
            row=1, column=0, sticky="w", pady=(0, 4)
        )
        self.global_combo = ttk.Combobox(
            parent,
            values=["Создать отдельные категории", "В «Прочее»"],
            state="readonly", width=34,
        )
        self.global_combo.set("Создать отдельные категории")
        self.global_combo.grid(row=1, column=1, sticky="w", pady=(0, 4))
        ttk.Checkbutton(
            parent, text="Выбрать для всех", variable=self.for_all_var,
            command=self._sync_controls,
        ).grid(row=2, column=1, sticky="w", pady=(0, 8))
        parent.rowconfigure(3, weight=1)

        self._row_values: dict = {}
        self._row_combos: list[ttk.Combobox] = []

        scroll = ScrollableFrame(parent, height=280)
        scroll.grid(row=3, column=0, columnspan=2, sticky="nsew")
        names = self._new
        for index, (name, kind) in enumerate(names):
            holder = ttk.Frame(scroll.content)
            holder.grid(row=index, column=0, columnspan=2, sticky="ew", pady=2)
            ttk.Label(
                holder,
                text=f"«{name}» · {KIND_LABELS[kind]}",
                foreground="#111827",
            ).pack(side="left", padx=(2, 10))
            options = [
                (f"Создать «{name}»", CREATE, None),
                ("В «Прочее»", FALLBACK, None),
            ]
            for cat in self._categories:
                if cat.kind == kind:
                    options.append((f"→ {cat.name}", EXISTING, cat.id))
            combo = ttk.Combobox(
                holder, state="readonly", width=38,
                values=[o[0] for o in options],
            )
            combo.set("Создать «{name}»".format(name=name))
            combo.pack(side="right")
            self._row_values[index] = {
                o[0]: (o[1], o[2]) for o in options
            }
            self._row_combos.append(combo)
        scroll.content.columnconfigure(0, weight=1)
        self._sync_controls()

    def _sync_controls(self) -> None:
        disabled = bool(self.for_all_var.get())
        state = "disabled" if disabled else "readonly"
        for combo in self._row_combos:
            combo.configure(state=state)

    def on_ok(self) -> None:
        use_global = bool(self.for_all_var.get())
        resolutions: dict[tuple[str, str], tuple[str, int | None]] = {}
        for index, (name, kind) in enumerate(self._new):
            if use_global:
                action, existing_id = (
                    (CREATE, None)
                    if self.global_combo.get().startswith("Создать")
                    else (FALLBACK, None)
                )
            else:
                value = self._row_combos[index].get()
                action, existing_id = self._row_values[index].get(
                    value, (FALLBACK, None)
                )
            resolutions[(name, kind)] = (action, existing_id if action == EXISTING else None)
        self.result = resolutions
        self.destroy()