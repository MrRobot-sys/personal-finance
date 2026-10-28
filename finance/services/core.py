"""Общая основа доменных сервисов."""
from __future__ import annotations

from ..repository import Repository


class ServiceBase:
    """Базовый компонент доменного сервиса.

    Хранит ссылку на репозиторий: домены не открывают собственных соединений
    с базой и не дублируют SQL. Зависимости между доменами передаются явно
    через конструкторы наследников.
    """

    def __init__(self, repo: Repository):
        self.repo = repo
