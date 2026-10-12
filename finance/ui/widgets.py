"""Переиспользуемые элементы интерфейса."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Sequence

from . import theme

SORT_ASC = "asc"
SORT_DESC = "desc"


def make_card(parent, title: str | None = None, padding: int = 14):
    """Плитка с рамкой: возвращает (внешняя рамка, контейнер содержимого)."""
    outer = ttk.Frame(parent, style="Border.TFrame", padding=1)
    card = ttk.Frame(outer, style="TFrame", padding=padding)
    card.pack(fill="both", expand=True)
    if title:
        ttk.Label(card, text=title, style="CardTitle.TLabel").pack(
            anchor="w", pady=(0, 10)
        )
    content = ttk.Frame(card, style="TFrame")
    content.pack(fill="both", expand=True)
    return outer, content


def add_divider(parent) -> tk.Frame:
    frame = tk.Frame(parent, bg=theme.BORDER, height=1)
    frame.pack(fill="x")
    return frame


class ScrollableFrame(ttk.Frame):
    """Контейнер с вертикальной прокруткой; содержимое складывайте в .content."""

    def __init__(self, master, height: int | None = None):
        super().__init__(master)
        self.canvas = tk.Canvas(self, highlightthickness=0, bg=theme.CARD)
        self.vscroll = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vscroll.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.vscroll.pack(side="right", fill="y")

        self.content = ttk.Frame(self.canvas, style="TFrame")
        self._window = self.canvas.create_window(
            (0, 0), window=self.content, anchor="nw"
        )
        self.content.bind(
            "<Configure>",
            lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfigure(self._window, width=e.width),
        )
        self._bind_wheel(self.canvas)
        self._bind_wheel(self.content)

    def _bind_wheel(self, widget) -> None:
        widget.bind("<MouseWheel>", self._on_wheel, add="+")
        widget.bind("<Button-4>", self._on_wheel, add="+")
        widget.bind("<Button-5>", self._on_wheel, add="+")

    def _on_wheel(self, event) -> str:
        if event.num == 4:
            self.canvas.yview_scroll(-3, "units")
        elif event.num == 5:
            self.canvas.yview_scroll(3, "units")
        elif event.delta:
            self.canvas.yview_scroll(-int(event.delta / 30), "units")
        return "break"


class PlaceholderEntry(ttk.Entry):
    """Поле ввода с серой подсказкой, исчезающей при вводе."""

    def __init__(self, master, placeholder: str = "", **kwargs):
        super().__init__(master, **kwargs)
        self.placeholder = placeholder
        self._placeholder_on = False
        self.show_placeholder()
        self.bind("<FocusIn>", self._on_focus_in)
        self.bind("<FocusOut>", self._on_focus_out)

    def show_placeholder(self) -> None:
        self._placeholder_on = True
        self.delete(0, tk.END)
        self.insert(0, self.placeholder)
        self.configure(foreground="gray")

    def _on_focus_in(self, _event) -> None:
        if self._placeholder_on:
            self.delete(0, tk.END)
            self.configure(foreground="black")
            self._placeholder_on = False

    def _on_focus_out(self, _event) -> None:
        if not self.get().strip() and not self._placeholder_on:
            self.show_placeholder()

    def get(self) -> str:  # type: ignore[override]
        if self._placeholder_on:
            return ""
        return super().get()


class TreeTable:
    """Таблица на базе Treeview с сортировкой по клику на заголовок."""

    def __init__(
        self,
        master,
        columns: Sequence[tuple],
        height: int = 12,
        on_double_click: Callable | None = None,
        on_select: Callable | None = None,
    ):
        self.columns = list(columns)
        frame = ttk.Frame(master)
        self.frame = frame
        keys = [c[0] for c in self.columns]
        self.tree = ttk.Treeview(
            frame, columns=keys, show="headings", height=height, selectmode="browse"
        )
        self.tree.tag_configure("over", foreground=theme.DANGER)
        self.tree.tag_configure("income", foreground="#047857")
        self.tree.tag_configure("expense", foreground="#B91C1C")
        self.tree.tag_configure("invest", foreground="#6D28D9")
        self.tree.tag_configure("alt", background=theme.ROW_ALT)

        ybar = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        xbar = ttk.Scrollbar(frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        self._sort_key: str | None = None
        self._sort_dir = SORT_ASC
        self._rows: list[dict] = []

        for col in self.columns:
            key, title, width, anchor = col[0], col[1], col[2], col[3]
            self.tree.heading(key, text=title, command=lambda k=key: self._sort_by(k))
            self.tree.column(key, width=width, anchor=anchor, stretch=bool(col[4]) if len(col) > 4 else True)

        if on_double_click:
            self.tree.bind("<Double-1>", lambda _e: on_double_click())
        if on_select:
            self.tree.bind("<<TreeviewSelect>>", lambda _e: on_select())

    def _sort_by(self, key: str) -> None:
        if self._sort_key == key:
            self._sort_dir = SORT_DESC if self._sort_dir == SORT_ASC else SORT_ASC
        else:
            self._sort_key = key
            self._sort_dir = SORT_ASC
        index = [c[0] for c in self.columns].index(key)
        reverse = self._sort_dir == SORT_DESC
        self._rows.sort(key=lambda r: r["sort"][index], reverse=reverse)
        self._write_rows()
        for col in self.columns:
            title = col[1]
            if col[0] == key:
                title += " ▼" if reverse else " ▲"
            self.tree.heading(col[0], text=title)

    def set_rows(self, rows: list[dict]) -> None:
        self._rows = list(rows)
        if self._sort_key:
            index = [c[0] for c in self.columns].index(self._sort_key)
            self._rows.sort(
                key=lambda r: r["sort"][index], reverse=self._sort_dir == SORT_DESC
            )
        self._write_rows()

    def _write_rows(self) -> None:
        self.tree.delete(*self.tree.get_children())
        used = set()
        for index, row_ in enumerate(self._rows):
            tags = list(row_.get("tags", ()))
            if index % 2:
                tags.append("alt")
            iid = row_["iid"]
            if iid in used:
                iid = f"{iid}#{index}"
            used.add(iid)
            self.tree.insert(
                "", tk.END, iid=iid, values=row_["values"], tags=tuple(tags)
            )

    def selected_iid(self) -> str | None:
        selection = self.tree.selection()
        return selection[0] if selection else None

    def clear(self) -> None:
        self._rows = []
        self.tree.delete(*self.tree.get_children())


class FormDialog(tk.Toplevel):
    """Базовое модальное окно формы с кнопками ОК/Отмена."""

    def __init__(self, parent, title: str, confirm_text: str = "Сохранить"):
        super().__init__(parent)
        self.result = None
        self._error_var = tk.StringVar(value="")
        self.configure(background=theme.CARD)
        self.transient(parent.winfo_toplevel())
        self.resizable(False, False)
        self.title(title)

        outer = ttk.Frame(self, padding=(16, 14, 16, 12))
        outer.pack(fill="both", expand=True)
        self.body = outer
        self.build_body(outer)

        error = ttk.Label(outer, textvariable=self._error_var, style="Danger.TLabel",
                          wraplength=340, justify="left")
        error.grid(row=100, column=0, columnspan=3, sticky="w", pady=(8, 0))

        buttons = ttk.Frame(outer)
        buttons.grid(row=101, column=0, columnspan=3, sticky="e", pady=(14, 0))
        ttk.Button(buttons, text="Отмена", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(
            buttons, text=confirm_text, style="Accent.TButton", command=self.on_ok
        ).pack(side="right")
        self._ok_button = buttons.winfo_children()[-1]

        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Return>", lambda _e: self.on_ok())
        self.after(50, self._focus_first)

        try:
            self.grab_set()
        except tk.TclError:
            pass
        self._center_over(parent)

    def build_body(self, parent) -> None:
        raise NotImplementedError

    def on_ok(self) -> None:
        raise NotImplementedError

    def _focus_first(self) -> None:
        for child in self.body.winfo_children():
            if isinstance(child, ttk.Entry) or isinstance(child, tk.Entry):
                child.focus_set()
                return
        self._ok_button.focus_set()

    def show_error(self, message: str) -> None:
        self._error_var.set(message)

    def _center_over(self, parent) -> None:
        self.update_idletasks()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        w, h = self.winfo_width(), self.winfo_height()
        x = px + max(0, (pw - w) // 2)
        y = py + max(0, (ph - h) // 2)
        self.geometry(f"+{x}+{y}")


def run_dialog(dialog_class, parent, **kwargs):
    dialog = dialog_class(parent, **kwargs)
    parent.wait_window(dialog)
    return dialog.result


class CanvasTooltip:
    """Всплывающая подсказка над элементами canvas-диаграмм.
    resolve(event, canvas) возвращает текст подсказки или None."""

    def __init__(self, canvas: tk.Canvas, resolve: Callable):
        self.canvas = canvas
        self.resolve = resolve
        self._win: tk.Toplevel | None = None
        self._label: tk.Label | None = None
        self._last: tuple | None = None
        canvas.bind("<Motion>", self._on_motion, add="+")
        canvas.bind("<Leave>", lambda _e: self.hide(), add="+")

    def _on_motion(self, event) -> None:
        text = self.resolve(event, self.canvas)
        if text is None or not text.strip():
            self.hide()
            return
        zone = (event.x_root, event.y_root, text)
        if zone == self._last:
            return
        self._last = zone
        self._show(event.x_root, event.y_root, text)

    def _show(self, x: int, y: int, text: str) -> None:
        if self._win is None:
            self._win = tk.Toplevel(self.canvas)
            self._win.withdraw()
            self._win.overrideredirect(True)
            self._win.attributes("-topmost", True)
            self._label = tk.Label(
                self._win, text="",
                background=theme.TOOLTIP_BG, foreground=theme.TOOLTIP_FG,
                font=(theme.font_family(), 12), padx=10, pady=5,
            )
            self._label.pack()
        self._label.configure(text=text)
        self._win.wm_geometry(f"+{x + 14}+{y + 12}")
        self._win.deiconify()
        self._win.lift()

    def hide(self) -> None:
        self._last = None
        if self._win is not None:
            self._win.withdraw()


def row(iid, values, tags=(), sort=None) -> dict:
    return {
        "iid": str(iid),
        "values": list(values),
        "tags": tuple(tags),
        "sort": list(sort) if sort is not None else list(values),
    }
