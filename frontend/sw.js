const SHELL_URLS = [
  "/",
  "/app.js",
  "/styles.css",
  "/manifest.json",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
];

// O nome do cache carrega a versão do build (contagem de commits, ver
// /api/versao e Dockerfile) — assim cada deploy usa um cache NOVO de
// verdade, e a limpeza em "activate" (que já existia mas nunca disparava,
// porque o nome era uma string fixa) passa a de fato descartar o antigo.
const VERSAO_PROMISE = fetch("/api/versao")
  .then((r) => r.json())
  .then((d) => d.versao)
  .catch(() => "dev");
const NOME_CACHE_PROMISE = VERSAO_PROMISE.then((versao) => `home-bispo-shell-v${versao}`);

self.addEventListener("install", (event) => {
  self.skipWaiting();
  event.waitUntil(NOME_CACHE_PROMISE.then((nome) => caches.open(nome).then((cache) => cache.addAll(SHELL_URLS))));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    NOME_CACHE_PROMISE.then((nomeAtual) =>
      caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== nomeAtual).map((k) => caches.delete(k))))
    )
  );
  self.clients.claim();
});

// Cache mínimo do "shell" (HTML/CSS/JS/ícones) pra abrir na hora — dado de
// verdade (Status/Catálogo/Lista) sempre vem da API, nunca do cache.
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.pathname.startsWith("/api/")) return;
  if (!SHELL_URLS.includes(url.pathname)) return;

  event.respondWith(
    NOME_CACHE_PROMISE.then((nome) =>
      caches.open(nome).then(async (cache) => {
        const cached = await cache.match(event.request);
        const network = fetch(event.request)
          .then((response) => {
            cache.put(event.request, response.clone());
            return response;
          })
          .catch(() => cached);
        return cached || network;
      })
    )
  );
});
