"""Traduz erros da Claude API em mensagens amigáveis pro usuário final.

Usado pelos três parsers que dependem da API (NFC-e, fatura fechada, print
semanal) — evita que um erro de billing/rate limit vire um 500 cru pro
usuário, quando na verdade é algo que ele mesmo pode resolver (ex: sem
crédito na conta)."""

import anthropic


def mensagem_amigavel(erro: anthropic.APIStatusError) -> str:
    mensagem = ""
    if isinstance(erro.body, dict):
        mensagem = ((erro.body or {}).get("error") or {}).get("message") or ""

    if erro.status_code == 400 and "credit" in mensagem.lower():
        return (
            "A conta da Claude API está sem créditos — verifique o saldo em "
            "console.anthropic.com/settings/billing antes de tentar de novo."
        )
    if erro.status_code == 429:
        return "Limite de uso da Claude API atingido no momento — aguarde um pouco e tente de novo."
    return f"Não foi possível se comunicar com a Claude API (erro {erro.status_code}): {mensagem or 'motivo desconhecido'}."
