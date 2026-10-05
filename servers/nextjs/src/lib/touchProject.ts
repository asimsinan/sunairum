import { apiFetch } from '@/lib/api'

/** Fire-and-forget: record last_opened_at for library Recents / Continue. */
export function touchProject(projectId: string): void {
  if (!projectId) return
  void apiFetch(`/api/projects/${encodeURIComponent(projectId)}/touch`, {
    method: 'POST',
  }).catch(() => {
    /* non-blocking */
  })
}
