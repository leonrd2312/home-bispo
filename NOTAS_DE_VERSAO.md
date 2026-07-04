# Notas de versão — Home Bispo

Formato inspirado em [Keep a Changelog](https://keepachangelog.com/pt-BR/). Esse arquivo é pensado pra ser exibido dentro do app, no menu de Configurações (ícone de engrenagem).

---

## [Não lançado]

### Validado
- **Parser de NFC-e via foto (Rota A) testado ponta a ponta com nota real.** Extração via Claude API + Structured Outputs bateu 100% no valor total (12 itens, R$89,35), chave de acesso e CNPJ corretos. Confirma a abordagem "foto do cupom" como viável e mais simples que scraping do portal Sefaz.
- Categoria dinâmica (schema montado a partir do banco) funcionou como esperado — nenhuma categoria fora da lista foi inventada.

### Observado
- Taxonomia de categorias ainda precisa de ajuste: itens de padaria (biscoito, fermento) não têm categoria ideal na lista atual, foram alocados na mais próxima disponível.

---

## [v1.0.0-mockup] — 2026-07-02

### Adicionado
- Tela **Status do mês**: gasto até hoje, projeção de fim do mês, comparação com média histórica, categorias, insights.
- Seção de **compras parceladas** no Status do mês, com comparativo visual entre parcelas fixas e demais gastos.
- Tela **Catálogo de produtos**: busca, filtro de categoria (combobox em folha inferior), ações independentes "acabou" e "+ lista".
- Tela **Lista de compras**.
- Menu de **Configurações** (engrenagem) com notas de versão e informações do app.

### Decisões de escopo
- Removida seleção de perfil de usuário (Leo/Jessica) — uso sem identificação individual.
- Removida sugestão automática de lista por recorrência — inclusão na lista é sempre manual.
- Ação "acabou" restrita a produtos com pelo menos uma compra confirmada via NFC-e.

### Observações
- Versão de mockup navegável, com dados fictícios (mock data), sem integração real com NFC-e, banco ou backend. Uso: validação de conceito com a Jessica antes do início da implementação.
