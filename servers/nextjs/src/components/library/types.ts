export type LibraryProject = {
  project_id: string
  topic?: string
  display_title?: string
  created_at: number
  last_opened_at?: number | null
  cover_url?: string | null
  slide_count?: number
  has_pdf?: boolean
  has_pptx?: boolean
  pptx_url?: string | null
  pdf_url?: string | null
  status: string
  progress?: number
  slide_current?: number | null
  slide_total?: number | null
  message?: string | null
  message_key?: string | null
  error_message?: string | null
  status_updated_at?: number | null
}

export type LibraryFilter = 'all' | 'ready' | 'draft' | 'failed' | 'generating'
export type LibrarySort = 'last_opened' | 'created'
export type LibraryView = 'grid' | 'list'

export const ACTIVE_STATUSES = [
  'queued',
  'planning',
  'generating',
  'compiling',
  'qa',
  'qa_fixing',
  'rendering',
  'source_uploading',
  'source_parsing',
  'source_grounding',
] as const

export const STATUS_BADGE: Record<string, { labelKey: string }> = {
  pending: { labelKey: 'statusPending' },
  draft: { labelKey: 'statusDraft' },
  draft_invalid: { labelKey: 'statusDraftInvalid' },
  queued: { labelKey: 'statusPending' },
  planning: { labelKey: 'statusPlanning' },
  generating: { labelKey: 'statusGenerating' },
  compiling: { labelKey: 'statusCompiling' },
  qa: { labelKey: 'statusGenerating' },
  qa_fixing: { labelKey: 'statusGenerating' },
  rendering: { labelKey: 'statusCompiling' },
  source_uploading: { labelKey: 'statusSourceParsing' },
  source_parsing: { labelKey: 'statusSourceParsing' },
  source_grounding: { labelKey: 'statusSourceParsing' },
  cancelled: { labelKey: 'statusCancelled' },
  done: { labelKey: 'statusCompleted' },
  // Legacy Job B terminal status. `isReadyStatus` counts it as ready, so
  // without an entry here it fell back to "Pending" — a finished deck
  // labelled as waiting.
  completed: { labelKey: 'statusCompleted' },
  done_with_issues: { labelKey: 'statusDoneWithIssues' },
  error: { labelKey: 'statusFailed' },
  failed: { labelKey: 'statusFailed' },
  source_error: { labelKey: 'statusFailed' },
}

export function projectTitle(proj: LibraryProject, fallback: string): string {
  return (proj.display_title || proj.topic || fallback).trim() || fallback
}

export function isActiveStatus(status: string): boolean {
  return (ACTIVE_STATUSES as readonly string[]).includes(status)
}

export function isReadyStatus(status: string): boolean {
  // "completed" is a legacy Job B terminal status (pre done/done_with_issues).
  return status === 'done' || status === 'done_with_issues' || status === 'completed'
}

export function isDraftStatus(status: string): boolean {
  return status === 'draft' || status === 'draft_invalid' || status === 'pending'
}

export function isFailedStatus(status: string): boolean {
  return (
    status === 'error' ||
    status === 'failed' ||
    status === 'source_error' ||
    status === 'cancelled'
  )
}

export function coverSrc(proj: LibraryProject, apiUrl: string): string | null {
  if (!proj.cover_url) return null
  const bust = proj.last_opened_at || proj.status_updated_at || proj.created_at || 0
  return `${apiUrl}${proj.cover_url}?v=${bust}`
}
