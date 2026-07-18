from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Categoria, ConfigSistema, Estabelecimento, Produto, TipoCategoria
from ..schemas import (
    CategoriaCreate,
    CategoriaResponse,
    CategoriaUpdate,
    ConfigSistemaResponse,
    ConfigSistemaUpdate,
    EstabelecimentoConfigResponse,
    EstabelecimentoConfigUpdate,
    GrupoDuplicata,
    MesclarProdutosRequest,
    OrmModel,
    ProdutoConfigUpdate,
    ProdutoDuplicataItem,
)
from ..services import identidade
from ..services.precos import calcular_preco_referencia

router = APIRouter(prefix="/config", tags=["config"])


class ProdutoConfigResponse(OrmModel):
    id: int
    nome_amigavel: str
    codigo_barras: str | None
    categoria_id: int | None


# ---------- categorias ----------


@router.get("/categorias", response_model=list[CategoriaResponse])
def listar_categorias(tipo: TipoCategoria | None = Query(default=None), db: Session = Depends(get_db)):
    query = db.query(Categoria)
    if tipo is not None:
        query = query.filter(Categoria.tipo == tipo)
    return query.order_by(Categoria.nome).all()


@router.post("/categorias", response_model=CategoriaResponse, status_code=201)
def criar_categoria(payload: CategoriaCreate, db: Session = Depends(get_db)):
    categoria = Categoria(nome=payload.nome, tipo=payload.tipo)
    db.add(categoria)
    db.commit()
    db.refresh(categoria)
    return categoria


@router.patch("/categorias/{categoria_id}", response_model=CategoriaResponse)
def renomear_categoria(categoria_id: int, payload: CategoriaUpdate, db: Session = Depends(get_db)):
    categoria = db.get(Categoria, categoria_id)
    if categoria is None:
        raise HTTPException(status_code=404, detail="Categoria não encontrada.")
    categoria.nome = payload.nome
    db.commit()
    db.refresh(categoria)
    return categoria


@router.delete("/categorias/{categoria_id}", status_code=204)
def remover_categoria(categoria_id: int, db: Session = Depends(get_db)):
    categoria = db.get(Categoria, categoria_id)
    if categoria is not None:
        db.delete(categoria)
        db.commit()


# ---------- produtos ----------


@router.get("/produtos", response_model=list[ProdutoConfigResponse])
def listar_produtos(db: Session = Depends(get_db)):
    return db.query(Produto).order_by(Produto.nome_amigavel).all()


@router.patch("/produtos/{produto_id}", response_model=ProdutoConfigResponse)
def atualizar_produto(produto_id: int, payload: ProdutoConfigUpdate, db: Session = Depends(get_db)):
    produto = db.get(Produto, produto_id)
    if produto is None:
        raise HTTPException(status_code=404, detail="Produto não encontrado.")
    if payload.nome_amigavel is not None:
        produto.nome_amigavel = payload.nome_amigavel
    if payload.categoria_id is not None:
        produto.categoria_id = payload.categoria_id
    db.commit()
    db.refresh(produto)
    return produto


@router.get("/produtos/duplicados", response_model=list[GrupoDuplicata])
def listar_produtos_duplicados(db: Session = Depends(get_db)):
    grupos = []
    for grupo in identidade.encontrar_grupos_duplicados(db):
        produtos = db.query(Produto).filter(Produto.id.in_(grupo.produto_ids)).all()
        itens = []
        for p in produtos:
            ref = calcular_preco_referencia(db, p.id)
            itens.append(
                ProdutoDuplicataItem(
                    id=p.id,
                    nome_amigavel=p.nome_amigavel,
                    categoria_nome=p.categoria.nome if p.categoria else None,
                    total_compras=len(p.compras),
                    ultima_compra_data=ref.ultima_compra_data,
                    ultimo_preco=ref.ultimo_preco,
                )
            )
        itens.sort(key=lambda i: i.total_compras, reverse=True)
        grupos.append(GrupoDuplicata(tipo=grupo.tipo, produtos=itens))
    return grupos


@router.post("/produtos/mesclar")
def mesclar_produtos(payload: MesclarProdutosRequest, db: Session = Depends(get_db)):
    sobrevivente = db.get(Produto, payload.produto_sobrevivente_id)
    if sobrevivente is None:
        raise HTTPException(status_code=404, detail="Produto sobrevivente não encontrado.")

    ids_remover = [pid for pid in payload.produto_ids_a_remover if pid != payload.produto_sobrevivente_id]
    if not ids_remover:
        raise HTTPException(status_code=400, detail="Nenhum produto válido pra remover na mesclagem.")

    perdedores = db.query(Produto).filter(Produto.id.in_(ids_remover)).all()
    if len(perdedores) != len(set(ids_remover)):
        raise HTTPException(status_code=400, detail="Um ou mais produtos a remover não foram encontrados.")

    identidade.mesclar_produtos(db, payload.produto_sobrevivente_id, ids_remover)
    db.commit()
    return {"mesclados": len(perdedores)}


@router.delete("/produtos/{produto_id}", status_code=204)
def excluir_produto(produto_id: int, db: Session = Depends(get_db)):
    produto = db.get(Produto, produto_id)
    if produto is None:
        raise HTTPException(status_code=404, detail="Produto não encontrado.")
    identidade.excluir_produto(db, produto_id)
    db.commit()


# ---------- estabelecimentos ----------


@router.get("/estabelecimentos", response_model=list[EstabelecimentoConfigResponse])
def listar_estabelecimentos(db: Session = Depends(get_db)):
    return db.query(Estabelecimento).order_by(Estabelecimento.nome_bruto).all()


@router.patch("/estabelecimentos/{estabelecimento_id}", response_model=EstabelecimentoConfigResponse)
def atualizar_estabelecimento(
    estabelecimento_id: int, payload: EstabelecimentoConfigUpdate, db: Session = Depends(get_db)
):
    estabelecimento = db.get(Estabelecimento, estabelecimento_id)
    if estabelecimento is None:
        raise HTTPException(status_code=404, detail="Estabelecimento não encontrado.")
    if payload.nome_amigavel is not None:
        estabelecimento.nome_amigavel = payload.nome_amigavel
    if payload.categoria_gasto_id is not None:
        estabelecimento.categoria_gasto_id = payload.categoria_gasto_id
    db.commit()
    db.refresh(estabelecimento)
    return estabelecimento


# ---------- config do sistema ----------


def _obter_ou_criar_config(db: Session) -> ConfigSistema:
    config = db.get(ConfigSistema, 1)
    if config is None:
        config = ConfigSistema(id=1)
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


@router.get("/sistema", response_model=ConfigSistemaResponse)
def obter_config_sistema(db: Session = Depends(get_db)):
    return _obter_ou_criar_config(db)


@router.patch("/sistema", response_model=ConfigSistemaResponse)
def atualizar_config_sistema(payload: ConfigSistemaUpdate, db: Session = Depends(get_db)):
    config = _obter_ou_criar_config(db)
    if payload.dia_fechamento_fatura is not None:
        config.dia_fechamento_fatura = payload.dia_fechamento_fatura
    if payload.dia_vencimento is not None:
        config.dia_vencimento = payload.dia_vencimento
    db.commit()
    db.refresh(config)
    return config
