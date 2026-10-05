import { API_URL, apiFetch } from '@/lib/api'
import type { SlideInfo } from './types'

async function readError(res: Response): Promise<string> {
  try {
    const data = await res.json()
    if (typeof data?.detail === 'string') return data.detail
    if (Array.isArray(data?.detail)) return data.detail.map((d: any) => d.msg || String(d)).join('; ')
  } catch {
    /* ignore */
  }
  return res.statusText || 'Request failed'
}

export async function fetchSlides(projectId: string): Promise<SlideInfo[]> {
  const res = await apiFetch(`/api/projects/${projectId}/preview`)
  if (!res.ok) throw new Error(await readError(res))
  const data = await res.json()
  return Array.isArray(data.slides) ? data.slides : []
}

export async function fetchPreviewMeta(
  projectId: string,
): Promise<{
  slides: SlideInfo[]
  mode?: string
  status?: string
  previousReleaseAvailable?: boolean
}> {
  const res = await apiFetch(`/api/projects/${projectId}/preview`)
  if (!res.ok) throw new Error(await readError(res))
  const data = await res.json()
  return {
    slides: Array.isArray(data.slides) ? data.slides : [],
    mode: typeof data.mode === 'string' ? data.mode : undefined,
    status: typeof data.status === 'string' ? data.status : undefined,
    previousReleaseAvailable: data.previous_release_available === true,
  }
}

export async function rebuildDeck(projectId: string) {
  const res = await apiFetch(`/api/projects/${projectId}/rebuild`, { method: 'POST' })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function updateSlideHtml(
  projectId: string,
  filename: string,
  htmlContent: string,
  refreshPreview = true,
): Promise<{
  status: string
  filename: string
  preview_refreshed?: boolean
  layout_valid?: boolean
  layout_advisory?: boolean
  layout_qa?: { hard?: string[]; issues?: string[] }
  previous_release_available?: boolean
}> {
  const res = await apiFetch(`/api/projects/${projectId}/update_html`, {
    method: 'POST',
    body: JSON.stringify({
      filename,
      html_content: htmlContent,
      refresh_preview: refreshPreview,
    }),
  })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function reorderSlides(projectId: string, filenames: string[]) {
  const res = await apiFetch(`/api/projects/${projectId}/slides/reorder`, {
    method: 'POST',
    body: JSON.stringify({ filenames }),
  })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function duplicateSlide(projectId: string, filename: string) {
  const res = await apiFetch(
    `/api/projects/${projectId}/slides/${encodeURIComponent(filename)}/duplicate`,
    { method: 'POST' },
  )
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function deleteSlide(projectId: string, filename: string) {
  const res = await apiFetch(
    `/api/projects/${projectId}/slides/${encodeURIComponent(filename)}`,
    { method: 'DELETE' },
  )
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function uploadImage(projectId: string, file: File) {
  const body = new FormData()
  body.append('file', file)
  const res = await apiFetch(`/api/projects/${projectId}/images`, {
    method: 'POST',
    body,
  })
  if (!res.ok) throw new Error(await readError(res))
  return res.json() as Promise<{ filename: string; path: string; url: string }>
}

export async function generateAiImage(
  projectId: string,
  payload: { prompt: string; aspect_ratio?: string; slide?: number },
) {
  const res = await apiFetch(`/api/projects/${projectId}/images/generate`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw new Error(await readError(res))
  return res.json() as Promise<{ filename: string; path: string; url: string }>
}

export function pptxDownloadUrl(projectId: string) {
  return `${API_URL}/api/download/${projectId}.pptx`
}

export function pdfDownloadUrl(projectId: string) {
  return `${API_URL}/api/download/${projectId}.pdf`
}

export async function editElementAi(
  projectId: string,
  payload: { filename: string; element_id: string; instruction: string; text: string },
): Promise<{ text: string }> {
  const res = await apiFetch(`/api/projects/${projectId}/edit_element`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function regenerateSlide(
  projectId: string,
  slide: number,
  feedback: string,
): Promise<{ status: string; task_id?: string; slide: number; ok?: boolean }> {
  const res = await apiFetch(`/api/projects/${projectId}/generate/regenerate-slide`, {
    method: 'POST',
    body: JSON.stringify({ slide, feedback }),
  })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function fetchRegenerateSlideResult(
  projectId: string,
): Promise<{ ok?: boolean; pending?: boolean; slide?: number; preview_url?: string; html_url?: string; scene_url?: string; ts?: number }> {
  const res = await apiFetch(`/api/projects/${projectId}/generate/regenerate-slide/result`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export type NotesTimingSlide = {
  slide_id: string
  filename?: string
  role?: string
  title?: string
  word_budget?: number
  word_count: number
  estimated_seconds: number
  notes?: string
  warnings?: string[]
}

export type NotesTimingReport = {
  target_duration_minutes: number
  wpm: number
  target_words: number
  actual_words: number
  estimated_seconds_total: number
  estimated_minutes_total?: number
  budget_ok?: boolean
  changed_slides?: number
  mode_used?: string
  orphan_notes_removed?: string[]
  slides: NotesTimingSlide[]
  warnings?: string[]
}

export async function fetchNotesTiming(projectId: string): Promise<NotesTimingReport> {
  const res = await apiFetch(`/api/projects/${projectId}/notes/timing`)
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function fitNotesDuration(
  projectId: string,
  payload: {
    target_duration_minutes?: number
    wpm?: number
    preserve_facts?: boolean
    mode?: 'auto' | 'compress' | 'regenerate'
    backup?: boolean
  },
): Promise<NotesTimingReport> {
  const res = await apiFetch(`/api/projects/${projectId}/notes/fit-duration`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function undoNotesFit(projectId: string): Promise<{ status: string; timing: NotesTimingReport }> {
  const res = await apiFetch(`/api/projects/${projectId}/notes/undo-fit`, { method: 'POST' })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function fetchSlideNotes(
  projectId: string,
  filename: string,
): Promise<{ filename: string; text: string; word_count: number }> {
  const stem = filename.replace(/\.(svg|png|html|json)$/i, '')
  const res = await apiFetch(`/api/projects/${projectId}/notes/${encodeURIComponent(stem)}`)
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function saveSlideNotes(
  projectId: string,
  filename: string,
  text: string,
): Promise<{ filename: string; text: string; timing: NotesTimingReport }> {
  const stem = filename.replace(/\.(svg|png|html|json)$/i, '')
  const res = await apiFetch(`/api/projects/${projectId}/notes/${encodeURIComponent(stem)}`, {
    method: 'PUT',
    body: JSON.stringify({ text }),
  })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}
