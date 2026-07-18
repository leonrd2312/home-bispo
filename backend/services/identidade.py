"""Resolução de identidade de produto e de estabelecimento.

Regras críticas (não quebrar — ver CLAUDE.md):
- Código de barras presente = match exato.
- Sem código: normaliza nome+quantidade; quantidade diferente = SEMPRE produto diferente.
- Nome parecido + quantidade igual = nunca decide sozinho, pede confirmação.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from ..models import Categoria, Compra, Estabelecimento, EventoConsumo, ItemListaCompra, Produto, TipoCategoria

FATORES_UNIDADE = {"kg": 1000.0, "g": 1.0, "l": 1000.0, "ml": 1.0}


def normalizar_nome(nome: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    sem_pontuacao = re.sub(r"[^\w\s]", "", sem_acento)
    return re.sub(r"\s+", " ", sem_pontuacao.strip().lower())


def normalizar_quantidade(quantidade: float, unidade: str) -> tuple[float, str]:
    unidade = unidade.lower()
    if unidade in ("kg", "g"):
        return quantidade * FATORES_UNIDADE[unidade], "g"
    if unidade in ("l", "ml"):
        return quantidade * FATORES_UNIDADE[unidade], "ml"
    return quantidade, "un"


@dataclass
class ResolucaoProduto:
    status: str  # "match_exato" | "criado_novo" | "requer_confirmacao"
    produto: Produto | None = None
    candidatos: list[Produto] = field(default_factory=list)


def buscar_match_exato(db: Session, nome_normalizado: str, quantidade_normalizada: float, unidade_normalizada: str) -> Produto | None:
    return (
        db.query(Produto)
        .filter_by(
            nome_normalizado=nome_normalizado,
            quantidade_normalizada=quantidade_normalizada,
            unidade_normalizada=unidade_normalizada,
        )
        .first()
    )


def resolver_produto(
    db: Session,
    *,
    codigo_barras: str | None,
    descricao: str,
    quantidade: float,
    unidade: str,
    categoria_nome: str | None = None,
) -> ResolucaoProduto:
    if codigo_barras:
        existente = db.query(Produto).filter_by(codigo_barras=codigo_barras).first()
        if existente:
            return ResolucaoProduto("match_exato", produto=existente)
        return ResolucaoProduto(
            "criado_novo",
            produto=criar_produto(db, codigo_barras, descricao, quantidade, unidade, categoria_nome),
        )

    nome_norm = normalizar_nome(descricao)
    qtd_norm, un_norm = normalizar_quantidade(quantidade, unidade)

    match_exato = buscar_match_exato(db, nome_norm, qtd_norm, un_norm)
    if match_exato:
        return ResolucaoProduto("match_exato", produto=match_exato)

    # TODO(próxima sessão): similaridade de nome real (ex: rapidfuzz). Por ora,
    # candidatos = mesma quantidade normalizada com nome diferente — nunca decide sozinho.
    candidatos = (
        db.query(Produto)
        .filter_by(quantidade_normalizada=qtd_norm, unidade_normalizada=un_norm)
        .all()
    )
    if candidatos:
        return ResolucaoProduto("requer_confirmacao", candidatos=candidatos)

    return ResolucaoProduto(
        "criado_novo",
        produto=criar_produto(db, codigo_barras, descricao, quantidade, unidade, categoria_nome),
    )


def criar_produto(
    db: Session,
    codigo_barras: str | None,
    descricao: str,
    quantidade: float,
    unidade: str,
    categoria_nome: str | None,
) -> Produto:
    qtd_norm, un_norm = normalizar_quantidade(quantidade, unidade)
    categoria = None
    if categoria_nome:
        categoria = db.query(Categoria).filter_by(nome=categoria_nome, tipo=TipoCategoria.PRODUTO).first()
    produto = Produto(
        codigo_barras=codigo_barras,
        nome_amigavel=descricao.title(),
        nome_normalizado=normalizar_nome(descricao),
        quantidade_normalizada=qtd_norm,
        unidade_normalizada=un_norm,
        categoria_id=categoria.id if categoria else None,
    )
    db.add(produto)
    db.flush()
    return produto


def resolver_estabelecimento(
    db: Session, *, nome_bruto: str, cnpj: str | None = None, endereco: str | None = None
) -> Estabelecimento:
    existente = db.query(Estabelecimento).filter_by(nome_bruto=nome_bruto).first()
    if existente:
        return existente
    novo = Estabelecimento(nome_bruto=nome_bruto, cnpj=cnpj, endereco=endereco)
    db.add(novo)
    db.flush()
    return novo


@dataclass
class GrupoDuplicataProduto:
    tipo: str  # "exato"
    produto_ids: list[int]


def encontrar_grupos_duplicados(db: Session) -> list[GrupoDuplicataProduto]:
    """Agrupa produtos com nome+quantidade+unidade normalizados idênticos —
    ou seja, produtos que já são a mesma identidade que o sistema usa pra
    decidir "mesmo produto" (ver resolver_produto), mas que acabaram
    duplicados mesmo assim (dado de antes de uma correção no fluxo de
    confirmação de NFC-e, por exemplo). Confiança alta, sem falso positivo.

    Deliberadamente NÃO tenta agrupar por nome "parecido" com quantidade
    igual: testado com dados reais, uma métrica simples de similaridade de
    texto (difflib) pontuou produtos genuinamente diferentes — ex. "Fanta
    Guaraná 3L" vs "Fanta Laranja 2L" — como mais parecidos entre si do que
    o par que era de fato o mesmo produto ("Alface Cres" vs "Alface Cres F
    V Hid"). Sem uma medida melhor (rapidfuzz, por exemplo — ver TODO em
    resolver_produto), sugerir esses grupos faria mais mal que bem.
    """
    produtos = db.query(Produto).all()
    grupos: list[GrupoDuplicataProduto] = []

    exatos: dict[tuple[str, float, str], list[Produto]] = {}
    for p in produtos:
        chave = (p.nome_normalizado, p.quantidade_normalizada, p.unidade_normalizada)
        exatos.setdefault(chave, []).append(p)
    for itens in exatos.values():
        if len(itens) > 1:
            grupos.append(GrupoDuplicataProduto(tipo="exato", produto_ids=[p.id for p in itens]))

    return grupos


def mesclar_produtos(db: Session, sobrevivente_id: int, perdedor_ids: list[int]) -> None:
    """Reatribui compras/eventos/item-de-lista dos produtos perdedores pro
    sobrevivente e remove os perdedores. Não decide sozinho quem é o
    sobrevivente — isso é escolha do usuário, feita antes de chamar aqui."""
    perdedor_ids = [pid for pid in perdedor_ids if pid != sobrevivente_id]
    if not perdedor_ids:
        return

    db.query(Compra).filter(Compra.produto_id.in_(perdedor_ids)).update(
        {"produto_id": sobrevivente_id}, synchronize_session=False
    )
    db.query(EventoConsumo).filter(EventoConsumo.produto_id.in_(perdedor_ids)).update(
        {"produto_id": sobrevivente_id}, synchronize_session=False
    )

    sobrevivente_tem_item_lista = (
        db.query(ItemListaCompra).filter(ItemListaCompra.produto_id == sobrevivente_id).first() is not None
    )
    for item in db.query(ItemListaCompra).filter(ItemListaCompra.produto_id.in_(perdedor_ids)).all():
        if sobrevivente_tem_item_lista:
            db.delete(item)
        else:
            item.produto_id = sobrevivente_id
            sobrevivente_tem_item_lista = True

    db.query(Produto).filter(Produto.id.in_(perdedor_ids)).delete(synchronize_session=False)


def excluir_produto(db: Session, produto_id: int) -> None:
    """Apaga o produto e todo o histórico que só existe em função dele
    (compras, eventos de consumo, item na lista). Não mexe em
    estabelecimento — a compra some, o estabelecimento onde foi feita
    continua cadastrado normalmente."""
    db.query(Compra).filter(Compra.produto_id == produto_id).delete(synchronize_session=False)
    db.query(EventoConsumo).filter(EventoConsumo.produto_id == produto_id).delete(synchronize_session=False)
    db.query(ItemListaCompra).filter(ItemListaCompra.produto_id == produto_id).delete(synchronize_session=False)
    db.query(Produto).filter(Produto.id == produto_id).delete(synchronize_session=False)
