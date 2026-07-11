"""
Home Bispo — Parser de NFC-e via foto do cupom
================================================

O que este script faz:
  1. Recebe a foto de uma NFC-e (bytes de imagem) + a lista de categorias
     atualmente cadastradas no app (vem do banco, editável pelo usuário).
  2. Monta um JSON Schema DINAMICAMENTE, incluindo essas categorias como
     enum válido — a extração nunca inventa categoria nova, sempre escolhe
     entre as que já existem.
  3. Chama a API da Claude usando Structured Outputs (via tool_choice
     forçado) — a resposta é GARANTIDA no formato do schema, sem parsing
     frágil de texto livre.
  4. Retorna um dict Python já pronto pra gravar no banco.

Pré-requisito:
  pip install anthropic
  export ANTHROPIC_API_KEY="sk-ant-..."   (gerada em platform.claude.com)

Custo aproximado por nota: menos de US$0,01 (Claude Sonnet 5, preço
promocional vigente até 31/08/2026: US$2 / US$10 por milhão de tokens
de entrada/saída).
"""

import base64
import json
import anthropic

MODEL = "claude-sonnet-5"


def build_schema(categorias_validas: list[str]) -> dict:
    """Monta o JSON Schema da extração, com o enum de categoria
    calculado a partir do que existe HOJE no banco do app."""
    return {
        "type": "object",
        "properties": {
            "documento": {
                "type": "object",
                "properties": {
                    "chave_acesso": {
                        "type": "string",
                        "description": "44 dígitos, sem espaços. Geralmente impressa como texto perto de 'Consulte a Chave de Acesso'."
                    },
                    "numero_nota": {"type": ["integer", "null"]},
                    "serie": {"type": ["integer", "null"]},
                    "data_emissao": {
                        "type": "string",
                        "description": "Formato ISO 8601, ex: 2026-06-26T10:39:12"
                    },
                },
                "required": ["chave_acesso", "data_emissao"],
            },
            "estabelecimento": {
                "type": "object",
                "properties": {
                    "razao_social": {"type": "string"},
                    "cnpj": {"type": "string"},
                    "endereco": {"type": ["string", "null"]},
                },
                "required": ["razao_social", "cnpj"],
            },
            "itens": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "codigo": {"type": ["string", "null"], "description": "Código de barras/produto, se impresso"},
                        "descricao": {"type": "string", "description": "Descrição exatamente como impressa no cupom"},
                        "categoria": {
                            "type": "string",
                            "enum": categorias_validas,
                            "description": "Escolha a categoria mais próxima entre as disponíveis. Nunca crie uma categoria nova."
                        },
                        "quantidade": {"type": "number"},
                        "unidade": {"type": "string", "description": "Ex: PT, UN, kg, BJ"},
                        "preco_unitario": {"type": "number"},
                        "valor_total": {"type": "number"},
                    },
                    "required": ["descricao", "categoria", "quantidade", "unidade", "preco_unitario", "valor_total"],
                },
            },
            "valor_total_nota": {"type": "number"},
        },
        "required": ["documento", "estabelecimento", "itens", "valor_total_nota"],
    }


EXTRACTION_PROMPT = """\
Você vai receber a foto de um cupom fiscal (NFC-e/DANFE) de supermercado.

Extraia:
- Os dados do documento (chave de acesso, número, série, data/hora de emissão)
- Os dados do estabelecimento (razão social, CNPJ, endereço se houver)
- TODOS os itens da lista de compras e saques, um por um, exatamente como impressos
- O valor total da nota

Regras importantes:
- Itens vendidos por peso (kg) têm quantidade fracionária (ex: 0,540) — mantenha a
  quantidade exata, não arredonde.
- Para "categoria", escolha sempre a opção mais adequada dentre as fornecidas no
  schema. Nunca invente uma categoria que não esteja na lista.
- A chave de acesso tem 44 dígitos. Se estiver impressa em grupos separados por
  espaço, junte tudo sem espaços.
- Se algum campo não estiver legível ou não existir no cupom, não invente valor —
  utilize null onde o schema permitir, ou a melhor estimativa possível para os
  campos obrigatórios.
"""


def extract_nfce(image_bytes: bytes, media_type: str, categorias_validas: list[str]) -> dict:
    """Chama a API da Claude e retorna os dados da nota já estruturados.

    Uma nota real pode ter dezenas de itens — usa max_tokens alto e streaming
    (evita timeout HTTP em respostas grandes), mesma abordagem do parser de
    fatura e do parser de print."""
    client = anthropic.Anthropic()  # lê ANTHROPIC_API_KEY do ambiente

    schema = build_schema(categorias_validas)
    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    with client.messages.stream(
        model=MODEL,
        max_tokens=16000,
        tools=[{
            "name": "registrar_nfce",
            "description": "Registra os dados extraídos da nota fiscal.",
            "input_schema": schema,
        }],
        tool_choice={"type": "tool", "name": "registrar_nfce"},
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_b64}},
                {"type": "text", "text": EXTRACTION_PROMPT},
            ],
        }],
    ) as stream:
        response = stream.get_final_message()

    if response.stop_reason == "max_tokens":
        raise RuntimeError("A nota tem itens demais para uma única extração (limite de tokens excedido).")

    for block in response.content:
        if block.type == "tool_use":
            return block.input

    raise RuntimeError("A API não retornou os dados estruturados esperados.")


if __name__ == "__main__":
    # Exemplo de uso — categorias viriam do banco do Home Bispo em produção
    categorias_do_app = [
        "Grãos", "Hortifruti", "Açougue e Frios", "Padaria", "Laticínios",
        "Mercearia", "Snacks e Guloseimas", "Bebidas", "Congelados",
        "Limpeza", "Higiene e Perfumaria", "Bazar e Utilidades",
    ]

    with open("nota_exemplo.jpg", "rb") as f:
        dados = extract_nfce(f.read(), "image/jpeg", categorias_do_app)

    print(json.dumps(dados, indent=2, ensure_ascii=False))
