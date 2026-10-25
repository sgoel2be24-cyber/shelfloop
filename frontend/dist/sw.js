/* ShelfLoop service worker.
   - Navigations & index.html: network-first (so deploys land on reload), cache fallback offline.
   - Hashed /assets: cache-first (immutable).
   - /api: network-only. */
const CACHE = 'shelfloop-v2'

self.addEventListener('install', () => {
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys()
      await Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
      await self.clients.claim()
    })(),
  )
})

self.addEventListener('fetch', (event) => {
  const req = event.request
  if (req.method !== 'GET') return
  const url = new URL(req.url)
  if (url.origin !== self.location.origin) return
  if (url.pathname.startsWith('/api')) return // always network

  const isNavigation = req.mode === 'navigate' || url.pathname === '/' || url.pathname === '/index.html'
  const isHashedAsset = url.pathname.startsWith('/assets/')

  if (isNavigation) {
    event.respondWith(
      (async () => {
        try {
          const res = await fetch(req)
          if (res.ok) {
            const cache = await caches.open(CACHE)
            cache.put('/index.html', res.clone()).catch(() => {})
          }
          return res
        } catch {
          const shell = (await caches.match('/index.html')) ?? (await caches.match(req))
          if (shell) return shell
          throw new Error('offline and no shell cached')
        }
      })(),
    )
    return
  }

  event.respondWith(
    (async () => {
      if (isHashedAsset) {
        const cached = await caches.match(req)
        if (cached) return cached
      }
      try {
        const res = await fetch(req)
        if (res.ok && res.type === 'basic' && isHashedAsset) {
          const cache = await caches.open(CACHE)
          cache.put(req, res.clone()).catch(() => {})
        }
        return res
      } catch {
        const cached = await caches.match(req)
        if (cached) return cached
        throw new Error('offline')
      }
    })(),
  )
})
