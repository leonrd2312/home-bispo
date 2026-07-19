from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ItemListaCompra, StatusItemLista
from ..schemas import ContagemListaResponse, ItemListaResponse, ItemListaUpdate
from ..services.precos import calcular_preco_referencia

router = APIRouter(prefix="/lista", tags=["lista"])


@router.get("", response_model=list[ItemListaResponse])
def listar_itens(
    status: StatusItemLista | None = Query(default=None),
    db: Session = Depends(get_db),
):
    query = db.query(ItemListaCompra)
    if status is not None:
        query = query.filter(ItemListaCompra.status == status)

    resultado = []
    for item in query.order_by(ItemListaCompra.data_inclusao.desc()).all():
        preco_ref = calcular_preco_referencia(db, item.produto_id)
        resultado.append(
            ItemListaResponse(
                id=item.id,
                produto_id=item.produto_id,
                nome_amigavel=item.produto.nome_amigavel,
                categoria=item.produto.categoria.nome if item.produto.categoria else None,
                status=item.status,
                quantidade=item.quantidade,
                data_inclusao=item.data_inclusao,
                ultimo_preco=preco_ref.ultimo_preco,
                ultimo_local=preco_ref.ultimo_local,
                melhor_preco=preco_ref.melhor_preco,
                melhor_local=preco_ref.melhor_local,
            )
        )
    return resultado


@router.get("/contagem", response_model=ContagemListaResponse)
def contagem_pendentes(db: Session = Depends(get_db)):
    pendentes = (
        db.query(ItemListaCompra).filter(ItemListaCompra.status == StatusItemLista.PENDENTE).count()
    )
    return ContagemListaResponse(pendentes=pendentes)


@router.patch("/{item_id}", response_model=ItemListaResponse)
def atualizar_item(item_id: int, payload: ItemListaUpdate, db: Session = Depends(get_db)):
    item = db.get(ItemListaCompra, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item não encontrado.")
    if payload.status is not None:
        item.status = payload.status
    if payload.quantidade is not None:
        item.quantidade = payload.quantidade
    db.commit()
    preco_ref = calcular_preco_referencia(db, item.produto_id)
    return ItemListaResponse(
        id=item.id,
        produto_id=item.produto_id,
        nome_amigavel=item.produto.nome_amigavel,
        categoria=item.produto.categoria.nome if item.produto.categoria else None,
        status=item.status,
        quantidade=item.quantidade,
        data_inclusao=item.data_inclusao,
        ultimo_preco=preco_ref.ultimo_preco,
        ultimo_local=preco_ref.ultimo_local,
        melhor_preco=preco_ref.melhor_preco,
        melhor_local=preco_ref.melhor_local,
    )


@router.delete("/{item_id}", status_code=204)
def remover_item(item_id: int, db: Session = Depends(get_db)):
    item = db.get(ItemListaCompra, item_id)
    if item is not None:
        db.delete(item)
        db.commit()
