# REQUISITOS.md — Checklist de Requisitos do Home Bispo

> **Como usar:** antes de cada deploy, percorra os requisitos da área que foi alterada.
> Se a mudança pode ter afetado outra área, verifique essa também.
> Marcar `[x]` significa "implementado e funcionando". Desmarcar se quebrar.

---

## 1. Cartão Crédito

- [ ] Mostra o valor total gasto até a data atual
- [ ] Projeção de fechamento do mês (baseada no ritmo: gasto até hoje ÷ dias decorridos × dias totais)
- [ ] Comparação com média dos meses anteriores (disponível quando houver histórico)
- [ ] Retrato categorizado por barras (do maior pro menor)
- [ ] Seção de compras parceladas: estabelecimento, valor, "parcela X de Y", mês de término
- [ ] Parcelas ordenadas por proximidade de término (menos restantes primeiro)
- [ ] Parcela na última prestação destacada em verde (é positivo)
- [ ] Barra comparativa visual: parcelas (fixo) vs. demais gastos
- [ ] Cards de insight: economia possível + recorrências que passam despercebidas

## 2. Produtos

- [ ] Busca por nome de produto (campo no topo)
- [ ] Filtro por categoria via combobox (folha inferior, não chips de rolagem lateral)
- [ ] Cada produto mostra: nome amigável, categoria, "costuma acabar a cada X dias", último preço+local, melhor preço+local
- [ ] Botão "🔔 acabou" — registra evento de consumo, alimenta cálculo de duração média, NÃO adiciona à lista
- [ ] Botão "+ lista" — adiciona/remove da lista de compras, independente de "acabou"
- [ ] Ambos os botões só visíveis para produtos com pelo menos 1 compra confirmada via NFC-e
- [ ] Produtos sem histórico de compra aparecem no catálogo mas sem ações (mensagem "ainda sem compra registrada via nota fiscal")

## 3. Lista de compras

- [ ] Mostra itens adicionados via "+ lista" no catálogo
- [ ] Checkbox pra marcar como comprado
- [ ] Cada item mostra último preço+local e melhor preço+local
- [ ] Badge no menu inferior atualiza com a contagem de itens pendentes

## 4. Parser de NFC-e

- [ ] Recebe foto (bytes) + lista de categorias válidas do banco
- [ ] Monta JSON Schema dinamicamente com as categorias como enum (nunca hardcoded)
- [ ] Usa Claude API Structured Outputs (tool_choice forçado) — resposta garantida no formato do schema
- [ ] Extrai: chave de acesso (44 dígitos), estabelecimento (razão social, CNPJ, endereço), itens (código, descrição, qtd, unidade, preço unitário, valor total, categoria), valor total da nota
- [ ] Itens por peso preservam quantidade fracionária (não arredondam)
- [ ] Soma dos itens extraídos bate com o valor total da nota (validação obrigatória pós-extração)

## 5. Resolução de identidade de produto

- [ ] Código de barras EAN/GTIN presente → match exato, ignora diferença de descrição entre notas
- [ ] Sem código de barras → normaliza nome + quantidade pra forma canônica
- [ ] Quantidade diferente (ex: 5kg ≠ 2kg) = produto diferente, SEMPRE, mesmo nome igual
- [ ] Nome parecido + quantidade igual → sugere como possível match, mas PEDE CONFIRMAÇÃO (nunca decide sozinho)
- [ ] `descricao_bruta` da nota é preservada mesmo quando associada a produto existente

## 6. Deduplicação de fontes

- [ ] Compra de supermercado que aparece na fatura E na NFC-e: NFC-e prevalece (mais granular)
- [ ] Divergência entre print semanal e PDF fechado: pede confirmação antes de aplicar

## 7. Cadastros (Configurações)

### 7.1 Categorias
- [ ] Tabela única com campo `tipo` (`produto` | `gasto`)
- [ ] Gerenciáveis pelo frontend (adicionar, remover)
- [ ] Categorias de produto usadas no catálogo e no schema de extração da NFC-e
- [ ] Categorias de gasto usadas na classificação do Cartão Crédito
- [ ] Remover categoria não quebra produtos/estabelecimentos já associados

### 7.2 Produtos
- [ ] Sempre originados de leitura de NFC-e (nunca cadastro manual)
- [ ] `nome_amigavel` editável, chave/id interna nunca muda
- [ ] `codigo_barras` (quando existir) é imutável
- [ ] Editar nome amigável não afeta histórico de preço

### 7.3 Estabelecimentos
- [ ] `nome_bruto` (como vem na fatura/nota) é a chave, imutável
- [ ] `nome_amigavel` editável
- [ ] Indicação visual de "ainda não renomeado" pra quem ainda tem nome bruto
- [ ] Renomear não afeta relacionamento com lançamentos existentes

## 8. Configuração do sistema

- [ ] Dia de fechamento da fatura (padrão: 2)
- [ ] Dia de vencimento (padrão: 9)
- [ ] `ANTHROPIC_API_KEY` via variável de ambiente, nunca no código

## 9. Histórico de meses (Funcionalidades)

- [ ] Cada mês anterior como card: total, variação vs mês anterior, nota-resumo
- [ ] Tocar no card do mês abre a mesma view do Cartão Crédito, com os dados daquele mês
- [ ] Indicação visual de "mês histórico" (banner + aviso)
- [ ] Link/opção "voltar ao mês atual" visível quando em modo histórico
- [ ] Menu Funcionalidades mostra "Mês Atual (mês/ano)" quando está visualizando histórico

## 10. Interface / UX

- [ ] Menu inferior fixo (Cartão Crédito / Produtos / Lista), conteúdo rola por dentro
- [ ] Mobile-first: em viewport < 460px, ocupa tela inteira com `100dvh`
- [ ] Ícone ☰ (Funcionalidades) e ⚙️ (Configurações) no topo da tela Cartão Crédito
- [ ] Clicar no fundo escuro (backdrop) de qualquer modal fecha o modal
- [ ] Configurações é menu com subseções: Categorias de produto, Categorias de gasto, Produtos, Estabelecimentos, Sobre
- [ ] Cada subseção tem "voltar" pro menu pai

## 11. Infraestrutura

- [x] Docker Compose funcional pra desktop (container Python + FastAPI + SQLite)
- [ ] App sobe sozinho ao ligar o PC de casa, idealmente sem precisar logar (deploy na Mi Box via Termux foi abandonado — build nativo do pymupdf/pydantic-core não viável lá)
- [ ] Backup do banco = copiar 1 arquivo SQLite
- [ ] Acesso remoto (Tailscale ou proxy reverso) — pra consultar catálogo fora de casa
