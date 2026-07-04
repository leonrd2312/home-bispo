# CLAUDE.md — Instruções do Projeto Home Bispo

> Este arquivo é lido automaticamente pelo Claude Code e pela extensão Claude no VS Code.
> Ele substitui a "memória" de conversas anteriores — tudo que o Claude precisa saber sobre
> o projeto está aqui, versionado junto com o código.

## O que é o Home Bispo

App doméstico, self-hosted, da família Bispo (Leo + Jessica) para:
1. **Status do mês** — acompanhar gastos mensais do cartão de crédito (todas as categorias), com projeção, comparação com média histórica, e detalhamento de compras parceladas.
2. **Catálogo de produtos** — consultar preços no supermercado confrontando o preço da gôndola com o histórico de preços já pagos em diferentes estabelecimentos.
3. **Lista de compras** — itens sinalizados como "acabou" ou adicionados manualmente, com referência de último/melhor preço.

Sem login, sem multiusuário formal. Acesso restrito na rede doméstica.

## Stack

- **Backend:** Python 3.12+ / FastAPI
- **Banco de dados:** SQLite (arquivo único, zero config)
- **Frontend:** HTML/CSS/JS puro (sem framework, sem build step)
- **Deploy principal:** Docker Compose no desktop
- **Deploy alternativo:** Termux + Python direto na Mi Box (Android TV)
- **Parser de NFC-e:** Claude API (Structured Outputs) — foto do cupom → JSON estruturado
- **Parser de fatura PDF:** PyMuPDF (já validado em conversas anteriores)

## Estrutura de diretórios (planejada)

```
home-bispo/
├── CLAUDE.md              ← este arquivo (instruções pro Claude)
├── DOCUMENTACAO.md         ← escopo, modelo de dados, decisões de design
├── NOTAS_DE_VERSAO.md      ← changelog
├── REQUISITOS.md           ← checklist rastreável de requisitos
├── docker-compose.yml
├── Dockerfile
├── backend/
│   ├── main.py             ← FastAPI app entry point
│   ├── models.py           ← SQLAlchemy/SQLite models
│   ├── database.py         ← conexão e sessão do banco
│   ├── routers/
│   │   ├── status.py       ← endpoints do Status do mês
│   │   ├── catalogo.py     ← endpoints do Catálogo
│   │   ├── lista.py        ← endpoints da Lista de compras
│   │   ├── config.py       ← endpoints de Configurações (categorias, produtos, estabelecimentos)
│   │   └── historico.py    ← endpoints do Histórico de meses
│   ├── services/
│   │   ├── parser_nfce.py  ← extração de NFC-e via Claude API
│   │   ├── parser_fatura.py← extração de fatura PDF
│   │   └── identidade.py   ← resolução de identidade de produto
│   └── tests/
│       ├── test_parser_nfce.py
│       ├── test_identidade.py
│       └── fixtures/       ← JSONs de exemplo (nota real já extraída)
├── frontend/
│   ├── index.html          ← SPA simples, mesma estrutura do mockup
│   ├── styles.css
│   └── app.js
└── data/
    └── homebispo.db        ← arquivo SQLite (gitignored, backup manual)
```

## Modelo de dados (resumo executivo)

**Categorias** — tabela única, campo `tipo` = `produto` | `gasto`. Gerenciável pelo frontend.

**Produtos** — chave interna (`id`), `codigo_barras` (opcional, EAN/GTIN), `nome_amigavel` (editável), `qtd_normalizada` + `unidade_normalizada`, `categoria_id`. Sempre originados de NFC-e.

**Estabelecimentos** — `nome_bruto` (chave imutável, como vem na fatura/nota), `nome_amigavel` (editável), `categoria_gasto_id`, endereço.

**Compras** — `produto_id`, `descricao_bruta`, `estabelecimento_id`, preço, data, origem (NFC-e/print/PDF).

**Eventos de consumo** — `produto_id`, data (quando o usuário sinalizou "acabou"). Usado para calcular "costuma acabar a cada X dias".

**Resolução de identidade de produto:**
1. Código de barras EAN/GTIN presente → chave universal, match exato.
2. Sem código de barras → normaliza nome + quantidade. Quantidade diferente (5kg ≠ 2kg) = produto diferente, SEMPRE. Nome parecido + quantidade igual → pede confirmação, nunca decide sozinho.

## Regras de negócio críticas (não quebrar)

- NFC-e prevalece sobre fatura quando a mesma compra aparece nas duas fontes.
- Divergência entre print semanal e PDF fechado nunca é aplicada automaticamente — pede confirmação.
- Ação "acabou" e "+ lista" são independentes (acabou ≠ adicionar à lista).
- Ação "acabou" só disponível para produtos com pelo menos uma compra confirmada via NFC-e.
- Categorias no schema de extração da NFC-e são montadas dinamicamente a partir do banco, nunca hardcoded.
- Compras parceladas ordenadas por proximidade de término (menos parcelas restantes primeiro).
- Histórico de meses reutiliza a mesma view do Status, com indicação visual de "mês histórico".

## Convenções de código

- Python: PEP 8, type hints, docstrings em português
- Frontend: CSS variables pra cores (já definidas no mockup), sem frameworks CSS
- Commits: mensagens em português, no imperativo ("Adiciona parser de NFC-e", "Corrige dedup de compras")
- Testes: pytest, rodar `pytest backend/tests/` antes de cada deploy

## Configuração

- `ANTHROPIC_API_KEY` — variável de ambiente, nunca no código
- Dia de fechamento da fatura: padrão 2 (configurável)
- Dia de vencimento: padrão 9 (configurável)

## Contexto do desenvolvedor

Leo trabalha com TI na LM2Rodas (Hybris + Protheus), tem experiência com Docker, Python, e já hospeda o Plan2Ops num servidor interno (192.168.10.7). Usa Windows no desktop de desenvolvimento. Jessica é a co-usuária do app mas não desenvolve.
