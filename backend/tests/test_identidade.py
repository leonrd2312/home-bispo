from datetime import date

from backend.models import (
    Categoria,
    Compra,
    Estabelecimento,
    EventoConsumo,
    ItemListaCompra,
    OrigemCompra,
    Produto,
    TipoCategoria,
)
from backend.services.identidade import (
    encontrar_grupos_duplicados,
    excluir_produto,
    mesclar_produtos,
    normalizar_nome,
    normalizar_quantidade,
    resolver_estabelecimento,
    resolver_produto,
)


def test_normalizar_nome_remove_acento_e_espacos_duplicados():
    assert normalizar_nome("  Café   com AÇÚCAR  ") == "cafe com acucar"


def test_normalizar_nome_remove_pontuacao():
    # bug real: "Suco Tial 100% 1L" e "Suco Tial. 100% 1L" (ponto de OCR)
    # criavam produtos duplicados por terem nome_normalizado diferente.
    assert normalizar_nome("Suco Tial. 100% 1L") == normalizar_nome("Suco Tial 100% 1L")


def test_normalizar_quantidade_kg_para_g():
    assert normalizar_quantidade(0.540, "kg") == (540.0, "g")


def test_normalizar_quantidade_litro_para_ml():
    assert normalizar_quantidade(1, "l") == (1000.0, "ml")


def test_resolver_produto_match_exato_por_codigo_barras(db_session):
    existente = Produto(
        codigo_barras="789123",
        nome_amigavel="Arroz 5kg",
        nome_normalizado="arroz 5kg",
        quantidade_normalizada=5000,
        unidade_normalizada="g",
    )
    db_session.add(existente)
    db_session.flush()

    resultado = resolver_produto(
        db_session,
        codigo_barras="789123",
        descricao="ARROZ TIPO 1 5KG",  # descrição diferente na nota, não importa
        quantidade=5,
        unidade="kg",
    )

    assert resultado.status == "match_exato"
    assert resultado.produto.id == existente.id


def test_resolver_produto_cria_novo_quando_nao_existe(db_session):
    categoria = Categoria(nome="Grãos", tipo=TipoCategoria.PRODUTO)
    db_session.add(categoria)
    db_session.flush()

    resultado = resolver_produto(
        db_session,
        codigo_barras=None,
        descricao="Feijão Carioca 1kg",
        quantidade=1,
        unidade="kg",
        categoria_nome="Grãos",
    )

    assert resultado.status == "criado_novo"
    assert resultado.produto.nome_normalizado == "feijao carioca 1kg"
    assert resultado.produto.quantidade_normalizada == 1000.0
    assert resultado.produto.categoria_id == categoria.id


def test_resolver_produto_quantidade_diferente_e_sempre_produto_diferente(db_session):
    existente = Produto(
        nome_amigavel="Arroz",
        nome_normalizado="arroz",
        quantidade_normalizada=5000,
        unidade_normalizada="g",
    )
    db_session.add(existente)
    db_session.flush()

    resultado = resolver_produto(
        db_session, codigo_barras=None, descricao="Arroz", quantidade=2, unidade="kg"
    )

    assert resultado.status == "criado_novo"
    assert resultado.produto.id != existente.id


def test_resolver_produto_nome_parecido_quantidade_igual_pede_confirmacao(db_session):
    existente = Produto(
        nome_amigavel="Café Torrado 500g",
        nome_normalizado="cafe torrado 500g",
        quantidade_normalizada=500,
        unidade_normalizada="g",
    )
    db_session.add(existente)
    db_session.flush()

    resultado = resolver_produto(
        db_session, codigo_barras=None, descricao="Café Torrado e Moído 500g", quantidade=500, unidade="g"
    )

    assert resultado.status == "requer_confirmacao"
    assert resultado.produto is None
    assert existente in resultado.candidatos


def test_resolver_estabelecimento_cria_e_reutiliza(db_session):
    primeiro = resolver_estabelecimento(db_session, nome_bruto="SUPERMERCADOS BH LTDA", cnpj="123")
    segundo = resolver_estabelecimento(db_session, nome_bruto="SUPERMERCADOS BH LTDA")

    assert primeiro.id == segundo.id
    assert primeiro.cnpj == "123"


def _produto(nome_amigavel: str, nome_normalizado: str, quantidade: float, unidade: str = "un") -> Produto:
    return Produto(
        nome_amigavel=nome_amigavel,
        nome_normalizado=nome_normalizado,
        quantidade_normalizada=quantidade,
        unidade_normalizada=unidade,
    )


def test_encontrar_grupos_duplicados_identifica_exato(db_session):
    a = _produto("Sab Flor Ype 85G", "sab flor ype 85g", 3)
    b = _produto("Sab Flor Ype 85G", "sab flor ype 85g", 3)
    outro = _produto("Arroz 5kg", "arroz 5kg", 5000, "g")
    db_session.add_all([a, b, outro])
    db_session.flush()

    grupos = encontrar_grupos_duplicados(db_session)

    assert len(grupos) == 1
    assert grupos[0].tipo == "exato"
    assert set(grupos[0].produto_ids) == {a.id, b.id}


def test_encontrar_grupos_duplicados_nao_agrupa_nome_so_parecido(db_session):
    # nome parecido mas nao identico nao e agrupado automaticamente (ver
    # docstring de encontrar_grupos_duplicados: similaridade de texto simples
    # gera falso positivo em dado real) -- fica pra fluxo de confirmacao
    # manual em resolver_produto, nao pra sugestao de mesclagem.
    a = _produto("Alface Cres", "alface cres", 1)
    b = _produto("Alface Cres F V Hid", "alface cres f v hid", 1)
    db_session.add_all([a, b])
    db_session.flush()

    assert encontrar_grupos_duplicados(db_session) == []


def test_encontrar_grupos_duplicados_nao_agrupa_quantidade_diferente(db_session):
    a = _produto("Arroz 5kg", "arroz 5kg", 5000, "g")
    b = _produto("Arroz 5kg", "arroz 5kg", 2000, "g")
    db_session.add_all([a, b])
    db_session.flush()

    assert encontrar_grupos_duplicados(db_session) == []


def test_mesclar_produtos_reatribui_compras_eventos_e_lista(db_session):
    sobrevivente = _produto("Alface Cres F V Hid", "alface cres f v hid", 1)
    perdedor = _produto("Alface Cres F V Hid", "alface cres f v hid", 1)
    estabelecimento = Estabelecimento(nome_bruto="BH BURITIS")
    db_session.add_all([sobrevivente, perdedor, estabelecimento])
    db_session.flush()

    compra_sobrevivente = Compra(
        produto_id=sobrevivente.id, estabelecimento_id=estabelecimento.id,
        descricao_bruta="ALFACE", preco=5.78, quantidade=1, data=date(2026, 6, 29), origem=OrigemCompra.NFCE,
    )
    compra_perdedor = Compra(
        produto_id=perdedor.id, estabelecimento_id=estabelecimento.id,
        descricao_bruta="ALFACE", preco=5.78, quantidade=1, data=date(2026, 6, 29), origem=OrigemCompra.NFCE,
    )
    evento_perdedor = EventoConsumo(produto_id=perdedor.id, data=date(2026, 7, 1))
    item_lista_perdedor = ItemListaCompra(produto_id=perdedor.id)
    db_session.add_all([compra_sobrevivente, compra_perdedor, evento_perdedor, item_lista_perdedor])
    db_session.flush()

    mesclar_produtos(db_session, sobrevivente.id, [perdedor.id])
    db_session.flush()

    assert db_session.query(Produto).filter_by(id=perdedor.id).first() is None
    assert db_session.query(Compra).filter_by(produto_id=sobrevivente.id).count() == 2
    assert db_session.query(EventoConsumo).filter_by(produto_id=sobrevivente.id).count() == 1
    item_lista = db_session.query(ItemListaCompra).filter_by(produto_id=sobrevivente.id).first()
    assert item_lista is not None
    assert item_lista.id == item_lista_perdedor.id


def test_mesclar_produtos_remove_item_lista_duplicado_quando_ambos_estao_na_lista(db_session):
    sobrevivente = _produto("Alface Cres F V Hid", "alface cres f v hid", 1)
    perdedor = _produto("Alface Cres F V Hid", "alface cres f v hid", 1)
    db_session.add_all([sobrevivente, perdedor])
    db_session.flush()

    item_sobrevivente = ItemListaCompra(produto_id=sobrevivente.id)
    item_perdedor = ItemListaCompra(produto_id=perdedor.id)
    db_session.add_all([item_sobrevivente, item_perdedor])
    db_session.flush()

    mesclar_produtos(db_session, sobrevivente.id, [perdedor.id])
    db_session.flush()

    itens = db_session.query(ItemListaCompra).all()
    assert len(itens) == 1
    assert itens[0].produto_id == sobrevivente.id


def test_excluir_produto_apaga_dependentes_mas_preserva_estabelecimento(db_session):
    produto = _produto("Alface Cres F V Hid", "alface cres f v hid", 1)
    estabelecimento = Estabelecimento(nome_bruto="BH BURITIS")
    db_session.add_all([produto, estabelecimento])
    db_session.flush()

    db_session.add_all([
        Compra(
            produto_id=produto.id, estabelecimento_id=estabelecimento.id, descricao_bruta="ALFACE",
            preco=5.78, quantidade=1, data=date(2026, 6, 29), origem=OrigemCompra.NFCE,
        ),
        EventoConsumo(produto_id=produto.id, data=date(2026, 7, 1)),
        ItemListaCompra(produto_id=produto.id),
    ])
    db_session.flush()

    excluir_produto(db_session, produto.id)
    db_session.flush()

    assert db_session.query(Produto).filter_by(id=produto.id).first() is None
    assert db_session.query(Compra).count() == 0
    assert db_session.query(EventoConsumo).count() == 0
    assert db_session.query(ItemListaCompra).count() == 0
    assert db_session.query(Estabelecimento).filter_by(id=estabelecimento.id).first() is not None
