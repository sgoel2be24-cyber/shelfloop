// Token + session persistence, separated so the fetch layer can use it
// without importing React.

import { SESSION_KEY, TOKEN_KEY } from './client'
import type { Role } from './types'

export interface StoredSession {
  token: string
  role: Role
  shopId: number | null
  shopName: string
}

export function storeSession(info: StoredSession): void {
  sessionStorage.setItem(TOKEN_KEY, info.token)
  sessionStorage.setItem(
    SESSION_KEY,
    JSON.stringify({ role: info.role, shop_id: info.shopId, shop_name: info.shopName }),
  )
}

export function getSession(): StoredSession | null {
  const token = sessionStorage.getItem(TOKEN_KEY)
  if (!token) return null
  try {
    const raw = sessionStorage.getItem(SESSION_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as { role?: string; shop_id?: number | null; shop_name?: string }
    if (parsed.role !== 'owner' && parsed.role !== 'operator') return null
    return {
      token,
      role: parsed.role,
      shopId: parsed.shop_id ?? null,
      shopName: parsed.shop_name ?? '',
    }
  } catch {
    return null
  }
}
