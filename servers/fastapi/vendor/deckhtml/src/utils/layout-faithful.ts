/**
 * L1 layout-faithful text — contract constants + pure helpers.
 * Browser-side line capture lives inside inspector page.evaluate;
 * Node-side eligibility / freeze decisions live here.
 */

import type { ElementInfo, TextLineBox, TextRun, LayoutFaithfulMode } from '../types';

/** Max relative font shrink allowed inside a frozen box (reported). */
export const LAYOUT_FAITHFUL_MAX_FONT_SHRINK = 0.08;

/** Geometry tolerance in CSS source pixels after EMU round-trip. */
export const LAYOUT_FAITHFUL_GEOM_TOL_PX = 1;

/** Reference slide (matches coordinate.ts). */
export const LAYOUT_FAITHFUL_SLIDE_W_IN = 10;
export const LAYOUT_FAITHFUL_SLIDE_H_IN = 5.625;
export const LAYOUT_FAITHFUL_VIEW_W_PX = 1280;
export const LAYOUT_FAITHFUL_VIEW_H_PX = 720;

export type LayoutFaithfulIneligibility =
  | 'disabled'
  | 'not_text'
  | 'vertical_writing'
  | 'rtl_or_bidi'
  | 'unsupported_transform'
  | 'non_rect_clip'
  | 'pill_path'
  | 'math_or_formula'
  | 'table_or_chart'
  | 'svg_foreign'
  | 'ambiguous_line_map'
  | 'no_lines'
  | 'empty_text';

export function resolveLayoutFaithfulMode(
  option?: LayoutFaithfulMode | true,
  env: NodeJS.ProcessEnv = process.env
): LayoutFaithfulMode {
  if (option === 'strict') return 'strict';
  const raw = String(env.DECKHTML_LAYOUT_FAITHFUL || '').trim().toLowerCase();
  if (raw === 'strict') return 'strict';
  return 'on';
}

export function isLayoutFaithfulStrict(mode: LayoutFaithfulMode): boolean {
  return mode === 'strict';
}

/** Detect CSS writing-mode that is not ordinary horizontal. */
export function isVerticalWritingMode(writingMode?: string): boolean {
  const wm = (writingMode || '').toLowerCase();
  return (
    wm.includes('vertical') ||
    wm.includes('sideways') ||
    wm === 'tb' ||
    wm === 'tb-rl'
  );
}

export function classifyLayoutFaithfulEligibility(
  el: ElementInfo,
  opts: { isPillBox?: boolean } = {}
): { eligible: boolean; reason?: LayoutFaithfulIneligibility } {
  if (el.type !== 'text') return { eligible: false, reason: 'not_text' };
  if (el.svgForeignObjectText || el.svgText) {
    return { eligible: false, reason: 'svg_foreign' };
  }
  if (el.mathml || el.ommlXml) {
    return { eligible: false, reason: 'math_or_formula' };
  }
  if (el.tableData || el.chartPayload || el.tableChrome) {
    return { eligible: false, reason: 'table_or_chart' };
  }
  if (opts.isPillBox || el.circleGlyphBadge) {
    return { eligible: false, reason: 'pill_path' };
  }
  if (isVerticalWritingMode(el.styles?.writingMode)) {
    return { eligible: false, reason: 'vertical_writing' };
  }
  if (el.layoutFaithfulUnsupportedReason) {
    return {
      eligible: false,
      reason: el.layoutFaithfulUnsupportedReason as LayoutFaithfulIneligibility,
    };
  }
  if (!el.layoutLines || el.layoutLines.length === 0) {
    return { eligible: false, reason: 'no_lines' };
  }
  const plain = (el.content || el.richText?.map((r) => r.text).join('') || '').trim();
  if (!plain) return { eligible: false, reason: 'empty_text' };
  if (el.layoutFaithfulAmbiguous) {
    return { eligible: false, reason: 'ambiguous_line_map' };
  }
  return { eligible: true };
}

function condensed(s: string): string {
  return (s || '').replace(/[\s\u00A0\u200B]+/g, '');
}

function condensedLen(s: string): number {
  return condensed(s).length;
}

/**
 * Inject softBreakBefore on rich runs at Chromium wrap boundaries.
 *
 * Whitespace-tolerant: alignment happens in "condensed" space (all whitespace
 * removed) because line capture and rich-text extraction collapse spaces
 * differently. Boundaries land on the first non-space character of each line.
 */
export function applyChromiumSoftBreaks(
  richText: TextRun[] | undefined,
  lines: TextLineBox[] | undefined,
  content?: string
): TextRun[] | undefined {
  void content;
  if (!richText?.length || !lines?.length) return richText;
  if (lines.length <= 1) return richText;

  const joinedCond = condensed(richText.map((r) => r.text).join(''));
  const linesCond = condensed(lines.map((l) => l.text).join(''));
  // Only break when both reconstructions carry the same ink.
  if (!joinedCond || joinedCond !== linesCond) return richText;

  // Condensed offsets where each new line starts (skip line 0).
  const boundaries: number[] = [];
  let acc = 0;
  for (let li = 0; li < lines.length - 1; li++) {
    acc += condensedLen(lines[li].text);
    boundaries.push(acc);
  }
  if (!boundaries.length) return richText;

  const out: TextRun[] = [];
  let cond = 0;
  let bi = 0;
  let pendingBreak = false;

  const pushRun = (base: TextRun, text: string, isFirstPiece: boolean) => {
    if (text === '' && out.length) return;
    const piece: TextRun = {
      ...base,
      text,
      styles: { ...base.styles },
    };
    if (pendingBreak) {
      piece.softBreakBefore = true;
      pendingBreak = false;
    } else if (!isFirstPiece) {
      piece.softBreakBefore = true;
    }
    // breakLine belongs only to the run's final piece — handled by caller.
    delete (piece as any).__last;
    out.push(piece);
  };

  for (const run of richText) {
    let remaining = run.text || '';
    let firstPiece = true;
    const runBreakLine = run.breakLine;

    while (bi < boundaries.length) {
      const target = boundaries[bi];
      const need = target - cond;
      if (need <= 0) {
        // Boundary exactly at the start of this run/piece.
        pendingBreak = true;
        bi++;
        continue;
      }
      // Find split index in `remaining` where condensed count reaches `need`.
      let c = 0;
      let idx = -1;
      for (let i = 0; i < remaining.length; i++) {
        if (!/[\s\u00A0\u200B]/.test(remaining[i])) {
          c++;
          if (c === need) {
            idx = i + 1;
            break;
          }
        }
      }
      if (idx < 0) break; // boundary lies beyond this run

      const left = remaining.slice(0, idx).replace(/[\s\u00A0]+$/, '');
      const right = remaining.slice(idx).replace(/^[\s\u00A0]+/, '');
      const base: TextRun = { ...run };
      delete base.breakLine;
      pushRun(base, left, firstPiece);
      firstPiece = false;
      cond += condensedLen(left);
      remaining = right;
      pendingBreak = true;
      bi++;
    }

    const tailBase: TextRun = { ...run };
    if (runBreakLine) tailBase.breakLine = true;
    else delete tailBase.breakLine;
    pushRun(tailBase, remaining, firstPiece);
    cond += condensedLen(remaining);
  }

  // Paragraph-leading whitespace never renders in HTML — strip from run 1.
  if (out.length && out[0].text) {
    out[0] = { ...out[0], text: out[0].text.replace(/^[\s\u00A0]+/, '') };
  }
  // Sanity: same ink after splitting.
  if (condensed(out.map((r) => r.text).join('')) !== joinedCond) return richText;
  return out;
}

/**
 * Synthesize rich runs directly from captured line boxes when the host has a
 * single style (no richText). Every line becomes one run; lines 2+ carry
 * softBreakBefore so PPTX emits `<a:br/>` exactly at Chromium wrap points.
 */
export function buildRunsFromLines(
  styles: TextRun['styles'],
  lines: TextLineBox[] | undefined,
  content?: string
): TextRun[] | undefined {
  if (!lines || lines.length < 2) return undefined;
  const linesCond = condensed(lines.map((l) => l.text).join(''));
  if (!linesCond) return undefined;
  if (content && condensed(content) !== linesCond) return undefined;
  // HTML never renders whitespace at a line's start or end — strip both.
  return lines.map((l, i) => ({
    text: l.text.replace(/^[\s\u00A0]+/, '').replace(/[\s\u00A0]+$/, ''),
    styles: { ...styles },
    ...(i > 0 ? { softBreakBefore: true } : {}),
  }));
}

/**
 * Line pitch (px) of a captured block: the distance between consecutive line boxes.
 *
 * A captured line's `height` is its glyph box — ascent plus descent — which for most faces is
 * taller than the CSS line box holding it (a 64px Georgia measures ~73px against a 67.8px
 * line-height). Summing those heights therefore claims a three-line heading needs more room
 * than the three-line frame Chromium measured it in, which is impossible; the frozen path
 * answered that phantom overflow by shrinking the font and stretching the pitch, and the text
 * walked out of its box. Consecutive line tops give the pitch the renderer must reproduce.
 */
export function layoutLinePitchPx(lines: TextLineBox[] | undefined): number {
  if (!lines?.length) return 0;
  const steps = lines
    .slice(1)
    .map((line, index) => Number(line.y) - Number(lines[index].y))
    .filter((step) => Number.isFinite(step) && step > 0)
    .sort((left, right) => left - right);
  if (steps.length) return steps[Math.floor(steps.length / 2)];
  const heights = lines
    .map((line) => Number(line.height) || 0)
    .filter((height) => height > 0);
  if (!heights.length) return 0;
  return heights.reduce((sum, height) => sum + height, 0) / heights.length;
}

/** Bound font shrink: return new size (pt) and whether shrink was applied. */
export function boundFontShrink(
  fontSizePt: number,
  needScale: number
): { fontSizePt: number; shrunk: boolean; scale: number } {
  if (!(fontSizePt > 0) || !(needScale < 1)) {
    return { fontSizePt, shrunk: false, scale: 1 };
  }
  const scale = Math.max(1 - LAYOUT_FAITHFUL_MAX_FONT_SHRINK, needScale);
  if (scale >= 0.999) return { fontSizePt, shrunk: false, scale: 1 };
  return {
    fontSizePt: Math.max(8, Math.round(fontSizePt * scale * 100) / 100),
    shrunk: true,
    scale,
  };
}

/** Reconstruct normalized text from layout lines. */
export function reconstructFromLines(lines: TextLineBox[]): string {
  return lines.map((l) => l.text).join('');
}
