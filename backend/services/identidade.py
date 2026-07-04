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

from ..models import Categoria, Estabelecimento, Produto, TipoCategoria

FATORES_UNIDADE = {"kg": 1000.0, "g": 1.0, "l": 1000.0, "ml": 1.0}


def normalizar_nome(nome: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", sem_acento.strip().lower())


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

    match_exato = (
        db.query(Produto)
        .filter_by(nome_normalizado=nome_norm, quantidade_normalizada=qtd_norm, unidade_normalizada=un_norm)
        .first()
    )
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
