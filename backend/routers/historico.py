"""Histórico de meses: totais/variação recalculados dinamicamente a partir de
LancamentoFatura; só a nota-resumo textual é persistida (ResumoMensal)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import LancamentoFatura, ResumoMensal
from ..schemas import MesHistoricoResponse, NotaResumoUpdate, StatusMesResponse
from .status import _mes_atual, obter_status_mes

router = APIRouter(prefix="/historico", tags=["historico"])


@router.get("/meses", response_model=list[MesHistoricoResponse])
def listar_meses(db: Session = Depends(get_db)):
    mes_atual = _mes_atual()
    totais = (
        db.query(LancamentoFatura.mes_referencia, func.sum(LancamentoFatura.valor))
        .filter(LancamentoFatura.mes_referencia != mes_atual)
        .group_by(LancamentoFatura.mes_referencia)
        .order_by(LancamentoFatura.mes_referencia.desc())
        .all()
    )

    resultado = []
    for i, (mes_referencia, total) in enumerate(totais):
        mes_anterior_total = totais[i + 1][1] if i + 1 < len(totais) else None
        variacao_pct = ((total - mes_anterior_total) / mes_anterior_total * 100) if mes_anterior_total else None
        resumo = db.get(ResumoMensal, mes_referencia)
        resultado.append(
            MesHistoricoResponse(
                mes_referencia=mes_referencia,
                total=total,
                variacao_pct=variacao_pct,
                nota_resumo=resumo.nota_resumo if resumo else None,
            )
        )
    return resultado


@router.get("/meses/{mes_referencia}", response_model=StatusMesResponse)
def obter_mes(mes_referencia: str, db: Session = Depends(get_db)):
    return obter_status_mes(db, mes_referencia)


@router.patch("/meses/{mes_referencia}/nota", response_model=MesHistoricoResponse)
def atualizar_nota_resumo(mes_referencia: str, payload: NotaResumoUpdate, db: Session = Depends(get_db)):
    total = (
        db.query(func.sum(LancamentoFatura.valor))
        .filter(LancamentoFatura.mes_referencia == mes_referencia)
        .scalar()
    )
    if total is None:
        raise HTTPException(status_code=404, detail="Mês sem lançamentos.")

    resumo = db.get(ResumoMensal, mes_referencia)
    if resumo is None:
        resumo = ResumoMensal(mes_referencia=mes_referencia)
        db.add(resumo)
    resumo.nota_resumo = payload.nota_resumo
    db.commit()

    return MesHistoricoResponse(
        mes_referencia=mes_referencia, total=total, variacao_pct=None, nota_resumo=resumo.nota_resumo
    )
