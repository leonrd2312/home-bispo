from datetime import date

from backend.models import Categoria, Compra, Estabelecimento, OrigemCompra, Produto, TipoCategoria


def _produto(nome_amigavel: str, nome_normalizado: str, quantidade: float, unidade: str = "un") -> Produto:
    return Produto(
        nome_amigavel=nome_amigavel,
        nome_normalizado=nome_normalizado,
        quantidade_normalizada=quantidade,
        unidade_normalizada=unidade,
    )


def test_listar_produtos_duplicados_retorna_grupo_exato_com_metadados(client, db_session):
    categoria = Categoria(nome="Hortifruti", tipo=TipoCategoria.PRODUTO)
    estabelecimento = Estabelecimento(nome_bruto="BH BURITIS")
    db_session.add_all([categoria, estabelecimento])
    db_session.flush()

    a = _produto("Alface Cres F V Hid", "alface cres f v hid", 1)
    a.categoria_id = categoria.id
    b = _produto("Alface Cres F V Hid", "alface cres f v hid", 1)
    b.categoria_id = categoria.id
    db_session.add_all([a, b])
    db_session.flush()

    db_session.add(
        Compra(
            produto_id=a.id, estabelecimento_id=estabelecimento.id, descricao_bruta="ALFACE",
            preco=5.78, quantidade=1, data=date(2026, 6, 29), origem=OrigemCompra.NFCE,
        )
    )
    db_session.commit()

    resposta = client.get("/api/config/produtos/duplicados")

    assert resposta.status_code == 200
    grupos = resposta.json()
    assert len(grupos) == 1
    assert grupos[0]["tipo"] == "exato"
    ids = {p["id"] for p in grupos[0]["produtos"]}
    assert ids == {a.id, b.id}
    produto_com_compra = next(p for p in grupos[0]["produtos"] if p["id"] == a.id)
    assert produto_com_compra["total_compras"] == 1
    assert produto_com_compra["ultimo_preco"] == 5.78
    assert produto_com_compra["categoria_nome"] == "Hortifruti"


def test_mesclar_produtos_endpoint_reatribui_e_remove_perdedor(client, db_session):
    a = _produto("Alface Cres F V Hid", "alface cres f v hid", 1)
    b = _produto("Alface Cres F V Hid", "alface cres f v hid", 1)
    db_session.add_all([a, b])
    db_session.commit()

    resposta = client.post(
        "/api/config/produtos/mesclar",
        json={"produto_sobrevivente_id": a.id, "produto_ids_a_remover": [b.id]},
    )

    assert resposta.status_code == 200
    assert resposta.json() == {"mesclados": 1}
    assert db_session.query(Produto).filter_by(id=b.id).first() is None
    assert db_session.query(Produto).filter_by(id=a.id).first() is not None


def test_mesclar_produtos_endpoint_404_quando_sobrevivente_nao_existe(client, db_session):
    resposta = client.post(
        "/api/config/produtos/mesclar",
        json={"produto_sobrevivente_id": 9999, "produto_ids_a_remover": [1]},
    )
    assert resposta.status_code == 404


def test_excluir_produto_apaga_compras_eventos_e_item_lista_mas_preserva_estabelecimento(client, db_session):
    from backend.models import EventoConsumo, ItemListaCompra

    estabelecimento = Estabelecimento(nome_bruto="BH BURITIS")
    db_session.add(estabelecimento)
    db_session.flush()

    produto = _produto("Alface Cres F V Hid", "alface cres f v hid", 1)
    db_session.add(produto)
    db_session.flush()

    db_session.add_all([
        Compra(
            produto_id=produto.id, estabelecimento_id=estabelecimento.id, descricao_bruta="ALFACE",
            preco=5.78, quantidade=1, data=date(2026, 6, 29), origem=OrigemCompra.NFCE,
        ),
        EventoConsumo(produto_id=produto.id, data=date(2026, 7, 1)),
        ItemListaCompra(produto_id=produto.id),
    ])
    db_session.commit()

    resposta = client.delete(f"/api/config/produtos/{produto.id}")

    assert resposta.status_code == 204
    assert db_session.query(Produto).filter_by(id=produto.id).first() is None
    assert db_session.query(Compra).filter_by(produto_id=produto.id).count() == 0
    assert db_session.query(EventoConsumo).filter_by(produto_id=produto.id).count() == 0
    assert db_session.query(ItemListaCompra).filter_by(produto_id=produto.id).count() == 0
    assert db_session.query(Estabelecimento).filter_by(id=estabelecimento.id).first() is not None


def test_excluir_produto_404_quando_nao_existe(client, db_session):
    resposta = client.delete("/api/config/produtos/9999")
    assert resposta.status_code == 404


def test_catalogo_produtos_expoe_total_compras(client, db_session):
    estabelecimento = Estabelecimento(nome_bruto="BH BURITIS")
    db_session.add(estabelecimento)
    db_session.flush()

    produto = _produto("Alface Cres F V Hid", "alface cres f v hid", 1)
    db_session.add(produto)
    db_session.flush()

    db_session.add_all([
        Compra(
            produto_id=produto.id, estabelecimento_id=estabelecimento.id, descricao_bruta="ALFACE",
            preco=5.78, quantidade=1, data=date(2026, 6, 29), origem=OrigemCompra.NFCE,
        ),
        Compra(
            produto_id=produto.id, estabelecimento_id=estabelecimento.id, descricao_bruta="ALFACE",
            preco=6.20, quantidade=1, data=date(2026, 7, 10), origem=OrigemCompra.NFCE,
        ),
    ])
    db_session.commit()

    resposta = client.get("/api/catalogo/produtos")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert len(corpo) == 1
    assert corpo[0]["total_compras"] == 2
