from datetime import date

from backend.models import Categoria, Estabelecimento, FormaPagamento, LancamentoFatura, OrigemCompra, TipoCategoria
from backend.routers.status import data_compra_parcelada, somar_meses


def test_somar_meses_mesmo_ano():
    assert somar_meses("2026-07", 1) == "2026-08"
    assert somar_meses("2026-07", -1) == "2026-06"


def test_somar_meses_vira_ano_seguinte():
    assert somar_meses("2026-12", 1) == "2027-01"


def test_somar_meses_vira_ano_anterior():
    assert somar_meses("2026-01", -1) == "2025-12"


def test_somar_meses_delta_grande():
    assert somar_meses("2026-07", -7) == "2025-12"
    assert somar_meses("2026-07", -12) == "2025-07"


# Casos de regressão: valores reais conferidos manualmente contra a fatura Itaú
# (vencimento 09/07/2026, mes_referencia "2026-07" -> vencimento_mes_ref) e o
# print do extrato seguinte (vencimento_mes_ref "2026-08"). Ver conversa de
# implementação do parser de fatura/print — bug real corrigido aqui: o modelo
# errava mês/ano em compras parceladas ao tentar "contar meses" sozinho.
def test_data_compra_parcelada_ultima_parcela_ano_anterior():
    # "ZURICH SEGUROS 07/12" na fatura de vencimento 2026-07, dia impresso 12
    assert data_compra_parcelada("2026-07", dia=12, parcela_atual=7) == date(2025, 12, 12)


def test_data_compra_parcelada_incrementa_no_proximo_ciclo():
    # a mesma parcela, um mês depois (vencimento_mes_ref 2026-08), agora 8/12
    assert data_compra_parcelada("2026-08", dia=12, parcela_atual=8) == date(2025, 12, 12)


def test_data_compra_parcelada_ultima_parcela_mesmo_ano():
    # "JIM.COM* TATIA 04/04" (última parcela) na fatura de vencimento 2026-07
    assert data_compra_parcelada("2026-07", dia=7, parcela_atual=4) == date(2026, 3, 7)


def test_data_compra_parcelada_clampa_dia_invalido_no_mes_calculado():
    # dia 31 impresso, mas o mês calculado (fevereiro) não tem dia 31
    resultado = data_compra_parcelada("2026-07", dia=31, parcela_atual=5)
    assert resultado.year == 2026
    assert resultado.month == 2
    assert resultado.day == 28


def test_recategorizar_lancamento_atualiza_lancamento_e_estabelecimento(client, db_session):
    cat_outros = Categoria(nome="Outros", tipo=TipoCategoria.GASTO)
    cat_transporte = Categoria(nome="Transporte", tipo=TipoCategoria.GASTO)
    db_session.add_all([cat_outros, cat_transporte])
    db_session.commit()

    estabelecimento = Estabelecimento(nome_bruto="99APP *99AppSaoP", categoria_gasto_id=cat_outros.id)
    db_session.add(estabelecimento)
    db_session.commit()

    lancamento = LancamentoFatura(
        mes_referencia="2026-07", data=date(2026, 7, 4), descricao_bruta="99APP *99AppSaoP",
        estabelecimento_id=estabelecimento.id, categoria_gasto_id=cat_outros.id, valor=23.10,
        origem=OrigemCompra.PDF, forma_pagamento=FormaPagamento.CREDITO,
    )
    db_session.add(lancamento)
    db_session.commit()

    resposta = client.patch(
        f"/api/status/lancamentos/{lancamento.id}/categoria",
        json={"categoria_id": cat_transporte.id},
    )

    assert resposta.status_code == 200
    db_session.refresh(lancamento)
    db_session.refresh(estabelecimento)
    assert lancamento.categoria_gasto_id == cat_transporte.id
    assert estabelecimento.categoria_gasto_id == cat_transporte.id  # vira o padrão pra próximos lançamentos


def test_recategorizar_lancamento_inexistente_devolve_404(client, db_session):
    cat = Categoria(nome="Outros", tipo=TipoCategoria.GASTO)
    db_session.add(cat)
    db_session.commit()

    resposta = client.patch("/api/status/lancamentos/999/categoria", json={"categoria_id": cat.id})
    assert resposta.status_code == 404


def test_recategorizar_lancamento_com_categoria_invalida_devolve_400(client, db_session):
    cat_produto = Categoria(nome="Grãos", tipo=TipoCategoria.PRODUTO)  # tipo errado (produto, não gasto)
    db_session.add(cat_produto)
    db_session.commit()

    lancamento = LancamentoFatura(
        mes_referencia="2026-07", data=date(2026, 7, 4), descricao_bruta="Loja X",
        valor=10.0, origem=OrigemCompra.PDF, forma_pagamento=FormaPagamento.CREDITO,
    )
    db_session.add(lancamento)
    db_session.commit()

    resposta = client.patch(
        f"/api/status/lancamentos/{lancamento.id}/categoria",
        json={"categoria_id": cat_produto.id},
    )
    assert resposta.status_code == 400
