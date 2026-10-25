import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'

export type ToastKind = 'ok' | 'err'

interface ToastItem {
  id: number
  msg: string
  kind: ToastKind
}

interface ToastCtx {
  push: (msg: string, kind?: ToastKind) => void
}

const ToastContext = createContext<ToastCtx | null>(null)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const nextId = useRef(1)

  const push = useCallback((msg: string, kind: ToastKind = 'ok') => {
    const id = nextId.current++
    setToasts((ts) => [...ts, { id, msg, kind }])
    window.setTimeout(() => {
      setToasts((ts) => ts.filter((t) => t.id !== id))
    }, 4500)
  }, [])

  const value = useMemo(() => ({ push }), [push])

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 bottom-24 z-50 flex flex-col items-center gap-2 px-4 sm:bottom-8">
        {toasts.map((t) => (
          <div
            key={t.id}
            role="status"
            className={`pointer-events-auto max-w-md rounded-lg px-4 py-3 text-sm font-semibold text-white shadow-lg ${
              t.kind === 'err' ? 'bg-red-600' : 'bg-ink'
            }`}
          >
            {t.msg}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast(): ToastCtx {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used inside ToastProvider')
  return ctx
}
