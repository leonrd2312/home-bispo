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
