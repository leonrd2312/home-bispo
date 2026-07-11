import io

import anthropic
import httpx
from PIL import Image

from backend.services import parser_fatura


def _imagem_png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (100, 100), color="white").save(buffer, format="PNG")
    return buffer.getvalue()


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


def test_extract_fatura_traduz_erro_de_creditos_insuficientes(monkeypatch):
    monkeypatch.setattr(parser_fatura.anthropic, "Anthropic", lambda: FakeAnthropicClient())

    try:
        parser_fatura.extract_fatura([_imagem_png()], ["Supermercado"])
        assert False, "deveria ter levantado RuntimeError"
    except RuntimeError as exc:
        assert "sem créditos" in str(exc).lower()
