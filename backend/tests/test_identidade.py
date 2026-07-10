from backend.models import Categoria, Produto, TipoCategoria
from backend.services.identidade import (
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
