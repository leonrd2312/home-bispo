"""Status do mês. Compras parceladas = LancamentoFatura com total_parcelas
preenchido (não há tabela própria — ver DOCUMENTACAO.md secao 4)."""
from __future__ import annotations

import calendar
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Categoria, Estabelecimento, FormaPagamento, LancamentoFatura, TipoCategoria
from ..schemas import (
    AlternarTerceiroRequest,
    CategoriaGastoResumo,
    CompraParceladaTerceiroResumo,
    InsightResumo,
    LancamentoResumo,
    ParcelaResumo,
    RecategorizarLancamentoRequest,
    SplitCreditoRefeicao,
    SplitFixoResto,
    SplitNossoTerceiro,
    StatusMesResponse,
)

router = APIRouter(prefix="/status", tags=["status"])


def _mes_atual() -> str:
    hoje = date.today()
    return f"{hoje.year:04d}-{hoje.month:02d}"


def somar_meses(mes_referencia: str, delta: int) -> str:
    ano, mes = (int(p) for p in mes_referencia.split("-"))
    total = (ano * 12 + (mes - 1)) + delta
    ano2, mes2 = divmod(total, 12)
    return f"{ano2:04d}-{mes2 + 1:02d}"


def data_compra_parcelada(vencimento_mes_ref: str, dia: int, parcela_atual: int) -> date:
    """Parcela N de um lançamento cujo ciclo fecha em vencimento_mes_ref foi
    comprada N meses antes — o dia impresso é confiável (cópia mecânica),
    mas mês/ano precisam ser calculados, nunca perguntados ao modelo (ver
    parser_fatura.py e parser_print.py: pedir isso à IA já se provou
    pouco confiável)."""
    ano_mes = somar_meses(vencimento_mes_ref, -parcela_atual)
    ano, mes = (int(p) for p in ano_mes.split("-"))
    dia = min(dia, calendar.monthrange(ano, mes)[1])
    return date(ano, mes, dia)


def obter_status_mes(db: Session, mes_referencia: str) -> StatusMesResponse:
    ano, mes = (int(p) for p in mes_referencia.split("-"))
    dias_total = calendar.monthrange(ano, mes)[1]

    hoje = date.today()
    mes_eh_atual = mes_referencia == _mes_atual()
    dia_atual = hoje.day if mes_eh_atual else dias_total

    lancamentos_mes = db.query(LancamentoFatura).filter(LancamentoFatura.mes_referencia == mes_referencia).all()
    gasto_ate_hoje = sum(l.valor for l in lancamentos_mes)

    totais_mensais_anteriores = (
        db.query(LancamentoFatura.mes_referencia, func.sum(LancamentoFatura.valor))
        .filter(LancamentoFatura.mes_referencia != mes_referencia)
        .group_by(LancamentoFatura.mes_referencia)
        .all()
    )
    valores_anteriores = [total for _, total in totais_mensais_anteriores]
    media_historica = (sum(valores_anteriores) / len(valores_anteriores)) if valores_anteriores else None
    comparacao_pct = (
        (gasto_ate_hoje - media_historica) / media_historica * 100 if media_historica else None
    )

    por_categoria: dict[str, float] = {}
    for l in lancamentos_mes:
        nome = l.categoria_gasto.nome if l.categoria_gasto else "Sem categoria"
        por_categoria[nome] = por_categoria.get(nome, 0.0) + l.valor
    categorias = [
        CategoriaGastoResumo(nome=nome, total=total, pct=(total / gasto_ate_hoje * 100) if gasto_ate_hoje else 0.0)
        for nome, total in sorted(por_categoria.items(), key=lambda item: item[1], reverse=True)
    ]

    lancamentos_detalhe = sorted(
        (
            LancamentoResumo(
                id=l.id,
                data=l.data,
                estabelecimento=l.estabelecimento.nome_exibicao if l.estabelecimento else l.descricao_bruta,
                valor=l.valor,
                categoria=l.categoria_gasto.nome if l.categoria_gasto else "Sem categoria",
                parcela_atual=l.parcela_atual,
                total_parcelas=l.total_parcelas,
            )
            for l in lancamentos_mes
        ),
        key=lambda l: l.data,
        reverse=True,
    )

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
            terceiro=l.terceiro,
        )
        for l in parcelados
    ]

    fixo = sum(l.valor for l in parcelados)
    resto = gasto_ate_hoje - fixo

    credito = sum(l.valor for l in lancamentos_mes if l.forma_pagamento == FormaPagamento.CREDITO)
    refeicao = sum(l.valor for l in lancamentos_mes if l.forma_pagamento == FormaPagamento.REFEICAO)

    # Terceiro só reclassifica o retrato "nossas vs. terceiros" das parcelas
    # (não afeta gasto_ate_hoje/fixo acima — a fatura cobra tudo igual,
    # terceiro ou não, é só quem realmente "é o gasto" pra fins de controle).
    nosso_parcelas = sum(l.valor for l in parcelados if not l.terceiro)
    terceiro_parcelas = sum(l.valor for l in parcelados if l.terceiro)

    # TODO(próxima sessão): geração real de insights (economia possível comprando
    # sempre no lugar mais barato; recorrências pequenas e frequentes).
    insights: list[InsightResumo] = []

    return StatusMesResponse(
        mes_referencia=mes_referencia,
        dia_atual=dia_atual,
        dias_total=dias_total,
        gasto_ate_hoje=gasto_ate_hoje,
        media_historica=media_historica,
        comparacao_pct=comparacao_pct,
        categorias=categorias,
        lancamentos=lancamentos_detalhe,
        parcelas=parcelas,
        split_fixo_resto=SplitFixoResto(fixo=fixo, resto=resto),
        split_credito_refeicao=SplitCreditoRefeicao(credito=credito, refeicao=refeicao),
        split_nossas_terceiros=SplitNossoTerceiro(nosso=nosso_parcelas, terceiro=terceiro_parcelas),
        insights=insights,
    )


@router.get("/mes", response_model=StatusMesResponse)
def status_do_mes(
    mes: str | None = Query(default=None, description="Formato YYYY-MM. Default: mês corrente."),
    db: Session = Depends(get_db),
):
    return obter_status_mes(db, mes or _mes_atual())


@router.patch("/lancamentos/{lancamento_id}/categoria", status_code=200)
def recategorizar_lancamento(
    lancamento_id: int, payload: RecategorizarLancamentoRequest, db: Session = Depends(get_db)
):
    """Corrige a categoria de UM lançamento e, se ele tiver estabelecimento
    resolvido, marca esse estabelecimento com a nova categoria como padrão —
    lançamentos futuros do mesmo estabelecimento passam a usar essa categoria
    corrigida em vez da que a extração da fatura/print sugerir (ver
    _registrar_lancamento em ingestao.py)."""
    lancamento = db.get(LancamentoFatura, lancamento_id)
    if lancamento is None:
        raise HTTPException(status_code=404, detail="Lançamento não encontrado.")

    categoria = db.get(Categoria, payload.categoria_id)
    if categoria is None or categoria.tipo != TipoCategoria.GASTO:
        raise HTTPException(status_code=400, detail="Categoria inválida.")

    lancamento.categoria_gasto_id = categoria.id
    if lancamento.estabelecimento_id is not None:
        estabelecimento = db.get(Estabelecimento, lancamento.estabelecimento_id)
        estabelecimento.categoria_gasto_id = categoria.id

    db.commit()
    return {"ok": True}


@router.get("/compras-parceladas", response_model=list[CompraParceladaTerceiroResumo])
def listar_compras_parceladas(db: Session = Depends(get_db)):
    """Compras parceladas AINDA EM ANDAMENTO, uma linha por parcelamento —
    não por mês. Usado pela função 'Compras de Terceiros' em Funcionalidades.
    "Em andamento" é decidido pela data PREVISTA de término (mes_referencia
    do lançamento mais recente + parcelas que faltavam), não só por
    parcela_atual == total_parcelas — um parcelamento pode nunca ter tido a
    última parcela importada (ex: o estabelecimento não apareceu de novo num
    print) e ainda assim já ter passado do mês em que terminaria; nesse caso
    também é tratado como concluído, senão ficaria na lista pra sempre. Um
    mesmo parcelamento aparece como várias linhas em LancamentoFatura (uma
    por mês); (estabelecimento_id, data, total_parcelas) identifica o grupo,
    já que `data` é a data da COMPRA ORIGINAL e não muda entre os meses (ver
    _resolver_data_lancamento em ingestao.py)."""
    linhas = (
        db.query(LancamentoFatura)
        .filter(LancamentoFatura.total_parcelas.isnot(None), LancamentoFatura.total_parcelas > 1)
        .all()
    )

    grupos: dict[tuple, list[LancamentoFatura]] = {}
    for l in linhas:
        chave = (l.estabelecimento_id, l.data, l.total_parcelas)
        grupos.setdefault(chave, []).append(l)

    mes_atual = _mes_atual()
    resultado = []
    for rows in grupos.values():
        rows.sort(key=lambda l: l.parcela_atual, reverse=True)
        recente = rows[0]
        mes_termino_previsto = somar_meses(recente.mes_referencia, recente.total_parcelas - recente.parcela_atual)
        if mes_termino_previsto < mes_atual:
            continue  # já passou do mês em que terminaria — concluído, mesmo sem a última parcela importada
        resultado.append(
            CompraParceladaTerceiroResumo(
                lancamento_id=recente.id,
                estabelecimento=recente.estabelecimento.nome_exibicao if recente.estabelecimento else recente.descricao_bruta,
                data=recente.data,
                valor_parcela=recente.valor,
                parcela_atual=recente.parcela_atual,
                total_parcelas=recente.total_parcelas,
                terceiro=any(r.terceiro for r in rows),
            )
        )

    resultado.sort(key=lambda c: c.data, reverse=True)
    return resultado


@router.patch("/parcelas/{lancamento_id}/terceiro", status_code=200)
def marcar_parcela_terceiro(lancamento_id: int, payload: AlternarTerceiroRequest, db: Session = Depends(get_db)):
    """Marca/desmarca terceiro em TODAS as parcelas do mesmo parcelamento
    (todos os meses já lançados) — ver listar_compras_parceladas acima sobre
    como o grupo é identificado."""
    lancamento = db.get(LancamentoFatura, lancamento_id)
    if lancamento is None:
        raise HTTPException(status_code=404, detail="Lançamento não encontrado.")
    if not lancamento.eh_parcelado:
        raise HTTPException(status_code=400, detail="Lançamento não é uma compra parcelada.")

    db.query(LancamentoFatura).filter(
        LancamentoFatura.estabelecimento_id == lancamento.estabelecimento_id,
        LancamentoFatura.data == lancamento.data,
        LancamentoFatura.total_parcelas == lancamento.total_parcelas,
    ).update({"terceiro": payload.terceiro})
    db.commit()
    return {"ok": True}
