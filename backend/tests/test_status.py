from datetime import date

from backend.models import Categoria, Estabelecimento, LancamentoFatura, OrigemCompra, TipoCategoria
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
        origem=OrigemCompra.PDF,
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
        valor=10.0, origem=OrigemCompra.PDF,
    )
    db_session.add(lancamento)
    db_session.commit()

    resposta = client.patch(
        f"/api/status/lancamentos/{lancamento.id}/categoria",
        json={"categoria_id": cat_produto.id},
    )
    assert resposta.status_code == 400


def _estabelecimento_com_parcelas(db_session, *, meses_ja_lancados: list[str]) -> Estabelecimento:
    """Simula um parcelamento de 6x já lançado em vários meses seguidos —
    mesma estabelecimento_id/data/total_parcelas, parcela_atual incrementando."""
    estabelecimento = Estabelecimento(nome_bruto="Cappta *Mobiliadora")
    db_session.add(estabelecimento)
    db_session.commit()

    for i, mes_referencia in enumerate(meses_ja_lancados, start=1):
        db_session.add(
            LancamentoFatura(
                mes_referencia=mes_referencia, data=date(2026, 4, 4), descricao_bruta="Cappta *Mobiliadora",
                estabelecimento_id=estabelecimento.id, valor=464.13, origem=OrigemCompra.PDF,
                parcela_atual=i, total_parcelas=6,
            )
        )
    db_session.commit()
    return estabelecimento


def test_listar_compras_parceladas_agrupa_por_parcelamento_nao_por_mes(client, db_session):
    _estabelecimento_com_parcelas(db_session, meses_ja_lancados=["2026-05", "2026-06", "2026-07"])

    resposta = client.get("/api/status/lancamentos-terceiros")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert len(corpo) == 1  # 3 lançamentos (um por mês), mas é 1 parcelamento só
    assert corpo[0]["parcela_atual"] == 3  # a mais recente das 3
    assert corpo[0]["terceiro"] is False


def test_listar_compras_parceladas_agrupa_mesmo_com_estabelecimento_diferente(client, db_session):
    # Caso real: "APP *COLAED" (mês 1) e "App *colaedecoragasparbra" (mês 2)
    # são a MESMA compra, mas resolveram como dois estabelecimento_id
    # diferentes — data/total_parcelas batem, valor diverge só por centavos.
    est1 = Estabelecimento(nome_bruto="APP *COLAED")
    est2 = Estabelecimento(nome_bruto="App *colaedecoragasparbra")
    db_session.add_all([est1, est2])
    db_session.commit()

    db_session.add_all([
        LancamentoFatura(
            mes_referencia="2026-06", data=date(2026, 6, 9), descricao_bruta="APP *COLAED",
            estabelecimento_id=est1.id, valor=155.13, origem=OrigemCompra.PDF,
            parcela_atual=1, total_parcelas=10,
        ),
        LancamentoFatura(
            mes_referencia="2026-07", data=date(2026, 6, 9), descricao_bruta="App *colaedecoragasparbra",
            estabelecimento_id=est2.id, valor=155.10, origem=OrigemCompra.PDF,
            parcela_atual=2, total_parcelas=10,
        ),
    ])
    db_session.commit()

    resposta = client.get("/api/status/lancamentos-terceiros")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert len(corpo) == 1  # não duas linhas
    assert corpo[0]["parcela_atual"] == 2  # prefere a do mes_referencia corrente (julho)


def test_marcar_terceiro_propaga_entre_estabelecimentos_diferentes_da_mesma_compra(client, db_session):
    est1 = Estabelecimento(nome_bruto="APP *COLAED")
    est2 = Estabelecimento(nome_bruto="App *colaedecoragasparbra")
    db_session.add_all([est1, est2])
    db_session.commit()

    lanc1 = LancamentoFatura(
        mes_referencia="2026-06", data=date(2026, 6, 9), descricao_bruta="APP *COLAED",
        estabelecimento_id=est1.id, valor=155.13, origem=OrigemCompra.PDF,
        parcela_atual=1, total_parcelas=10,
    )
    lanc2 = LancamentoFatura(
        mes_referencia="2026-07", data=date(2026, 6, 9), descricao_bruta="App *colaedecoragasparbra",
        estabelecimento_id=est2.id, valor=155.10, origem=OrigemCompra.PDF,
        parcela_atual=2, total_parcelas=10,
    )
    db_session.add_all([lanc1, lanc2])
    db_session.commit()

    resposta = client.patch(f"/api/status/lancamentos/{lanc2.id}/terceiro", json={"terceiro": True})

    assert resposta.status_code == 200
    db_session.refresh(lanc1)
    db_session.refresh(lanc2)
    assert lanc1.terceiro is True  # propagou pro outro estabelecimento_id
    assert lanc2.terceiro is True


def test_listar_compras_parceladas_omite_parcelamento_ja_concluido(client, db_session):
    estabelecimento = Estabelecimento(nome_bruto="MikeAugustoBor")
    db_session.add(estabelecimento)
    db_session.commit()
    db_session.add(
        LancamentoFatura(
            mes_referencia="2026-04", data=date(2025, 8, 12), descricao_bruta="MikeAugustoBor",
            estabelecimento_id=estabelecimento.id, valor=155.57, origem=OrigemCompra.PDF,
            parcela_atual=10, total_parcelas=10,
        )
    )
    db_session.commit()

    resposta = client.get("/api/status/lancamentos-terceiros")

    assert resposta.status_code == 200
    assert resposta.json() == []  # 10/10 já concluiu, não deve mais aparecer


def test_listar_compras_parceladas_omite_quando_mes_previsto_de_termino_ja_passou(client, db_session):
    # Caso real: parcela 9/10 lançada em abril/2026 (a 10/10 terminaria em
    # maio/2026), mas a última parcela nunca chegou a ser importada — mesmo
    # assim já passou do mês previsto de término (hoje é depois de maio/2026),
    # então deve sumir da lista igual a uma concluída de verdade.
    estabelecimento = Estabelecimento(nome_bruto="MikeAugustoBor")
    db_session.add(estabelecimento)
    db_session.commit()
    db_session.add(
        LancamentoFatura(
            mes_referencia="2026-04", data=date(2025, 8, 12), descricao_bruta="MikeAugustoBor",
            estabelecimento_id=estabelecimento.id, valor=155.57, origem=OrigemCompra.PDF,
            parcela_atual=9, total_parcelas=10,
        )
    )
    db_session.commit()

    resposta = client.get("/api/status/lancamentos-terceiros")

    assert resposta.status_code == 200
    assert resposta.json() == []


def test_marcar_parcela_terceiro_propaga_para_todos_os_meses_ja_lancados(client, db_session):
    _estabelecimento_com_parcelas(db_session, meses_ja_lancados=["2026-05", "2026-06", "2026-07"])
    lancamento_recente = (
        db_session.query(LancamentoFatura).filter(LancamentoFatura.mes_referencia == "2026-07").first()
    )

    resposta = client.patch(
        f"/api/status/lancamentos/{lancamento_recente.id}/terceiro", json={"terceiro": True}
    )

    assert resposta.status_code == 200
    todos = db_session.query(LancamentoFatura).all()
    assert len(todos) == 3
    assert all(l.terceiro for l in todos)  # os 3 meses já lançados, não só o de julho


def test_marcar_terceiro_em_lancamento_avulso_marca_so_ele_mesmo(client, db_session):
    # Compra de terceiro não precisa ser parcelada — uma compra avulsa (1x)
    # também pode ser de terceiro; marcar não deve propagar pra mais nada.
    lancamento = LancamentoFatura(
        mes_referencia="2026-07", data=date(2026, 7, 4), descricao_bruta="Loja X",
        valor=10.0, origem=OrigemCompra.PDF,
    )
    outro = LancamentoFatura(
        mes_referencia="2026-07", data=date(2026, 7, 4), descricao_bruta="Loja Y",
        valor=10.0, origem=OrigemCompra.PDF,
    )
    db_session.add_all([lancamento, outro])
    db_session.commit()

    resposta = client.patch(f"/api/status/lancamentos/{lancamento.id}/terceiro", json={"terceiro": True})

    assert resposta.status_code == 200
    db_session.refresh(lancamento)
    db_session.refresh(outro)
    assert lancamento.terceiro is True
    assert outro.terceiro is False


def test_marcar_terceiro_lancamento_inexistente_devolve_404(client, db_session):
    resposta = client.patch("/api/status/lancamentos/999/terceiro", json={"terceiro": True})
    assert resposta.status_code == 404


def test_listar_lancamentos_terceiros_inclui_avulsas_da_fatura_atual(client, db_session):
    mes_atual_hoje = date.today()
    mes_atual = f"{mes_atual_hoje.year:04d}-{mes_atual_hoje.month:02d}"

    avulsa = LancamentoFatura(
        mes_referencia=mes_atual, data=date(mes_atual_hoje.year, mes_atual_hoje.month, 1),
        descricao_bruta="Restaurante do amigo", valor=45.0, origem=OrigemCompra.PDF,
        # sem parcela_atual/total_parcelas
    )
    db_session.add(avulsa)
    db_session.commit()

    resposta = client.get("/api/status/lancamentos-terceiros")

    assert resposta.status_code == 200
    corpo = resposta.json()
    entrada = next(c for c in corpo if c["id"] == avulsa.id)
    assert entrada["total_parcelas"] is None
    assert entrada["terceiro"] is False


def test_split_nossas_terceiros_reflete_avulsa_marcada_como_terceiro(client, db_session):
    # Bug real: o card "Parcelas nossas vs. Terceiros" só somava
    # lançamentos parcelados — marcar uma compra AVULSA como terceiro não
    # movia o card, mesmo aparecendo certo no modal "Terceiros este mês".
    mes_atual_hoje = date.today()
    mes_atual = f"{mes_atual_hoje.year:04d}-{mes_atual_hoje.month:02d}"

    avulsa = LancamentoFatura(
        mes_referencia=mes_atual, data=date(mes_atual_hoje.year, mes_atual_hoje.month, 1),
        descricao_bruta="Restaurante do amigo", valor=45.0, origem=OrigemCompra.PDF,
        terceiro=True,
    )
    db_session.add(avulsa)
    db_session.commit()

    resposta = client.get("/api/status/mes")

    assert resposta.status_code == 200
    split = resposta.json()["split_nossas_terceiros"]
    assert split["terceiro"] == 45.0
