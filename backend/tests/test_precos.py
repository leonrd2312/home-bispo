from datetime import date

from backend.models import Compra, Estabelecimento, OrigemCompra, Produto
from backend.services.precos import calcular_dias_medio_consumo, calcular_preco_referencia


def _produto(db):
    produto = Produto(
        nome_amigavel="Suco Tial 100% 1L",
        nome_normalizado="suco tial 100 1l",
        quantidade_normalizada=1000,
        unidade_normalizada="ml",
    )
    db.add(produto)
    db.flush()
    return produto


def _estabelecimento(db, nome="BH Buritis"):
    estabelecimento = Estabelecimento(nome_bruto=nome)
    db.add(estabelecimento)
    db.flush()
    return estabelecimento


def _compra(db, produto, estabelecimento, data_compra, quantidade=1.0, preco=10.9):
    db.add(
        Compra(
            produto_id=produto.id,
            estabelecimento_id=estabelecimento.id,
            descricao_bruta=produto.nome_amigavel,
            preco=preco,
            quantidade=quantidade,
            data=data_compra,
            origem=OrigemCompra.NFCE,
        )
    )


def test_duracao_divide_pela_quantidade_comprada_no_intervalo(db_session):
    from backend.models import EventoConsumo

    produto = _produto(db_session)
    estabelecimento = _estabelecimento(db_session)

    # comprou 2 unidades de uma vez em 01/06, e só sinalizou "acabou" 30 dias
    # depois -> duração por unidade deve ser 30/2 = 15 dias, não 30.
    _compra(db_session, produto, estabelecimento, date(2026, 6, 1), quantidade=2.0)
    db_session.add(EventoConsumo(produto_id=produto.id, data=date(2026, 6, 1)))
    db_session.add(EventoConsumo(produto_id=produto.id, data=date(2026, 7, 1)))
    db_session.flush()

    resultado = calcular_dias_medio_consumo(db_session, produto.id)

    assert resultado == 15.0


def test_duracao_sem_compra_no_intervalo_assume_uma_unidade(db_session):
    from backend.models import EventoConsumo

    produto = _produto(db_session)

    db_session.add(EventoConsumo(produto_id=produto.id, data=date(2026, 6, 1)))
    db_session.add(EventoConsumo(produto_id=produto.id, data=date(2026, 6, 21)))
    db_session.flush()

    resultado = calcular_dias_medio_consumo(db_session, produto.id)

    assert resultado == 20.0


def test_duracao_com_menos_de_dois_eventos_e_none(db_session):
    from backend.models import EventoConsumo

    produto = _produto(db_session)
    db_session.add(EventoConsumo(produto_id=produto.id, data=date(2026, 6, 1)))
    db_session.flush()

    assert calcular_dias_medio_consumo(db_session, produto.id) is None


def test_preco_referencia_usa_preco_unitario_nao_o_total_da_linha(db_session):
    produto = _produto(db_session)
    caro = _estabelecimento(db_session, "Loja Cara")
    barato = _estabelecimento(db_session, "Loja Barata")

    _compra(db_session, produto, caro, date(2026, 6, 1), quantidade=5.0, preco=1.0)
    _compra(db_session, produto, barato, date(2026, 6, 10), quantidade=1.0, preco=0.8)
    db_session.flush()

    referencia = calcular_preco_referencia(db_session, produto.id)

    assert referencia.ultimo_preco == 0.8
    assert referencia.ultimo_local == "Loja Barata"
    assert referencia.melhor_preco == 0.8
