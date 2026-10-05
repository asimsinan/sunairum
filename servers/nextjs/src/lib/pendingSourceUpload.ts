/** In-memory PDF handoff from home → editor (File cannot live in sessionStorage). */

export type PendingSourceUpload = {
  projectId: string
  file: File
  topic: string
  claimed?: boolean
}

let pending: PendingSourceUpload | null = null

/** One HTTP upload per project — survives React Strict Mode remounts. */
const inflightUploads = new Map<string, Promise<Response>>()

export function setPendingSourceUpload(next: PendingSourceUpload): void {
  pending = { ...next, claimed: false }
}

export function peekPendingSourceUpload(projectId: string): PendingSourceUpload | null {
  if (!pending || pending.projectId !== projectId) return null
  return pending
}

/** Claim bytes for the HTTP upload; keep peekable until `clearPendingSourceUpload`. */
export function claimPendingSourceUpload(
  projectId: string,
): PendingSourceUpload | null {
  if (!pending || pending.projectId !== projectId || pending.claimed) return null
  pending = { ...pending, claimed: true }
  return pending
}

/** React Strict Mode abort — allow the remounted effect to claim again. */
export function releasePendingSourceUploadClaim(projectId: string): void {
  if (!pending || pending.projectId !== projectId || !pending.claimed) return
  pending = { ...pending, claimed: false }
}

export function clearPendingSourceUpload(projectId?: string): void {
  if (!pending) return
  if (projectId && pending.projectId !== projectId) return
  pending = null
}

/**
 * Start an upload or join one already in flight for this project.
 * Prevents Strict Mode double-mount from POSTing upload_source twice
 * (which would enqueue two Docling Celery tasks).
 */
export function startOrJoinSourceUpload(
  projectId: string,
  start: () => Promise<Response>,
): Promise<Response> {
  const existing = inflightUploads.get(projectId)
  if (existing) return existing
  const request = start().finally(() => {
    if (inflightUploads.get(projectId) === request) {
      inflightUploads.delete(projectId)
    }
  })
  inflightUploads.set(projectId, request)
  return request
}
