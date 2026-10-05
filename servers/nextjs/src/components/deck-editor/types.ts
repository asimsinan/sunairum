export type SlideInfo = {
  filename: string
  url: string
  html_url?: string
  mtime?: number
}

export type SaveStatus = 'idle' | 'dirty' | 'saving' | 'saved' | 'error'

export type DeckStatus = 'draft' | 'draft_invalid' | 'done' | 'done_with_issues' | string

export type InspectorState = {
  id: string
  tag: string
  x?: number
  y?: number
  width?: number
  height?: number
  fill?: string
  stroke?: string
  opacity?: number
  fontSize?: string
  fontFamily?: string
  fontWeight?: string
  text?: string
  imageHref?: string
}

export type EditorMode = 'refine' | 'edit'

export type HtmlSelection = {
  id: string
  tag: string
  text: string
  positioned: boolean
  hidden: boolean
  zIndex: number
  x: number
  y: number
  width: number
  height: number
  color: string
  background: string
  fontSize: string
  fontFamily: string
  fontWeight: string
  opacity: number
  /** Degrees clockwise; 0 when unrotated. */
  rotation: number
  imageHref?: string
}

export type HtmlLayerItem = {
  id: string
  label: string
  tag: string
  positioned: boolean
  hidden: boolean
  zIndex: number
  /** Nearest ancestor layer id, or null for top-level slide children. */
  parentId: string | null
  /** Nesting depth from the slide root (0 = top-level). */
  depth: number
}

export type HtmlStylePatch = {
  color?: string
  background?: string
  fontSize?: string
  fontFamily?: string
  fontWeight?: string
  opacity?: number
  left?: number
  top?: number
  width?: number
  height?: number
  /** Degrees clockwise. */
  rotation?: number
  hidden?: boolean
}
