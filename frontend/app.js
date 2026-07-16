const API = "/api";

const MESES_PT = [
  "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
  "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
];
const MESES_PT_ABREV = [
  "jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez",
];

function mesLabel(mesReferencia) {
  const [ano, mes] = mesReferencia.split("-").map(Number);
  return `${MESES_PT[mes - 1]}/${ano}`;
}
function mesLabelAbrev(mesReferencia) {
  const [ano, mes] = mesReferencia.split("-").map(Number);
  return `${MESES_PT_ABREV[mes - 1]}/${ano}`;
}
function fmtMoney(v) {
  if (v === null || v === undefined) return "—";
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}
function fmtDataCurta(iso) {
  // Nunca usar `new Date(iso)` aqui: uma string "YYYY-MM-DD" (sem hora) é
  // interpretada como meia-noite UTC, e getDate()/getMonth() devolvem o
  // horário LOCAL — num fuso atrás de UTC (ex: Brasil, UTC-3), isso vira o
  // dia anterior. Parseia os componentes direto da string, sem passar por
  // Date, imune a fuso horário. iso.slice(0,10) cobre tanto "YYYY-MM-DD"
  // quanto "YYYY-MM-DDTHH:mm:ss".
  const [ano, mes, dia] = iso.slice(0, 10).split("-").map(Number);
  return `${dia} ${MESES_PT_ABREV[mes - 1]}`;
}

function attrEscape(value) {
  return JSON.stringify(value).replace(/"/g, "&quot;");
}

async function api(path, options = {}) {
  const resp = await fetch(API + path, {
    headers: options.body ? { "Content-Type": "application/json" } : undefined,
    ...options,
  });
  if (!resp.ok) {
    let detail = resp.statusText;
    try { detail = (await resp.json()).detail || detail; } catch (e) {}
    throw new Error(detail);
  }
  if (resp.status === 204) return null;
  return resp.json();
}

let toastTimer;
function showToast(msg) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 2200);
}

function goTo(id) {
  document.querySelectorAll(".screen").forEach((s) => s.classList.remove("active"));
  document.getElementById(id).classList.add("active");
}

// ---------- STATUS ----------

let modoHistorico = null;
let ultimoStatusLancamentos = [];

function renderStatus(data, historicoNota) {
  const isHistorico = modoHistorico !== null;
  ultimoStatusLancamentos = data.lancamentos;

  document.getElementById("status-title").textContent = isHistorico
    ? `${mesLabel(data.mes_referencia)} · mês fechado`
    : `${data.dia_atual} de ${data.dias_total} de ${MESES_PT[Number(data.mes_referencia.split("-")[1]) - 1]}`;

  document.getElementById("hero-label").textContent = isHistorico ? "GASTO TOTAL DO MÊS" : "GASTO ATÉ HOJE";
  document.getElementById("hero-value").textContent = fmtMoney(data.gasto_ate_hoje);

  const compareWrap = document.getElementById("hero-compare-wrap");
  if (data.media_historica != null && data.comparacao_pct != null) {
    compareWrap.style.display = "flex";
    const pill = document.getElementById("hero-compare-pill");
    const caiu = data.comparacao_pct < 0;
    pill.textContent = `${caiu ? "↓" : "↑"} ${Math.abs(data.comparacao_pct).toFixed(0)}% vs média (${fmtMoney(data.media_historica)})`;
    pill.className = "pill " + (caiu ? "ok" : "warn");
  } else {
    compareWrap.style.display = "none";
  }

  const recentes = [...data.lancamentos].sort((a, b) => new Date(b.data) - new Date(a.data)).slice(0, 3);
  document.getElementById("por-data-list").innerHTML = recentes.map((l) => `
    <div class="compare-row" onclick="abrirRecategorizar(${l.id}, ${attrEscape(l.categoria)})" style="cursor:pointer;">
      <div>
        <div class="place">${l.estabelecimento}</div>
        <div class="date">${fmtDataCurta(l.data)}${l.parcela_atual ? ` · ${l.parcela_atual}/${l.total_parcelas}` : ""}</div>
      </div>
      <span class="price">${fmtMoney(l.valor)}</span>
    </div>
  `).join("") || `<div class="empty-state"><span class="ic">🗓️</span><p>Nenhum lançamento ainda este mês.</p></div>`;

  const paletaCategorias = ["var(--green)", "var(--gold)", "var(--red)", "var(--ink-soft)"];
  document.getElementById("categorias-list").innerHTML = data.categorias.map((c, i) => `
    <div class="cat-row" onclick="abrirCategoriaDetalhe(${attrEscape(c.nome)})">
      <div class="cat-bar-wrap">
        <div class="cat-top"><span class="name">${c.nome}</span><span class="val"><span class="qtd">${c.qtd_lancamentos} lançamento${c.qtd_lancamentos === 1 ? "" : "s"}</span>${fmtMoney(c.total)}</span></div>
        <div class="cat-track"><div class="cat-fill" style="width:${c.pct.toFixed(0)}%; background:${paletaCategorias[i % paletaCategorias.length]};"></div></div>
      </div>
    </div>
  `).join("");

  const fixo = data.split_fixo_resto.fixo;
  const resto = data.split_fixo_resto.resto;
  const total = fixo + resto;
  document.getElementById("split-fixo").style.width = total ? `${(fixo / total * 100).toFixed(1)}%` : "0%";
  document.getElementById("split-resto").style.width = total ? `${(resto / total * 100).toFixed(1)}%` : "100%";
  document.getElementById("split-fixo-valor").textContent = fmtMoney(fixo);
  document.getElementById("split-resto-valor").textContent = fmtMoney(resto);

  const nosso = data.split_nossas_terceiros.nosso;
  const terceiroValor = data.split_nossas_terceiros.terceiro;
  const totalNossoTerceiro = nosso + terceiroValor;
  const mostrarNossoTerceiro = terceiroValor > 0;
  document.getElementById("nossas-terceiros-title").style.display = mostrarNossoTerceiro ? "flex" : "none";
  document.getElementById("nossas-terceiros-card").style.display = mostrarNossoTerceiro ? "block" : "none";
  if (mostrarNossoTerceiro) {
    document.getElementById("split-nosso").style.width = `${(nosso / totalNossoTerceiro * 100).toFixed(1)}%`;
    document.getElementById("split-terceiro").style.width = `${(terceiroValor / totalNossoTerceiro * 100).toFixed(1)}%`;
    document.getElementById("split-nosso-valor").textContent = fmtMoney(nosso);
    document.getElementById("split-terceiro-valor").textContent = fmtMoney(terceiroValor);
  }

  const parcelasFinalizando = data.parcelas.filter((p) => p.ultima);
  const somaFinalizando = parcelasFinalizando.reduce((soma, p) => soma + p.valor_parcela, 0);
  const cardFinalizando = document.getElementById("parcelas-finalizando-card");
  if (somaFinalizando > 0) {
    cardFinalizando.style.display = "block";
    const plural = parcelasFinalizando.length > 1;
    document.getElementById("parcelas-finalizando-titulo").textContent = "🎉 Uma boa notícia pro bolso";
    document.getElementById("parcelas-finalizando-texto").innerHTML =
      `<b>${fmtMoney(somaFinalizando)}</b> saem da fatura a partir do mês que vem — ${parcelasFinalizando.length} parcela${plural ? "s" : ""} ${plural ? "bateram" : "bateu"} ponto pela última vez por aqui. 🥳`;
  } else {
    cardFinalizando.style.display = "none";
  }

  document.getElementById("parcelas-title").style.display = data.parcelas.length ? "flex" : "none";
  document.getElementById("parcelas-list").innerHTML = data.parcelas.map((p) => `
    <div class="parcela-card ${p.terceiro ? "terceiro-ativo" : (p.ultima ? "last" : "")}">
      <div class="parcela-top">
        <span class="parcela-est">${p.estabelecimento}</span>
        <span class="parcela-valor">${fmtMoney(p.valor_parcela)}</span>
      </div>
      <div class="parcela-bottom">
        <div style="display:flex; gap:6px; align-items:center;">
          <span class="parcela-tag ${p.ultima ? "last-tag" : ""}">${p.ultima ? "última parcela" : "parcela"} · ${p.parcela_atual} de ${p.total_parcelas}</span>
          ${p.terceiro ? `<span class="parcela-tag terceiro-tag">terceiro</span>` : ""}
        </div>
        <span class="parcela-fim">${p.ultima ? "termina este mês" : "termina " + mesLabelAbrev(p.mes_termino)}</span>
      </div>
      <div class="parcela-track"><div class="parcela-fill" style="width:${(p.parcela_atual / p.total_parcelas * 100).toFixed(1)}%;"></div></div>
    </div>
  `).join("");

  document.getElementById("insights-title").style.display = data.insights.length ? "flex" : "none";
  document.getElementById("insights-list").innerHTML = data.insights.map((ins) => `
    <div class="insight-card ${ins.tipo === "economia" ? "savings" : ins.tipo === "recorrencia" ? "recur" : ""}">
      <div class="ihead">${ins.titulo}</div>
      <p>${ins.texto}</p>
    </div>
  `).join("");

  const banner = document.getElementById("historico-banner");
  if (isHistorico) {
    banner.style.display = "flex";
    document.getElementById("historico-banner-text").textContent = "📅 " + (historicoNota || mesLabel(data.mes_referencia));
  } else {
    banner.style.display = "none";
  }

  const hoje = new Date();
  document.getElementById("menu-row-mes-atual-label").textContent =
    `Mês Atual (${MESES_PT[hoje.getMonth()]}/${hoje.getFullYear()})`;
  document.getElementById("menu-row-mes-atual").style.display = isHistorico ? "flex" : "none";
}

function abrirCategoriaDetalhe(categoriaNome) {
  const itens = ultimoStatusLancamentos.filter((l) => l.categoria === categoriaNome);
  const total = itens.reduce((soma, l) => soma + l.valor, 0);

  document.getElementById("categoria-detalhe-titulo").textContent = categoriaNome;
  document.getElementById("categoria-detalhe-sub").textContent =
    `${itens.length} ${itens.length === 1 ? "lançamento" : "lançamentos"} · ${fmtMoney(total)}`;
  document.getElementById("categoria-detalhe-lista").innerHTML = itens.map((l) => `
    <div class="compare-row" onclick="abrirRecategorizar(${l.id}, ${attrEscape(l.categoria)})" style="cursor:pointer;">
      <div>
        <div class="place">${l.estabelecimento}</div>
        <div class="date">${fmtDataCurta(l.data)}${l.parcela_atual ? ` · ${l.parcela_atual}/${l.total_parcelas}` : ""}</div>
      </div>
      <span class="price">${fmtMoney(l.valor)}</span>
    </div>
  `).join("");
  document.getElementById("categoria-detalhe-modal").classList.add("open");
}
function closeCategoriaDetalhe() {
  document.getElementById("categoria-detalhe-modal").classList.remove("open");
}

let recategorizarLancamentoId = null;

async function abrirRecategorizar(lancamentoId, categoriaAtual) {
  recategorizarLancamentoId = lancamentoId;
  const categorias = await api("/config/categorias?tipo=gasto");
  const outras = categorias.filter((c) => c.nome !== categoriaAtual);

  document.getElementById("recategorizar-atual").textContent = categoriaAtual;
  document.getElementById("recategorizar-lista").innerHTML = outras.map((c) => `
    <div class="cat-modal-row" onclick="confirmarRecategorizar(${c.id}, ${attrEscape(c.nome)})">
      <span>${c.nome}</span>
    </div>
  `).join("");
  document.getElementById("recategorizar-modal").classList.add("open");
}

function closeRecategorizar() {
  document.getElementById("recategorizar-modal").classList.remove("open");
  recategorizarLancamentoId = null;
}

async function confirmarRecategorizar(categoriaId, categoriaNome) {
  const lancamentoId = recategorizarLancamentoId;
  try {
    await api(`/status/lancamentos/${lancamentoId}/categoria`, {
      method: "PATCH",
      body: JSON.stringify({ categoria_id: categoriaId }),
    });
    showToast(`Recategorizado para "${categoriaNome}"`);
    closeRecategorizar();
    closeCategoriaDetalhe();
    if (modoHistorico) {
      const data = await api(`/historico/meses/${modoHistorico}`);
      renderStatus(data);
    } else {
      await carregarStatusAtual();
    }
  } catch (e) {
    showToast("Erro ao recategorizar: " + e.message);
  }
}

function abrirExtratoPorData() {
  const itens = [...ultimoStatusLancamentos].sort((a, b) => new Date(b.data) - new Date(a.data));
  const total = itens.reduce((soma, l) => soma + l.valor, 0);

  document.getElementById("categoria-detalhe-titulo").textContent = "Por data";
  document.getElementById("categoria-detalhe-sub").textContent =
    `${itens.length} ${itens.length === 1 ? "lançamento" : "lançamentos"} · ${fmtMoney(total)}`;
  document.getElementById("categoria-detalhe-lista").innerHTML = itens.map((l) => `
    <div class="compare-row" onclick="abrirRecategorizar(${l.id}, ${attrEscape(l.categoria)})" style="cursor:pointer;">
      <div>
        <div class="place">${l.estabelecimento}</div>
        <div class="date">${fmtDataCurta(l.data)}${l.parcela_atual ? ` · ${l.parcela_atual}/${l.total_parcelas}` : ""} · ${l.categoria}</div>
      </div>
      <span class="price">${fmtMoney(l.valor)}</span>
    </div>
  `).join("");
  document.getElementById("categoria-detalhe-modal").classList.add("open");
}

function abrirTerceirosDoMes() {
  const itens = ultimoStatusLancamentos
    .filter((l) => l.terceiro)
    .sort((a, b) => new Date(b.data) - new Date(a.data));
  const total = itens.reduce((soma, l) => soma + l.valor, 0);

  document.getElementById("categoria-detalhe-titulo").textContent = "Terceiros este mês";
  document.getElementById("categoria-detalhe-sub").textContent =
    `${itens.length} ${itens.length === 1 ? "lançamento" : "lançamentos"} · ${fmtMoney(total)} pra cobrar`;
  document.getElementById("categoria-detalhe-lista").innerHTML = itens.map((l) => `
    <div class="compare-row">
      <div>
        <div class="place">${l.estabelecimento}</div>
        <div class="date">${fmtDataCurta(l.data)}${l.parcela_atual ? ` · ${l.parcela_atual}/${l.total_parcelas}` : ""} · ${l.categoria}</div>
      </div>
      <span class="price">${fmtMoney(l.valor)}</span>
    </div>
  `).join("");
  document.getElementById("categoria-detalhe-modal").classList.add("open");
}

async function carregarStatusAtual() {
  modoHistorico = null;
  const data = await api("/status/mes");
  renderStatus(data);
}

async function abrirMesHistorico(mesReferencia, notaResumo) {
  modoHistorico = mesReferencia;
  const data = await api(`/historico/meses/${mesReferencia}`);
  renderStatus(data, notaResumo);
  closeFeatures();
  goTo("screen-status");
}

async function voltarParaMesAtual() {
  await carregarStatusAtual();
  closeFeatures();
  goTo("screen-status");
}

async function carregarHistoricoLista() {
  const meses = await api("/historico/meses");
  document.getElementById("historico-list").innerHTML = meses.map((m) => `
    <div class="hist-card" onclick="abrirMesHistorico('${m.mes_referencia}', ${attrEscape(m.nota_resumo || mesLabel(m.mes_referencia))})">
      <div class="hist-top">
        <span class="hist-mes">${mesLabel(m.mes_referencia)}</span>
        <span class="hist-valor">${fmtMoney(m.total)}</span>
      </div>
      ${m.variacao_pct != null ? `<div class="hist-delta ${m.variacao_pct < 0 ? "down" : "up"}">${m.variacao_pct < 0 ? "↓" : "↑"} ${Math.abs(m.variacao_pct).toFixed(0)}% vs mês anterior</div>` : ""}
      ${m.nota_resumo ? `<p class="hist-nota">${m.nota_resumo}</p>` : ""}
    </div>
  `).join("") || `<div class="empty-state"><span class="ic">🕰️</span><p>Ainda sem meses fechados no histórico.</p></div>`;
}

function somarMesesJS(mesReferencia, delta) {
  const [ano, mes] = mesReferencia.split("-").map(Number);
  const total = ano * 12 + (mes - 1) + delta;
  const ano2 = Math.floor(total / 12);
  const mes2 = total % 12;
  return `${String(ano2).padStart(4, "0")}-${String(mes2 + 1).padStart(2, "0")}`;
}

async function carregarPrevisaoParcelas() {
  const data = await api("/status/mes");
  const parcelas = data.parcelas;
  const container = document.getElementById("previsao-parcelas-lista");

  const maxRestante = Math.max(0, ...parcelas.map((p) => p.total_parcelas - p.parcela_atual), 0);
  if (maxRestante === 0) {
    container.innerHTML = `<div class="empty-state"><span class="ic">🎉</span><p>Nenhuma parcela em aberto pros próximos meses.</p></div>`;
    return;
  }

  let html = "";
  let indice = 0;
  for (let i = 1; i <= maxRestante; i++) {
    const itensDoMes = parcelas
      .filter((p) => p.total_parcelas - p.parcela_atual >= i)
      .map((p) => ({
        estabelecimento: p.estabelecimento,
        numero: p.parcela_atual + i,
        total: p.total_parcelas,
        valor: p.valor_parcela,
        libera: p.parcela_atual + i === p.total_parcelas,
      }));

    if (itensDoMes.length === 0) continue;

    const totalMes = itensDoMes.reduce((soma, it) => soma + it.valor, 0);
    const valorLiberado = itensDoMes.filter((it) => it.libera).reduce((soma, it) => soma + it.valor, 0);
    const mesRef = somarMesesJS(data.mes_referencia, i);
    const idAtual = indice;

    html += `
      <div class="hist-card" onclick="togglePrevisaoMes(${idAtual})">
        <div class="hist-top">
          <span class="hist-mes">${mesLabel(mesRef)} <span id="previsao-chevron-${idAtual}" style="color:var(--ink-faint); font-size:11px;">▾</span></span>
          <span class="hist-valor">${fmtMoney(totalMes)}</span>
        </div>
        ${valorLiberado > 0 ? `<div class="hist-delta down">LIBERA ${fmtMoney(valorLiberado)}</div>` : ""}
      </div>
      <div id="previsao-itens-${idAtual}" style="display:none; margin:-2px 0 12px 0;">
        ${itensDoMes.map((it) => `
          <div class="parcela-card ${it.libera ? "last" : ""}">
            <div class="parcela-top">
              <span class="parcela-est">${it.estabelecimento}</span>
              <span class="parcela-valor">${fmtMoney(it.valor)}</span>
            </div>
            <div class="parcela-bottom">
              <span class="parcela-tag ${it.libera ? "last-tag" : ""}">${it.libera ? "última parcela" : "parcela"} · ${it.numero} de ${it.total}</span>
            </div>
            <div class="parcela-track"><div class="parcela-fill" style="width:${(it.numero / it.total * 100).toFixed(1)}%;"></div></div>
          </div>
        `).join("")}
      </div>
    `;
    indice++;
  }

  container.innerHTML = html;
}

async function carregarComprasTerceiros() {
  const lancamentos = await api("/status/lancamentos-terceiros");
  document.getElementById("terceiros-lista").innerHTML = lancamentos.map((c) => {
    const tagPrincipal = c.total_parcelas ? `parcela ${c.parcela_atual} de ${c.total_parcelas}` : fmtDataCurta(c.data);
    return `
    <div class="parcela-card ${c.terceiro ? "terceiro-ativo" : "terceiro-inativo"}" onclick="alternarTerceiro(${c.id}, ${!c.terceiro})">
      <div class="parcela-top">
        <span class="parcela-est">${c.estabelecimento}</span>
        <span class="parcela-valor">${fmtMoney(c.valor)}</span>
      </div>
      <div class="parcela-bottom">
        <span class="parcela-tag ${c.terceiro ? "terceiro-tag" : ""}">${tagPrincipal}</span>
        <span style="font-size:11.5px; font-weight:600; color:${c.terceiro ? "var(--red)" : "var(--ink-faint)"};">${c.terceiro ? "✓ de terceiro" : "marcar como terceiro"}</span>
      </div>
    </div>
  `;
  }).join("") || `<div class="empty-state"><span class="ic">👥</span><p>Nenhum lançamento candidato a terceiro este mês.</p></div>`;
}

async function alternarTerceiro(lancamentoId, novoValor) {
  try {
    await api(`/status/lancamentos/${lancamentoId}/terceiro`, {
      method: "PATCH",
      body: JSON.stringify({ terceiro: novoValor }),
    });
    await carregarComprasTerceiros();
    // Atualiza o card "nossas vs. terceiros" na hora, sem depender do gate
    // de carregarStatusSilencioso() (que só refaz o fetch fora do modo
    // histórico e engole qualquer erro em silêncio — se o estado de
    // histórico ficasse "preso" de uma navegação anterior, o card parava
    // de atualizar sem nenhum aviso, só resolvendo com F5).
    if (modoHistorico) {
      const data = await api(`/historico/meses/${modoHistorico}`);
      renderStatus(data);
    } else {
      await carregarStatusAtual();
    }
  } catch (e) {
    showToast("Erro ao marcar terceiro: " + e.message);
  }
}

function togglePrevisaoMes(indice) {
  const div = document.getElementById(`previsao-itens-${indice}`);
  const chevron = document.getElementById(`previsao-chevron-${indice}`);
  const aberto = div.style.display !== "none";
  div.style.display = aberto ? "none" : "block";
  chevron.textContent = aberto ? "▾" : "▴";
}

// ---------- FUNCIONALIDADES / CONFIGURAÇÕES (modais) ----------

function openFeatures() {
  backToFeaturesMenu();
  carregarHistoricoLista();
  document.getElementById("features-modal").classList.add("open");
}
function closeFeatures() {
  document.getElementById("features-modal").classList.remove("open");
}
function showFeaturesSection(id) {
  document.getElementById("features-menu").style.display = "none";
  document.querySelectorAll("#features-modal .settings-section").forEach((s) => s.classList.remove("open"));
  document.getElementById(id).classList.add("open");
}
function backToFeaturesMenu() {
  document.querySelectorAll("#features-modal .settings-section").forEach((s) => s.classList.remove("open"));
  document.getElementById("features-menu").style.display = "block";
}

function openSettings() {
  backToSettingsMenu();
  carregarCategoriasProduto();
  carregarCategoriasGasto();
  carregarProdutosConfig();
  carregarEstabelecimentosConfig();
  document.getElementById("settings-modal").classList.add("open");
}
function closeSettings() {
  document.getElementById("settings-modal").classList.remove("open");
}
function showSettingsSection(id) {
  document.getElementById("settings-menu").style.display = "none";
  document.querySelectorAll("#settings-modal .settings-section").forEach((s) => s.classList.remove("open"));
  document.getElementById(id).classList.add("open");
}
function backToSettingsMenu() {
  document.querySelectorAll("#settings-modal .settings-section").forEach((s) => s.classList.remove("open"));
  document.getElementById("settings-menu").style.display = "block";
}

// ---------- CATEGORIAS (produto / gasto) ----------

let categoriasProduto = [];
let categoriasProdutoMap = {};

async function carregarCategoriasProduto() {
  categoriasProduto = await api("/config/categorias?tipo=produto");
  categoriasProdutoMap = Object.fromEntries(categoriasProduto.map((c) => [c.id, c.nome]));
  document.getElementById("cat-manage-list").innerHTML = categoriasProduto.map((c) => `
    <div class="cat-manage-row"><span>${c.nome}</span><button class="del-btn" aria-label="Remover ${c.nome}" onclick="removeCategory(${c.id})">✕</button></div>
  `).join("");
}

async function addCategory() {
  const input = document.getElementById("new-cat-input");
  const nome = input.value.trim();
  if (!nome) return;
  try {
    await api("/config/categorias", { method: "POST", body: JSON.stringify({ nome, tipo: "produto" }) });
    input.value = "";
    await carregarCategoriasProduto();
    await carregarCatalogoCategorias();
    showToast(`Categoria "${nome}" adicionada`);
  } catch (e) { showToast("Erro: " + e.message); }
}

async function removeCategory(id) {
  const cat = categoriasProduto.find((c) => c.id === id);
  await api(`/config/categorias/${id}`, { method: "DELETE" });
  await carregarCategoriasProduto();
  await carregarCatalogoCategorias();
  await carregarCatalogoProdutos();
  showToast(`Categoria "${cat ? cat.nome : ""}" removida`);
}

async function carregarCategoriasGasto() {
  const categorias = await api("/config/categorias?tipo=gasto");
  document.getElementById("cat-gasto-manage-list").innerHTML = categorias.map((c) => `
    <div class="cat-manage-row"><span>${c.nome}</span><button class="del-btn" aria-label="Remover ${c.nome}" onclick="removeCategoriaGasto(${c.id})">✕</button></div>
  `).join("");
}

async function addCategoriaGasto() {
  const input = document.getElementById("new-cat-gasto-input");
  const nome = input.value.trim();
  if (!nome) return;
  try {
    await api("/config/categorias", { method: "POST", body: JSON.stringify({ nome, tipo: "gasto" }) });
    input.value = "";
    await carregarCategoriasGasto();
    showToast(`Categoria "${nome}" adicionada`);
  } catch (e) { showToast("Erro: " + e.message); }
}

async function removeCategoriaGasto(id) {
  await api(`/config/categorias/${id}`, { method: "DELETE" });
  await carregarCategoriasGasto();
  showToast("Categoria removida");
}

// ---------- PRODUTOS / ESTABELECIMENTOS (config) ----------

async function carregarProdutosConfig() {
  const produtos = await api("/config/produtos");
  document.getElementById("produtos-manage-list").innerHTML = produtos.map((p) => `
    <div class="produto-manage-row" id="prow-${p.id}">
      <div class="produto-manage-top">
        <span class="produto-nome-display" id="pname-${p.id}">${p.nome_amigavel}</span>
        <button class="produto-edit-btn" aria-label="Renomear ${p.nome_amigavel}" onclick="editProdutoNome(${p.id})">✏️</button>
      </div>
      <div class="produto-meta">${p.codigo_barras ? "EAN " + p.codigo_barras : "sem código de barras"} · ${p.categoria_id != null ? (categoriasProdutoMap[p.categoria_id] || "categoria #" + p.categoria_id) : "sem categoria"}</div>
    </div>
  `).join("");
}

function editProdutoNome(id) {
  const span = document.getElementById("pname-" + id);
  const nomeAtual = span.textContent;
  const input = document.createElement("input");
  input.className = "produto-nome-input";
  input.value = nomeAtual;
  span.replaceWith(input);
  input.focus();
  input.select();

  const save = async () => {
    const novoNome = input.value.trim() || nomeAtual;
    try {
      await api(`/config/produtos/${id}`, { method: "PATCH", body: JSON.stringify({ nome_amigavel: novoNome }) });
      showToast("Nome amigável atualizado — histórico de preço continua o mesmo");
    } catch (e) { showToast("Erro: " + e.message); }
    await carregarProdutosConfig();
    await carregarCatalogoProdutos();
  };
  input.addEventListener("blur", save);
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") input.blur(); });
}

async function carregarEstabelecimentosConfig() {
  const estabelecimentos = await api("/config/estabelecimentos");
  document.getElementById("estabelecimentos-manage-list").innerHTML = estabelecimentos.map((e) => {
    const renomeado = e.nome_amigavel && e.nome_amigavel !== e.nome_bruto;
    const nomeExibido = e.nome_amigavel || e.nome_bruto;
    return `
    <div class="produto-manage-row" id="erow-${e.id}">
      <div class="produto-manage-top">
        <span class="produto-nome-display" id="ename-${e.id}">${nomeExibido}${renomeado ? "" : ' <span class="unrenamed-tag">NÃO RENOMEADO</span>'}</span>
        <button class="produto-edit-btn" aria-label="Renomear ${nomeExibido}" onclick="editEstabelecimentoNome(${e.id}, ${attrEscape(e.nome_bruto)})">✏️</button>
      </div>
      <div class="produto-meta">nome na fatura: "${e.nome_bruto}"</div>
    </div>`;
  }).join("");
}

function editEstabelecimentoNome(id, nomeBruto) {
  const span = document.getElementById("ename-" + id);
  const input = document.createElement("input");
  input.className = "produto-nome-input";
  input.value = span.textContent.replace("NÃO RENOMEADO", "").trim();
  span.replaceWith(input);
  input.focus();
  input.select();

  const save = async () => {
    const novoNome = input.value.trim() || nomeBruto;
    try {
      await api(`/config/estabelecimentos/${id}`, { method: "PATCH", body: JSON.stringify({ nome_amigavel: novoNome }) });
      showToast(`Nome amigável salvo — a fatura continua reconhecendo por "${nomeBruto}"`);
    } catch (e) { showToast("Erro: " + e.message); }
    await carregarEstabelecimentosConfig();
    await carregarCatalogoProdutos();
    await carregarLista();
    await carregarStatusSilencioso();
  };
  input.addEventListener("blur", save);
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") input.blur(); });
}

async function carregarStatusSilencioso() {
  if (modoHistorico === null) {
    try { await carregarStatusAtual(); } catch (e) {}
  }
}

// ---------- CONFIG DO SISTEMA ----------

async function carregarConfigSistema() {
  const config = await api("/config/sistema");
  document.getElementById("config-dia-fechamento").value = config.dia_fechamento_fatura;
  document.getElementById("config-dia-vencimento").value = config.dia_vencimento;
}

async function salvarConfigSistema() {
  const dia_fechamento_fatura = Number(document.getElementById("config-dia-fechamento").value);
  const dia_vencimento = Number(document.getElementById("config-dia-vencimento").value);
  try {
    await api("/config/sistema", { method: "PATCH", body: JSON.stringify({ dia_fechamento_fatura, dia_vencimento }) });
    showToast("Configuração salva");
  } catch (e) {
    showToast("Erro: " + e.message);
  }
}

// ---------- CATÁLOGO ----------

let catalogoCategorias = [];
let catalogoCategoriaId = null;
let catalogoBusca = "";
let catalogoBuscaTimer;

async function carregarCatalogoCategorias() {
  catalogoCategorias = await api("/catalogo/categorias");
}

async function carregarCatalogoContagem() {
  const { total } = await api("/catalogo/produtos/contagem");
  document.getElementById("catalog-title").textContent =
    `Catálogo de produtos · ${total} cadastrado${total === 1 ? "" : "s"}`;
}

function renderCategoryModalList() {
  const selList = document.getElementById("cat-select-list");
  let html = `<div class="cat-modal-row ${catalogoCategoriaId === null ? "active" : ""}" onclick="selecionarCategoriaCatalogo(null,'Todas')"><span>Todas</span><span class="check">✓</span></div>`;
  html += catalogoCategorias.map((c) => `
    <div class="cat-modal-row ${catalogoCategoriaId === c.id ? "active" : ""}" onclick="selecionarCategoriaCatalogo(${c.id}, ${attrEscape(c.nome)})">
      <span>${c.nome}</span><span class="check">✓</span>
    </div>
  `).join("");
  selList.innerHTML = html;
}

function openCategoryModal() {
  renderCategoryModalList();
  document.getElementById("category-modal").classList.add("open");
}
function closeCategoryModal() {
  document.getElementById("category-modal").classList.remove("open");
}
async function selecionarCategoriaCatalogo(id, label) {
  catalogoCategoriaId = id;
  document.getElementById("cat-select-label").textContent = label;
  closeCategoryModal();
  await carregarCatalogoProdutos();
}

function onCatalogSearch(valor) {
  catalogoBusca = valor;
  clearTimeout(catalogoBuscaTimer);
  catalogoBuscaTimer = setTimeout(carregarCatalogoProdutos, 250);
}

function renderTagsProduto(p) {
  const mesmoPreco = p.ultimo_preco != null && p.melhor_preco === p.ultimo_preco && p.melhor_local === p.ultimo_local;
  if (p.ultimo_preco == null) return "";
  const dataUltima = p.ultima_compra_data ? `${fmtDataCurta(p.ultima_compra_data)} · ` : "";
  if (mesmoPreco) {
    return `<span class="tag last">${dataUltima}<span class="lbl">melhor</span> ${fmtMoney(p.ultimo_preco)} · ${p.ultimo_local}</span>`;
  }
  return `
    <span class="tag last">${dataUltima}<span class="lbl">último</span> ${fmtMoney(p.ultimo_preco)} · ${p.ultimo_local}</span>
    ${p.melhor_preco != null ? `<span class="tag best"><span class="lbl">melhor</span> ${fmtMoney(p.melhor_preco)} · ${p.melhor_local}</span>` : ""}
  `;
}

async function carregarCatalogoProdutos() {
  const params = new URLSearchParams();
  if (catalogoBusca.trim()) params.set("q", catalogoBusca.trim());
  if (catalogoCategoriaId != null) params.set("categoria_id", catalogoCategoriaId);

  const produtos = await api(`/catalogo/produtos?${params}`);
  const container = document.getElementById("catalog-list");
  document.getElementById("no-results").style.display = produtos.length === 0 ? "block" : "none";

  container.querySelectorAll(".prod-row").forEach((el) => el.remove());
  const html = produtos.map((p) => `
    <div class="prod-row">
      <div class="prod-body">
        <div class="prod-top"><p class="prod-name">${p.nome_amigavel}</p>${p.categoria ? `<span class="cat-badge">${p.categoria}</span>` : ""}</div>
        <p class="prod-cycle">${p.dias_medio_consumo != null ? `costuma acabar a cada ~${Math.round(p.dias_medio_consumo)} dias` : "ainda sem histórico de duração"}</p>
        <div class="tags">${renderTagsProduto(p)}</div>
        ${!p.acoes_disponiveis ? `<div class="no-history-note">📄 ainda sem compra registrada via nota fiscal</div>` : ""}
      </div>
      ${p.acoes_disponiveis ? `
      <div class="action-row">
        <button class="flag-btn finish" onclick="marcarAcabou(${p.id}, this)">🔔 acabou</button>
        <button class="flag-btn addlist ${p.na_lista ? "on" : ""}" onclick="onCliqueListaCatalogo(${p.id}, ${p.na_lista}, ${attrEscape(p.nome_amigavel)})">${p.na_lista ? "✓ na lista" : "+ lista"}</button>
      </div>` : ""}
    </div>
  `).join("");
  document.getElementById("no-results").insertAdjacentHTML("beforebegin", html);
}

async function marcarAcabou(produtoId, btn) {
  try {
    await api(`/catalogo/produtos/${produtoId}/acabou`, { method: "POST" });
    showToast("Consumo registrado — ajuda a calcular a duração média");
    await carregarCatalogoProdutos();
  } catch (e) { showToast("Erro: " + e.message); }
}

function onCliqueListaCatalogo(produtoId, naLista, nomeAmigavel) {
  if (naLista) {
    removerDaLista(produtoId);
  } else {
    abrirQtyModalParaAdicionar(produtoId, nomeAmigavel);
  }
}

async function removerDaLista(produtoId) {
  try {
    await api(`/catalogo/produtos/${produtoId}/lista`, { method: "DELETE" });
    showToast("Removido da lista de compras");
    await carregarCatalogoProdutos();
    await refreshBadges();
  } catch (e) { showToast("Erro: " + e.message); }
}

// ---------- MODAL DE QUANTIDADE (Catálogo "+ lista" e Lista de compras) ----------

let qtyModalState = null;

function abrirQtyModalParaAdicionar(produtoId, nomeAmigavel) {
  qtyModalState = { mode: "add", produtoId, quantidade: 1 };
  document.getElementById("qty-modal-title").textContent = "Adicionar à lista";
  document.getElementById("qty-modal-sub").textContent = nomeAmigavel;
  document.getElementById("qty-modal-value").textContent = "1";
  document.getElementById("qty-modal").classList.add("open");
}

function abrirQtyModalParaEditar(itemId, nomeAmigavel, quantidadeAtual) {
  qtyModalState = { mode: "edit", itemId, quantidade: quantidadeAtual };
  document.getElementById("qty-modal-title").textContent = "Quantidade";
  document.getElementById("qty-modal-sub").textContent = nomeAmigavel;
  document.getElementById("qty-modal-value").textContent = String(quantidadeAtual);
  document.getElementById("qty-modal").classList.add("open");
}

function closeQtyModal() {
  qtyModalState = null;
  document.getElementById("qty-modal").classList.remove("open");
}

function alterarQtyModal(delta) {
  if (!qtyModalState) return;
  qtyModalState.quantidade = Math.max(1, qtyModalState.quantidade + delta);
  document.getElementById("qty-modal-value").textContent = String(qtyModalState.quantidade);
}

async function confirmarQtyModal() {
  if (!qtyModalState) return;
  const { mode, produtoId, itemId, quantidade } = qtyModalState;
  try {
    if (mode === "add") {
      await api(`/catalogo/produtos/${produtoId}/lista`, { method: "POST", body: JSON.stringify({ quantidade }) });
      showToast("Adicionado à lista de compras");
      closeQtyModal();
      await carregarCatalogoProdutos();
      await refreshBadges();
    } else {
      await api(`/lista/${itemId}`, { method: "PATCH", body: JSON.stringify({ quantidade }) });
      showToast("Quantidade atualizada");
      closeQtyModal();
      await carregarLista();
    }
  } catch (e) { showToast("Erro: " + e.message); }
}

// ---------- LISTA DE COMPRAS ----------

async function carregarLista() {
  const itens = await api("/lista");
  const container = document.getElementById("lista-container");
  document.getElementById("lista-empty").style.display = itens.length === 0 ? "block" : "none";

  container.innerHTML = itens.map((item) => `
    <div class="item-row ${item.status === "comprado" ? "done" : ""}">
      <div class="checkbox ${item.status === "comprado" ? "checked" : ""}" onclick="alternarCheck(${item.id}, ${attrEscape(item.status)})"></div>
      <div class="item-body">
        <p class="item-name">${item.nome_amigavel}</p>
        <p class="item-origin">adicionado dia ${fmtDataCurta(item.data_inclusao)}</p>
        <div class="tags">${renderTagsProduto(item)}</div>
      </div>
      <div class="item-qty" onclick="abrirQtyModalParaEditar(${item.id}, ${attrEscape(item.nome_amigavel)}, ${item.quantidade})">${item.quantidade}</div>
    </div>
  `).join("");

  const pendentes = itens.filter((i) => i.status === "pendente");
  document.getElementById("lista-count").textContent =
    `${pendentes.length} ${pendentes.length === 1 ? "item sinalizado" : "itens sinalizados"}`;
  const gastoPrevisto = pendentes.reduce((soma, i) => soma + (i.ultimo_preco ?? i.melhor_preco ?? 0) * i.quantidade, 0);
  document.getElementById("lista-total").textContent = fmtMoney(gastoPrevisto);
}

async function alternarCheck(itemId, statusAtual) {
  const novoStatus = statusAtual === "pendente" ? "comprado" : "pendente";
  try {
    await api(`/lista/${itemId}`, { method: "PATCH", body: JSON.stringify({ status: novoStatus }) });
    await carregarLista();
    await refreshBadges();
  } catch (e) { showToast("Erro: " + e.message); }
}

async function refreshBadges() {
  const { pendentes } = await api("/lista/contagem");
  ["nav-badge", "nav-badge-2", "nav-badge-3"].forEach((id) => {
    const el = document.getElementById(id);
    el.textContent = pendentes;
    el.style.display = pendentes === 0 ? "none" : "flex";
  });
}

// ---------- LEITURA DE NFC-e ----------

let nfceState = null;

function openNfceUpload() {
  nfceState = null;
  document.getElementById("nfce-modal-body").innerHTML = `
    <label class="upload-label">
      📷 Tirar foto
      <input type="file" accept="image/*" capture="environment" onchange="onNfceFileSelected(event)">
    </label>
    <label class="upload-label">
      🖼️ Escolher da galeria
      <input type="file" accept="image/*" onchange="onNfceFileSelected(event)">
    </label>
  `;
  document.getElementById("nfce-modal").classList.add("open");
}
function closeNfceUpload() {
  document.getElementById("nfce-modal").classList.remove("open");
  nfceState = null;
}

function nfceModalBody(html) {
  document.getElementById("nfce-modal-body").innerHTML = html;
}

async function onNfceFileSelected(event) {
  const file = event.target.files[0];
  if (!file) return;

  nfceModalBody(`<p class="nfce-loading">📷 Lendo a nota fiscal...<br>isso pode levar alguns segundos</p>`);

  try {
    const formData = new FormData();
    formData.append("imagem", file);
    const resp = await fetch(`${API}/ingestao/nfce`, { method: "POST", body: formData });
    if (!resp.ok) {
      let detail = resp.statusText;
      try { detail = (await resp.json()).detail || detail; } catch (e) {}
      throw new Error(detail);
    }
    const preview = await resp.json();
    const produtos = await api("/config/produtos");
    const produtosMap = Object.fromEntries(produtos.map((p) => [p.id, p.nome_amigavel]));

    nfceState = {
      preview,
      produtosMap,
      decisoes: preview.itens.map((item) =>
        item.resolucao_status === "match_exato" ? item.produto_id : "novo"
      ),
    };
    renderNfcePreview();
  } catch (e) {
    nfceModalBody(`
      <p class="nfce-loading">Não foi possível ler a nota: ${e.message}</p>
      <label class="upload-label">
        📷 Tirar foto
        <input type="file" accept="image/*" capture="environment" onchange="onNfceFileSelected(event)">
      </label>
      <label class="upload-label">
        🖼️ Escolher da galeria
        <input type="file" accept="image/*" onchange="onNfceFileSelected(event)">
      </label>
    `);
  }
}

function nfceDecisaoChange(index, valor) {
  nfceState.decisoes[index] = valor === "novo" ? "novo" : Number(valor);
}

function renderNfcePreview() {
  const { preview, produtosMap, decisoes } = nfceState;
  const chave = preview.chave_acesso;
  const chaveResumida = chave.length > 12 ? `${chave.slice(0, 6)}...${chave.slice(-6)}` : chave;

  if (preview.ja_lida) {
    nfceModalBody(`
      <div class="insight-card" style="background:var(--red-soft); border-color:#e3bcae;">
        <div class="ihead" style="color:var(--red);">⚠️ Nota já lida antes</div>
        <p>Essa chave de acesso já tem compras registradas no catálogo (chave ${chaveResumida}). Não é possível processar a mesma nota duas vezes.</p>
      </div>
      <label class="upload-label">
        📷 Tirar foto
        <input type="file" accept="image/*" capture="environment" onchange="onNfceFileSelected(event)">
      </label>
      <label class="upload-label">
        🖼️ Escolher da galeria
        <input type="file" accept="image/*" onchange="onNfceFileSelected(event)">
      </label>
    `);
    return;
  }

  const itensHtml = preview.itens.map((item, i) => {
    const statusTexto = {
      match_exato: "✓ produto já conhecido no catálogo",
      criado_novo: "🆕 novo produto será criado",
      requer_confirmacao: "⚠ produto parecido já existe — confirme abaixo",
    }[item.resolucao_status] || item.resolucao_status;

    let selectHtml = "";
    if (item.resolucao_status === "requer_confirmacao") {
      const options = [`<option value="novo">Criar produto novo</option>`]
        .concat(item.candidatos.map((id) => `<option value="${id}">${produtosMap[id] || "produto #" + id}</option>`));
      selectHtml = `<select class="nfce-item-decisao" onchange="nfceDecisaoChange(${i}, this.value)">${options.join("")}</select>`;
    }

    return `
      <div class="nfce-item-row">
        <div class="nfce-item-top">
          <span>${item.descricao}</span>
          <span class="nfce-item-price">${fmtMoney(item.valor_total)}</span>
        </div>
        <div class="nfce-item-meta">${item.quantidade} ${item.unidade} × ${fmtMoney(item.preco_unitario)} · ${item.categoria_sugerida}</div>
        <div class="nfce-item-status ${item.resolucao_status}">${statusTexto}</div>
        ${selectHtml}
      </div>
    `;
  }).join("");

  nfceModalBody(`
    <div class="nfce-header">
      <b>${preview.estabelecimento_nome_bruto}</b>
      ${fmtDataCurta(preview.data_emissao)} · chave ${chaveResumida}
    </div>
    ${itensHtml}
    <div class="nfce-total">
      <span>Total da nota</span>
      <span>${fmtMoney(preview.valor_total_nota)}</span>
    </div>
    <button class="cta-btn" id="nfce-confirmar-btn" onclick="confirmarNfce()">Confirmar e gravar compras</button>
  `);
}

async function confirmarNfce() {
  const { preview, decisoes } = nfceState;
  const payload = {
    chave_acesso: preview.chave_acesso,
    estabelecimento_nome_bruto: preview.estabelecimento_nome_bruto,
    data_emissao: preview.data_emissao.split("T")[0],
    itens: preview.itens.map((item, i) => ({
      descricao: item.descricao,
      categoria_sugerida: item.categoria_sugerida,
      quantidade: item.quantidade,
      unidade: item.unidade,
      preco_unitario: item.preco_unitario,
      valor_total: item.valor_total,
      resolucao_status: item.resolucao_status,
      produto_id: typeof decisoes[i] === "number" ? decisoes[i] : null,
      candidatos: item.candidatos,
    })),
  };

  try {
    const resultado = await api("/ingestao/nfce/confirmar", { method: "POST", body: JSON.stringify(payload) });
    showToast(`${resultado.compras_criadas} compra(s) registrada(s) com sucesso`);
    closeNfceUpload();
    await carregarCatalogoCategorias();
    await carregarCatalogoProdutos();
    await carregarCatalogoContagem();
    await carregarLista();
    await refreshBadges();
    await carregarStatusSilencioso();
  } catch (e) {
    showToast("Erro ao confirmar: " + e.message);
  }
}

// ---------- LEITURA DE FATURA ----------

let faturaState = null;
let faturaArquivos = [];

function openFaturaUpload() {
  faturaState = null;
  faturaArquivos = [];
  renderFaturaStaging();
  document.getElementById("fatura-modal").classList.add("open");
}
function closeFaturaUpload() {
  document.getElementById("fatura-modal").classList.remove("open");
  faturaState = null;
  faturaArquivos = [];
}
function faturaModalBody(html) {
  document.getElementById("fatura-modal-body").innerHTML = html;
}

// Fatura pode vir em várias fotos (uma por página) tiradas aos poucos com a
// câmera — junta tudo numa lista antes de enviar, em vez de disparar a
// leitura assim que a primeira foto é escolhida. Isso importa porque o
// vencimento (essencial pro cálculo do mês de referência) só aparece na
// página de resumo/capa: se ela não estiver entre as fotos enviadas, a
// leitura falha — e o usuário precisa poder ADICIONAR essa página que faltou
// sem perder as fotos já selecionadas.
function renderFaturaStaging(erro) {
  const thumbsHtml = faturaArquivos.map((file, i) => `
    <div class="fatura-thumb">
      <span>📄 ${file.name}</span>
      <button type="button" onclick="removerFaturaArquivo(${i})">✕</button>
    </div>
  `).join("");

  faturaModalBody(`
    ${erro ? `<p class="nfce-loading">${erro}</p>` : ""}
    ${faturaArquivos.length ? `<div class="fatura-thumbs">${thumbsHtml}</div>` : ""}
    <label class="upload-label">
      📸 ${faturaArquivos.length ? "Adicionar mais fotos" : "Selecionar fotos das páginas da fatura"}
      <input type="file" accept="image/*" multiple onchange="onFaturaArquivosAdicionados(event)">
    </label>
    <button class="cta-btn" onclick="lerFaturaComArquivosSelecionados()" ${faturaArquivos.length === 0 ? "disabled" : ""}>
      Ler fatura (${faturaArquivos.length} foto${faturaArquivos.length === 1 ? "" : "s"})
    </button>
  `);
}

function onFaturaArquivosAdicionados(event) {
  faturaArquivos.push(...Array.from(event.target.files || []));
  renderFaturaStaging();
}

function removerFaturaArquivo(indice) {
  faturaArquivos.splice(indice, 1);
  renderFaturaStaging();
}

async function lerFaturaComArquivosSelecionados() {
  if (!faturaArquivos.length) return;

  faturaModalBody(`<p class="nfce-loading">📸 Lendo a fatura...<br>pode levar até um minuto com muitos lançamentos</p>`);

  try {
    const formData = new FormData();
    for (const file of faturaArquivos) formData.append("paginas", file);
    const resp = await fetch(`${API}/ingestao/fatura`, { method: "POST", body: formData });
    if (!resp.ok) {
      let detail = resp.statusText;
      try { detail = (await resp.json()).detail || detail; } catch (e) {}
      throw new Error(detail);
    }
    const preview = await resp.json();
    faturaState = { preview };
    renderFaturaPreview();
  } catch (e) {
    // Mantém faturaArquivos intacto — se o erro foi "faltou a página de
    // capa", o usuário só precisa adicionar essa foto e tentar de novo,
    // sem perder as que já tinha selecionado.
    renderFaturaStaging(`Não foi possível ler a fatura: ${e.message}`);
  }
}

function renderFaturaPreview() {
  const { preview } = faturaState;

  const itensHtml = preview.lancamentos.map((item) => `
    <div class="fatura-item-row">
      <div class="fatura-item-top">
        <span>${item.estabelecimento}</span>
        <span>${fmtMoney(item.valor)}</span>
      </div>
      <div class="fatura-item-meta">
        ${fmtDataCurta(item.data)} · ${item.categoria}${item.parcela_atual ? ` · parcela ${item.parcela_atual}/${item.total_parcelas}` : ""}
      </div>
    </div>
  `).join("");

  faturaModalBody(`
    <div class="nfce-header">
      <b>${preview.cartao_titular} · final ${preview.cartao_final}</b>
      Vencimento ${fmtDataCurta(preview.vencimento)} · ${preview.lancamentos.length} lançamentos
    </div>
    <div class="fatura-lista">${itensHtml}</div>
    <div class="nfce-total">
      <span>Total da fatura</span>
      <span>${fmtMoney(preview.total_fatura)}</span>
    </div>
    <button class="cta-btn" onclick="confirmarFatura()">Confirmar e gravar lançamentos</button>
  `);
}

async function confirmarFatura() {
  const { preview } = faturaState;
  const payload = {
    mes_referencia: preview.mes_referencia,
    lancamentos: preview.lancamentos,
  };

  try {
    const resultado = await api("/ingestao/fatura/confirmar", { method: "POST", body: JSON.stringify(payload) });
    showToast(`${resultado.lancamentos_criados} lançamento(s) registrado(s) com sucesso`);
    closeFaturaUpload();
    await carregarStatusSilencioso();
    await carregarHistoricoLista();
  } catch (e) {
    showToast("Erro ao confirmar: " + e.message);
  }
}

// ---------- ENVIO DE PRINT DO EXTRATO ----------

let printState = null;

function openPrintUpload() {
  printState = null;
  const hoje = new Date();
  const mesDefault = `${hoje.getFullYear()}-${String(hoje.getMonth() + 1).padStart(2, "0")}`;
  printModalBody(`
    <label style="display:block; font-size:12.5px; color:var(--ink-soft); margin:8px 0 4px 0;">Mês de referência</label>
    <input type="month" id="print-mes-referencia" class="cat-add-input" style="width:100%; margin-bottom:10px;" value="${mesDefault}">
    <label class="upload-label">
      🧾 Selecionar print do extrato
      <input type="file" accept="image/*" onchange="onPrintFileSelected(event)">
    </label>
  `);
  document.getElementById("print-modal").classList.add("open");
}
function closePrintUpload() {
  document.getElementById("print-modal").classList.remove("open");
  printState = null;
}
function printModalBody(html) {
  document.getElementById("print-modal-body").innerHTML = html;
}

async function onPrintFileSelected(event) {
  const file = event.target.files[0];
  if (!file) return;
  const mesReferencia = document.getElementById("print-mes-referencia").value;
  if (!mesReferencia) {
    showToast("Escolha o mês de referência antes de enviar o print");
    return;
  }

  printModalBody(`<p class="nfce-loading">🧾 Lendo o extrato...<br>pode levar um tempinho num print longo</p>`);

  try {
    const formData = new FormData();
    formData.append("imagem", file);
    formData.append("mes_referencia", mesReferencia);
    const resp = await fetch(`${API}/ingestao/print`, { method: "POST", body: formData });
    if (!resp.ok) {
      let detail = resp.statusText;
      try { detail = (await resp.json()).detail || detail; } catch (e) {}
      throw new Error(detail);
    }
    const preview = await resp.json();
    printState = { preview };
    renderPrintPreview();
  } catch (e) {
    printModalBody(`
      <p class="nfce-loading">Não foi possível ler o extrato: ${e.message}</p>
      <label class="upload-label">
        🧾 Tentar outra imagem
        <input type="file" accept="image/*" onchange="onPrintFileSelected(event)">
      </label>
    `);
  }
}

function renderPrintPreview() {
  const { preview } = printState;
  const novos = preview.lancamentos.filter((l) => !l.duplicado);
  const duplicados = preview.lancamentos.filter((l) => l.duplicado);

  const itemHtml = (item) => `
    <div class="fatura-item-row" style="${item.duplicado ? "opacity:.5;" : ""}">
      <div class="fatura-item-top">
        <span>${item.estabelecimento}</span>
        <span>${fmtMoney(item.valor)}</span>
      </div>
      <div class="fatura-item-meta">
        ${fmtDataCurta(item.data)} · ${item.categoria}${item.parcela_atual ? ` · parcela ${item.parcela_atual}/${item.total_parcelas}` : ""}${item.duplicado ? " · já lançado" : ""}
      </div>
    </div>
  `;

  const resumoDuplicados = duplicados.length
    ? `, ${duplicados.length} já lançado${duplicados.length === 1 ? "" : "s"} (ignorado${duplicados.length === 1 ? "" : "s"})`
    : "";

  printModalBody(`
    <div class="nfce-header">
      <b>${mesLabel(preview.mes_referencia)}</b>
      ${novos.length} novo${novos.length === 1 ? "" : "s"}${resumoDuplicados}
    </div>
    <div class="fatura-lista">${preview.lancamentos.map(itemHtml).join("")}</div>
    <button class="cta-btn" onclick="confirmarPrint()" ${novos.length === 0 ? "disabled" : ""}>Confirmar e gravar ${novos.length} lançamento${novos.length === 1 ? "" : "s"}</button>
  `);
}

async function confirmarPrint() {
  const { preview } = printState;
  const novos = preview.lancamentos.filter((l) => !l.duplicado);
  const payload = {
    mes_referencia: preview.mes_referencia,
    lancamentos: novos.map((l) => ({
      data: l.data,
      estabelecimento: l.estabelecimento,
      valor: l.valor,
      categoria: l.categoria,
      parcela_atual: l.parcela_atual,
      total_parcelas: l.total_parcelas,
    })),
  };

  try {
    const resultado = await api("/ingestao/print/confirmar", { method: "POST", body: JSON.stringify(payload) });
    showToast(`${resultado.lancamentos_criados} lançamento(s) registrado(s) com sucesso`);
    closePrintUpload();
    await carregarStatusSilencioso();
    await carregarHistoricoLista();
  } catch (e) {
    showToast("Erro ao confirmar: " + e.message);
  }
}

// ---------- INIT ----------

function sinalizarAmbienteHomologacao() {
  const ehLocalhost = ["localhost", "127.0.0.1"].includes(window.location.hostname);
  document.querySelectorAll(".env-badge").forEach((el) => {
    el.style.display = ehLocalhost ? "inline-block" : "none";
  });
}

async function init() {
  sinalizarAmbienteHomologacao();
  try {
    await carregarStatusAtual();
    await carregarCatalogoCategorias();
    await carregarCatalogoProdutos();
    await carregarCatalogoContagem();
    await carregarLista();
    await refreshBadges();
  } catch (e) {
    showToast("Erro ao carregar dados: " + e.message);
  }
}

document.addEventListener("DOMContentLoaded", init);
