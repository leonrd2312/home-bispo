# Home Bispo — Documentação do Sistema

**Versão do documento:** v1.0
**Status:** escopo validado com mockup navegável (mock data) · pré-arquitetura técnica

---

## 1. Visão geral

Home Bispo é um app doméstico, self-hosted, pra ajudar a família Bispo (Leo + Jessica) a:

1. **Entender onde o dinheiro do mês está indo** ("Status do mês") — de forma automática, puxando dado real da fatura de cartão.
2. **Decidir com mais informação na hora de comprar** ("Catálogo de produtos") — comparando o preço que está sendo visto na gôndola com o histórico de preços já pagos, em diferentes estabelecimentos.

Sem login, sem multiusuário formal — uso doméstico, acesso restrito aos dois.

---

## 2. Escopo da v1

### 2.1 Status do mês (hub)
- Número total gasto no mês até a data atual
- Projeção de fechamento do mês, baseada no ritmo de gasto até agora (dias decorridos vs. total do período)
- Comparação com a média dos meses anteriores (fica disponível assim que houver histórico suficiente)
- Retrato categorizado do gasto (barras por categoria, do maior pro menor)
- **Seção de compras parceladas**: cada parcela em aberto mostrando estabelecimento, valor da parcela, "parcela X de Y" e mês de término
- Componente visual comparando **parcelas (fixo) vs. demais gastos** do mês, como fração do total
- Cards de insight (ex: economia possível se sempre comprasse no local mais barato já visto; recorrências pequenas e frequentes que passam despercebidas)
- Acesso a **Configurações** via ícone de engrenagem → menu com Categorias de produto, Categorias de gasto, Produtos, Estabelecimentos, Notas de versão e Sobre (cada um como uma subseção própria, com "voltar" pro menu)

### 2.2 Catálogo de produtos
- Cadastro de produtos categorizados (grãos, laticínios, hortifruti, limpeza, higiene, etc.)
- Campo de busca (uso pensado pra consulta rápida andando no supermercado)
- Seletor de categoria em formato combobox (abre uma folha com todas as categorias, ao invés de rolagem lateral)
- Cada produto no catálogo mostra:
  - "Costuma acabar a cada X dias" (estatística calculada a partir do histórico de consumo sinalizado — **não é gatilho automático de sugestão**, é só informação)
  - Último preço pago + estabelecimento
  - Melhor preço já visto + estabelecimento (quando diferente do último)
  - Dois botões **independentes**:
    - **"🔔 Acabou"** — registra apenas o evento de consumo, alimenta o cálculo de duração média. Não adiciona à lista.
    - **"+ Lista"** — adiciona/remove o item da lista de compras.
- **Regra importante:** as ações "acabou" e "+ lista" só ficam disponíveis para produtos que já têm pelo menos uma compra confirmada via leitura de NFC-e. Produtos ainda sem histórico de compra aparecem no catálogo, mas sem essas ações (mensagem: "ainda sem compra registrada via nota fiscal").

### 2.3 Lista de compras
- Lista simples dos itens adicionados via "+ Lista" no catálogo
- Checkbox pra marcar como comprado
- Mostra último preço/melhor preço de referência pra cada item, pra consulta rápida no mercado

### 2.4 Funcionalidades (menu separado de Configurações)
- Ícone próprio na tela de Status, ao lado da engrenagem — reúne recursos de consulta/memória, distintos de cadastro/ajuste
- **Histórico de meses**: cartão por mês anterior, com total gasto, variação vs. mês anterior e uma nota-resumo do que marcou aquele mês
- Pensado como menu extensível — outros recursos de consulta entram aqui no futuro

> **Decisão em aberto:** o Histórico é um "snapshot" de verdade (dado congelado como estava no fechamento daquele mês) ou uma visão recalculada dinamicamente com os dados/categorias atuais? Isso importa porque, se você renomear um estabelecimento ou reclassificar uma categoria hoje, um histórico dinâmico mudaria retroativamente como março apareceria — um snapshot de verdade preservaria a leitura de março exatamente como era em março. Ver seção 7.

---

## 3. Fontes de dados

| Fonte | Uso | Confiabilidade | Observação |
|---|---|---|---|
| **NFC-e (QR code escaneado no ato da compra)** | Alimenta o catálogo de produtos (item, preço, estabelecimento) | Alta | Fonte que "libera" as ações de um produto no catálogo |
| **Print semanal do app do banco (leitura de imagem)** | Alimenta o Status do mês durante o período aberto | Média (provisória) | Layout varia por tela do app; precisa de inferência de ano/mês via config de fechamento |
| **PDF da fatura fechada** | Reconcilia e fecha o mês oficialmente | Alta (definitiva) | Ao chegar, **pede confirmação do usuário antes de aplicar qualquer divergência** com o que os prints já haviam registrado |

**Regra de deduplicação (compra de supermercado):** quando a mesma compra aparece tanto na fatura quanto via NFC-e, a NFC-e prevalece (mais granular, por item).

---

## 4. Modelo de dados (alto nível)

**Categorias** *(tabela única, compartilhada entre catálogo de produtos e classificação de gastos)*
- `id`, `nome`, `tipo` (`produto` | `gasto`)
- Gerenciável direto no app, em Configurações → Categorias de produto / Categorias de gasto
- Evita ter listas fixas em arquivo de configuração — categoria é dado, não código

**Produtos (catálogo)**
- `id` (chave interna da aplicação — gerada uma vez, nunca muda)
- `codigo_barras` (opcional — quando presente na NFC-e em formato EAN/GTIN, é o identificador mais confiável que existe)
- `nome_amigavel` (editável — o que aparece na interface)
- `quantidade_normalizada` + `unidade_normalizada` (ex: `5000` + `g` — parte da identidade do produto quando não há código de barras)
- `categoria_id` (referência à tabela Categorias, tipo=`produto`)
- Gestão acessível em Configurações → Produtos (renomear o nome amigável sem afetar a identidade/histórico)

**Resolução de identidade na leitura de uma NFC-e** *(evita duplicar produto ou misturar produtos diferentes)*
1. Item tem código de barras válido (EAN/GTIN)? → busca produto existente por esse código. Achou → é o mesmo produto, ponto (a descrição pode até vir diferente entre notas — não importa). Não achou → cria produto novo.
2. Item **sem** código de barras (comum em hortifruti/itens por peso — usam código curto interno da loja, não padronizado, não serve como chave)? → normaliza nome (minúsculo, sem acento, sem espaço duplicado) + normaliza quantidade/unidade pra uma forma canônica (tudo em g/ml/unidade). Busca produto existente com nome normalizado similar **e** quantidade normalizada igual.
   - Quantidade diferente (ex: 5kg vs 2kg) → **sempre** produto diferente, mesmo com nome idêntico — evita comparar preço de embalagens diferentes.
   - Nome parecido mas não idêntico, quantidade igual → sugere como possível mesmo produto, mas **pede confirmação** antes de associar ao histórico existente (nunca decide sozinho — erro aqui corrompe o histórico de preço).

**Compras** *(cada linha de item, de cada nota lida)*
- `produto_id` (referência ao produto já resolvido pela lógica acima)
- `descricao_bruta` (como veio impressa naquela nota específica — preservada mesmo que o nome amigável seja diferente)
- estabelecimento, preço, data, origem (NFC-e / print / PDF)

**Estabelecimentos**
- `nome_bruto` (chave/id — como vem da fatura/nota, imutável)
- `nome_amigavel` (editável)
- `categoria_gasto_id` (referência à tabela Categorias, tipo=`gasto` — corrige classificações genéricas tipo "outros")
- endereço (via NFC-e, quando houver)

**Lista de compras**
- item, status (pendente/comprado), data de inclusão

**Compras parceladas**
- estabelecimento, valor da parcela, parcela atual, total de parcelas, mês de término

**Configuração**
- dia de fechamento da fatura (padrão: dia 2)
- dia de vencimento (padrão: dia 9)

---

## 5. Fora de escopo da v1

- Outras categorias no fluxo de comparação de preço (só supermercado por ora — o Status do mês já cobre todas as categorias da fatura)
- Descoberta de estabelecimentos novos sem histórico de compra
- Notificações/alertas automáticos
- Login/autenticação de verdade (uso doméstico, sem essa necessidade por ora)
- Sugestão automática de lista por recorrência (decisão explícita: o gatilho de "entrar na lista" é sempre manual)

---

## 6. Decisões de design registradas

- **Sem perfil de usuário** — não há seleção de "quem está usando"; qualquer ação é anônima dentro do app.
- **"Acabou" ≠ "adicionar à lista"** — são ações independentes, porque nem todo item que acaba precisa ser comprado imediatamente.
- **Ação "acabou" exige histórico de compra via NFC-e** — evita que o catálogo vire uma lista genérica de produtos nunca comprados de fato pela família.
- **Divergência entre print semanal e PDF fechado nunca é aplicada automaticamente** — o usuário sempre confirma antes.
- **Identidade visual** inspirada em feira/hortifruti (etiquetas de preço), reforçando o conceito central do app: comparar preço entre lugares.

---

## 7. Pontos técnicos em aberto (ver seção de próximos passos para detalhamento)

- Stack de backend/frontend e banco de dados
- Estratégia de acesso remoto (o app roda em servidor de casa, mas o uso mais crítico — consulta no catálogo — acontece **fora de casa**, no supermercado)
- ~~Parser da NFC-e~~ — **decidido:** foto do cupom físico + Claude API com Structured Outputs. Validado com nota real em 02/07/2026 (ver Notas de Versão). Categoria é injetada dinamicamente no schema a partir do banco, nunca inventada pelo modelo.
- Ajuste fino da taxonomia de categorias conforme mais notas de tipos variados (padaria, açougue) forem testadas
- Motor de leitura dos prints/PDF do banco (OCR tradicional vs. modelo de visão) — mesma abordagem do parser de NFC-e provavelmente se aplica
- **Implementação da normalização de nome/quantidade** para a resolução de identidade de produto sem código de barras (estratégia já desenhada — ver seção 4 — falta escrever o algoritmo de normalização e o limiar de similaridade que dispara pedido de confirmação)
- Estratégia de backup dos dados (self-hosted em casa = sem redundância por padrão)
- **Semântica do Histórico de meses**: snapshot congelado no fechamento vs. recálculo dinâmico com dados/categorias atuais (afeta se o mês fechado é gravado como registro imutável ou apenas consultado sob demanda)
