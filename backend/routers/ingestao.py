"""Ingestão de NFC-e (foto, câmera ou galeria — mesma rota para o backend em
qualquer caso) e de fatura PDF (stub, ver plano de implementação).

Fluxo de NFC-e é stateless em duas fases: /nfce resolve identidade e devolve
um preview SEM gravar nada (rollback explícito no fim); /nfce/confirmar
recebe as decisões do usuário para itens ambíguos e grava de fato.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Categoria, Compra, OrigemCompra, Produto, TipoCategoria
from ..schemas import ItemNfcePreview, NfceConfirmarRequest, NfcePreviewResponse
from ..services import identidade
from ..services.parser_nfce import extract_nfce

router = APIRouter(prefix="/ingestao", tags=["ingestao"])


@router.post("/nfce", response_model=NfcePreviewResponse)
async def preview_nfce(imagem: UploadFile, db: Session = Depends(get_db)):
    categorias_validas = [
        c.nome for c in db.query(Categoria).filter(Categoria.tipo == TipoCategoria.PRODUTO).all()
    ]
    conteudo = await imagem.read()
    dados = extract_nfce(conteudo, imagem.content_type or "image/jpeg", categorias_validas)

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

    return NfcePreviewResponse(
        chave_acesso=dados["documento"]["chave_acesso"],
        estabelecimento_nome_bruto=dados["estabelecimento"]["razao_social"],
        data_emissao=dados["documento"]["data_emissao"],
        itens=itens_preview,
        valor_total_nota=dados["valor_total_nota"],
    )


@router.post("/nfce/confirmar", status_code=201)
def confirmar_nfce(payload: NfceConfirmarRequest, db: Session = Depends(get_db)):
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


@router.post("/fatura", status_code=501)
async def preview_fatura(pdf: UploadFile):
    """Reservado — parser de fatura (PyMuPDF) ainda não implementado.
    Contrato espelha o de NFC-e: preview aqui, gravação em /fatura/confirmar."""
    raise HTTPException(status_code=501, detail="Parser de fatura PDF ainda não implementado.")


@router.post("/fatura/confirmar", status_code=501)
def confirmar_fatura():
    raise HTTPException(status_code=501, detail="Parser de fatura PDF ainda não implementado.")
