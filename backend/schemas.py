"""Schemas Pydantic de request/response, agrupados por router."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from .models import OrigemCompra, StatusItemLista, TipoCategoria

# ---------- comuns ----------


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- status ----------


class CategoriaGastoResumo(OrmModel):
    nome: str
    total: float
    pct: float
    qtd_lancamentos: int


class ParcelaResumo(OrmModel):
    id: int
    estabelecimento: str
    valor_parcela: float
    parcela_atual: int
    total_parcelas: int
    mes_termino: str
    ultima: bool
    terceiro: bool
    categoria: str
    nome_compra: str | None = None


class InsightResumo(OrmModel):
    tipo: str
    titulo: str
    texto: str


class LancamentoResumo(OrmModel):
    id: int
    data: date
    estabelecimento: str
    valor: float
    categoria: str
    parcela_atual: int | None = None
    total_parcelas: int | None = None
    terceiro: bool = False
    nome_compra: str | None = None


class RecategorizarLancamentoRequest(BaseModel):
    categoria_id: int


class NomearCompraRequest(BaseModel):
    nome_compra: str


class SplitFixoResto(OrmModel):
    fixo: float
    resto: float


class SplitNossoTerceiro(OrmModel):
    nosso: float
    terceiro: float


class StatusMesResponse(OrmModel):
    mes_referencia: str
    dia_atual: int
    dias_total: int
    gasto_ate_hoje: float
    media_historica: float | None
    comparacao_pct: float | None
    categorias: list[CategoriaGastoResumo]
    lancamentos: list[LancamentoResumo]
    parcelas: list[ParcelaResumo]
    split_fixo_resto: SplitFixoResto
    split_nossas_terceiros: SplitNossoTerceiro
    insights: list[InsightResumo]


class AlternarTerceiroRequest(BaseModel):
    terceiro: bool


# ---------- catalogo ----------


class CategoriaResponse(OrmModel):
    id: int
    nome: str
    tipo: TipoCategoria


class ProdutoCatalogoResponse(OrmModel):
    id: int
    nome_amigavel: str
    categoria: str | None
    dias_medio_consumo: float | None
    ultimo_preco: float | None
    ultimo_local: str | None
    ultima_compra_data: date | None
    melhor_preco: float | None
    melhor_local: str | None
    acoes_disponiveis: bool
    na_lista: bool


class ContagemProdutosResponse(BaseModel):
    total: int


# ---------- lista ----------


class ItemListaResponse(OrmModel):
    id: int
    produto_id: int
    nome_amigavel: str
    status: StatusItemLista
    quantidade: int
    data_inclusao: datetime
    ultimo_preco: float | None
    ultimo_local: str | None
    melhor_preco: float | None
    melhor_local: str | None


class ItemListaAdicionar(BaseModel):
    quantidade: int = 1


class ItemListaUpdate(BaseModel):
    status: StatusItemLista | None = None
    quantidade: int | None = None


class ContagemListaResponse(BaseModel):
    pendentes: int


# ---------- config ----------


class CategoriaCreate(BaseModel):
    nome: str
    tipo: TipoCategoria


class CategoriaUpdate(BaseModel):
    nome: str


class ProdutoConfigUpdate(BaseModel):
    nome_amigavel: str | None = None
    categoria_id: int | None = None


class EstabelecimentoConfigResponse(OrmModel):
    id: int
    nome_bruto: str
    nome_amigavel: str | None
    categoria_gasto_id: int | None
    categoria_gasto_nome: str | None


class EstabelecimentoConfigUpdate(BaseModel):
    nome_amigavel: str | None = None
    categoria_gasto_id: int | None = None


class ConfigSistemaResponse(OrmModel):
    dia_fechamento_fatura: int
    dia_vencimento: int


class ConfigSistemaUpdate(BaseModel):
    dia_fechamento_fatura: int | None = None
    dia_vencimento: int | None = None


# ---------- historico ----------


class MesHistoricoResponse(BaseModel):
    mes_referencia: str
    total: float
    variacao_pct: float | None
    nota_resumo: str | None


class NotaResumoUpdate(BaseModel):
    nota_resumo: str


# ---------- ingestao ----------


class ItemNfcePreview(BaseModel):
    descricao: str
    categoria_sugerida: str
    quantidade: float
    unidade: str
    preco_unitario: float
    valor_total: float
    resolucao_status: str  # match_exato | criado_novo | requer_confirmacao
    produto_id: int | None = None
    candidatos: list[int] = []


class NfcePreviewResponse(BaseModel):
    chave_acesso: str
    estabelecimento_nome_bruto: str
    data_emissao: datetime
    itens: list[ItemNfcePreview]
    valor_total_nota: float
    ja_lida: bool = False


class NfceConfirmarRequest(BaseModel):
    chave_acesso: str
    estabelecimento_nome_bruto: str
    estabelecimento_cnpj: str | None = None
    estabelecimento_endereco: str | None = None
    data_emissao: date
    itens: list[ItemNfcePreview]


class LancamentoFaturaItem(BaseModel):
    data: date
    estabelecimento: str
    valor: float
    categoria: str
    parcela_atual: int | None = None
    total_parcelas: int | None = None


class FaturaPreviewResponse(BaseModel):
    cartao_titular: str
    cartao_final: str
    vencimento: date
    mes_referencia: str
    total_fatura: float
    lancamentos: list[LancamentoFaturaItem]


class FaturaConfirmarRequest(BaseModel):
    mes_referencia: str
    lancamentos: list[LancamentoFaturaItem]


class ItemPrintPreview(LancamentoFaturaItem):
    duplicado: bool = False


class PrintPreviewResponse(BaseModel):
    mes_referencia: str
    lancamentos: list[ItemPrintPreview]


class PrintConfirmarRequest(BaseModel):
    mes_referencia: str
    lancamentos: list[LancamentoFaturaItem]
