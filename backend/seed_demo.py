"""Popula o banco com dados de demonstração pra visualizar o frontend
funcionando sem depender de leitura real de NFC-e/fatura.

Uso: python -m backend.seed_demo
Idempotente — limpa as tabelas de domínio (mantém config_sistema) antes de inserir.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from .database import SessionLocal
from .fuso_horario import hoje as hoje_brasil
from .models import (
    Categoria,
    Compra,
    Estabelecimento,
    EventoConsumo,
    ItemListaCompra,
    LancamentoFatura,
    OrigemCompra,
    Produto,
    ResumoMensal,
    StatusItemLista,
    TipoCategoria,
)


def mes_ref(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def somar_meses(mes_referencia: str, delta: int) -> str:
    ano, mes = (int(p) for p in mes_referencia.split("-"))
    total = (ano * 12 + (mes - 1)) + delta
    ano2, mes2 = divmod(total, 12)
    return f"{ano2:04d}-{mes2 + 1:02d}"


def normalizar(nome: str) -> str:
    return nome.strip().lower()


def main() -> None:
    db = SessionLocal()

    for Model in (EventoConsumo, ItemListaCompra, Compra, LancamentoFatura, ResumoMensal, Produto, Estabelecimento, Categoria):
        db.query(Model).delete()
    db.commit()

    hoje = hoje_brasil()
    mes_atual = mes_ref(hoje)
    mes_jun = somar_meses(mes_atual, -1)
    mes_mai = somar_meses(mes_atual, -2)
    mes_abr = somar_meses(mes_atual, -3)

    # ---------- categorias ----------
    cat_produto_nomes = ["Grãos", "Hortifruti", "Laticínios", "Limpeza", "Higiene"]
    cat_gasto_nomes = ["Supermercado", "Seguros", "Combustível", "Restaurante", "Outros"]

    cats_produto = {nome: Categoria(nome=nome, tipo=TipoCategoria.PRODUTO) for nome in cat_produto_nomes}
    cats_gasto = {nome: Categoria(nome=nome, tipo=TipoCategoria.GASTO) for nome in cat_gasto_nomes}
    db.add_all([*cats_produto.values(), *cats_gasto.values()])
    db.flush()

    # ---------- estabelecimentos ----------
    estabs = {
        "bh": Estabelecimento(nome_bruto="SUPERMERCADOS BHBELO HO", nome_amigavel="Supermercados BH", categoria_gasto=cats_gasto["Supermercado"]),
        "rococo": Estabelecimento(nome_bruto="RococoBeerLtdaBELO HORI", nome_amigavel=None, categoria_gasto=cats_gasto["Supermercado"]),
        "pad_jardim": Estabelecimento(nome_bruto="PAD JARDIM AMERICABELO", nome_amigavel=None, categoria_gasto=cats_gasto["Supermercado"]),
        "na_madruga": Estabelecimento(nome_bruto="NaMadrugaBeerBELO HORIZ", nome_amigavel=None, categoria_gasto=cats_gasto["Supermercado"]),
        "sr_granel": Estabelecimento(nome_bruto="SR A GRANEL HORTIFRUTI", nome_amigavel="SR A Granel", categoria_gasto=cats_gasto["Supermercado"]),
        "zurich": Estabelecimento(nome_bruto="ZURICH SEGUROS", nome_amigavel="Zurich Seguros", categoria_gasto=cats_gasto["Seguros"]),
        "posto": Estabelecimento(nome_bruto="POSTO SHELL BH", nome_amigavel="Posto Shell", categoria_gasto=cats_gasto["Combustível"]),
        "restaurante": Estabelecimento(nome_bruto="RESTAURANTE DO ZE", nome_amigavel="Restaurante do Zé", categoria_gasto=cats_gasto["Restaurante"]),
        "jim": Estabelecimento(nome_bruto="JIM.COM", nome_amigavel="Jim.com", categoria_gasto=cats_gasto["Outros"]),
        "pantani": Estabelecimento(nome_bruto="PANTANI MOTOCICLETAS", nome_amigavel="Pantani Motocicletas", categoria_gasto=cats_gasto["Outros"]),
        "mercado_livre": Estabelecimento(nome_bruto="MERCADOLIVRE*COMPRA", nome_amigavel="Mercado Livre", categoria_gasto=cats_gasto["Outros"]),
    }
    db.add_all(estabs.values())
    db.flush()

    # ---------- produtos ----------
    def produto(nome, categoria, qtd, unidade, codigo=None):
        return Produto(
            nome_amigavel=nome,
            nome_normalizado=normalizar(nome),
            quantidade_normalizada=qtd,
            unidade_normalizada=unidade,
            categoria=categoria,
            codigo_barras=codigo,
        )

    produtos = {
        "arroz": produto("Arroz 5kg", cats_produto["Grãos"], 5000, "g", "7896006751234"),
        "feijao": produto("Feijão carioca 1kg", cats_produto["Grãos"], 1000, "g", "7891234567890"),
        "cafe": produto("Café 500g", cats_produto["Grãos"], 500, "g"),
        "leite": produto("Leite integral 1L", cats_produto["Laticínios"], 1000, "ml", "7896051112223"),
        "queijo": produto("Queijo mussarela", cats_produto["Laticínios"], 400, "g"),
        "ovos": produto("Ovos (dúzia)", cats_produto["Hortifruti"], 12, "un"),
        "banana": produto("Banana prata (kg)", cats_produto["Hortifruti"], 1000, "g"),
        "abacate": produto("Abacate", cats_produto["Hortifruti"], 1, "un"),
        "detergente": produto("Detergente", cats_produto["Limpeza"], 500, "ml"),
        "papel_higienico": produto("Papel higiênico (12un)", cats_produto["Higiene"], 12, "un"),
    }
    db.add_all(produtos.values())
    db.flush()

    # ---------- compras (histórico de preço) ----------
    def compra(produto_key, estab_key, preco, dias_atras, quantidade=1.0):
        db.add(
            Compra(
                produto=produtos[produto_key],
                estabelecimento=estabs[estab_key],
                descricao_bruta=produtos[produto_key].nome_amigavel.upper(),
                preco=preco,
                quantidade=quantidade,
                data=hoje - timedelta(days=dias_atras),
                origem=OrigemCompra.NFCE,
                nfce_chave_acesso=str(uuid.uuid4().int)[:44],
            )
        )

    compra("arroz", "pad_jardim", 27.90, 6)
    compra("arroz", "bh", 24.50, 35)

    compra("feijao", "rococo", 8.49, 4)
    compra("feijao", "bh", 7.90, 40)

    compra("cafe", "na_madruga", 14.00, 5)
    compra("cafe", "rococo", 13.20, 32)

    compra("leite", "bh", 5.49, 2)

    compra("queijo", "pad_jardim", 32.90, 8)
    compra("queijo", "sr_granel", 29.90, 28)

    compra("ovos", "na_madruga", 12.00, 3)
    compra("ovos", "sr_granel", 9.80, 25)

    compra("banana", "sr_granel", 6.90, 3)

    compra("detergente", "rococo", 3.20, 10)
    compra("detergente", "pad_jardim", 2.89, 45)

    compra("papel_higienico", "bh", 18.90, 12)
    # "abacate" fica sem compra — demonstra o estado "ainda sem histórico".

    # ---------- eventos de consumo (alimentam "costuma acabar a cada X dias") ----------
    def eventos(produto_key, ciclo_dias, quantidade=4):
        for i in range(quantidade):
            dias_atras = ciclo_dias * (quantidade - i)
            db.add(EventoConsumo(produto=produtos[produto_key], data=hoje - timedelta(days=dias_atras)))

    eventos("feijao", 18)
    eventos("cafe", 15)
    eventos("leite", 5)
    eventos("queijo", 10)
    eventos("ovos", 9)
    eventos("banana", 7)
    eventos("detergente", 20)

    # ---------- lista de compras ----------
    db.add(ItemListaCompra(produto=produtos["feijao"], status=StatusItemLista.PENDENTE, data_inclusao=datetime.now(timezone.utc) - timedelta(days=6)))
    db.add(ItemListaCompra(produto=produtos["ovos"], status=StatusItemLista.PENDENTE, data_inclusao=datetime.now(timezone.utc) - timedelta(days=4)))

    # ---------- lançamentos de fatura: mês atual (com parcelas) ----------
    db.add_all([
        LancamentoFatura(mes_referencia=mes_atual, data=hoje - timedelta(days=2), descricao_bruta="SUPERMERCADOS BHBELO HO", estabelecimento=estabs["bh"], categoria_gasto=cats_gasto["Supermercado"], valor=180.00, origem=OrigemCompra.NFCE),
        LancamentoFatura(mes_referencia=mes_atual, data=hoje - timedelta(days=1), descricao_bruta="RococoBeerLtdaBELO HORI", estabelecimento=estabs["rococo"], categoria_gasto=cats_gasto["Supermercado"], valor=95.30, origem=OrigemCompra.NFCE),
        LancamentoFatura(mes_referencia=mes_atual, data=hoje, descricao_bruta="POSTO SHELL BH", estabelecimento=estabs["posto"], categoria_gasto=cats_gasto["Combustível"], valor=250.00, origem=OrigemCompra.PDF),
        LancamentoFatura(mes_referencia=mes_atual, data=hoje - timedelta(days=2), descricao_bruta="RESTAURANTE DO ZE", estabelecimento=estabs["restaurante"], categoria_gasto=cats_gasto["Restaurante"], valor=68.90, origem=OrigemCompra.PDF),
        LancamentoFatura(
            mes_referencia=mes_atual, data=hoje - timedelta(days=1), descricao_bruta="JIM.COM", estabelecimento=estabs["jim"],
            categoria_gasto=cats_gasto["Outros"], valor=282.50, origem=OrigemCompra.PDF,
            parcela_atual=4, total_parcelas=4, grupo_parcelamento=str(uuid.uuid4()), mes_termino=mes_atual,
        ),
        LancamentoFatura(
            mes_referencia=mes_atual, data=hoje - timedelta(days=1), descricao_bruta="PANTANI MOTOCICLETAS", estabelecimento=estabs["pantani"],
            categoria_gasto=cats_gasto["Outros"], valor=150.00, origem=OrigemCompra.PDF,
            parcela_atual=2, total_parcelas=3, grupo_parcelamento=str(uuid.uuid4()), mes_termino=somar_meses(mes_atual, 1),
        ),
        LancamentoFatura(
            mes_referencia=mes_atual, data=hoje - timedelta(days=1), descricao_bruta="ZURICH SEGUROS", estabelecimento=estabs["zurich"],
            categoria_gasto=cats_gasto["Seguros"], valor=124.57, origem=OrigemCompra.PDF,
            parcela_atual=8, total_parcelas=12, grupo_parcelamento=str(uuid.uuid4()), mes_termino=somar_meses(mes_atual, 4),
        ),
        LancamentoFatura(
            mes_referencia=mes_atual, data=hoje - timedelta(days=1), descricao_bruta="MERCADOLIVRE*COMPRA", estabelecimento=estabs["mercado_livre"],
            categoria_gasto=cats_gasto["Outros"], valor=51.11, origem=OrigemCompra.PDF,
            parcela_atual=5, total_parcelas=9, grupo_parcelamento=str(uuid.uuid4()), mes_termino=somar_meses(mes_atual, 7),
        ),
    ])

    # ---------- meses anteriores (histórico) ----------
    def lancamentos_mes_simples(mes_referencia, dia, itens):
        for categoria_nome, valor in itens:
            db.add(LancamentoFatura(
                mes_referencia=mes_referencia, data=date(int(mes_referencia[:4]), int(mes_referencia[5:7]), dia),
                descricao_bruta=f"lançamento {categoria_nome.lower()}", categoria_gasto=cats_gasto[categoria_nome],
                valor=valor, origem=OrigemCompra.PDF,
            ))

    lancamentos_mes_simples(mes_jun, 15, [
        ("Supermercado", 1400), ("Supermercado", 1100), ("Supermercado", 700),
        ("Seguros", 712), ("Combustível", 480), ("Restaurante", 260),
        ("Outros", 700), ("Outros", 468),
    ])
    lancamentos_mes_simples(mes_mai, 15, [
        ("Supermercado", 1900), ("Supermercado", 1500),
        ("Seguros", 700), ("Combustível", 420), ("Restaurante", 310),
        ("Outros", 1510),
    ])
    lancamentos_mes_simples(mes_abr, 15, [
        ("Supermercado", 1800), ("Supermercado", 1200),
        ("Seguros", 700), ("Combustível", 400), ("Restaurante", 300),
        ("Outros", 700),
    ])

    db.add_all([
        ResumoMensal(mes_referencia=mes_jun, nota_resumo="Mês mais leve — poucas compras parceladas novas, maior peso foi Supermercado.", congelado=True),
        ResumoMensal(mes_referencia=mes_mai, nota_resumo="Puxado por manutenção da moto (Pantani Motocicletas, parcelado) e um seguro novo contratado.", congelado=True),
        ResumoMensal(mes_referencia=mes_abr, nota_resumo="Mês estável, sem parcelas novas relevantes.", congelado=True),
    ])

    db.commit()
    print(f"Seed concluído. Mês atual: {mes_atual}. Meses históricos: {mes_jun}, {mes_mai}, {mes_abr}.")


if __name__ == "__main__":
    main()
