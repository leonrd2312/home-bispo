import io

import anthropic
import httpx
from PIL import Image

from backend.services import parser_print
from backend.services.parser_print import ALTURA_MAXIMA_FATIA, SOBREPOSICAO_FATIA, dividir_em_fatias


def _imagem_png(largura: int, altura: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (largura, altura), color="white").save(buffer, format="PNG")
    return buffer.getvalue()


def _imagem_jpeg(largura: int, altura: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (largura, altura), color="white").save(buffer, format="JPEG")
    return buffer.getvalue()


def test_detectar_media_type_reconhece_png_e_jpeg():
    assert parser_print.detectar_media_type(_imagem_png(10, 10)) == "image/png"
    assert parser_print.detectar_media_type(_imagem_jpeg(10, 10)) == "image/jpeg"


def test_imagem_pequena_nao_e_dividida():
    imagem = _imagem_png(1080, 1200)
    fatias = dividir_em_fatias(imagem)
    assert len(fatias) == 1
    assert fatias[0] == imagem


def test_imagem_alta_e_dividida_em_fatias_com_sobreposicao():
    altura_total = ALTURA_MAXIMA_FATIA * 3
    imagem = _imagem_png(1080, altura_total)
    fatias = dividir_em_fatias(imagem)

    assert len(fatias) > 1
    for fatia_bytes in fatias:
        fatia = Image.open(io.BytesIO(fatia_bytes))
        assert fatia.width == 1080
        assert fatia.height <= ALTURA_MAXIMA_FATIA

    # a soma das alturas cobre a imagem inteira, contando a sobreposição
    alturas = [Image.open(io.BytesIO(f)).height for f in fatias]
    cobertura = alturas[0] + sum(h - SOBREPOSICAO_FATIA for h in alturas[1:])
    assert cobertura == altura_total


def _erro_creditos_insuficientes() -> anthropic.APIStatusError:
    corpo = {
        "type": "error",
        "error": {
            "type": "invalid_request_error",
            "message": "Your credit balance is too low to access the Claude API. Please go to Plans & Billing to upgrade or purchase credits.",
        },
    }
    resposta = httpx.Response(400, json=corpo, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
    return anthropic.APIStatusError("bad request", response=resposta, body=corpo)


class FakeMessages:
    def stream(self, **kwargs):
        raise _erro_creditos_insuficientes()


class FakeAnthropicClient:
    def __init__(self):
        self.messages = FakeMessages()


def test_extract_print_traduz_erro_de_creditos_insuficientes(monkeypatch):
    monkeypatch.setattr(parser_print.anthropic, "Anthropic", lambda: FakeAnthropicClient())

    try:
        parser_print.extract_print(_imagem_png(1080, 1200), ["Restaurante"])
        assert False, "deveria ter levantado RuntimeError"
    except RuntimeError as exc:
        assert "sem créditos" in str(exc).lower()


class FakeMessagesCaptura:
    def __init__(self):
        self.kwargs_recebidos = None

    def stream(self, **kwargs):
        self.kwargs_recebidos = kwargs
        raise _erro_creditos_insuficientes()


class FakeAnthropicClientCaptura:
    def __init__(self):
        self.messages = FakeMessagesCaptura()


def test_extract_print_envia_media_type_real_para_jpeg_sem_fatiar(monkeypatch):
    """Bug real: uma foto/screenshot Android normalmente é JPEG. Quando a
    imagem não precisa ser fatiada, dividir_em_fatias devolve os bytes
    originais sem reencodar — mas o media_type mandado pra Claude API estava
    hardcoded como "image/png", e a API rejeitava com erro 400 porque o
    conteúdo real não batia com o media_type declarado."""
    fake_client = FakeAnthropicClientCaptura()
    monkeypatch.setattr(parser_print.anthropic, "Anthropic", lambda: fake_client)

    try:
        parser_print.extract_print(_imagem_jpeg(1080, 1200), ["Restaurante"])
    except RuntimeError:
        pass  # esperado: o fake sempre levanta erro de créditos após capturar os kwargs

    bloco_imagem = fake_client.messages.kwargs_recebidos["messages"][0]["content"][0]
    assert bloco_imagem["source"]["media_type"] == "image/jpeg"


def test_dividir_valores_de_compra_recente_divide_formato_em_nx():
    """Formato novo: compra recém-feita mostra só 'em Nx', com o valor TOTAL
    impresso (ex: R$560,06 em 4x) — precisa virar o valor da parcela."""
    dados = {
        "lancamentos": [
            {"estabelecimento": "jorlan barao", "valor": 560.06, "parcela_atual": 1,
             "total_parcelas": 4, "valor_e_total_da_compra": True},
        ]
    }
    resultado = parser_print._dividir_valores_de_compra_recente(dados)
    assert resultado["lancamentos"][0]["valor"] == 140.01
    assert "valor_e_total_da_compra" not in resultado["lancamentos"][0]


def test_dividir_valores_de_compra_recente_preserva_formato_antigo():
    """Formato antigo (ainda em uso): 'Parcela X de Y' já mostra o valor da
    parcela — não deve ser dividido de novo."""
    dados = {
        "lancamentos": [
            {"estabelecimento": "loja x", "valor": 140.02, "parcela_atual": 3,
             "total_parcelas": 4, "valor_e_total_da_compra": False},
            {"estabelecimento": "loja y", "valor": 50.0, "parcela_atual": None,
             "total_parcelas": None, "valor_e_total_da_compra": False},
        ]
    }
    resultado = parser_print._dividir_valores_de_compra_recente(dados)
    assert resultado["lancamentos"][0]["valor"] == 140.02
    assert resultado["lancamentos"][1]["valor"] == 50.0
