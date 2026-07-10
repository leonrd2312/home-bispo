from datetime import date

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
