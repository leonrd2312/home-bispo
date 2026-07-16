from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Categoria, EventoConsumo, ItemListaCompra, Produto, StatusItemLista, TipoCategoria
from ..schemas import CategoriaResponse, ContagemProdutosResponse, ItemListaAdicionar, ProdutoCatalogoResponse
from ..services.precos import calcular_dias_medio_consumo, calcular_preco_referencia, produto_tem_compra_nfce

router = APIRouter(prefix="/catalogo", tags=["catalogo"])


@router.get("/categorias", response_model=list[CategoriaResponse])
def listar_categorias_produto(db: Session = Depends(get_db)):
    return db.query(Categoria).filter(Categoria.tipo == TipoCategoria.PRODUTO).order_by(Categoria.nome).all()


@router.get("/produtos", response_model=list[ProdutoCatalogoResponse])
def listar_produtos(
    q: str | None = Query(default=None),
    categoria_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    query = db.query(Produto)
    if categoria_id is not None:
        query = query.filter(Produto.categoria_id == categoria_id)
    if q:
        termo = f"%{q.strip().lower()}%"
        query = query.filter(Produto.nome_normalizado.like(termo))

    resultado = []
    for produto in query.order_by(Produto.nome_amigavel).all():
        preco_ref = calcular_preco_referencia(db, produto.id)
        acoes_disponiveis = produto_tem_compra_nfce(db, produto.id)
        na_lista = (
            db.query(ItemListaCompra)
            .filter(ItemListaCompra.produto_id == produto.id, ItemListaCompra.status == StatusItemLista.PENDENTE)
            .first()
            is not None
        )
        resultado.append(
            ProdutoCatalogoResponse(
                id=produto.id,
                nome_amigavel=produto.nome_amigavel,
                categoria=produto.categoria.nome if produto.categoria else None,
                dias_medio_consumo=calcular_dias_medio_consumo(db, produto.id),
                ultimo_preco=preco_ref.ultimo_preco,
                ultimo_local=preco_ref.ultimo_local,
                ultima_compra_data=preco_ref.ultima_compra_data,
                melhor_preco=preco_ref.melhor_preco,
                melhor_local=preco_ref.melhor_local,
                acoes_disponiveis=acoes_disponiveis,
                na_lista=na_lista,
            )
        )
    return resultado


@router.get("/produtos/contagem", response_model=ContagemProdutosResponse)
def contagem_produtos(db: Session = Depends(get_db)):
    return ContagemProdutosResponse(total=db.query(Produto).count())


def _exigir_produto_com_historico_nfce(db: Session, produto_id: int) -> Produto:
    produto = db.get(Produto, produto_id)
    if produto is None:
        raise HTTPException(status_code=404, detail="Produto não encontrado.")
    if not produto_tem_compra_nfce(db, produto_id):
        raise HTTPException(
            status_code=400,
            detail="Produto ainda sem compra registrada via nota fiscal.",
        )
    return produto


@router.post("/produtos/{produto_id}/acabou", status_code=201)
def marcar_produto_acabou(produto_id: int, db: Session = Depends(get_db)):
    _exigir_produto_com_historico_nfce(db, produto_id)
    db.add(EventoConsumo(produto_id=produto_id, data=date.today()))
    db.commit()
    return {"ok": True}


@router.post("/produtos/{produto_id}/lista", status_code=201)
def adicionar_produto_lista(produto_id: int, payload: ItemListaAdicionar, db: Session = Depends(get_db)):
    _exigir_produto_com_historico_nfce(db, produto_id)
    item = db.query(ItemListaCompra).filter(ItemListaCompra.produto_id == produto_id).first()
    if item is None:
        item = ItemListaCompra(produto_id=produto_id, status=StatusItemLista.PENDENTE, quantidade=payload.quantidade)
        db.add(item)
    else:
        item.status = StatusItemLista.PENDENTE
        item.quantidade = payload.quantidade
    db.commit()
    return {"ok": True}


@router.delete("/produtos/{produto_id}/lista", status_code=204)
def remover_produto_lista(produto_id: int, db: Session = Depends(get_db)):
    item = db.query(ItemListaCompra).filter(ItemListaCompra.produto_id == produto_id).first()
    if item is not None:
        db.delete(item)
        db.commit()
