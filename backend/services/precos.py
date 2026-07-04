"""Cálculos de preço de referência e ciclo de consumo, reaproveitados
entre o Catálogo e a Lista de compras."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..models import Compra, EventoConsumo, OrigemCompra


@dataclass
class PrecoReferencia:
    ultimo_preco: float | None = None
    ultimo_local: str | None = None
    melhor_preco: float | None = None
    melhor_local: str | None = None


def calcular_preco_referencia(db: Session, produto_id: int) -> PrecoReferencia:
    ultima_compra = (
        db.query(Compra)
        .filter(Compra.produto_id == produto_id)
        .order_by(Compra.data.desc(), Compra.id.desc())
        .first()
    )
    melhor_compra = (
        db.query(Compra)
        .filter(Compra.produto_id == produto_id)
        .order_by(Compra.preco.asc())
        .first()
    )
    if ultima_compra is None:
        return PrecoReferencia()

    return PrecoReferencia(
        ultimo_preco=ultima_compra.preco,
        ultimo_local=ultima_compra.estabelecimento.nome_exibicao,
        melhor_preco=melhor_compra.preco,
        melhor_local=melhor_compra.estabelecimento.nome_exibicao,
    )


def calcular_dias_medio_consumo(db: Session, produto_id: int) -> float | None:
    datas = [
        e.data
        for e in db.query(EventoConsumo)
        .filter(EventoConsumo.produto_id == produto_id)
        .order_by(EventoConsumo.data.asc())
        .all()
    ]
    if len(datas) < 2:
        return None
    intervalos = [(datas[i] - datas[i - 1]).days for i in range(1, len(datas))]
    return sum(intervalos) / len(intervalos)


def produto_tem_compra_nfce(db: Session, produto_id: int) -> bool:
    return (
        db.query(Compra)
        .filter(Compra.produto_id == produto_id, Compra.origem == OrigemCompra.NFCE)
        .first()
        is not None
    )
