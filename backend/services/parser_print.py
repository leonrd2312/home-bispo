"""
Home Bispo — Parser de print semanal do extrato (imagem)
==========================================================

O print é um screenshot do app do banco — a extração usa visão (mesma
abordagem do parser de NFC-e e do parser de fatura fechada, ver
parser_fatura.py).

Layout observado (app Itaú, tela de extrato/lançamentos não fechados):
  - Lançamentos agrupados sob cabeçalhos de data no formato "D de MÊS" (sem
    ano), do mais recente para o mais antigo.
  - Cada lançamento: nome do estabelecimento, "Cartão físico"/"Cartão
    virtual" (tipo de cartão, não é categoria — não há categoria impressa
    neste layout), valor em R$, e opcionalmente "Parcela X de Y".
  - Lançamentos parcelados mostram a data da COMPRA ORIGINAL no cabeçalho
    (sem ano) — mesma convenção validada no parser de fatura fechada.
  - Uma compra parcelada recém-feita (ainda na mesma abertura de ciclo em
    que foi feita) pode aparecer só com a tag "em Nx", sem "Parcela X de Y"
    — nesse caso o valor impresso é o TOTAL da compra, não o valor da
    parcela deste mês (confirmado com o usuário depois de um lançamento de
    R$560,06 "em 4x" ter sido gravado inteiro num único mês). `extract_print`
    detecta esse caso pelo campo `valor_e_total_da_compra` e divide o valor
    pelo número de parcelas antes de devolver.
"""

import base64
import io

import anthropic
from PIL import Image

from .claude_errors import mensagem_amigavel

MODEL = "claude-sonnet-5"

ALTURA_MAXIMA_FATIA = 1800
SOBREPOSICAO_FATIA = 150


def detectar_media_type(imagem_bytes: bytes) -> str:
    """`dividir_em_fatias` reencoda fatias como PNG, mas devolve os bytes
    originais sem alterar quando a imagem não precisa ser fatiada — e uma
    foto de câmera ou screenshot de Android normalmente é JPEG, não PNG.
    Detecta o formato de verdade em vez de supor, ou a Claude API recebe um
    media_type que não bate com o conteúdo (erro 400)."""
    formato = Image.open(io.BytesIO(imagem_bytes)).format or "PNG"
    return f"image/{formato.lower()}"


def dividir_em_fatias(image_bytes: bytes) -> list[bytes]:
    """Screenshots de extrato de rolagem completa podem ser extremamente
    altos — enviar a imagem inteira arriscaria redimensionamento pela API e
    perda de legibilidade nas linhas mais distantes. Divide em fatias
    verticais (mantendo a largura, e portanto a resolução nativa do texto)
    com uma pequena sobreposição pra não cortar um lançamento ao meio."""
    imagem = Image.open(io.BytesIO(image_bytes))
    largura, altura = imagem.size
    if altura <= ALTURA_MAXIMA_FATIA:
        return [image_bytes]

    fatias = []
    y = 0
    while y < altura:
        fim = min(y + ALTURA_MAXIMA_FATIA, altura)
        buffer = io.BytesIO()
        imagem.crop((0, y, largura, fim)).save(buffer, format="PNG")
        fatias.append(buffer.getvalue())
        if fim == altura:
            break
        y = fim - SOBREPOSICAO_FATIA
    return fatias


def build_schema(categorias_validas: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "lancamentos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "dia": {
                            "type": "integer",
                            "description": "Dia do cabeçalho de data que agrupa este lançamento (ex: em '3 de julho', dia=3)"
                        },
                        "mes_nome": {
                            "type": "string",
                            "enum": [
                                "janeiro", "fevereiro", "março", "abril", "maio", "junho",
                                "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
                            ],
                            "description": "Nome do mês do cabeçalho de data (ex: em '3 de julho', mes_nome='julho')"
                        },
                        "estabelecimento": {
                            "type": "string",
                            "description": "Nome do estabelecimento exatamente como impresso"
                        },
                        "valor": {
                            "type": "number",
                            "description": "Valor em R$. Se houver também um valor em outra moeda (ex: US$), use apenas o valor em R$."
                        },
                        "categoria": {
                            "type": "string",
                            "enum": categorias_validas,
                            "description": "Escolha a categoria mais próxima entre as disponíveis, com base no nome do estabelecimento (não há categoria impressa nesta tela)."
                        },
                        "parcela_atual": {
                            "type": ["integer", "null"],
                            "description": "Em 'Parcela X de Y', X. Em 'em Nx' (compra recém-feita, sem parcela impressa), sempre 1. Null se o lançamento não é parcelado."
                        },
                        "total_parcelas": {
                            "type": ["integer", "null"],
                            "description": "Em 'Parcela X de Y', Y. Em 'em Nx', N. Null se o lançamento não é parcelado."
                        },
                        "valor_e_total_da_compra": {
                            "type": "boolean",
                            "description": (
                                "true quando o lançamento mostra só 'em Nx' (sem 'Parcela X de Y' explícito) — "
                                "nesse caso 'valor' é o TOTAL da compra parcelada, ainda não dividido pelas "
                                "parcelas. false em qualquer outro caso (incluindo lançamentos não parcelados)."
                            ),
                        },
                    },
                    "required": ["dia", "mes_nome", "estabelecimento", "valor", "categoria", "parcela_atual", "total_parcelas", "valor_e_total_da_compra"],
                },
            },
        },
        "required": ["lancamentos"],
    }


EXTRACTION_PROMPT = """\
Você vai receber um ou mais recortes de um screenshot do extrato de cartão
de crédito (lançamentos ainda não fechados em fatura) do app Itaú. Se houver
mais de uma imagem, elas são fatias verticais consecutivas de UM ÚNICO
screenshot de rolagem, na ordem de cima para baixo, com uma pequena
sobreposição entre cada fatia e a seguinte — trate como uma lista contínua
e NÃO repita um lançamento que apareça em duas fatias por causa dessa
sobreposição.

A tela mostra lançamentos agrupados sob cabeçalhos de data no formato
"D de MÊS" (sem ano), do mais recente para o mais antigo. Cada lançamento
abaixo de um cabeçalho pertence à data daquele cabeçalho (o mais próximo
ACIMA dele na tela).

Para cada lançamento, extraia: o dia e mês do cabeçalho de data
correspondente, o nome do estabelecimento, o valor em R$, a categoria mais
próxima (baseada no nome do estabelecimento, já que esta tela não imprime
categoria), e se houver "Parcela X de Y", os dois números.

Regras importantes:
- Uma compra parcelada recém-feita pode aparecer só com a tag "em Nx" (ex:
  "em 4x"), SEM "Parcela X de Y" — isso significa que o valor impresso é o
  TOTAL da compra, ainda não dividido pelas parcelas, e que esta é a
  primeira parcela do ciclo atual. Nesse caso: parcela_atual=1,
  total_parcelas=N, e valor_e_total_da_compra=true (NÃO divida o valor você
  mesmo, o sistema faz essa conta). Quando o lançamento mostrar "Parcela X
  de Y" explícito, o valor já é o da parcela — valor_e_total_da_compra=false.
- "Cartão físico" / "Cartão virtual" é o tipo de cartão usado, NÃO é
  categoria — ignore para fins de categorização.
- Extraia TODOS os lançamentos, incluindo taxas pequenas (ex: "Itaú avisa",
  "IOF internacional").
- NUNCA inclua lançamentos cujo "estabelecimento" seja uma descrição de
  PAGAMENTO da fatura (ex: "Pagamento com saldo", "Pagamento via conta",
  "Pagamento do cartão") — isso é o titular pagando a fatura anterior, não
  uma compra. Esses lançamentos aparecem com valor negativo bem alto,
  próximo do total de uma fatura inteira.
- Estornos/reembolsos de compras (valor negativo, mas com nome de
  estabelecimento real — ex: "Mercadolivre*...") DEVEM ser incluídos
  normalmente, com o valor negativo exatamente como impresso — eles abatem
  o total da fatura atual. Escolha a categoria com base no nome do
  estabelecimento, igual a qualquer lançamento comum.
- Se um lançamento internacional mostrar valor em outra moeda (ex: US$),
  use apenas o valor em R$ já convertido.
- Compras parceladas têm a data do cabeçalho referente à COMPRA ORIGINAL,
  que pode ser vários meses ou anos atrás — extraia o dia/mês exatamente
  como impresso, não tente calcular ou corrigir.
- Não invente valores. Se algo não estiver legível, utilize null onde o
  schema permitir.
"""


def extract_print(image_bytes: bytes, categorias_validas: list[str]) -> dict:
    """Chama a API da Claude e retorna os lançamentos do print já estruturados."""
    client = anthropic.Anthropic()  # lê ANTHROPIC_API_KEY do ambiente

    schema = build_schema(categorias_validas)
    fatias = dividir_em_fatias(image_bytes)

    blocos_imagem = [
        {"type": "image", "source": {"type": "base64", "media_type": detectar_media_type(fatia), "data": base64.standard_b64encode(fatia).decode("utf-8")}}
        for fatia in fatias
    ]

    try:
        with client.messages.stream(
            model=MODEL,
            max_tokens=16000,
            tools=[{
                "name": "registrar_extrato",
                "description": "Registra os lançamentos extraídos do print do extrato.",
                "input_schema": schema,
            }],
            tool_choice={"type": "tool", "name": "registrar_extrato"},
            messages=[{
                "role": "user",
                "content": [*blocos_imagem, {"type": "text", "text": EXTRACTION_PROMPT}],
            }],
        ) as stream:
            response = stream.get_final_message()
    except anthropic.APIStatusError as exc:
        raise RuntimeError(mensagem_amigavel(exc)) from exc
    except anthropic.APIConnectionError as exc:
        raise RuntimeError("Não foi possível conectar à Claude API — verifique a internet do servidor.") from exc

    if response.stop_reason == "max_tokens":
        raise RuntimeError("O print tem lançamentos demais para uma única extração (limite de tokens excedido).")

    for block in response.content:
        if block.type == "tool_use":
            return _dividir_valores_de_compra_recente(block.input)

    raise RuntimeError("A API não retornou os dados estruturados esperados.")


def _dividir_valores_de_compra_recente(dados: dict) -> dict:
    """Uma compra parcelada recém-feita aparece no extrato aberto só com a
    tag 'em Nx' (sem 'Parcela X de Y'), com o valor TOTAL impresso — pedir
    pro modelo já dividir esse valor é o tipo de conta que já se provou
    pouco confiável (ver data_compra_parcelada em status.py), então a
    divisão acontece aqui, determinística."""
    for item in dados.get("lancamentos", []):
        if item.pop("valor_e_total_da_compra", False) and item.get("total_parcelas"):
            item["valor"] = round(item["valor"] / item["total_parcelas"], 2)
    return dados
