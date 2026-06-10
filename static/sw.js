const CACHE_NAME = 'ledgr-v2';
const URLS_TO_CACHE = ['/static/icon-192.png', '/static/icon-512.png'];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(URLS_TO_CACHE))
  );
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', event => {
  // No interceptar requests POST ni rutas de la app
  if (event.request.method !== 'GET') return;
  if (event.request.url.includes('/analizar') ||
      event.request.url.includes('/registro') ||
      event.request.url.includes('/login') ||
      event.request.url.includes('/comparar') ||
      event.request.url.includes('/descargar-pdf') ||
      event.request.url.includes('/tendencias') ||
      event.request.url.includes('/crear-pago')) return;

  event.respondWith(
    fetch(event.request).catch(() => caches.match(event.request))
  );
});