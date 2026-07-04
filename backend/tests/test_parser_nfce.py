from types import SimpleNamespace

from backend.services import parser_nfce


class FakeMessages:
    def __init__(self, resposta_tool_input: dict):
        self._resposta_tool_input = resposta_tool_input
        self.ultima_chamada = None

    def create(self, **kwargs):
        self.ultima_chamada = kwargs
        bloco = SimpleNamespace(type="tool_use", input=self._resposta_tool_input)
        return SimpleNamespace(content=[bloco])


class FakeAnthropicClient:
    def __init__(self, resposta_tool_input: dict):
        self.messages = FakeMessages(resposta_tool_input)


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
    fake_client.messages.create = lambda **kwargs: SimpleNamespace(content=[SimpleNamespace(type="text", text="oops")])
    monkeypatch.setattr(parser_nfce.anthropic, "Anthropic", lambda: fake_client)

    try:
        parser_nfce.extract_nfce(b"fake", "image/jpeg", ["Grãos"])
        assert False, "deveria ter levantado RuntimeError"
    except RuntimeError:
        pass
