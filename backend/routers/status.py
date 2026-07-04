"""Status do mês. Compras parceladas = LancamentoFatura com total_parcelas
preenchido (não há tabela própria — ver DOCUMENTACAO.md secao 4)."""
from __future__ import annotations

import calendar
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import LancamentoFatura
from ..schemas import (
    CategoriaGastoResumo,
    InsightResumo,
    ParcelaResumo,
    SplitFixoResto,
    StatusMesResponse,
)

router = APIRouter(prefix="/status", tags=["status"])


def _mes_atual() -> str:
    hoje = date.today()
    return f"{hoje.year:04d}-{hoje.month:02d}"


def obter_status_mes(db: Session, mes_referencia: str) -> StatusMesResponse:
    ano, mes = (int(p) for p in mes_referencia.split("-"))
    dias_total = calendar.monthrange(ano, mes)[1]

    hoje = date.today()
    mes_eh_atual = mes_referencia == _mes_atual()
    dia_atual = hoje.day if mes_eh_atual else dias_total

    lancamentos_mes = db.query(LancamentoFatura).filter(LancamentoFatura.mes_referencia == mes_referencia).all()
    gasto_ate_hoje = sum(l.valor for l in lancamentos_mes)
    projecao_fechamento = (gasto_ate_hoje / dia_atual * dias_total) if dia_atual else gasto_ate_hoje

    totais_mensais_anteriores = (
        db.query(LancamentoFatura.mes_referencia, func.sum(LancamentoFatura.valor))
        .filter(LancamentoFatura.mes_referencia != mes_referencia)
        .group_by(LancamentoFatura.mes_referencia)
        .all()
    )
    valores_anteriores = [total for _, total in totais_mensais_anteriores]
    media_historica = (sum(valores_anteriores) / len(valores_anteriores)) if valores_anteriores else None
    comparacao_pct = (
        (projecao_fechamento - media_historica) / media_historica * 100 if media_historica else None
    )

    por_categoria: dict[str, float] = {}
    for l in lancamentos_mes:
        nome = l.categoria_gasto.nome if l.categoria_gasto else "Sem categoria"
        por_categoria[nome] = por_categoria.get(nome, 0.0) + l.valor
    categorias = [
        CategoriaGastoResumo(nome=nome, total=total, pct=(total / gasto_ate_hoje * 100) if gasto_ate_hoje else 0.0)
        for nome, total in sorted(por_categoria.items(), key=lambda item: item[1], reverse=True)
    ]

    parcelados = [l for l in lancamentos_mes if l.eh_parcelado]
    parcelados.sort(key=lambda l: l.parcelas_restantes)
    parcelas = [
        ParcelaResumo(
            estabelecimento=l.estabelecimento.nome_exibicao if l.estabelecimento else l.descricao_bruta,
            valor_parcela=l.valor,
            parcela_atual=l.parcela_atual,
            total_parcelas=l.total_parcelas,
            mes_termino=l.mes_termino or mes_referencia,
            ultima=l.parcelas_restantes == 0,
        )
        for l in parcelados
    ]

    fixo = sum(l.valor for l in parcelados)
    resto = gasto_ate_hoje - fixo

    # TODO(próxima sessão): geração real de insights (economia possível comprando
    # sempre no lugar mais barato; recorrências pequenas e frequentes).
    insights: list[InsightResumo] = []

    return StatusMesResponse(
        mes_referencia=mes_referencia,
        dia_atual=dia_atual,
        dias_total=dias_total,
        gasto_ate_hoje=gasto_ate_hoje,
        projecao_fechamento=projecao_fechamento,
        media_historica=media_historica,
        comparacao_pct=comparacao_pct,
        categorias=categorias,
        parcelas=parcelas,
        split_fixo_resto=SplitFixoResto(fixo=fixo, resto=resto),
        insights=insights,
    )


@router.get("/mes", response_model=StatusMesResponse)
def status_do_mes(
    mes: str | None = Query(default=None, description="Formato YYYY-MM. Default: mês corrente."),
    db: Session = Depends(get_db),
):
    return obter_status_mes(db, mes or _mes_atual())
