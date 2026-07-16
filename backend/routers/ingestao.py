"""Ingestão de NFC-e, fatura fechada e print de extrato — todas via foto/print
(câmera ou galeria), mesma rota para o backend em qualquer caso.

Fluxo de NFC-e é stateless em duas fases: /nfce resolve identidade e devolve
um preview SEM gravar nada (rollback explícito no fim); /nfce/confirmar
recebe as decisões do usuário para itens ambíguos e grava de fato.
"""
from __future__ import annotations

import calendar
import uuid
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Categoria, Compra, LancamentoFatura, OrigemCompra, Produto, TipoCategoria
from ..schemas import (
    FaturaConfirmarRequest,
    FaturaPreviewResponse,
    ItemNfcePreview,
    ItemPrintPreview,
    LancamentoFaturaItem,
    NfceConfirmarRequest,
    NfcePreviewResponse,
    PrintConfirmarRequest,
    PrintPreviewResponse,
)
from ..services import identidade
from ..services.parser_fatura import extract_fatura
from ..services.parser_nfce import extract_nfce
from ..services.parser_print import extract_print
from .status import chave_parcelamento, data_compra_parcelada, somar_meses

router = APIRouter(prefix="/ingestao", tags=["ingestao"])

MESES_PT_NUM = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "abril": 4, "maio": 5, "junho": 6,
    "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}


def _resolver_data_lancamento(
    *, dia: int, mes_nome: str, parcela_atual: int | None, vencimento_mes_ref: str, mes_referencia: str
) -> date:
    """Nunca pergunta ano ao modelo (só dia + mês são impressos na fatura/print,
    sem ano) — ver data_compra_parcelada em status.py sobre por que pedir isso
    à IA já se provou pouco confiável.

    Parcelada: mês/ano vêm da aritmética de parcela (ver data_compra_parcelada).
    Sem parcela: o lançamento pertence ao ciclo em aberto, mas o fechamento
    real do cartão nem sempre bate com o limite exato do calendário — alguns
    dos últimos dias do mês anterior podem "vazar" pro ciclo atual. Testa o
    mês do vencimento, o mes_referencia e um mês antes, nessa ordem."""
    if parcela_atual:
        return data_compra_parcelada(vencimento_mes_ref, dia, parcela_atual)

    mes_num = MESES_PT_NUM[mes_nome]
    candidatos = [vencimento_mes_ref, mes_referencia, somar_meses(mes_referencia, -1)]
    ano_mes = next((c for c in candidatos if int(c.split("-")[1]) == mes_num), mes_referencia)
    ano, mes = (int(p) for p in ano_mes.split("-"))
    dia = min(dia, calendar.monthrange(ano, mes)[1])
    return date(ano, mes, dia)


def _registrar_lancamento(
    db: Session,
    *,
    mes_referencia: str,
    origem: OrigemCompra,
    item: LancamentoFaturaItem,
    categorias_gasto: dict[str, Categoria],
) -> None:
    estabelecimento = identidade.resolver_estabelecimento(db, nome_bruto=item.estabelecimento)
    # Se o usuário já corrigiu a categoria desse estabelecimento antes (ver
    # recategorizar_lancamento em status.py), essa correção manual prevalece
    # sobre o que a extração da fatura/print sugerir desta vez — evita que a
    # mesma categoria genérica errada volte lançamento após lançamento.
    categoria_id_corrigida = estabelecimento.categoria_gasto_id
    categoria = (
        db.get(Categoria, categoria_id_corrigida) if categoria_id_corrigida else categorias_gasto.get(item.categoria)
    )

    mes_termino = None
    if item.total_parcelas and item.parcela_atual and item.total_parcelas > item.parcela_atual:
        mes_termino = somar_meses(mes_referencia, item.total_parcelas - item.parcela_atual)

    # Se uma parcela anterior desse mesmo parcelamento já foi marcada como
    # "de terceiro" (ver marcar_parcela_terceiro em status.py), a parcela nova
    # já entra marcada também — sem isso, o usuário teria que remarcar todo
    # mês. Usa chave_parcelamento (não estabelecimento_id) porque o mesmo
    # estabelecimento às vezes resolve com texto diferente entre importações.
    terceiro = False
    if item.total_parcelas:
        chave = (item.data, item.total_parcelas, round(item.valor))
        candidatos = (
            db.query(LancamentoFatura)
            .filter(
                LancamentoFatura.data == item.data,
                LancamentoFatura.total_parcelas == item.total_parcelas,
                LancamentoFatura.terceiro.is_(True),
            )
            .all()
        )
        terceiro = any(chave_parcelamento(c) == chave for c in candidatos)

    db.add(
        LancamentoFatura(
            mes_referencia=mes_referencia,
            data=item.data,
            descricao_bruta=item.estabelecimento,
            estabelecimento_id=estabelecimento.id,
            categoria_gasto_id=categoria.id if categoria else None,
            valor=item.valor,
            origem=origem,
            parcela_atual=item.parcela_atual,
            total_parcelas=item.total_parcelas,
            grupo_parcelamento=str(uuid.uuid4()) if item.total_parcelas else None,
            mes_termino=mes_termino,
            terceiro=terceiro,
        )
    )


@router.post("/nfce", response_model=NfcePreviewResponse)
async def preview_nfce(imagem: UploadFile, db: Session = Depends(get_db)):
    categorias_validas = [
        c.nome for c in db.query(Categoria).filter(Categoria.tipo == TipoCategoria.PRODUTO).all()
    ]
    conteudo = await imagem.read()
    try:
        dados = extract_nfce(conteudo, imagem.content_type or "image/jpeg", categorias_validas)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    itens_preview: list[ItemNfcePreview] = []
    try:
        for item in dados["itens"]:
            resolucao = identidade.resolver_produto(
                db,
                codigo_barras=item.get("codigo"),
                descricao=item["descricao"],
                quantidade=item["quantidade"],
                unidade=item["unidade"],
                categoria_nome=item["categoria"],
            )
            itens_preview.append(
                ItemNfcePreview(
                    descricao=item["descricao"],
                    categoria_sugerida=item["categoria"],
                    quantidade=item["quantidade"],
                    unidade=item["unidade"],
                    preco_unitario=item["preco_unitario"],
                    valor_total=item["valor_total"],
                    resolucao_status=resolucao.status,
                    # "criado_novo" tem produto.id de um flush que será desfeito no
                    # rollback abaixo — nunca expor esse id, ou o confirmar() referenciaria
                    # uma linha que não existe mais. Só match_exato aponta pra um produto
                    # que já existia antes desta chamada (id real e estável).
                    produto_id=resolucao.produto.id if resolucao.status == "match_exato" else None,
                    candidatos=[c.id for c in resolucao.candidatos],
                )
            )
    finally:
        # Preview nunca persiste: desfaz qualquer INSERT feito por resolver_produto
        # ao criar produtos novos durante a resolução (ver plano de implementação).
        db.rollback()

    ja_lida = (
        db.query(Compra)
        .filter(Compra.nfce_chave_acesso == dados["documento"]["chave_acesso"])
        .first()
        is not None
    )

    return NfcePreviewResponse(
        chave_acesso=dados["documento"]["chave_acesso"],
        estabelecimento_nome_bruto=dados["estabelecimento"]["razao_social"],
        data_emissao=dados["documento"]["data_emissao"],
        itens=itens_preview,
        valor_total_nota=dados["valor_total_nota"],
        ja_lida=ja_lida,
    )


@router.post("/nfce/confirmar", status_code=201)
def confirmar_nfce(payload: NfceConfirmarRequest, db: Session = Depends(get_db)):
    ja_lida = db.query(Compra).filter(Compra.nfce_chave_acesso == payload.chave_acesso).first() is not None
    if ja_lida:
        raise HTTPException(status_code=409, detail="Esta nota já foi lida e registrada antes — não pode ser processada de novo.")

    estabelecimento = identidade.resolver_estabelecimento(
        db,
        nome_bruto=payload.estabelecimento_nome_bruto,
        cnpj=payload.estabelecimento_cnpj,
        endereco=payload.estabelecimento_endereco,
    )

    compras_criadas = 0
    for item in payload.itens:
        if item.produto_id is not None:
            produto = db.get(Produto, item.produto_id)
            if produto is None:
                raise HTTPException(status_code=400, detail=f"Produto {item.produto_id} não encontrado.")
        else:
            produto = identidade.criar_produto(
                db,
                codigo_barras=None,
                descricao=item.descricao,
                quantidade=item.quantidade,
                unidade=item.unidade,
                categoria_nome=item.categoria_sugerida,
            )

        db.add(
            Compra(
                produto_id=produto.id,
                estabelecimento_id=estabelecimento.id,
                descricao_bruta=item.descricao,
                preco=item.preco_unitario,
                quantidade=item.quantidade,
                data=payload.data_emissao,
                origem=OrigemCompra.NFCE,
                nfce_chave_acesso=payload.chave_acesso,
            )
        )
        compras_criadas += 1

    db.commit()
    return {"compras_criadas": compras_criadas}


@router.post("/fatura", response_model=FaturaPreviewResponse)
async def preview_fatura(paginas: list[UploadFile] = File(...), db: Session = Depends(get_db)):
    """Preview stateless — extrai e estrutura os lançamentos, sem gravar nada.
    Gravação de fato acontece em /fatura/confirmar, após revisão do usuário.

    `paginas` é uma foto/print por página da fatura fechada, na ordem em que
    aparecem (mesma técnica de visão do parser de NFC-e e do print semanal —
    ver parser_fatura.py)."""
    categorias_validas = [
        c.nome for c in db.query(Categoria).filter(Categoria.tipo == TipoCategoria.GASTO).all()
    ]
    imagens = [await pagina.read() for pagina in paginas]
    dados = extract_fatura(imagens, categorias_validas)

    if not dados.get("vencimento"):
        raise HTTPException(
            status_code=422,
            detail=(
                "Não encontrei a data de vencimento nas fotos enviadas — inclua a página de "
                "resumo/capa da fatura (a que mostra 'Com vencimento em: ...') e tente de novo."
            ),
        )
    vencimento = date.fromisoformat(dados["vencimento"])
    # A fatura com vencimento em julho fecha por volta do dia 2 de julho e cobre,
    # majoritariamente, os gastos de JUNHO — por isso mes_referencia é o mês
    # anterior ao do vencimento (convenção real do cartão, não o mês em que ela
    # é paga). O ciclo de parcelas, por outro lado, incrementa junto com o mês
    # de vencimento (parcela 7/12 nesta fatura -> 8/12 na de vencimento seguinte),
    # então a aritmética de parcela usa o mês do vencimento como âncora, não o
    # mes_referencia.
    vencimento_mes_ref = f"{vencimento.year:04d}-{vencimento.month:02d}"
    mes_referencia = somar_meses(vencimento_mes_ref, -1)

    lancamentos = [
        LancamentoFaturaItem(
            data=_resolver_data_lancamento(
                dia=item["dia"],
                mes_nome=item["mes_nome"],
                parcela_atual=item.get("parcela_atual"),
                vencimento_mes_ref=vencimento_mes_ref,
                mes_referencia=mes_referencia,
            ),
            estabelecimento=item["estabelecimento"],
            valor=item["valor"],
            categoria=item["categoria"],
            parcela_atual=item.get("parcela_atual"),
            total_parcelas=item.get("total_parcelas"),
        )
        for item in dados["lancamentos"]
    ]

    return FaturaPreviewResponse(
        cartao_titular=dados["cartao"]["titular"],
        cartao_final=dados["cartao"]["final"],
        vencimento=vencimento,
        mes_referencia=mes_referencia,
        total_fatura=dados["total_fatura"],
        lancamentos=lancamentos,
    )


@router.post("/fatura/confirmar", status_code=201)
def confirmar_fatura(payload: FaturaConfirmarRequest, db: Session = Depends(get_db)):
    categorias_gasto = {
        c.nome: c for c in db.query(Categoria).filter(Categoria.tipo == TipoCategoria.GASTO).all()
    }

    # A fatura fechada é a fonte definitiva do mês — substitui (não concilia)
    # qualquer lançamento provisório de print já registrado pra este mes_referencia.
    db.query(LancamentoFatura).filter(
        LancamentoFatura.mes_referencia == payload.mes_referencia,
        LancamentoFatura.origem == OrigemCompra.PRINT,
    ).delete()

    for item in payload.lancamentos:
        _registrar_lancamento(
            db,
            mes_referencia=payload.mes_referencia,
            origem=OrigemCompra.PDF,
            item=item,
            categorias_gasto=categorias_gasto,
        )

    db.commit()
    return {"lancamentos_criados": len(payload.lancamentos)}


@router.post("/print", response_model=PrintPreviewResponse)
async def preview_print(
    imagem: UploadFile,
    mes_referencia: str = Form(...),
    db: Session = Depends(get_db),
):
    """Preview stateless — extrai os lançamentos do print e marca quais já
    foram lançados antes (mesma data+estabelecimento+valor no mês), pra
    evitar duplicar quando os prints semanais se sobrepõem."""
    categorias_validas = [
        c.nome for c in db.query(Categoria).filter(Categoria.tipo == TipoCategoria.GASTO).all()
    ]
    conteudo = await imagem.read()
    try:
        dados = extract_print(conteudo, categorias_validas)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Prints não têm data de vencimento impressa — o ciclo de parcelas ainda
    # incrementa junto com o mês de vencimento (mesma convenção da fatura em
    # PDF), então usamos o mês seguinte ao mes_referencia como âncora.
    vencimento_mes_ref = somar_meses(mes_referencia, 1)

    lancamentos_extraidos = [
        {
            "data": _resolver_data_lancamento(
                dia=item["dia"],
                mes_nome=item["mes_nome"],
                parcela_atual=item.get("parcela_atual"),
                vencimento_mes_ref=vencimento_mes_ref,
                mes_referencia=mes_referencia,
            ),
            "estabelecimento": item["estabelecimento"],
            "valor": item["valor"],
            "categoria": item["categoria"],
            "parcela_atual": item.get("parcela_atual"),
            "total_parcelas": item.get("total_parcelas"),
        }
        for item in dados["lancamentos"]
    ]

    existentes = {
        (e.data, e.descricao_bruta.strip().lower(), round(e.valor, 2))
        for e in db.query(LancamentoFatura).filter(LancamentoFatura.mes_referencia == mes_referencia).all()
    }

    lancamentos = [
        ItemPrintPreview(
            **item,
            duplicado=(item["data"], item["estabelecimento"].strip().lower(), round(item["valor"], 2)) in existentes,
        )
        for item in lancamentos_extraidos
    ]

    return PrintPreviewResponse(mes_referencia=mes_referencia, lancamentos=lancamentos)


@router.post("/print/confirmar", status_code=201)
def confirmar_print(payload: PrintConfirmarRequest, db: Session = Depends(get_db)):
    categorias_gasto = {
        c.nome: c for c in db.query(Categoria).filter(Categoria.tipo == TipoCategoria.GASTO).all()
    }

    for item in payload.lancamentos:
        _registrar_lancamento(
            db,
            mes_referencia=payload.mes_referencia,
            origem=OrigemCompra.PRINT,
            item=item,
            categorias_gasto=categorias_gasto,
        )

    db.commit()
    return {"lancamentos_criados": len(payload.lancamentos)}
