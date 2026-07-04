from backend.models import Categoria, Compra, Produto, TipoCategoria


def _dados_nfce_fake(chave_acesso: str = "31260604641376016563650150001823491702951201"):
    return {
        "documento": {"chave_acesso": chave_acesso, "data_emissao": "2026-06-26T10:39:12"},
        "estabelecimento": {
            "razao_social": "SUPERMERCADOS BH COM. DE ALIMENTOS S.A",
            "cnpj": "04.641.376/0165-63",
            "endereco": None,
        },
        "itens": [
            {
                "codigo": None,
                "descricao": "ARROZ TIPO 1 5KG",
                "categoria": "Grãos",
                "quantidade": 1,
                "unidade": "un",
                "preco_unitario": 24.5,
                "valor_total": 24.5,
            }
        ],
        "valor_total_nota": 24.5,
    }


def test_preview_nfce_nao_persiste_produto_novo(client, db_session, monkeypatch):
    db_session.add(Categoria(nome="Grãos", tipo=TipoCategoria.PRODUTO))
    db_session.commit()

    monkeypatch.setattr("backend.routers.ingestao.extract_nfce", lambda *a, **k: _dados_nfce_fake())

    resposta = client.post("/api/ingestao/nfce", files={"imagem": ("nota.jpg", b"fake", "image/jpeg")})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["itens"][0]["resolucao_status"] == "criado_novo"
    assert corpo["itens"][0]["produto_id"] is None  # preview não expõe id de algo que foi desfeito
    assert db_session.query(Produto).count() == 0  # rollback confirmado: nada persistido


def test_confirmar_nfce_grava_produto_estabelecimento_e_compra(client, db_session, monkeypatch):
    db_session.add(Categoria(nome="Grãos", tipo=TipoCategoria.PRODUTO))
    db_session.commit()

    payload = {
        "chave_acesso": "31260604641376016563650150001823491702951201",
        "estabelecimento_nome_bruto": "SUPERMERCADOS BH COM. DE ALIMENTOS S.A",
        "estabelecimento_cnpj": "04.641.376/0165-63",
        "estabelecimento_endereco": None,
        "data_emissao": "2026-06-26",
        "itens": [
            {
                "descricao": "ARROZ TIPO 1 5KG",
                "categoria_sugerida": "Grãos",
                "quantidade": 1,
                "unidade": "un",
                "preco_unitario": 24.5,
                "valor_total": 24.5,
                "resolucao_status": "criado_novo",
                "produto_id": None,
                "candidatos": [],
            }
        ],
    }

    resposta = client.post("/api/ingestao/nfce/confirmar", json=payload)

    assert resposta.status_code == 201
    assert resposta.json() == {"compras_criadas": 1}
    assert db_session.query(Produto).count() == 1
    assert db_session.query(Compra).count() == 1
    compra = db_session.query(Compra).first()
    assert compra.nfce_chave_acesso == payload["chave_acesso"]
    assert compra.estabelecimento.nome_bruto == payload["estabelecimento_nome_bruto"]
