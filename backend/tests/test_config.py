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
