import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import '@fontsource/baloo-2/400.css'
import '@fontsource/baloo-2/500.css'
import '@fontsource/baloo-2/600.css'
import '@fontsource/baloo-2/700.css'
import '@fontsource/baloo-2/800.css'
import '@fontsource/baloo-2/devanagari-400.css'
import '@fontsource/baloo-2/devanagari-600.css'
import '@fontsource/baloo-2/devanagari-700.css'
import './index.css'
import App from './App'
import { flushOutbox } from './api/outbox'
import { I18nProvider } from './i18n'
import { SessionProvider } from './state/Session'
import { ToastProvider } from './state/Toast'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <I18nProvider>
      <SessionProvider>
        <ToastProvider>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </ToastProvider>
      </SessionProvider>
    </I18nProvider>
  </StrictMode>,
)

// Offline outbox: replay queued capture confirms on load and on `online`.
void flushOutbox()
window.addEventListener('online', () => {
  void flushOutbox()
})

// Service worker (production only so the dev server is never cached):
// cache-first for built assets, network-only for /api.
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {
      // SW is a best-effort enhancement; ignore registration failures
    })
  })
}
