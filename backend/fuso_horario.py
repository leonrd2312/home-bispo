"""Data/hora "de hoje" no fuso de Brasília — nunca `date.today()`/`datetime.now()`
puro: o container roda em UTC, e Brasília é UTC-3, então entre 21h e 23h59
(horário de Brasília) o relógio do container já virou o dia seguinte."""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

FUSO_BRASIL = ZoneInfo("America/Sao_Paulo")


def agora() -> datetime:
    return datetime.now(FUSO_BRASIL)


def hoje() -> date:
    return agora().date()
