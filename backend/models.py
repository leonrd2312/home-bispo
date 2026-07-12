"""Modelos SQLAlchemy do Home Bispo.

Compras parceladas não têm tabela própria — são linhas de LancamentoFatura
com parcela_atual/total_parcelas preenchidos (ver DOCUMENTACAO.md secao 4).
"""
from __future__ import annotations

import enum
from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class TipoCategoria(str, enum.Enum):
    PRODUTO = "produto"
    GASTO = "gasto"


class OrigemCompra(str, enum.Enum):
    NFCE = "nfce"
    PRINT = "print"
    PDF = "pdf"


class StatusItemLista(str, enum.Enum):
    PENDENTE = "pendente"
    COMPRADO = "comprado"


class FormaPagamento(str, enum.Enum):
    CREDITO = "credito"
    REFEICAO = "refeicao"


class Categoria(Base):
    __tablename__ = "categorias"
    __table_args__ = (UniqueConstraint("nome", "tipo", name="uq_categoria_nome_tipo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(80), nullable=False)
    tipo: Mapped[TipoCategoria] = mapped_column(SAEnum(TipoCategoria, native_enum=False), nullable=False)

    produtos: Mapped[list["Produto"]] = relationship(back_populates="categoria")
    estabelecimentos: Mapped[list["Estabelecimento"]] = relationship(back_populates="categoria_gasto")
    lancamentos: Mapped[list["LancamentoFatura"]] = relationship(back_populates="categoria_gasto")


class Produto(Base):
    __tablename__ = "produtos"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo_barras: Mapped[str | None] = mapped_column(String(20), unique=True, index=True)
    nome_amigavel: Mapped[str] = mapped_column(String(120), nullable=False)
    nome_normalizado: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    quantidade_normalizada: Mapped[float] = mapped_column(Float, nullable=False)
    unidade_normalizada: Mapped[str] = mapped_column(String(10), nullable=False)
    categoria_id: Mapped[int | None] = mapped_column(ForeignKey("categorias.id"))
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    categoria: Mapped["Categoria | None"] = relationship(back_populates="produtos")
    compras: Mapped[list["Compra"]] = relationship(back_populates="produto")
    eventos_consumo: Mapped[list["EventoConsumo"]] = relationship(back_populates="produto")
    item_lista: Mapped["ItemListaCompra | None"] = relationship(back_populates="produto", uselist=False)


class Estabelecimento(Base):
    __tablename__ = "estabelecimentos"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome_bruto: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    nome_amigavel: Mapped[str | None] = mapped_column(String(120))
    cnpj: Mapped[str | None] = mapped_column(String(20), index=True)
    endereco: Mapped[str | None] = mapped_column(String(200))
    categoria_gasto_id: Mapped[int | None] = mapped_column(ForeignKey("categorias.id"))

    categoria_gasto: Mapped["Categoria | None"] = relationship(back_populates="estabelecimentos")
    compras: Mapped[list["Compra"]] = relationship(back_populates="estabelecimento")
    lancamentos: Mapped[list["LancamentoFatura"]] = relationship(back_populates="estabelecimento")

    @property
    def nome_exibicao(self) -> str:
        return self.nome_amigavel or self.nome_bruto


class Compra(Base):
    __tablename__ = "compras"

    id: Mapped[int] = mapped_column(primary_key=True)
    produto_id: Mapped[int] = mapped_column(ForeignKey("produtos.id"), nullable=False)
    estabelecimento_id: Mapped[int] = mapped_column(ForeignKey("estabelecimentos.id"), nullable=False)
    descricao_bruta: Mapped[str] = mapped_column(String(120), nullable=False)
    preco: Mapped[float] = mapped_column(Float, nullable=False)
    quantidade: Mapped[float] = mapped_column(Float, default=1.0)
    data: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    origem: Mapped[OrigemCompra] = mapped_column(SAEnum(OrigemCompra, native_enum=False), nullable=False)
    nfce_chave_acesso: Mapped[str | None] = mapped_column(String(44), index=True)

    produto: Mapped["Produto"] = relationship(back_populates="compras")
    estabelecimento: Mapped["Estabelecimento"] = relationship(back_populates="compras")


class EventoConsumo(Base):
    __tablename__ = "eventos_consumo"

    id: Mapped[int] = mapped_column(primary_key=True)
    produto_id: Mapped[int] = mapped_column(ForeignKey("produtos.id"), nullable=False, index=True)
    data: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)

    produto: Mapped["Produto"] = relationship(back_populates="eventos_consumo")


class ItemListaCompra(Base):
    __tablename__ = "itens_lista_compra"

    id: Mapped[int] = mapped_column(primary_key=True)
    produto_id: Mapped[int] = mapped_column(ForeignKey("produtos.id"), unique=True, nullable=False)
    status: Mapped[StatusItemLista] = mapped_column(
        SAEnum(StatusItemLista, native_enum=False), default=StatusItemLista.PENDENTE
    )
    data_inclusao: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    produto: Mapped["Produto"] = relationship(back_populates="item_lista")


class LancamentoFatura(Base):
    """Linha de fatura de cartão. Parcelas = lançamentos com total_parcelas > 1;
    a seção 'Compras parceladas' do Status é uma query filtrada sobre esta tabela."""

    __tablename__ = "lancamentos_fatura"

    id: Mapped[int] = mapped_column(primary_key=True)
    mes_referencia: Mapped[str] = mapped_column(String(7), nullable=False, index=True)  # "2026-07"
    data: Mapped[date] = mapped_column(Date, nullable=False)
    descricao_bruta: Mapped[str] = mapped_column(String(150), nullable=False)
    estabelecimento_id: Mapped[int | None] = mapped_column(ForeignKey("estabelecimentos.id"))
    categoria_gasto_id: Mapped[int | None] = mapped_column(ForeignKey("categorias.id"))
    valor: Mapped[float] = mapped_column(Float, nullable=False)
    origem: Mapped[OrigemCompra] = mapped_column(SAEnum(OrigemCompra, native_enum=False), nullable=False)
    forma_pagamento: Mapped[FormaPagamento] = mapped_column(
        SAEnum(FormaPagamento, native_enum=False), nullable=False, default=FormaPagamento.CREDITO
    )

    parcela_atual: Mapped[int | None] = mapped_column(Integer)
    total_parcelas: Mapped[int | None] = mapped_column(Integer)
    grupo_parcelamento: Mapped[str | None] = mapped_column(String(36), index=True)
    mes_termino: Mapped[str | None] = mapped_column(String(7))
    # Compra parcelada de terceiro (alguém que usou nosso cartão, paga por
    # fora) — não afeta o total da fatura (a pessoa ainda usa nosso crédito),
    # só o retrato "nossas vs. terceiros" no Status. Identificar o mesmo
    # parcelamento em meses diferentes é feito por (estabelecimento_id, data,
    # total_parcelas), já que `data` é a data da COMPRA ORIGINAL e não muda
    # mês a mês (ver _resolver_data_lancamento em ingestao.py) — `grupo_parcelamento`
    # não serve pra isso porque é gerado de novo a cada importação.
    terceiro: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    estabelecimento: Mapped["Estabelecimento | None"] = relationship(back_populates="lancamentos")
    categoria_gasto: Mapped["Categoria | None"] = relationship(back_populates="lancamentos")

    @property
    def eh_parcelado(self) -> bool:
        return bool(self.total_parcelas and self.total_parcelas > 1)

    @property
    def parcelas_restantes(self) -> int | None:
        if not self.eh_parcelado:
            return None
        return self.total_parcelas - self.parcela_atual


class ResumoMensal(Base):
    """Só a nota-resumo textual do Histórico. Números vêm de LancamentoFatura."""

    __tablename__ = "resumos_mensais"

    mes_referencia: Mapped[str] = mapped_column(String(7), primary_key=True)
    nota_resumo: Mapped[str | None] = mapped_column(Text)
    congelado: Mapped[bool] = mapped_column(Boolean, default=False)


class ConfigSistema(Base):
    __tablename__ = "config_sistema"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    dia_fechamento_fatura: Mapped[int] = mapped_column(Integer, default=2)
    dia_vencimento: Mapped[int] = mapped_column(Integer, default=9)
