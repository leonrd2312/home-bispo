"""
Home Bispo — Parser de fatura de cartão (fatura fechada, fotos/prints)
========================================================================

Recebe uma ou mais imagens (fotos ou capturas de tela) das páginas da fatura
já fechada e usa visão (Claude API, Structured Outputs) pra estruturar os
lançamentos — mesma abordagem do parser de NFC-e e do print semanal do
extrato (ver parser_nfce.py e parser_print.py). Reaproveita `dividir_em_fatias`
de parser_print.py caso alguma página venha como uma imagem muito alta.

Convenção de parcelas observada na fatura real: a coluna "DATA" de um
lançamento parcelado é a data da COMPRA ORIGINAL (ex: "12/12" impresso =
12 de dezembro de um ano anterior), não a data da fatura atual. O que muda
mês a mês é o indicador "parcela atual/total" (ex: "07/12" na fatura de
julho vira "08/12" na de agosto), impresso logo antes do valor.
"""

import base64
import io

import anthropic
from PIL import Image

from .parser_print import dividir_em_fatias

MODEL = "claude-sonnet-5"


def _media_type(imagem_bytes: bytes) -> str:
    """`dividir_em_fatias` reencoda fatias como PNG, mas devolve os bytes
    originais sem alterar quando a imagem não precisa ser fatiada — e uma
    foto de câmera normalmente é JPEG, não PNG. Detecta o formato de verdade
    em vez de supor, ou a Claude API recebe um media_type que não bate com o
    conteúdo."""
    formato = Image.open(io.BytesIO(imagem_bytes)).format or "PNG"
    return f"image/{formato.lower()}"


def build_schema(categorias_validas: list[str]) -> dict:
    """Monta o JSON Schema da extração, com o enum de categoria calculado a
    partir do que existe HOJE no banco do app (categorias tipo=gasto)."""
    return {
        "type": "object",
        "properties": {
            "cartao": {
                "type": "object",
                "properties": {
                    "titular": {"type": "string"},
                    "final": {"type": "string", "description": "Últimos 4 dígitos impressos do número do cartão"},
                },
                "required": ["titular", "final"],
            },
            "vencimento": {
                "type": ["string", "null"],
                "description": (
                    "Data em que ESTA fatura vence (quando o titular precisa pagá-la), formato ISO "
                    "YYYY-MM-DD. É o valor ao lado do rótulo 'Vencimento' (no bloco de metadados perto "
                    "do endereço) ou 'Com vencimento em:' (na caixa com o total da fatura) — os dois "
                    "sempre mostram a MESMA data. NUNCA use a data de 'Previsão de próx. Fechamento' "
                    "(ou similar) — essa é sobre a PRÓXIMA fatura, um mês depois do vencimento desta, e "
                    "usá-la aqui por engano desloca todos os lançamentos pro mês errado. Também não é a "
                    "data de 'Emissão' nem de 'Postagem'. Use null se a página de resumo/capa não estiver "
                    "entre as imagens fornecidas — NUNCA invente ou escreva um placeholder como "
                    "'<UNKNOWN>'."
                ),
            },
            "total_fatura": {
                "type": "number",
                "description": "'Total desta fatura' ou 'Total dos lançamentos atuais' — o total cobrado, sem contar pagamentos já efetuados"
            },
            "lancamentos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "dia": {
                            "type": "integer",
                            "description": (
                                "Dia da data impressa do lançamento (ex: em '12/12', dia=12). Para "
                                "compras parceladas, é o dia da COMPRA ORIGINAL, não desta fatura."
                            ),
                        },
                        "mes_nome": {
                            "type": "string",
                            "enum": [
                                "janeiro", "fevereiro", "março", "abril", "maio", "junho",
                                "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
                            ],
                            "description": (
                                "Mês da data impressa do lançamento (ex: em '12/12', mes_nome='dezembro'). "
                                "Para compras parceladas, é o mês da COMPRA ORIGINAL, não desta fatura. "
                                "NUNCA infira o ano — a fatura não imprime ano nessas datas, e o sistema "
                                "calcula o ano sozinho a partir da parcela ou do ciclo da fatura."
                            ),
                        },
                        "estabelecimento": {
                            "type": "string",
                            "description": "Nome do estabelecimento exatamente como impresso, sem o sufixo de parcela"
                        },
                        "valor": {"type": "number"},
                        "categoria": {
                            "type": "string",
                            "enum": categorias_validas,
                            "description": (
                                "Escolha a categoria mais próxima entre as disponíveis, com base na "
                                "categoria impressa na fatura (ex: 'supermercado', 'saúde', 'outros', "
                                "'serviços') e/ou no nome do estabelecimento. Nunca invente uma categoria "
                                "que não esteja na lista."
                            ),
                        },
                        "parcela_atual": {
                            "type": ["integer", "null"],
                            "description": "Em 'NN/MM' impresso antes do valor, NN. Null se a compra não é parcelada."
                        },
                        "total_parcelas": {
                            "type": ["integer", "null"],
                            "description": "Em 'NN/MM' impresso antes do valor, MM. Null se a compra não é parcelada."
                        },
                    },
                    "required": ["dia", "mes_nome", "estabelecimento", "valor", "categoria", "parcela_atual", "total_parcelas"],
                },
            },
        },
        "required": ["cartao", "vencimento", "total_fatura", "lancamentos"],
    }


EXTRACTION_PROMPT = """\
Você vai receber uma ou mais imagens (fotos ou capturas de tela) das páginas
de uma fatura de cartão de crédito Itaú já fechada, na ordem em que aparecem
na fatura. Se uma página tiver lançamentos em duas colunas, leia a coluna da
esquerda de cima a baixo e só depois a coluna da direita.

Extraia:
- Dados do cartão (titular, últimos 4 dígitos) e a data de vencimento —
  normalmente impressos na página de resumo/capa. ATENÇÃO: essa página
  costuma imprimir várias datas próximas (Postagem, Vencimento, Emissão,
  Previsão de próx. Fechamento) — use SOMENTE a rotulada "Vencimento" (ou
  "Com vencimento em:"). A "Previsão de próx. Fechamento" é sobre a fatura
  SEGUINTE, cerca de um mês depois, e usá-la por engano desloca todos os
  lançamentos pro mês errado.
- O total da fatura ("Total desta fatura" ou "Total dos lançamentos atuais").
- TODOS os lançamentos das seções "Lançamentos: compras e saques",
  "Lançamentos internacionais" (use o valor já convertido em R$, não o valor
  em dólar) e "Lançamentos: produtos e serviços", em qualquer página.

Cada lançamento normalmente aparece em duas linhas:
  1. DATA ESTABELECIMENTO [PARCELA_ATUAL/TOTAL_PARCELAS] VALOR
  2. categoria CIDADE  (a categoria é opcional, às vezes está ausente)

Regras importantes:
- NUNCA inclua a seção "Pagamentos efetuados" — não são compras, são
  pagamentos da fatura anterior.
- NUNCA inclua a seção "Compras parceladas - próximas faturas" — é apenas
  uma prévia informativa de parcelas futuras, os valores desses meses futuros
  não devem ser somados nesta fatura.
- Para compras parceladas, o padrão "NN/MM" impresso logo antes do valor é
  parcela_atual/total_parcelas (ex: "07/12" = parcela 7 de 12 daquele
  parcelamento). A "DATA" no início da linha nesse caso é a data da COMPRA
  ORIGINAL, normalmente vários meses ou anos atrás — extraia dia e mês
  exatamente como impressos, mas NUNCA infira o ano (a fatura não imprime
  ano nessas datas, e não há como adivinhar com confiança).
- Se o nome de um estabelecimento estiver quebrado em duas linhas sem uma
  categoria reconhecível na segunda linha, junte o nome e escolha a categoria
  mais parecida com base nesse nome.
- Não invente valores. Se algo não estiver legível, utilize null onde o
  schema permitir.
"""


def extract_fatura(imagens: list[bytes], categorias_validas: list[str]) -> dict:
    """Chama a API da Claude e retorna os dados da fatura já estruturados.

    `imagens` é uma foto/print por página da fatura, na ordem em que aparecem.
    Uma fatura real pode ter uma centena de lançamentos — usa max_tokens alto
    e streaming (evita timeout HTTP em respostas grandes)."""
    client = anthropic.Anthropic()  # lê ANTHROPIC_API_KEY do ambiente

    schema = build_schema(categorias_validas)

    blocos_imagem = [
        {"type": "image", "source": {"type": "base64", "media_type": _media_type(fatia), "data": base64.standard_b64encode(fatia).decode("utf-8")}}
        for imagem_bytes in imagens
        for fatia in dividir_em_fatias(imagem_bytes)
    ]

    with client.messages.stream(
        model=MODEL,
        max_tokens=16000,
        tools=[{
            "name": "registrar_fatura",
            "description": "Registra os dados extraídos da fatura de cartão.",
            "input_schema": schema,
        }],
        tool_choice={"type": "tool", "name": "registrar_fatura"},
        messages=[{
            "role": "user",
            "content": [*blocos_imagem, {"type": "text", "text": EXTRACTION_PROMPT}],
        }],
    ) as stream:
        response = stream.get_final_message()

    if response.stop_reason == "max_tokens":
        raise RuntimeError("A fatura tem lançamentos demais para uma única extração (limite de tokens excedido).")

    for block in response.content:
        if block.type == "tool_use":
            return block.input

    raise RuntimeError("A API não retornou os dados estruturados esperados.")
