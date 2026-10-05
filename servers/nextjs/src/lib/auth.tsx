'use client'

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { apiFetch, apiJson } from '@/lib/api'

export type AuthUser = {
  id: string
  email: string
  display_name: string
  role: string
  status: string
  created_at?: number
  last_login_at?: number | null
  idle_expires_at?: number
  absolute_expires_at?: number
  session_idle_minutes?: number
  session_absolute_hours?: number
}

type AuthContextValue = {
  user: AuthUser | null
  loading: boolean
  login: (email: string, password: string) => Promise<AuthUser>
  logout: () => Promise<void>
  signup: (email: string, password: string, displayName?: string) => Promise<void>
  refreshMe: () => Promise<AuthUser | null>
  updateUser: (patch: Partial<AuthUser>) => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

function detailMessage(detail: unknown, fallback: string): string {
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object') {
    const d = detail as { detail?: unknown; message?: string; code?: string }
    if (typeof d.detail === 'string') return d.detail
    if (d.detail && typeof d.detail === 'object') {
      const nested = d.detail as { message?: string; code?: string }
      if (typeof nested.message === 'string') return nested.message
      if (typeof nested.code === 'string') return nested.code
    }
    if (typeof d.message === 'string') return d.message
  }
  return fallback
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(true)

  const refreshMe = useCallback(async (): Promise<AuthUser | null> => {
    try {
      const data = await apiJson<{ user: AuthUser }>('/api/auth/me', { skipAuthRedirect: true })
      const next = data?.user ?? null
      setUser(next)
      return next
    } catch {
      setUser(null)
      return null
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const data = await apiJson<{ user: AuthUser }>('/api/auth/me', { skipAuthRedirect: true })
        if (!cancelled) setUser(data?.user ?? null)
      } catch {
        if (!cancelled) setUser(null)
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const res = await apiFetch('/api/auth/login', {
      method: 'POST',
      skipAuthRedirect: true,
      body: JSON.stringify({ email, password }),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      throw new Error(detailMessage(data, 'Login failed'))
    }
    const next = data.user as AuthUser
    setUser(next)
    return next
  }, [])

  const signup = useCallback(async (email: string, password: string, displayName = '') => {
    const res = await apiFetch('/api/auth/signup', {
      method: 'POST',
      skipAuthRedirect: true,
      body: JSON.stringify({
        email,
        password,
        display_name: displayName,
      }),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      throw new Error(detailMessage(data, 'Signup failed'))
    }
  }, [])

  const logout = useCallback(async () => {
    try {
      await apiFetch('/api/auth/logout', { method: 'POST', skipAuthRedirect: true })
    } catch {
      /* ignore network errors on logout */
    } finally {
      setUser(null)
    }
  }, [])

  const updateUser = useCallback((patch: Partial<AuthUser>) => {
    setUser((prev) => (prev ? { ...prev, ...patch } : prev))
  }, [])

  const value = useMemo(
    () => ({ user, loading, login, logout, signup, refreshMe, updateUser }),
    [user, loading, login, logout, signup, refreshMe, updateUser],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return ctx
}

export const AUTH_ROUTES = ['/login', '/signup', '/pending', '/rejected'] as const

export function isAuthRoute(pathname: string | null | undefined): boolean {
  if (!pathname) return false
  return AUTH_ROUTES.some((route) => pathname === route || pathname.startsWith(`${route}/`))
}
