import { useEffect, useState } from 'react'
import { listProducts, listShops } from '../api/client'
import type { Lang } from '../i18n'
import type { Product, Shop } from '../api/types'

// Reference data (shops, products) is small and stable within a session;
// cache it so several pages can share one fetch.

let shopsCache: Shop[] | null = null
let shopsPromise: Promise<Shop[]> | null = null

export function fetchShops(): Promise<Shop[]> {
  if (shopsCache) return Promise.resolve(shopsCache)
  if (!shopsPromise) {
    shopsPromise = listShops().then((s) => {
      shopsCache = s
      return s
    })
      .catch((e: unknown) => {
        shopsPromise = null   // never cache a rejected fetch
        throw e
      })
  }
  return shopsPromise
}

export function invalidateShops(): void {
  shopsCache = null
  shopsPromise = null
}

let productsCache: Product[] | null = null
let productsPromise: Promise<Product[]> | null = null

export function fetchProducts(): Promise<Product[]> {
  if (productsCache) return Promise.resolve(productsCache)
  if (!productsPromise) {
    productsPromise = listProducts().then((p) => {
      productsCache = p
      return p
    })
      .catch((e: unknown) => {
        productsPromise = null   // never cache a rejected fetch
        throw e
      })
  }
  return productsPromise
}

export function useShops() {
  const [shops, setShops] = useState<Shop[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    let alive = true
    fetchShops()
      .then((s) => alive && setShops(s))
      .catch((e: unknown) => alive && setError(e instanceof Error ? e.message : String(e)))
    return () => {
      alive = false
    }
  }, [])
  return { shops, error }
}

export function useProducts() {
  const [products, setProducts] = useState<Product[] | null>(null)
  useEffect(() => {
    let alive = true
    fetchProducts()
      .then((p) => alive && setProducts(p))
      .catch(() => alive && setProducts([]))
    return () => {
      alive = false
    }
  }, [])
  return products
}

export function shopLabel(shop: Shop | undefined, id: number, lang: Lang): string {
  if (!shop) return lang === 'hi' ? `दुकान ${id}` : `Shop ${id}`
  return lang === 'hi' && shop.name_hi ? shop.name_hi : shop.name
}

export function productNameFor(products: Product[] | null, id: number): Product | undefined {
  return products?.find((p) => p.id === id)
}
