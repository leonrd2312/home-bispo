from types import SimpleNamespace

from backend.services import parser_nfce


class FakeStream:
    def __init__(self, response):
        self._response = response

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get_final_message(self):
        return self._response


class FakeMessages:
    def __init__(self, resposta_tool_input: dict, stop_reason: str = "tool_use"):
        self._resposta_tool_input = resposta_tool_input
        self._stop_reason = stop_reason
        self.ultima_chamada = None

    def stream(self, **kwargs):
        self.ultima_chamada = kwargs
        bloco = SimpleNamespace(type="tool_use", input=self._resposta_tool_input)
        response = SimpleNamespace(content=[bloco], stop_reason=self._stop_reason)
        return FakeStream(response)


class FakeAnthropicClient:
    def __init__(self, resposta_tool_input: dict, stop_reason: str = "tool_use"):
        self.messages = FakeMessages(resposta_tool_input, stop_reason)


def test_build_schema_usa_categorias_do_banco_como_enum():
    categorias = ["Grãos", "Laticínios"]
    schema = parser_nfce.build_schema(categorias)

    assert schema["properties"]["itens"]["items"]["properties"]["categoria"]["enum"] == categorias


def test_extract_nfce_retorna_input_estruturado_do_tool_use(monkeypatch, exemplo_nfce):
    resposta_esperada = {
        "documento": {"chave_acesso": exemplo_nfce["documento"]["chave_acesso"], "data_emissao": "2026-06-26T10:39:12"},
        "estabelecimento": {"razao_social": exemplo_nfce["estabelecimento"]["razao_social"], "cnpj": exemplo_nfce["estabelecimento"]["cnpj"]},
        "itens": [],
        "valor_total_nota": exemplo_nfce["totais"]["valor_total"],
    }
    fake_client = FakeAnthropicClient(resposta_esperada)
    monkeypatch.setattr(parser_nfce.anthropic, "Anthropic", lambda: fake_client)

    resultado = parser_nfce.extract_nfce(b"fake-image-bytes", "image/jpeg", ["Grãos"])

    assert resultado == resposta_esperada
    assert fake_client.messages.ultima_chamada["tool_choice"] == {"type": "tool", "name": "registrar_nfce"}


def test_extract_nfce_levanta_erro_sem_tool_use(monkeypatch):
    fake_client = FakeAnthropicClient({})
    fake_client.messages.stream = lambda **kwargs: FakeStream(
        SimpleNamespace(content=[SimpleNamespace(type="text", text="oops")], stop_reason="end_turn")
    )
    monkeypatch.setattr(parser_nfce.anthropic, "Anthropic", lambda: fake_client)

    try:
        parser_nfce.extract_nfce(b"fake", "image/jpeg", ["Grãos"])
        assert False, "deveria ter levantado RuntimeError"
    except RuntimeError:
        pass


def test_extract_nfce_levanta_erro_no_limite_de_tokens(monkeypatch):
    fake_client = FakeAnthropicClient({"itens": []}, stop_reason="max_tokens")
    monkeypatch.setattr(parser_nfce.anthropic, "Anthropic", lambda: fake_client)

    try:
        parser_nfce.extract_nfce(b"fake", "image/jpeg", ["Grãos"])
        assert False, "deveria ter levantado RuntimeError"
    except RuntimeError:
        pass
