from backend.models import Categoria, Produto, TipoCategoria


def test_contagem_produtos_reflete_total_cadastrado(client, db_session):
    db_session.add(Categoria(nome="Grãos", tipo=TipoCategoria.PRODUTO))
    db_session.commit()
    categoria = db_session.query(Categoria).first()

    resposta_vazia = client.get("/api/catalogo/produtos/contagem")
    assert resposta_vazia.json() == {"total": 0}

    db_session.add_all([
        Produto(
            nome_amigavel="Arroz 5kg", nome_normalizado="arroz 5kg",
            quantidade_normalizada=5000, unidade_normalizada="g", categoria_id=categoria.id,
        ),
        Produto(
            nome_amigavel="Feijão 1kg", nome_normalizado="feijao 1kg",
            quantidade_normalizada=1000, unidade_normalizada="g", categoria_id=categoria.id,
        ),
    ])
    db_session.commit()

    resposta = client.get("/api/catalogo/produtos/contagem")
    assert resposta.status_code == 200
    assert resposta.json() == {"total": 2}
