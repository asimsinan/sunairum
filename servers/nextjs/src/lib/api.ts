/**
 * API origin for browser calls.
 * Empty string = same-origin (Next rewrite locally, Caddy in cloud) so the
 * session cookie is first-party with SameSite=Lax.
 * Setting NEXT_PUBLIC_API_URL restores an absolute cross-origin base (debug only).
 */
const configured = (process.env.NEXT_PUBLIC_API_URL ?? '').trim().replace(/\/+$/, '')

export const API_URL =
  configured || (process.env.NODE_ENV === 'production' ? '' : '')

export const CSRF_HEADER = 'X-Requested-With'
export const CSRF_VALUE = 'sunairum'

type ApiFetchOptions = RequestInit & {
  /** Skip login redirect on 401 (auth pages). */
  skipAuthRedirect?: boolean
}

let lastActivityAt = Date.now()

export function markApiActivity() {
  lastActivityAt = Date.now()
}

export function getLastApiActivityAt() {
  return lastActivityAt
}

export async function apiFetch(path: string, init: ApiFetchOptions = {}): Promise<Response> {
  const { skipAuthRedirect, headers: initHeaders, ...rest } = init
  const headers = new Headers(initHeaders || {})
  const method = (rest.method || 'GET').toUpperCase()
  if (method !== 'GET' && method !== 'HEAD') {
    headers.set(CSRF_HEADER, CSRF_VALUE)
  }
  if (!headers.has('Content-Type') && rest.body && typeof rest.body === 'string') {
    headers.set('Content-Type', 'application/json')
  }
  const url = path.startsWith('http') ? path : `${API_URL}${path.startsWith('/') ? '' : '/'}${path}`
  const res = await fetch(url, {
    ...rest,
    headers,
    credentials: 'include',
  })
  if (res.ok) {
    markApiActivity()
  }
  if (!skipAuthRedirect && (res.status === 401 || res.status === 403)) {
    let code = ''
    try {
      const data = await res.clone().json()
      code = data?.detail?.code || data?.detail || ''
    } catch {
      /* ignore */
    }
    if (
      typeof window !== 'undefined' &&
      !window.location.pathname.startsWith('/login') &&
      !window.location.pathname.startsWith('/signup')
    ) {
      if (code === 'not_approved' || code === 'pending') {
        window.location.href = '/pending'
        return res
      }
      if (code === 'session_expired' || res.status === 401) {
        const reason = code === 'session_expired' ? 'idle' : 'auth'
        window.location.href = `/login?reason=${reason}`
        return res
      }
    }
  }
  return res
}

export async function apiJson<T = unknown>(path: string, init: ApiFetchOptions = {}): Promise<T> {
  const res = await apiFetch(path, init)
  if (!res.ok) {
    let detail: unknown = res.statusText
    try {
      detail = await res.json()
    } catch {
      /* ignore */
    }
    throw Object.assign(new Error('API error'), { status: res.status, detail })
  }
  return res.json() as Promise<T>
}

/** Download a binary API file with session cookies; surfaces JSON error bodies as Error. */
export async function downloadAuthenticatedFile(path: string, filename: string): Promise<void> {
  const res = await apiFetch(path)
  if (!res.ok) {
    let detail = res.statusText
    try {
      const payload = await res.json()
      const raw = payload?.detail ?? payload?.message
      detail = typeof raw === 'string' ? raw : detail
    } catch {
      /* keep statusText */
    }
    throw new Error(detail || `Download failed (${res.status})`)
  }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

export class ExportTransactionError extends Error {
  previousReleaseAvailable: boolean
  previousReleaseUrl?: string

  constructor(message: string, previousReleaseAvailable = false, previousReleaseUrl?: string) {
    super(message)
    this.name = 'ExportTransactionError'
    this.previousReleaseAvailable = previousReleaseAvailable
    this.previousReleaseUrl = previousReleaseUrl
  }
}

/** One canonical export transaction: validate → rebuild → atomically publish → download. */
export async function exportDeckTransaction(
  projectId: string,
  format: 'pptx' | 'pdf' | 'notes-pdf',
  filename: string,
): Promise<void> {
  const res = await apiFetch(`/api/projects/${projectId}/export/${format}`, { method: 'POST' })
  if (!res.ok) {
    let message = `Export failed (${res.status})`
    let previousReleaseAvailable = false
    let previousReleaseUrl: string | undefined
    try {
      const payload = await res.json()
      const detail = payload?.detail
      if (typeof detail === 'string') message = detail
      else if (detail && typeof detail === 'object') {
        message = typeof detail.message === 'string' ? detail.message : message
        previousReleaseAvailable = detail.previous_release_available === true
        previousReleaseUrl =
          typeof detail.previous_release_url === 'string' ? detail.previous_release_url : undefined
      }
    } catch {
      /* keep the HTTP status message */
    }
    throw new ExportTransactionError(message, previousReleaseAvailable, previousReleaseUrl)
  }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
