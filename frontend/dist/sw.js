const CACHE = 'shelfloop-8d9c7020be34'
self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const response = await fetch('/precache-manifest.json', { cache: 'no-store' })
    if (!response.ok) throw new Error('Offline manifest unavailable')
    const manifest = await response.json()
    const cache = await caches.open(CACHE)
    await cache.addAll(['/index.html', '/manifest.webmanifest', '/favicon.svg', ...manifest.assets])
    await self.skipWaiting()
  })())
})
self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    const keys = await caches.keys()
    await Promise.all(keys.filter(k => k.startsWith('shelfloop-') && k !== CACHE).map(k => caches.delete(k)))
    await self.clients.claim()
  })())
})
self.addEventListener('fetch', event => {
  const request = event.request
  const url = new URL(request.url)
  if (request.method !== 'GET' || url.origin !== self.location.origin || url.pathname.startsWith('/api')) return
  event.respondWith((async () => {
    const cache = await caches.open(CACHE)
    if (request.mode === 'navigate') {
      try { return await fetch(request) } catch { return (await cache.match('/index.html')) ?? Response.error() }
    }
    return (await cache.match(request)) ?? fetch(request)
  })())
})
