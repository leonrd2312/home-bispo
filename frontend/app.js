const API = "/api";

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").then((registration) => {
      registration.addEventListener("updatefound", () => {
        const novoWorker = registration.installing;
        // "installed" com um controller já ativo = já tinha uma versão
        // rodando antes desta (não é a primeira instalação) -- é aí que faz
        // sentido avisar o usuário, em vez de silenciosamente trocar por
        // baixo e deixar ele sem saber se atualizou.
        novoWorker.addEventListener("statechange", () => {
          if (novoWorker.state === "installed" && navigator.serviceWorker.controller) {
            document.getElementById("update-banner").classList.add("show");
          }
        });
      });
    });
  });
}

fetch(`${API}/versao`)
  .then((r) => r.json())
  .then((d) => {
    const el = document.getElementById("version-badge");
    if (el) el.textContent = `v${d.versao}`;
  })
  .catch(() => {});

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

function nomeLancamento(l) {
  return l.nome_compra || l.estabelecimento;
}

function renderParcelaCard(p, { clicavel = false } = {}) {
  const numero = p._numeroProjetado ?? p.parcela_atual;
  const ultima = p._ultimaProjetada ?? p.ultima;
  const acao = clicavel
    ? `style="cursor:pointer;" onclick="abrirAcoesLancamento(${p.id}, ${attrEscape(p.categoria)}, ${attrEscape(p.estabelecimento)}, ${attrEscape(p.nome_compra)})"`
    : "";
  return `
    <div class="parcela-card ${p.terceiro ? "terceiro-ativo" : (ultima ? "last" : "")}" ${acao}>
      <div class="parcela-top">
        <div>
          <div class="parcela-est">${nomeLancamento(p)}</div>
          ${p.nome_compra ? `<div class="parcela-est-ref">${p.estabelecimento}</div>` : ""}
        </div>
        <span class="parcela-valor">${fmtMoney(p.valor_parcela)}</span>
      </div>
      <div class="parcela-bottom">
        <div style="display:flex; gap:6px; align-items:center;">
          <span class="parcela-tag ${ultima ? "last-tag" : ""}">${ultima ? "última parcela" : "parcela"} · ${numero} de ${p.total_parcelas}</span>
          ${p.terceiro ? `<span class="parcela-tag terceiro-tag">terceiro</span>` : ""}
        </div>
        <span class="parcela-fim">${ultima ? "termina este mês" : "termina " + mesLabelAbrev(p.mes_termino)}</span>
      </div>
      <div class="parcela-track"><div class="parcela-fill" style="width:${(numero / p.total_parcelas * 100).toFixed(1)}%;"></div></div>
    </div>
  `;
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
  // A Lista pode ter sido alterada em outra aba (ex: "+ lista" em Produtos)
  // sem que esta tela tenha recarregado — sempre busca de novo ao entrar.
  if (id === "screen-lista") carregarLista();
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

  document.getElementById("hero-label").textContent = isHistorico
    ? "GASTO TOTAL DO MÊS"
    : `GASTO ATÉ ${data.dia_gasto_ate} DE ${MESES_PT[Number(data.mes_referencia.split("-")[1]) - 1].toUpperCase()}`;
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
    <div class="compare-row" onclick="abrirAcoesLancamento(${l.id}, ${attrEscape(l.categoria)}, ${attrEscape(l.estabelecimento)}, ${attrEscape(l.nome_compra)})" style="cursor:pointer;">
      <div>
        <div class="place">${nomeLancamento(l)}</div>
        <div class="date">${l.nome_compra ? `${l.estabelecimento} · ` : ""}${fmtDataCurta(l.data)}${l.parcela_atual ? ` · ${l.parcela_atual}/${l.total_parcelas}` : ""}${l.categoria && l.categoria !== "Sem categoria" ? ` · ${l.categoria}` : ""}</div>
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
  document.getElementById("parcelas-list").innerHTML = data.parcelas.map((p) => renderParcelaCard(p, { clicavel: true })).join("");

  montarParcelasFuturas(data);

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
    <div class="compare-row" onclick="abrirAcoesLancamento(${l.id}, ${attrEscape(l.categoria)}, ${attrEscape(l.estabelecimento)}, ${attrEscape(l.nome_compra)})" style="cursor:pointer;">
      <div>
        <div class="place">${nomeLancamento(l)}</div>
        <div class="date">${l.nome_compra ? `${l.estabelecimento} · ` : ""}${fmtDataCurta(l.data)}${l.parcela_atual ? ` · ${l.parcela_atual}/${l.total_parcelas}` : ""}</div>
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

let acaoLancamento = { id: null, categoria: null, estabelecimento: null, nomeCompra: null };

function abrirAcoesLancamento(id, categoriaAtual, estabelecimento, nomeCompraAtual) {
  acaoLancamento = { id, categoria: categoriaAtual, estabelecimento, nomeCompra: nomeCompraAtual };
  document.getElementById("lancamento-acoes-sub").textContent = estabelecimento;
  document.getElementById("lancamento-acoes-modal").classList.add("open");
}

function closeLancamentoAcoes() {
  document.getElementById("lancamento-acoes-modal").classList.remove("open");
}

function escolherCategorizar() {
  closeLancamentoAcoes();
  abrirRecategorizar(acaoLancamento.id, acaoLancamento.categoria);
}

function escolherNomearCompra() {
  closeLancamentoAcoes();
  document.getElementById("nomear-compra-sub").textContent = `Nome na fatura: "${acaoLancamento.estabelecimento}"`;
  const input = document.getElementById("nomear-compra-input");
  input.value = acaoLancamento.nomeCompra || "";
  document.getElementById("nomear-compra-modal").classList.add("open");
  input.focus();
}

function closeNomearCompra() {
  document.getElementById("nomear-compra-modal").classList.remove("open");
}

async function salvarNomeCompra() {
  const input = document.getElementById("nomear-compra-input");
  const nome = input.value.trim();
  if (!nome) {
    showToast("Digite um nome pra essa compra");
    return;
  }
  try {
    await api(`/status/lancamentos/${acaoLancamento.id}/nome`, {
      method: "PATCH",
      body: JSON.stringify({ nome_compra: nome }),
    });
    showToast(`Compra nomeada como "${nome}"`);
    closeNomearCompra();
    if (modoHistorico) {
      const data = await api(`/historico/meses/${modoHistorico}`);
      renderStatus(data);
    } else {
      await carregarStatusAtual();
    }
  } catch (e) {
    showToast("Erro ao nomear: " + e.message);
  }
}

function abrirExtratoPorData() {
  const itens = [...ultimoStatusLancamentos].sort((a, b) => new Date(b.data) - new Date(a.data));
  const total = itens.reduce((soma, l) => soma + l.valor, 0);

  document.getElementById("categoria-detalhe-titulo").textContent = "Por data";
  document.getElementById("categoria-detalhe-sub").textContent =
    `${itens.length} ${itens.length === 1 ? "lançamento" : "lançamentos"} · ${fmtMoney(total)}`;
  document.getElementById("categoria-detalhe-lista").innerHTML = itens.map((l) => `
    <div class="compare-row" onclick="abrirAcoesLancamento(${l.id}, ${attrEscape(l.categoria)}, ${attrEscape(l.estabelecimento)}, ${attrEscape(l.nome_compra)})" style="cursor:pointer;">
      <div>
        <div class="place">${nomeLancamento(l)}</div>
        <div class="date">${l.nome_compra ? `${l.estabelecimento} · ` : ""}${fmtDataCurta(l.data)}${l.parcela_atual ? ` · ${l.parcela_atual}/${l.total_parcelas}` : ""} · ${l.categoria}</div>
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
    <div class="compare-row terceiro" onclick="abrirAcoesLancamento(${l.id}, ${attrEscape(l.categoria)}, ${attrEscape(l.estabelecimento)}, ${attrEscape(l.nome_compra)})" style="cursor:pointer;">
      <div>
        <div class="place">${nomeLancamento(l)}</div>
        <div class="date">${l.nome_compra ? `${l.estabelecimento} · ` : ""}${fmtDataCurta(l.data)}${l.parcela_atual ? ` · ${l.parcela_atual}/${l.total_parcelas}` : ""} · ${l.categoria}</div>
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

let parcelasFuturasPorMes = {};

function montarParcelasFuturas(data) {
  const parcelas = data.parcelas;
  const tituloEl = document.getElementById("parcelas-futuras-title");
  const listaEl = document.getElementById("parcelas-futuras-list");
  parcelasFuturasPorMes = {};

  const maxRestante = Math.max(0, ...parcelas.map((p) => p.total_parcelas - p.parcela_atual), 0);
  if (maxRestante === 0) {
    tituloEl.style.display = "none";
    listaEl.innerHTML = "";
    return;
  }

  let html = "";
  let contagemMesAnterior = parcelas.length; // "este mês", base de comparação do primeiro card
  for (let i = 1; i <= maxRestante; i++) {
    const itensDoMes = parcelas
      .filter((p) => p.total_parcelas - p.parcela_atual >= i)
      .map((p) => ({
        ...p,
        _numeroProjetado: p.parcela_atual + i,
        _ultimaProjetada: p.parcela_atual + i === p.total_parcelas,
      }));
    if (itensDoMes.length === 0) continue;

    const mesRef = somarMesesJS(data.mes_referencia, i);
    const totalMes = itensDoMes.reduce((soma, p) => soma + p.valor_parcela, 0);
    parcelasFuturasPorMes[mesRef] = itensDoMes;

    // A contagem só pode cair de um mês pro outro (projeção nunca "ganha"
    // parcela nova) — a diferença é sempre quantas terminaram no mês anterior.
    const finalizaram = contagemMesAnterior - itensDoMes.length;
    contagemMesAnterior = itensDoMes.length;

    html += `
      <div class="hist-card" onclick="abrirParcelasMes('${mesRef}')">
        <div class="hist-top">
          <span class="hist-mes">${mesLabel(mesRef)}</span>
          <span class="hist-valor">${fmtMoney(totalMes)}</span>
        </div>
        <div style="display:flex; justify-content:space-between; align-items:center; gap:8px;">
          <p class="hist-nota" style="margin:0;">${itensDoMes.length} compra${itensDoMes.length === 1 ? "" : "s"} parcelada${itensDoMes.length === 1 ? "" : "s"}</p>
          ${finalizaram > 0 ? `<span class="tag best">-${finalizaram} parcela${finalizaram === 1 ? "" : "s"}</span>` : ""}
        </div>
      </div>
    `;
  }

  tituloEl.style.display = "flex";
  listaEl.innerHTML = html;
}

function abrirParcelasMes(mesRef) {
  const itens = parcelasFuturasPorMes[mesRef] || [];
  document.getElementById("parcelas-mes-titulo").textContent = mesLabel(mesRef);
  document.getElementById("parcelas-mes-sub").textContent =
    `${itens.length} compra${itens.length === 1 ? "" : "s"} parcelada${itens.length === 1 ? "" : "s"}`;
  document.getElementById("parcelas-mes-lista").innerHTML = itens.map((p) => renderParcelaCard(p)).join("");
  document.getElementById("parcelas-mes-modal").classList.add("open");
}

function closeParcelasMes() {
  document.getElementById("parcelas-mes-modal").classList.remove("open");
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
  carregarProdutosDuplicados();
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
  document.getElementById("count-cat-produto").textContent = categoriasProduto.length;
  document.getElementById("cat-manage-list").innerHTML = categoriasProduto.map((c) => `
    <div class="cat-manage-row">
      <span id="catname-${c.id}">${c.nome}</span>
      <div class="cat-manage-actions">
        <button class="edit-btn" aria-label="Renomear ${c.nome}" onclick="editCategoriaProduto(${c.id})">✏️</button>
        <button class="del-btn" aria-label="Remover ${c.nome}" onclick="removeCategory(${c.id})">✕</button>
      </div>
    </div>
  `).join("");
}

function editCategoriaProduto(id) {
  const span = document.getElementById("catname-" + id);
  const nomeAtual = span.textContent;
  const input = document.createElement("input");
  input.className = "cat-add-input";
  input.value = nomeAtual;
  span.replaceWith(input);
  input.focus();
  input.select();

  const save = async () => {
    const novoNome = input.value.trim() || nomeAtual;
    try {
      await api(`/config/categorias/${id}`, { method: "PATCH", body: JSON.stringify({ nome: novoNome }) });
      showToast(`Categoria renomeada para "${novoNome}"`);
    } catch (e) { showToast("Erro: " + e.message); }
    await carregarCategoriasProduto();
    await carregarCatalogoCategorias();
    await carregarCatalogoProdutos();
  };
  input.addEventListener("blur", save);
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") input.blur(); });
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

let categoriasGasto = [];

async function carregarCategoriasGasto() {
  categoriasGasto = await api("/config/categorias?tipo=gasto");
  document.getElementById("count-cat-gasto").textContent = categoriasGasto.length;
  document.getElementById("cat-gasto-manage-list").innerHTML = categoriasGasto.map((c) => `
    <div class="cat-manage-row">
      <span id="catgasto-${c.id}">${c.nome}</span>
      <div class="cat-manage-actions">
        <button class="edit-btn" aria-label="Renomear ${c.nome}" onclick="editCategoriaGasto(${c.id})">✏️</button>
        <button class="del-btn" aria-label="Remover ${c.nome}" onclick="removeCategoriaGasto(${c.id})">✕</button>
      </div>
    </div>
  `).join("");
}

function editCategoriaGasto(id) {
  const span = document.getElementById("catgasto-" + id);
  const nomeAtual = span.textContent;
  const input = document.createElement("input");
  input.className = "cat-add-input";
  input.value = nomeAtual;
  span.replaceWith(input);
  input.focus();
  input.select();

  const save = async () => {
    const novoNome = input.value.trim() || nomeAtual;
    try {
      await api(`/config/categorias/${id}`, { method: "PATCH", body: JSON.stringify({ nome: novoNome }) });
      showToast(`Categoria renomeada para "${novoNome}"`);
    } catch (e) { showToast("Erro: " + e.message); }
    await carregarCategoriasGasto();
    await carregarStatusSilencioso();
  };
  input.addEventListener("blur", save);
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") input.blur(); });
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
  document.getElementById("count-produtos").textContent = produtos.length;
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

let duplicadosGrupos = [];
let produtosParaMesclagemManual = [];

async function carregarProdutosDuplicados() {
  const [grupos, produtos] = await Promise.all([
    api("/config/produtos/duplicados"),
    api("/catalogo/produtos"),
  ]);
  duplicadosGrupos = grupos;
  duplicadosGrupos.forEach((grupo) => { grupo._sobreviventeId = grupo.produtos[0].id; });
  produtosParaMesclagemManual = produtos.slice().sort((a, b) => a.nome_amigavel.localeCompare(b.nome_amigavel, "pt-BR"));

  const totalDuplicados = duplicadosGrupos.reduce((soma, g) => soma + g.produtos.length, 0);
  const contador = document.getElementById("count-produtos-duplicados");
  contador.textContent = totalDuplicados;
  contador.classList.toggle("alert", totalDuplicados > 0);
  renderProdutosDuplicados();
  renderMesclagemManual();
}

function renderProdutosDuplicados() {
  const container = document.getElementById("duplicados-list");
  if (duplicadosGrupos.length === 0) {
    container.innerHTML = `<div class="empty-state"><span class="ic">✅</span><p>Nenhum produto duplicado encontrado.</p></div>`;
    return;
  }
  container.innerHTML = duplicadosGrupos.map((grupo, gi) => {
    const tipoLabel = "🔴 Duplicata idêntica (mesmo nome e quantidade)";
    const itens = grupo.produtos.map((p) => {
      const meta = [
        p.categoria_nome || "sem categoria",
        `${p.total_compras} compra${p.total_compras === 1 ? "" : "s"}`,
        p.ultima_compra_data ? `última ${fmtDataCurta(p.ultima_compra_data)}${p.ultimo_preco != null ? " · " + fmtMoney(p.ultimo_preco) : ""}` : null,
      ].filter(Boolean).join(" · ");
      return `
        <div class="cat-modal-row ${p.id === grupo._sobreviventeId ? "active" : ""}" id="dup-${gi}-${p.id}" onclick="selecionarSobreviventeDuplicado(${gi}, ${p.id})">
          <span><b>${p.nome_amigavel}</b><br><span style="font-size:11px; color:var(--ink-faint); font-weight:400;">${meta}</span></span>
          <span class="check">✓</span>
        </div>
      `;
    }).join("");
    return `
      <div class="produto-manage-row">
        <div class="produto-meta" style="margin-bottom:6px;">${tipoLabel}</div>
        ${itens}
        <button class="cta-btn" style="margin-top:10px;" onclick="confirmarMesclagemDuplicado(${gi})">Mesclar neste</button>
      </div>
    `;
  }).join("");
}

function selecionarSobreviventeDuplicado(grupoIndex, produtoId) {
  const grupo = duplicadosGrupos[grupoIndex];
  grupo._sobreviventeId = produtoId;
  grupo.produtos.forEach((p) => {
    document.getElementById(`dup-${grupoIndex}-${p.id}`).classList.toggle("active", p.id === produtoId);
  });
}

async function confirmarMesclagemDuplicado(grupoIndex) {
  const grupo = duplicadosGrupos[grupoIndex];
  const sobrevivente = grupo.produtos.find((p) => p.id === grupo._sobreviventeId) || grupo.produtos[0];
  const perdedores = grupo.produtos.filter((p) => p.id !== sobrevivente.id).map((p) => p.id);
  const confirmado = window.confirm(
    `Mesclar ${grupo.produtos.length} produtos em "${sobrevivente.nome_amigavel}"?\n\nO histórico de compras dos outros é somado a ele, e eles são removidos. Não pode ser desfeito.`
  );
  if (!confirmado) return;
  try {
    await api("/config/produtos/mesclar", {
      method: "POST",
      body: JSON.stringify({ produto_sobrevivente_id: sobrevivente.id, produto_ids_a_remover: perdedores }),
    });
    showToast(`Mesclado em "${sobrevivente.nome_amigavel}"`);
    await carregarProdutosDuplicados();
    await carregarCatalogoProdutos();
    await carregarCatalogoContagem();
  } catch (e) {
    showToast("Erro ao mesclar: " + e.message);
  }
}

let mesclarManualSobreviventeId = null;

function renderMesclagemManual() {
  const options = produtosParaMesclagemManual.map((p) => `<option value="${p.id}">${p.nome_amigavel}</option>`).join("");
  document.getElementById("mesclar-manual-a").innerHTML = `<option value="">Produto A...</option>${options}`;
  document.getElementById("mesclar-manual-b").innerHTML = `<option value="">Produto B...</option>${options}`;
  mesclarManualSobreviventeId = null;
  atualizarMesclagemManual();
}

function atualizarMesclagemManual() {
  const idA = Number(document.getElementById("mesclar-manual-a").value) || null;
  const idB = Number(document.getElementById("mesclar-manual-b").value) || null;
  const container = document.getElementById("mesclar-manual-sobrevivente");
  const btn = document.getElementById("mesclar-manual-btn");

  if (!idA || !idB || idA === idB) {
    container.innerHTML = idA && idA === idB ? `<p class="sub" style="color:var(--red);">Escolha dois produtos diferentes.</p>` : "";
    btn.disabled = true;
    return;
  }

  const produtoA = produtosParaMesclagemManual.find((p) => p.id === idA);
  const produtoB = produtosParaMesclagemManual.find((p) => p.id === idB);
  if (mesclarManualSobreviventeId !== idA && mesclarManualSobreviventeId !== idB) {
    mesclarManualSobreviventeId = idA;
  }

  const linhaProduto = (p) => `
    <div class="cat-modal-row ${mesclarManualSobreviventeId === p.id ? "active" : ""}" onclick="selecionarSobreviventeManual(${p.id})">
      <span style="display:flex; align-items:center; gap:6px; min-width:0;">
        <span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${p.nome_amigavel}</span>
        ${p.ultima_compra_data ? `<span class="tag last">${fmtDataCurta(p.ultima_compra_data)}</span>` : ""}
      </span>
      <span class="check">✓</span>
    </div>
  `;

  container.innerHTML = `
    <p class="sub" style="margin:10px 0 4px 0;">Qual nome deve continuar?</p>
    ${linhaProduto(produtoA)}
    ${linhaProduto(produtoB)}
  `;
  btn.disabled = false;
}

function selecionarSobreviventeManual(id) {
  mesclarManualSobreviventeId = id;
  atualizarMesclagemManual();
}

async function confirmarMesclagemManual() {
  const idA = Number(document.getElementById("mesclar-manual-a").value) || null;
  const idB = Number(document.getElementById("mesclar-manual-b").value) || null;
  if (!idA || !idB || idA === idB) return;

  const sobreviventeId = mesclarManualSobreviventeId || idA;
  const perdedorId = sobreviventeId === idA ? idB : idA;
  const sobrevivente = produtosParaMesclagemManual.find((p) => p.id === sobreviventeId);

  const confirmado = window.confirm(
    `Mesclar em "${sobrevivente.nome_amigavel}"?\n\nO histórico de compras do outro produto é somado a ele, e ele é removido. Não pode ser desfeito.`
  );
  if (!confirmado) return;

  try {
    await api("/config/produtos/mesclar", {
      method: "POST",
      body: JSON.stringify({ produto_sobrevivente_id: sobreviventeId, produto_ids_a_remover: [perdedorId] }),
    });
    showToast(`Mesclado em "${sobrevivente.nome_amigavel}"`);
    await carregarProdutosDuplicados();
    await carregarCatalogoProdutos();
    await carregarCatalogoContagem();
  } catch (e) {
    showToast("Erro ao mesclar: " + e.message);
  }
}

async function carregarEstabelecimentosConfig() {
  const estabelecimentos = await api("/config/estabelecimentos");
  document.getElementById("count-estabelecimentos").textContent = estabelecimentos.length;
  document.getElementById("estabelecimentos-manage-list").innerHTML = estabelecimentos.map((e) => {
    const nomeExibido = e.nome_amigavel || e.nome_bruto;
    return `
    <div class="produto-manage-row" id="erow-${e.id}">
      <div class="produto-manage-top">
        <span class="produto-nome-display" id="ename-${e.id}">${nomeExibido}</span>
        <div class="produto-edit-actions">
          <button class="produto-edit-btn" aria-label="Renomear ${nomeExibido}" onclick="editEstabelecimentoNome(${e.id}, ${attrEscape(e.nome_bruto)})">✏️</button>
          <button class="produto-edit-btn" aria-label="Categorizar ${nomeExibido}" onclick="abrirEstabelecimentoCategoria(${e.id}, ${attrEscape(e.categoria_gasto_nome)})">🏷️</button>
        </div>
      </div>
      <div class="produto-meta">nome na fatura: "${e.nome_bruto}"</div>
      <div class="produto-meta">categoria: ${e.categoria_gasto_nome || '<span class="uncategorized-tag">não categorizado</span>'}</div>
    </div>`;
  }).join("");
}

function editEstabelecimentoNome(id, nomeBruto) {
  const span = document.getElementById("ename-" + id);
  const input = document.createElement("input");
  input.className = "produto-nome-input";
  input.value = span.textContent.trim();
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

let estabelecimentoCategoriaId = null;

async function abrirEstabelecimentoCategoria(id, categoriaAtualNome) {
  estabelecimentoCategoriaId = id;
  const categorias = await api("/config/categorias?tipo=gasto");
  document.getElementById("estabelecimento-categoria-sub").textContent = categoriaAtualNome
    ? `Categoria atual: ${categoriaAtualNome}`
    : "Ainda não categorizado.";
  document.getElementById("estabelecimento-categoria-lista").innerHTML = categorias.map((c) => `
    <div class="cat-modal-row ${c.nome === categoriaAtualNome ? "active" : ""}" onclick="confirmarEstabelecimentoCategoria(${c.id}, ${attrEscape(c.nome)})">
      <span>${c.nome}</span><span class="check">✓</span>
    </div>
  `).join("");
  document.getElementById("estabelecimento-categoria-modal").classList.add("open");
}

function closeEstabelecimentoCategoria() {
  document.getElementById("estabelecimento-categoria-modal").classList.remove("open");
  estabelecimentoCategoriaId = null;
}

async function confirmarEstabelecimentoCategoria(categoriaId, categoriaNome) {
  const id = estabelecimentoCategoriaId;
  try {
    await api(`/config/estabelecimentos/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ categoria_gasto_id: categoriaId }),
    });
    showToast(`Categorizado como "${categoriaNome}"`);
    closeEstabelecimentoCategoria();
    await carregarEstabelecimentosConfig();
    await carregarStatusSilencioso();
  } catch (e) {
    showToast("Erro ao categorizar: " + e.message);
  }
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
    `Produtos · ${total} cadastrado${total === 1 ? "" : "s"}`;
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
  catalogoBusca = "";
  document.getElementById("catalog-search").value = "";
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
        <div class="prod-top">
          <div class="prod-top-left">
            <p class="prod-name" id="catprod-name-${p.id}">${p.nome_amigavel}</p>
            ${p.categoria ? `<span class="cat-badge">${p.categoria}</span>` : ""}
          </div>
          <div class="produto-edit-actions">
            <button class="produto-edit-btn" aria-label="Excluir ${p.nome_amigavel}" onclick="confirmarExclusaoProduto(${p.id}, ${attrEscape(p.nome_amigavel)}, ${p.total_compras}, ${p.na_lista})">🗑️</button>
            <button class="produto-edit-btn" aria-label="Renomear ${p.nome_amigavel}" onclick="editCatalogoProdutoNome(${p.id})">✏️</button>
            <button class="produto-edit-btn" aria-label="Categorizar ${p.nome_amigavel}" onclick="abrirProdutoCategoria(${p.id}, ${attrEscape(p.nome_amigavel)}, ${attrEscape(p.categoria || "")})">🏷️</button>
          </div>
        </div>
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

async function confirmarExclusaoProduto(id, nome, totalCompras, naLista) {
  const partes = [`${totalCompras} compra${totalCompras === 1 ? "" : "s"} registrada${totalCompras === 1 ? "" : "s"}`];
  if (naLista) partes.push("remove da lista de compras");
  const confirmado = window.confirm(
    `Excluir "${nome}"?\n\nIsso apaga ${partes.join(" e ")}. O estabelecimento onde foi comprado continua cadastrado normalmente. Não pode ser desfeito.`
  );
  if (!confirmado) return;
  try {
    await api(`/config/produtos/${id}`, { method: "DELETE" });
    showToast(`"${nome}" excluído`);
    await carregarCatalogoProdutos();
    await carregarCatalogoContagem();
  } catch (e) {
    showToast("Erro ao excluir: " + e.message);
  }
}

function editCatalogoProdutoNome(id) {
  const span = document.getElementById("catprod-name-" + id);
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
    await carregarCatalogoProdutos();
  };
  input.addEventListener("blur", save);
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") input.blur(); });
}

let catalogoProdutoCategoriaId = null;

function abrirProdutoCategoria(id, nomeProduto, categoriaAtualNome) {
  catalogoProdutoCategoriaId = id;
  document.getElementById("produto-categoria-sub").textContent = categoriaAtualNome
    ? `${nomeProduto} · categoria atual: ${categoriaAtualNome}`
    : `${nomeProduto} · ainda sem categoria`;
  document.getElementById("produto-categoria-lista").innerHTML = catalogoCategorias.map((c) => `
    <div class="cat-modal-row ${c.nome === categoriaAtualNome ? "active" : ""}" onclick="confirmarProdutoCategoria(${c.id}, ${attrEscape(c.nome)})">
      <span>${c.nome}</span><span class="check">✓</span>
    </div>
  `).join("");
  document.getElementById("produto-categoria-modal").classList.add("open");
}

function closeProdutoCategoria() {
  document.getElementById("produto-categoria-modal").classList.remove("open");
  catalogoProdutoCategoriaId = null;
}

async function confirmarProdutoCategoria(categoriaId, categoriaNome) {
  const id = catalogoProdutoCategoriaId;
  try {
    await api(`/config/produtos/${id}`, { method: "PATCH", body: JSON.stringify({ categoria_id: categoriaId }) });
    showToast(`Categorizado como "${categoriaNome}"`);
    closeProdutoCategoria();
    await carregarCatalogoProdutos();
  } catch (e) {
    showToast("Erro ao categorizar: " + e.message);
  }
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

// ---------- MODAL DE QUANTIDADE (Produtos "+ lista" e Lista de compras) ----------

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
    <div class="item-row">
      <div class="checkbox" onclick="marcarComprado(${item.id})"></div>
      <div class="item-body">
        <p class="item-name">${item.nome_amigavel}</p>
        <p class="item-origin">adicionado dia ${fmtDataCurta(item.data_inclusao)}</p>
        <div class="tags">${renderTagsProduto(item)}</div>
      </div>
      <div class="item-qty" onclick="abrirQtyModalParaEditar(${item.id}, ${attrEscape(item.nome_amigavel)}, ${item.quantidade})">${item.quantidade}</div>
    </div>
  `).join("");

  document.getElementById("lista-count").textContent =
    `${itens.length} ${itens.length === 1 ? "item" : "itens"}`;
  const gastoPrevisto = itens.reduce((soma, i) => soma + (i.ultimo_preco ?? i.melhor_preco ?? 0) * i.quantidade, 0);
  document.getElementById("lista-total").textContent = fmtMoney(gastoPrevisto);
}

async function marcarComprado(itemId) {
  try {
    await api(`/lista/${itemId}`, { method: "DELETE" });
    showToast("Comprado! Removido da lista");
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
let printMesReferenciaAtual = null;

function openPrintUpload() {
  printState = null;
  printMesReferenciaAtual = null;
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
  printMesReferenciaAtual = null;
}
function printModalBody(html) {
  document.getElementById("print-modal-body").innerHTML = html;
}

async function onPrintFileSelected(event) {
  const file = event.target.files[0];
  if (!file) return;
  // Na tela de retry ("Tentar outra imagem") o input de mês não existe mais
  // no DOM — cai pro valor já escolhido na primeira tentativa em vez de
  // travar com erro ao ler .value de null.
  const mesInput = document.getElementById("print-mes-referencia");
  const mesReferencia = mesInput ? mesInput.value : printMesReferenciaAtual;
  if (!mesReferencia) {
    showToast("Escolha o mês de referência antes de enviar o print");
    return;
  }
  printMesReferenciaAtual = mesReferencia;

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
  // Lançamentos não-duplicados vêm marcados como incluídos por padrão — o
  // usuário pode desmarcar um específico (ex: compra que não deve ser
  // contabilizada) sem perder a seleção ao marcar/desmarcar outros, por isso
  // o Set de excluídos vive em printState em vez de ser recalculado aqui.
  if (!printState.excluidos) printState.excluidos = new Set();

  const itemHtml = (item, idx) => `
    <div class="fatura-item-row" style="${item.duplicado ? "opacity:.5;" : ""} display:flex; align-items:flex-start; gap:8px;">
      ${item.duplicado ? "" : `<input type="checkbox" style="margin-top:3px;" ${printState.excluidos.has(idx) ? "" : "checked"} onchange="togglePrintItemExcluido(${idx})">`}
      <div style="flex:1;">
        <div class="fatura-item-top">
          <span>${item.estabelecimento}</span>
          <span>${fmtMoney(item.valor)}</span>
        </div>
        <div class="fatura-item-meta">
          ${fmtDataCurta(item.data)} · ${item.categoria}${item.parcela_atual ? ` · parcela ${item.parcela_atual}/${item.total_parcelas}` : ""}${item.duplicado ? " · já lançado" : ""}
        </div>
      </div>
    </div>
  `;

  const duplicados = preview.lancamentos.filter((l) => l.duplicado);
  const selecionados = preview.lancamentos.filter((l, idx) => !l.duplicado && !printState.excluidos.has(idx));

  const resumoDuplicados = duplicados.length
    ? `, ${duplicados.length} já lançado${duplicados.length === 1 ? "" : "s"} (ignorado${duplicados.length === 1 ? "" : "s"})`
    : "";

  printModalBody(`
    <div class="nfce-header">
      <b>${mesLabel(preview.mes_referencia)}</b>
      ${preview.lancamentos.length - duplicados.length} novo${preview.lancamentos.length - duplicados.length === 1 ? "" : "s"}${resumoDuplicados}
    </div>
    <div class="fatura-lista">${preview.lancamentos.map(itemHtml).join("")}</div>
    <button class="cta-btn" onclick="confirmarPrint()" ${selecionados.length === 0 ? "disabled" : ""}>Confirmar e gravar ${selecionados.length} lançamento${selecionados.length === 1 ? "" : "s"}</button>
  `);
}

function togglePrintItemExcluido(idx) {
  if (printState.excluidos.has(idx)) printState.excluidos.delete(idx);
  else printState.excluidos.add(idx);
  renderPrintPreview();
}

async function confirmarPrint() {
  const { preview, excluidos } = printState;
  const selecionados = preview.lancamentos.filter((l, idx) => !l.duplicado && !excluidos.has(idx));
  const payload = {
    mes_referencia: preview.mes_referencia,
    lancamentos: selecionados.map((l) => ({
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
  } finally {
    document.getElementById("loading-overlay").classList.add("hide");
  }
}

document.addEventListener("DOMContentLoaded", init);

let atualizandoApp = false;

async function atualizarApp() {
  if (atualizandoApp) return;
  atualizandoApp = true;
  showToast("Atualizando...");
  try {
    await Promise.all([
      carregarStatusSilencioso(),
      carregarCatalogoCategorias(),
      carregarCatalogoProdutos(),
      carregarCatalogoContagem(),
      carregarLista(),
      refreshBadges(),
    ]);
    showToast("Atualizado");
  } catch (e) {
    showToast("Erro ao atualizar: " + e.message);
  } finally {
    atualizandoApp = false;
  }
}
