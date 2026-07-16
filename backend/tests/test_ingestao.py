from datetime import date

from backend.models import (
    Categoria,
    Compra,
    Estabelecimento,
    LancamentoFatura,
    OrigemCompra,
    Produto,
    TipoCategoria,
)


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


def test_confirmar_nfce_bloqueia_nota_ja_lida(client, db_session, monkeypatch):
    db_session.add(Categoria(nome="Grãos", tipo=TipoCategoria.PRODUTO))
    db_session.commit()
    monkeypatch.setattr("backend.routers.ingestao.extract_nfce", lambda *a, **k: _dados_nfce_fake())

    payload = {
        "chave_acesso": "31260604641376016563650150001823491702951201",
        "estabelecimento_nome_bruto": "SUPERMERCADOS BH COM. DE ALIMENTOS S.A",
        "estabelecimento_cnpj": None,
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

    primeira = client.post("/api/ingestao/nfce/confirmar", json=payload)
    assert primeira.status_code == 201

    # Preview da mesma nota agora deve avisar que já foi lida
    preview = client.post("/api/ingestao/nfce", files={"imagem": ("nota.jpg", b"fake", "image/jpeg")})
    assert preview.json()["ja_lida"] is True

    # E confirmar de novo deve ser bloqueado, não duplicado
    segunda = client.post("/api/ingestao/nfce/confirmar", json=payload)
    assert segunda.status_code == 409
    assert db_session.query(Compra).count() == 1


def test_confirmar_fatura_substitui_lancamentos_print_do_mesmo_mes(client, db_session):
    db_session.add(Categoria(nome="Supermercado", tipo=TipoCategoria.GASTO))
    db_session.commit()

    # simula um lançamento de print já gravado pra julho/2026
    db_session.add(
        LancamentoFatura(
            mes_referencia="2026-07",
            data=date(2026, 7, 3),
            descricao_bruta="LOJA DO PRINT",
            valor=50.0,
            origem=OrigemCompra.PRINT,
        )
    )
    db_session.commit()
    assert db_session.query(LancamentoFatura).count() == 1

    payload = {
        "mes_referencia": "2026-07",
        "lancamentos": [
            {
                "data": "2026-07-05",
                "estabelecimento": "SUPERMERCADO DA FATURA",
                "valor": 120.0,
                "categoria": "Supermercado",
                "parcela_atual": None,
                "total_parcelas": None,
            }
        ],
    }

    resposta = client.post("/api/ingestao/fatura/confirmar", json=payload)

    assert resposta.status_code == 201
    lancamentos = db_session.query(LancamentoFatura).filter(LancamentoFatura.mes_referencia == "2026-07").all()
    assert len(lancamentos) == 1  # o de print sumiu, só ficou o da fatura
    assert lancamentos[0].origem == OrigemCompra.PDF
    assert lancamentos[0].descricao_bruta == "SUPERMERCADO DA FATURA"


def test_confirmar_fatura_usa_categoria_corrigida_do_estabelecimento(client, db_session):
    # Categoria "errada" que a extração da fatura vai sugerir desta vez
    cat_outros = Categoria(nome="Outros", tipo=TipoCategoria.GASTO)
    # Categoria que o usuário já corrigiu manualmente antes (ver recategorizar_lancamento)
    cat_transporte = Categoria(nome="Transporte", tipo=TipoCategoria.GASTO)
    db_session.add_all([cat_outros, cat_transporte])
    db_session.commit()

    db_session.add(Estabelecimento(nome_bruto="99APP *99AppSaoP", categoria_gasto_id=cat_transporte.id))
    db_session.commit()

    payload = {
        "mes_referencia": "2026-07",
        "lancamentos": [
            {
                "data": "2026-07-04",
                "estabelecimento": "99APP *99AppSaoP",
                "valor": 23.10,
                "categoria": "Outros",  # é o que a extração sugeriu desta vez
                "parcela_atual": None,
                "total_parcelas": None,
            }
        ],
    }

    resposta = client.post("/api/ingestao/fatura/confirmar", json=payload)

    assert resposta.status_code == 201
    lancamento = db_session.query(LancamentoFatura).filter(LancamentoFatura.mes_referencia == "2026-07").first()
    # a correção manual no estabelecimento prevalece sobre a categoria extraída
    assert lancamento.categoria_gasto_id == cat_transporte.id


def test_confirmar_fatura_herda_terceiro_de_parcela_ja_marcada(client, db_session):
    db_session.add(Categoria(nome="Outros", tipo=TipoCategoria.GASTO))
    db_session.commit()

    estabelecimento = Estabelecimento(nome_bruto="Cappta *Mobiliadora")
    db_session.add(estabelecimento)
    db_session.commit()
    # parcela 1/6 de maio, já marcada como terceiro antes (ver marcar_parcela_terceiro)
    db_session.add(
        LancamentoFatura(
            mes_referencia="2026-05", data=date(2026, 4, 4), descricao_bruta="Cappta *Mobiliadora",
            estabelecimento_id=estabelecimento.id, valor=464.13, origem=OrigemCompra.PDF,
            parcela_atual=1, total_parcelas=6, terceiro=True,
        )
    )
    db_session.commit()

    payload = {
        "mes_referencia": "2026-06",
        "lancamentos": [
            {
                "data": "2026-04-04",  # mesma data da compra original
                "estabelecimento": "Cappta *Mobiliadora",
                "valor": 464.13,
                "categoria": "Outros",
                "parcela_atual": 2,
                "total_parcelas": 6,
            }
        ],
    }

    resposta = client.post("/api/ingestao/fatura/confirmar", json=payload)

    assert resposta.status_code == 201
    parcela_nova = db_session.query(LancamentoFatura).filter(LancamentoFatura.mes_referencia == "2026-06").first()
    assert parcela_nova.terceiro is True  # herdou da parcela 1/6 já marcada


def test_confirmar_fatura_herda_terceiro_mesmo_com_estabelecimento_resolvendo_diferente(client, db_session):
    # A mesma compra pode resolver como um estabelecimento_id diferente do
    # mês anterior (texto ligeiramente diferente na fatura) — a herança do
    # terceiro não pode depender do estabelecimento_id bater.
    db_session.add(Categoria(nome="Outros", tipo=TipoCategoria.GASTO))
    db_session.commit()

    db_session.add(
        LancamentoFatura(
            mes_referencia="2026-05", data=date(2026, 4, 4), descricao_bruta="APP *COLAED",
            estabelecimento_id=None, valor=155.13, origem=OrigemCompra.PDF,
            parcela_atual=1, total_parcelas=10, terceiro=True,
        )
    )
    db_session.commit()

    payload = {
        "mes_referencia": "2026-06",
        "lancamentos": [
            {
                "data": "2026-04-04",
                "estabelecimento": "App *colaedecoragasparbra",  # texto diferente do mês anterior
                "valor": 155.10,  # centavos de diferença
                "categoria": "Outros",
                "parcela_atual": 2,
                "total_parcelas": 10,
            }
        ],
    }

    resposta = client.post("/api/ingestao/fatura/confirmar", json=payload)

    assert resposta.status_code == 201
    parcela_nova = db_session.query(LancamentoFatura).filter(LancamentoFatura.mes_referencia == "2026-06").first()
    assert parcela_nova.terceiro is True


def test_preview_fatura_aceita_multiplas_paginas_e_nao_persiste(client, db_session, monkeypatch):
    db_session.add(Categoria(nome="Supermercado", tipo=TipoCategoria.GASTO))
    db_session.commit()

    dados_fake = {
        "cartao": {"titular": "LEONARDO BISPO", "final": "1234"},
        "vencimento": "2026-07-09",
        "total_fatura": 120.0,
        "lancamentos": [
            {
                "dia": 5,
                "mes_nome": "junho",
                "estabelecimento": "SUPERMERCADO DA FATURA",
                "valor": 120.0,
                "categoria": "Supermercado",
                "parcela_atual": None,
                "total_parcelas": None,
            }
        ],
    }
    imagens_recebidas = []

    def _extract_fatura_fake(imagens, categorias_validas):
        imagens_recebidas.extend(imagens)
        return dados_fake

    monkeypatch.setattr("backend.routers.ingestao.extract_fatura", _extract_fatura_fake)

    resposta = client.post(
        "/api/ingestao/fatura",
        files=[
            ("paginas", ("pagina1.jpg", b"fake-pagina-1", "image/jpeg")),
            ("paginas", ("pagina2.jpg", b"fake-pagina-2", "image/jpeg")),
        ],
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["cartao_final"] == "1234"
    assert corpo["mes_referencia"] == "2026-06"  # vencimento em julho -> referência é junho
    assert imagens_recebidas == [b"fake-pagina-1", b"fake-pagina-2"]
    assert db_session.query(LancamentoFatura).count() == 0  # preview não grava nada


def test_preview_fatura_sem_pagina_de_capa_devolve_erro_claro(client, db_session, monkeypatch):
    db_session.add(Categoria(nome="Supermercado", tipo=TipoCategoria.GASTO))
    db_session.commit()

    # simula fotos que não incluem a página de resumo/capa (sem vencimento) —
    # cenário real que quebrava com "Invalid isoformat string: '<UNKNOWN>'"
    dados_sem_capa = {
        "cartao": {"titular": None, "final": None},
        "vencimento": None,
        "total_fatura": 120.0,
        "lancamentos": [],
    }
    monkeypatch.setattr("backend.routers.ingestao.extract_fatura", lambda *a, **k: dados_sem_capa)

    resposta = client.post(
        "/api/ingestao/fatura",
        files=[("paginas", ("pagina3.jpg", b"fake-pagina-3", "image/jpeg"))],
    )

    assert resposta.status_code == 422
    assert "vencimento" in resposta.json()["detail"]


def test_preview_print_marca_lancamento_ja_existente_como_duplicado(client, db_session, monkeypatch):
    db_session.add(Categoria(nome="Restaurante", tipo=TipoCategoria.GASTO))
    db_session.add(
        LancamentoFatura(
            mes_referencia="2026-07",
            data=date(2026, 7, 3),
            descricao_bruta="Ja Lancado Antes",
            valor=19.5,
            origem=OrigemCompra.PRINT,
        )
    )
    db_session.commit()

    dados_fake = {
        "lancamentos": [
            {
                "dia": 3, "mes_nome": "julho", "estabelecimento": "Ja Lancado Antes",
                "valor": 19.5, "categoria": "Restaurante", "parcela_atual": None, "total_parcelas": None,
            },
            {
                "dia": 3, "mes_nome": "julho", "estabelecimento": "Compra Nova",
                "valor": 30.0, "categoria": "Restaurante", "parcela_atual": None, "total_parcelas": None,
            },
        ]
    }
    monkeypatch.setattr("backend.routers.ingestao.extract_print", lambda *a, **k: dados_fake)

    resposta = client.post(
        "/api/ingestao/print",
        files={"imagem": ("extrato.jpg", b"fake", "image/jpeg")},
        data={"mes_referencia": "2026-07"},
    )

    assert resposta.status_code == 200
    lancamentos = resposta.json()["lancamentos"]
    por_estabelecimento = {l["estabelecimento"]: l["duplicado"] for l in lancamentos}
    assert por_estabelecimento["Ja Lancado Antes"] is True
    assert por_estabelecimento["Compra Nova"] is False
