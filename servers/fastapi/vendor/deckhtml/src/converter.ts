/**
 * Element Converter Module
 * Converts DOM elements to pptxgenjs objects
 */

import PptxGenJSBase from 'pptxgenjs';
import { ElementInfo, TextRun, UsedFontDescriptor } from './types';
import {
  pxToInch,
  pxToInchX,
  pxToInchY,
  pxToPoints,
  pxToSlidePointsY,
  inchToPoints,
  getSlideWidthPx,
  getSlideHeightPx,
  clampPptxTablePositionInch,
  SLIDE_HEIGHT_INCH,
  SLIDE_WIDTH_INCH,
} from './utils/coordinate';
import {
  applyChromiumSoftBreaks,
  buildRunsFromLines,
  classifyLayoutFaithfulEligibility,
  layoutLinePitchPx,
  LAYOUT_FAITHFUL_MAX_FONT_SHRINK,
} from './utils/layout-faithful';
import { prepareChartPayload } from './utils/chart-scale';
import {
  getTextOptions,
  getOoxmlBodyPrVert,
  expandRunTextForInlineHighlightPadding,
  marginLeftPxToLeadingSpaces,
  getFillOptions,
  getLineOptions,
  getTableCellBorderOptions,
  sanitizeTextForXml,
  parseBoxShadow,
  parseBoxShadowClassified,
  parseBorderRadius,
  parseCornerRadii,
  parseBlurFilter,
  parseColor as parseColorUtil,
  parseGradientFull,
  parseLetterSpacing,
  parseBackgroundImageUrl,
  parseBorderStyleToDashType,
  parseTransparency,
  parseTransformRotate,
  ScriptFontFaces,
  parseScriptFontFaces,
  normalizeFontAwesomeFreeFamily,
  normalizeFontAwesomeFamily,
  isBold,
  isItalic,
  fitTextBoxToIntentionalLines,
  fitWrappedTextBox,
  hasVisibleBorder,
  isInlinePillBox,
  isVisibleTextBackgroundColor,
  fitPillBox,
  layoutPillBoxForText,
  parseTextAlign,
} from './utils/style';
import { PlatformFontContext, PlatformFontLang } from './utils/platformFontMap';
import {
  ContainerScriptHints,
  detectContainerScriptHints,
  splitTextByScript,
} from './utils/textScript';
import { StyleEnhancementRegistry } from './enhancer/registry';
import { getMathPresentationMeta } from './utils/omml-style';
import {
  getPlaceholderForMediaType,
  type PlaceholderMediaType,
} from './utils/placeholder-assets';

/**
 * Background is rendered as a separate shape — strip a:highlight from host and per-run options
 * (buildScriptSplitTextPieces / rich-text runs may still carry highlight from getTextOptions).
 */
function stripTextHighlights(textOptions: Record<string, unknown>, textContent: unknown): unknown {
  delete textOptions.highlight;
  if (!Array.isArray(textContent)) return textContent;
  return textContent.map((run) => {
    if (!run || typeof run !== 'object') return run;
    const piece = run as { text?: string; options?: Record<string, unknown> };
    if (!piece.options || piece.options.highlight === undefined) return run;
    const nextOpts = { ...piece.options };
    delete nextOpts.highlight;
    return { ...piece, options: nextOpts };
  });
}

/**
 * Locale-aware uppercasing for `text-transform: uppercase`.
 *
 * CSS casing follows the element's language; JS `toUpperCase()` does not.
 * Turkish maps "i" to "İ" while the language-neutral mapping yields "I", so
 * re-applying the transform in JS silently de-localizes the text Chromium
 * already rendered correctly.  The lang tag is measured per element by the
 * inspector (`styles.lang`) and falls back to language-neutral casing.
 */
function localeUpperCase(value: string, lang?: string): string {
  const tag = String(lang || '').trim();
  if (!tag) return value.toUpperCase();
  try {
    return value.toLocaleUpperCase(tag);
  } catch {
    return value.toUpperCase();
  }
}

type PillPeerRect = { x: number; y: number; w: number; h: number };
type TextBandRect = { x: number; y: number; w: number; h: number };

export class ElementConverter {
  private registry: StyleEnhancementRegistry;
  private fontResolver?: (d: UsedFontDescriptor) => string;
  private platformFontContext?: PlatformFontContext;
  /** HTML-measured pill boxes on the current slide (flex-row collision caps). */
  private pillPeerRects: PillPeerRect[] = [];
  private pillPeerSlideIndex = -1;
  /** Emitted wrapping titles — thin accent bars must not paint through them. */
  private textBands: TextBandRect[] = [];
  /** Thin HTML accent bars (underlines) — title wrap must not spill into them. */
  private accentBands: TextBandRect[] = [];
  /** Large opaque panels — wrapping titles must not grow into them. */
  private columnWalls: TextBandRect[] = [];
  /** Bottom-right page chrome — callouts must not grow into this band. */
  private chromeBands: TextBandRect[] = [];
  private textBandSlideIndex = -1;
  /** One measured shrink factor shared by repeated semantic text peers. */
  private peerTypographyScales = new Map<string, number>();
  /** The same discipline for chips, whose size is settled by the pill path. */
  private pillPeerScales = new Map<string, number>();
  /**
   * Clearance between title ink (incl. serif descenders) and a thin accent rule.
   * 4px was too tight for Georgia/Times — PPT drew the bar through q/g/y.
   */
  private static readonly ACCENT_DESCENDER_CLEAR_PX = 12;
  /** L1 diagnostics from this conversion (fallback / shrink). */
  readonly layoutFaithfulNotes: Array<{
    elementId?: string;
    reason: string;
    message: string;
  }> = [];

  constructor(
    registry: StyleEnhancementRegistry,
    fontResolver?: (d: UsedFontDescriptor) => string,
    platformFontContext?: PlatformFontContext
  ) {
    this.registry = registry;
    this.fontResolver = fontResolver;
    this.platformFontContext = platformFontContext;
  }

  /**
   * Reset per-slide pill peers from measured HTML boxes so early chips cannot
   * grow into later siblings in the same flex row.
   */
  beginSlide(slideIndex: number, elements?: ElementInfo[], slideStartY: number = 0): void {
    if (this.textBandSlideIndex !== slideIndex) {
      this.textBandSlideIndex = slideIndex;
      this.textBands = [];
      this.accentBands = [];
      this.columnWalls = [];
      this.chromeBands = [];
      this.textNeighborRects = [];
      this.peerTypographyScales = this.measurePeerTypographyScales(elements || []);
      if (elements?.length) {
        for (const el of elements) {
          if (el.type !== 'text') continue;
          const rect = {
            x: pxToInchX(el.x),
            y: pxToInchY(el.y - slideStartY),
            w: pxToInchX(el.width),
            h: pxToInchY(el.height),
          };
          this.textNeighborRects.push(rect);
          // Seed text bands from HTML so thin accent shapes nudged below titles
          // even when paint order emits the rule before the title text.
          this.textBands.push(rect);
          if (el.pageChrome) {
            // Inflate slightly so growth clamps leave air around n/N.
            this.chromeBands.push({
              x: Math.max(0, rect.x - pxToInchX(10)),
              y: Math.max(0, rect.y - pxToInchY(8)),
              w: rect.w + pxToInchX(20),
              h: rect.h + pxToInchY(16),
            });
          }
        }
      }
      if (elements?.length) {
        for (const el of elements) {
          if (el.type !== 'shape') continue;
          const hPx = Number(el.height) || 0;
          const wPx = Number(el.width) || 0;
          const hasFill = isVisibleTextBackgroundColor(el.styles?.backgroundColor);
          if (!hasFill) continue;
          const rect = {
            x: pxToInchX(el.x),
            y: pxToInchY(el.y - slideStartY),
            w: pxToInchX(wPx),
            h: pxToInchY(hPx),
          };
          // Thin filled rules / underlines that titles must not spill into.
          if (hPx > 0 && hPx <= 14 && wPx >= 24) {
            this.accentBands.push(rect);
          }
          // Opaque cards / right panels (area ≳ 8000 CSS px).
          if (wPx * hPx >= 8000) {
            this.columnWalls.push(rect);
          }
        }
      }
    }
    if (this.pillPeerSlideIndex === slideIndex && this.pillPeerRects.length > 0) return;
    this.pillPeerSlideIndex = slideIndex;
    this.pillPeerRects = [];
    if (!elements?.length) return;
    for (const el of elements) {
      if (el.type !== 'text') continue;
      const multiLine = Boolean(
        el.richText && el.richText.some((r) => r.softBreakBefore || r.breakLine)
      );
      if (
        !isInlinePillBox(
          el.styles,
          { width: el.width, height: el.height },
          { multiLine }
        )
      ) {
        continue;
      }
      this.pillPeerRects.push({
        x: pxToInchX(el.x),
        y: pxToInchY(el.y - slideStartY),
        w: pxToInchX(el.width),
        h: pxToInchY(el.height),
      });
    }
    this.pillPeerScales = this.measurePillPeerScales(elements, slideStartY);
  }

  /**
   * The size a row of chips will agree on.
   *
   * A chip may only grow into the gap that happens to sit beside it, so the
   * last chip in a row -- with open space to its right -- kept its authored
   * size while its neighbours were squeezed: three chips written identically
   * exported at 8.2pt, 7.0pt and 9.0pt. Each had negotiated alone. This settles
   * the question once for the whole row, before any member is laid out, the way
   * `measurePeerTypographyScales` already does for repeated cards.
   *
   * Runs after `pillPeerRects` is filled, because the answer depends on where
   * the neighbours are.
   */
  private measurePillPeerScales(
    elements: ElementInfo[],
    slideStartY: number
  ): Map<string, number> {
    const groups = new Map<string, Array<{ key: string; scale: number }>>();
    for (const el of elements) {
      if (el.type !== 'text') continue;
      const key = this.semanticPeerKey(el);
      if (!key) continue;
      const scale = this.pillFontScaleFor(el, slideStartY);
      if (scale === undefined) continue;
      const members = groups.get(key) || [];
      members.push({ key, scale });
      groups.set(key, members);
    }
    const result = new Map<string, number>();
    for (const [key, members] of groups) {
      if (members.length < 2) continue;
      const shared = members.reduce((min, m) => Math.min(min, m.scale), 1);
      if (shared >= 0.999) continue;
      result.set(key, shared);
    }
    return result;
  }

  /**
   * What the pill path would do to this element's font, as a factor of the
   * authored size, or undefined when the element is not a chip.
   */
  private pillFontScaleFor(el: ElementInfo, slideStartY: number): number | undefined {
    const text = String(el.content || '').replace(/\s+/g, ' ').trim();
    if (!text) return undefined;
    const shortLabel = text.length <= 28 && text.split(/\s+/).filter(Boolean).length <= 3;
    if (
      !isInlinePillBox(
        el.styles,
        { width: el.width, height: el.height },
        { multiLine: false, shortLabel }
      )
    ) {
      return undefined;
    }
    const authoredPt = pxToPoints(parseFloat(String(el.styles?.fontSize || '0')) || 0);
    if (!(authoredPt > 0)) return undefined;
    const weight = String(el.styles?.fontWeight || '');
    const bold = weight === 'bold' || (Number(weight) || 0) >= 600;
    const mlPt = pxToPoints(parseFloat(String(el.styles?.paddingLeft || '0')) || 0);
    const mrPt = pxToPoints(parseFloat(String(el.styles?.paddingRight || '0')) || 0);
    const xInch = pxToInchX(el.x);
    const yInch = pxToInchY(el.y - slideStartY);
    const wInch = pxToInchX(el.width);
    const hInch = pxToInchY(el.height);
    const laidOut = fitPillBox({
      fontSizePt: authoredPt,
      text,
      xInch,
      yInch,
      wInch,
      hInch,
      marginLeftPt: mlPt,
      marginRightPt: mrPt,
      marginTopPt: 0,
      marginBottomPt: 0,
      bold,
      preferShrinkFont: !shortLabel,
      maxGrowInch: shortLabel ? pxToInchX(80) : pxToInchX(12),
      ...this.pillCollisionBounds(xInch, yInch, wInch, hInch),
    });
    return laidOut.fontSizePt / authoredPt;
  }

  private semanticPeerKey(element: ElementInfo): string | undefined {
    const tag = String(element.tag || '').trim().toLowerCase();
    let role = tag.includes('.') ? tag : '';
    const id = String(element.elementId || '').trim().toLowerCase();
    if (!role && id && !id.startsWith('dh-auto')) {
      const normalized = id.replace(/-(?:\d+)(?=-|$)/g, '-*');
      if (normalized !== id) role = `id:${normalized}`;
    }
    if (!role && id.startsWith('dh-auto')) {
      // A chip row is often bare markup -- <span>koordinat</span> beside
      // <span>slack</span>, or three unclassed <li> in one <ul> -- so its only
      // identity is the structural path the inspector synthesises. Excluding
      // those paths left exactly these elements with no peer group, and each
      // one negotiated its own font size against PowerPoint's metrics: one row
      // of identical chips exported at 6.4pt, 7.9pt and 9.0pt.
      //
      // Only the final index is generalised. Keeping the ancestor path exact
      // means the group is the children of one parent -- real siblings -- and
      // not every <li> on the slide, so one crowded list cannot shrink an
      // unrelated one.
      const siblings = id.replace(/-(\d+)$/, '-*');
      if (siblings !== id) role = `auto:${siblings}`;
    }
    if (!role) return undefined;
    return `${role}|${String(element.styles?.fontSize || '').trim().toLowerCase()}`;
  }

  /**
   * Chromium lays repeated cards as a peer system; PowerPoint must not shrink
   * each card independently. Compute the strictest bounded factor once and
   * reuse it across the semantic group.
   */
  private measurePeerTypographyScales(elements: ElementInfo[]): Map<string, number> {
    const groups = new Map<string, Array<{ element: ElementInfo; scale: number }>>();
    for (const element of elements) {
      if (element.type !== 'text') continue;
      const key = this.semanticPeerKey(element);
      if (!key) continue;
      const lines = element.layoutLines || [];
      const widest = lines.reduce((max, line) => Math.max(max, Number(line.width) || 0), 0);
      const padX =
        (parseFloat(String(element.styles?.paddingLeft || '0')) || 0) +
        (parseFloat(String(element.styles?.paddingRight || '0')) || 0);
      const availableW = Math.max(1, (Number(element.width) || 0) - padX);
      const widthScale = widest > 0
        ? Math.min(1, availableW / (widest * 1.08))
        : 1;
      const neededH = lines.reduce((sum, line) => sum + (Number(line.height) || 0), 0);
      const padY =
        (parseFloat(String(element.styles?.paddingTop || '0')) || 0) +
        (parseFloat(String(element.styles?.paddingBottom || '0')) || 0);
      const availableH = Math.max(1, (Number(element.height) || 0) - padY);
      const heightScale = neededH > 0 ? Math.min(1, availableH / neededH) : 1;
      // Deliberately only the two Chromium-based scales. A PowerPoint-metric
      // estimate looks tempting here, but the deck embeds its fonts, so the
      // estimate is pessimistic: applied to ordinary paragraphs it shrank copy
      // that PowerPoint renders faithfully at full size (9.0pt -> 8.28pt),
      // manufacturing the very mismatch this pass exists to prevent.
      const scale = Math.max(
        1 - LAYOUT_FAITHFUL_MAX_FONT_SHRINK,
        Math.min(widthScale, heightScale)
      );
      const members = groups.get(key) || [];
      members.push({ element, scale });
      groups.set(key, members);
    }
    const result = new Map<string, number>();
    for (const [key, members] of groups) {
      if (members.length < 2) continue;
      const shared = members.reduce((min, member) => Math.min(min, member.scale), 1);
      if (shared >= 0.999) continue;
      for (const member of members) {
        if (member.element.elementId) result.set(member.element.elementId, shared);
      }
    }
    return result;
  }

  private recordTextBand(x: number, y: number, w: number, h: number): void {
    if (!(w > 0) || !(h > 0)) return;
    this.textBands.push({ x, y, w, h });
  }

  /** Top of the first accent bar below this text (overlapping X). */
  private accentCeilingBelow(
    xInch: number,
    yInch: number,
    wInch: number
  ): number | undefined {
    const x1 = xInch;
    const x2 = xInch + wInch;
    const clear = pxToInchY(ElementConverter.ACCENT_DESCENDER_CLEAR_PX);
    let best: number | undefined;
    for (const b of this.accentBands) {
      const overlapsX = !(b.x + b.w < x1 + 0.02 || b.x > x2 - 0.02);
      if (!overlapsX) continue;
      if (b.y <= yInch + 0.01) continue;
      // Leave descender air above the rule.
      const ceiling = Math.max(yInch + 0.05, b.y - clear);
      best = best === undefined ? ceiling : Math.min(best, ceiling);
    }
    return best;
  }

  /** Horizontal walls from opaque panels overlapping this text band in Y. */
  private columnWallsBeside(
    xInch: number,
    yInch: number,
    wInch: number,
    hInch: number
  ): { minLeftInch?: number; maxRightInch?: number } {
    const y1 = yInch;
    const y2 = yInch + hInch;
    const selfRight = xInch + wInch;
    const gap = pxToInchX(8);
    let minLeft: number | undefined;
    let maxRight: number | undefined;
    for (const wall of this.columnWalls) {
      const overlapsY = !(wall.y + wall.h < y1 + 0.02 || wall.y > y2 - 0.02);
      if (!overlapsY) continue;
      // Skip walls that are essentially this box (same origin/size).
      if (Math.abs(wall.x - xInch) < 0.05 && Math.abs(wall.w - wInch) < 0.05) continue;
      const wallRight = wall.x + wall.w;
      const wallLeft = wall.x;
      if (wallRight <= xInch + 0.08) {
        minLeft = Math.max(minLeft ?? 0, wallRight + gap);
      } else if (wallLeft >= selfRight - 0.08) {
        maxRight = Math.min(maxRight ?? Number.POSITIVE_INFINITY, wallLeft - gap);
      } else if (wallLeft > xInch + 0.12) {
        // Already overlapping a later panel — clip to its left edge.
        maxRight = Math.min(maxRight ?? Number.POSITIVE_INFINITY, wallLeft - gap);
      }
    }
    return {
      ...(minLeft !== undefined ? { minLeftInch: minLeft } : {}),
      ...(maxRight !== undefined && Number.isFinite(maxRight)
        ? { maxRightInch: maxRight }
        : {}),
    };
  }

  /** Push thin accent bars below overlapping title text bottoms. */
  private nudgeAccentBelowTitles(options: {
    x: number;
    y: number;
    w: number;
    h: number;
  }): void {
    const h = Number(options.h) || 0;
    // Decorative rules / underlines (~≤14 CSS px).
    if (!(h > 0) || h > pxToInchY(14)) return;
    const x = Number(options.x) || 0;
    const y = Number(options.y) || 0;
    const w = Number(options.w) || 0;
    const clear = pxToInchY(ElementConverter.ACCENT_DESCENDER_CLEAR_PX);
    let targetY = y;
    for (const b of this.textBands) {
      const overlapsX = !(b.x + b.w < x + 0.02 || b.x > x + w - 0.02);
      if (!overlapsX) continue;
      const textBottom = b.y + b.h;
      // Accent sits on / through the title band (incl. descender zone).
      if (y + h >= b.y - 0.02 && y <= textBottom + clear) {
        targetY = Math.max(targetY, textBottom + clear);
      }
    }
    if (targetY > y + 1e-4) {
      options.y = Math.min(targetY, SLIDE_HEIGHT_INCH - h);
    }
  }

  /** All measured HTML text rects on the current slide (drift headroom walls). */
  private textNeighborRects: PillPeerRect[] = [];

  /**
   * Rightmost edge a frozen text box may grow to without touching another
   * frozen text box or opaque panel that overlaps it vertically.
   */
  private layoutDriftRightLimit(
    xInch: number,
    yInch: number,
    wInch: number,
    hInch: number
  ): number {
    let limit = SLIDE_WIDTH_INCH - 0.05;
    const y1 = yInch;
    const y2 = yInch + hInch;
    const selfRight = xInch + wInch;
    const gap = pxToInchX(8);
    for (const r of [...this.textNeighborRects, ...this.columnWalls, ...this.chromeBands]) {
      const overlapsY = !(r.y + r.h < y1 + 0.02 || r.y > y2 - 0.02);
      if (!overlapsY) continue;
      // Skip self / near-identical measured box.
      if (Math.abs(r.x - xInch) < 0.03 && Math.abs(r.w - wInch) < 0.03) continue;
      if (r.x >= selfRight - 0.02) limit = Math.min(limit, r.x - gap);
    }
    return Math.max(limit, selfRight);
  }

  /** Top of the first page-chrome band below this box (overlapping X). */
  private chromeCeilingBelow(
    xInch: number,
    yInch: number,
    wInch: number
  ): number | undefined {
    const x1 = xInch;
    const x2 = xInch + wInch;
    const gap = pxToInchY(6);
    let best: number | undefined;
    for (const b of this.chromeBands) {
      const overlapsX = !(b.x + b.w < x1 + 0.02 || b.x > x2 - 0.02);
      if (!overlapsX) continue;
      if (b.y <= yInch + 0.01) continue;
      const ceiling = Math.max(yInch + 0.05, b.y - gap);
      best = best === undefined ? ceiling : Math.min(best, ceiling);
    }
    return best;
  }

  /** Clamp a fitted box so it does not cover page chrome. */
  private clampBoxAwayFromChrome(box: {
    x: number;
    y: number;
    w: number;
    h: number;
  }): void {
    if (!this.chromeBands.length) return;
    const gap = pxToInchY(6);
    const gapX = pxToInchX(8);
    for (const c of this.chromeBands) {
      const overlapsX = !(box.x + box.w < c.x + 0.02 || box.x > c.x + c.w - 0.02);
      const overlapsY = !(box.y + box.h < c.y + 0.02 || box.y > c.y + c.h - 0.02);
      if (!overlapsX || !overlapsY) continue;
      // Prefer trimming height so the callout sits above n/N.
      const maxH = Math.max(0.15, c.y - gap - box.y);
      if (maxH < box.h) box.h = maxH;
      // If still overlapping horizontally at the bottom band, trim width.
      if (box.y + box.h > c.y - gap + 0.01 && box.x + box.w > c.x) {
        box.w = Math.max(0.4, Math.min(box.w, c.x - gapX - box.x));
      }
    }
  }

  /**
   * O27: native charts paint the full host AABB. When body copy overlaps the
   * chart host (absolute bottom inset), push the chart below the text band.
   */
  private clampChartAwayFromTextBands(box: {
    x: number;
    y: number;
    w: number;
    h: number;
  }): void {
    if (!this.textBands.length) return;
    const gap = pxToInchY(10);
    const minH = pxToInchY(48);
    const origBottom = box.y + box.h;
    let top = box.y;
    for (const t of this.textBands) {
      const overlapsX = !(t.x + t.w <= box.x + 0.02 || t.x >= box.x + box.w - 0.02);
      if (!overlapsX) continue;
      const textBottom = t.y + t.h;
      const chartMid = box.y + box.h * 0.5;
      // Text that intrudes into the upper half of the chart host.
      if (textBottom > box.y + 0.02 && t.y < chartMid) {
        top = Math.max(top, textBottom + gap);
      }
    }
    if (top <= box.y + 0.01) return;
    // Stay inside the original host bottom; shrink height rather than spill.
    const maxTop = Math.max(box.y, origBottom - minH);
    box.y = Math.min(top, maxTop);
    box.h = Math.max(minH, origBottom - box.y);
    if (box.y + box.h > SLIDE_HEIGHT_INCH - 0.05) {
      box.h = Math.max(minH * 0.75, SLIDE_HEIGHT_INCH - 0.05 - box.y);
    }
  }

  private pillCollisionBounds(
    xInch: number,
    yInch: number,
    wInch: number,
    hInch: number
  ): { minLeftInch?: number; maxRightInch?: number } {
    const yMid = yInch + hInch / 2;
    // Text neighbours count too. This used to see pill peers only, so a
    // right-aligned label needing 42px more width grew *leftward* straight
    // through the text box beside it — the export introduced an overlap the
    // HTML did not have, which is the one thing a faithful conversion must
    // never do. `roomLeft` defaults to the slide edge when no bound is given,
    // so an unbounded grow has nothing to stop it.
    const neighbours = [
      ...this.pillPeerRects,
      ...this.textNeighborRects,
      ...this.columnWalls,
    ];
    const peers = neighbours.filter(
      (p) => yMid >= p.y - 0.02 && yMid <= p.y + p.h + 0.02
    );
    let minLeft: number | undefined;
    let maxRight: number | undefined;
    const gap = pxToInchX(4);
    const selfRight = xInch + wInch;
    for (const p of peers) {
      const pRight = p.x + p.w;
      const pLeft = p.x;
      // Skip self / near-identical measured box.
      if (Math.abs(p.x - xInch) < 1e-4 && Math.abs(p.w - wInch) < 1e-4) continue;
      if (pRight <= xInch + 0.02) {
        minLeft = Math.max(minLeft ?? 0, pRight + gap);
      } else if (pLeft >= selfRight - 0.02) {
        maxRight = Math.min(maxRight ?? Number.POSITIVE_INFINITY, pLeft - gap);
      }
    }
    return {
      ...(minLeft !== undefined ? { minLeftInch: minLeft } : {}),
      ...(maxRight !== undefined && Number.isFinite(maxRight)
        ? { maxRightInch: maxRight }
        : {}),
    };
  }

  /** Resolve script faces with Bold/Italic suffix only when registry has exact match */
  private resolveScriptFontFaces(
    styles: {
      fontFamily?: string;
      fontFamilySpecified?: string;
      fontWeight?: string;
      fontStyle?: string;
    },
    textScript: PlatformFontLang = 'latin'
  ): ScriptFontFaces | undefined {
    if (!styles?.fontFamily) return undefined;
    const faFreeFace = normalizeFontAwesomeFreeFamily(
      styles.fontFamily,
      styles.fontWeight?.toString()
    );
    if (faFreeFace) {
      const latin = this.fontResolver
        ? this.fontResolver({
            fontFamily: faFreeFace,
            bold: false,
            italic: isItalic(styles.fontStyle),
          })
        : faFreeFace;
      return { latin, ea: latin, cs: 'Arial' };
    }
    const faFace = normalizeFontAwesomeFamily(styles.fontFamily, styles.fontWeight?.toString());
    if (faFace) {
      const latin = this.fontResolver
        ? this.fontResolver({
            fontFamily: faFace,
            bold: false,
            italic: isItalic(styles.fontStyle),
          })
        : faFace;
      return { latin, ea: latin, cs: 'Arial' };
    }

    const faces = parseScriptFontFaces(styles.fontFamily, {
      platformFontContext: this.platformFontContext,
      specifiedFontFamily: styles.fontFamilySpecified,
      textScript,
    });
    if (!this.fontResolver) return faces;

    const bold = isBold(styles.fontWeight);
    const italic = isItalic(styles.fontStyle);
    const latinResolved = this.fontResolver({
      fontFamily: faces.latin,
      bold,
      italic,
    });
    const eaResolved =
      faces.ea === faces.latin
        ? latinResolved
        : this.fontResolver({
            fontFamily: faces.ea,
            bold,
            italic,
          });
    return { latin: latinResolved, ea: eaResolved, cs: faces.cs };
  }

  private getContainerText(element: ElementInfo): string {
    if (element.richText?.length) {
      return element.richText.map((run) => run.text).join('');
    }
    return element.content ?? '';
  }

  private splitTextRunByScript(run: TextRun, hints: ContainerScriptHints): TextRun[] {
    const segments = splitTextByScript(run.text, hints);
    if (segments.length <= 1) {
      return [{ ...run, textScript: segments[0]?.script ?? 'latin' }];
    }
    return segments.map((seg, index) => ({
      ...run,
      text: seg.text,
      textScript: seg.script,
      softBreakBefore: run.softBreakBefore && index === 0,
      breakLine: run.breakLine && index === segments.length - 1,
    }));
  }

  private buildScriptSplitTextPieces(
    text: string,
    styles: ElementInfo['styles'],
    baseOptions: Record<string, unknown>,
    hints: ContainerScriptHints
  ): Array<{ text: string; options: Record<string, unknown> }> | string {
    const segments = splitTextByScript(text, hints);
    if (segments.length <= 1) return text;

    return segments.map((seg) => {
      const pieceOptions = getTextOptions(styles, this.platformFontContext, seg.text);
      const faces = this.resolveScriptFontFaces(styles, seg.script);
      if (faces !== undefined) {
        pieceOptions.fontFace = faces.latin;
      } else if (baseOptions.fontFace) {
        pieceOptions.fontFace = baseOptions.fontFace;
      }
      return { text: seg.text, options: pieceOptions };
    });
  }

  /**
   * Convert element to pptxgenjs object properties
   * Returns an array of converted elements (main element + any border decorations)
   */
  convertElement(
    element: ElementInfo,
    slideStartY: number = 0,
    slideIndex: number = 0,
    elementIndex: number = 0
  ): any[] {
    this.beginSlide(slideIndex);
    const baseProps = this.getBaseProperties(element, slideStartY);
    const results: any[] = [];

    // Detect gradient for registration
    const gradientData = parseGradientFull(element.styles.backgroundImage, element, element.styles.backgroundSize);

    let mainElement: any = null;

    switch (element.type) {
      case 'text':
        mainElement = this.convertTextElement(element, baseProps);
        break;
      case 'icon':
        mainElement = this.convertIconElement(element, baseProps);
        break;
      case 'image':
        mainElement = this.convertImageElement(element, baseProps);
        break;
      case 'video':
        mainElement = this.convertMediaPlaceholderElement(element, baseProps, 'video');
        break;
      case 'audio':
        mainElement = this.convertMediaPlaceholderElement(element, baseProps, 'audio');
        break;
      case 'canvas':
        mainElement = this.convertCanvasElement(element, baseProps);
        break;
      case 'iframe':
        // Placeholders are resolved in the inspector; defensive no-op.
        return [];
      case 'svg':
        mainElement = this.convertImageElement(element, baseProps);
        break;
      case 'math':
        mainElement = this.convertMathElement(element, baseProps);
        break;
      case 'table':
        mainElement = this.convertTableElement(element, baseProps);
        break;
      case 'chart':
        mainElement = this.convertChartElement(element, baseProps);
        break;
      case 'shape':
        // Check for full-slide background with image + gradient overlay (e.g. slide-container)
        const imageUrl = parseBackgroundImageUrl(element.styles.backgroundImage);
        const isFullSlide =
          slideStartY === 0 &&
          element.width >= getSlideWidthPx() * 0.9 &&
          element.height >= getSlideHeightPx() * 0.9;
        if (imageUrl && gradientData && isFullSlide) {
          mainElement = {
            type: 'slideBackgroundWithGradient',
            options: { ...baseProps, path: imageUrl },
            _gradientData: gradientData,
            _sourceElement: element,
          };
        } else {
          mainElement = this.convertShapeElement(
            element,
            baseProps,
            slideIndex,
            elementIndex,
            slideStartY
          );
        }
        break;
      default:
        return [];
    }

    if (mainElement) {
      // Handle both single element and array of elements (e.g., rounded background + text)
      if (Array.isArray(mainElement)) {
        results.push(...mainElement);
      } else {
        results.push(mainElement);
      }
    }

    // Add border decorations (single-side borders only)
    // Skip for images - pic element handles its own shape (roundRect etc.), no extra border shapes
    const borderType = this.getBorderType(element.styles);
    if (borderType === 'single' && element.type !== 'image') {
      // Use the emitted fill/text box when rounded-path fit moved geometry — otherwise the
      // left accent bar stays at the HTML origin while text drifts left of the plate (O23).
      const decoBase = this.resolveBorderDecorationBase(results, baseProps);
      const borderDecorations = this.createBorderDecorations(element, decoBase);
      results.push(...borderDecorations);
    }

    // Attach gradient metadata to the element that has the fill
    // The generator will register it with the correct index when adding to slide
    if (gradientData && results.length > 0) {
      // CSS allows layered backgrounds: background-color (base) + multiple gradients/images on top.
      // Our XML enhancer can only replace ONE <a:solidFill> with ONE <a:gradFill>.
      // When authors use "solid base + overlay gradients" (like bg-primary-pattern),
      // applying gradient enhancement would erase the base color entirely.
      const bgColor = parseColorUtil(element.styles.backgroundColor);
      const bgImg = String(element.styles.backgroundImage || '');
      const hasVisibleBgColor = !!bgColor;
      const hasLayeredBackgrounds = bgImg.includes(','); // multiple backgrounds separated by commas
      if (hasVisibleBgColor && hasLayeredBackgrounds) {
        return results;
      }

      let fillElementIndex = results.findIndex((el: any) => el?._prefersGradient);
      if (fillElementIndex < 0) {
        fillElementIndex = results.findIndex(
          (el: any) => el?.options && el.options.fill
        );
      }
      if (fillElementIndex < 0) {
        fillElementIndex = results.findIndex(
          (el: any) =>
            el.type === 'rect' ||
            el.type === 'roundRect' ||
            el.type === 'ellipse' ||
            el.type === 'shape'
        );
      }
      if (fillElementIndex >= 0) {
        results[fillElementIndex]._gradientData = gradientData;
        results[fillElementIndex]._sourceElement = element;
      }
    }

    return results;
  }

  /**
   * Get base properties (position, size, and rotation from CSS transform)
   */
  private getBaseProperties(element: ElementInfo, slideStartY: number): any {
    // HTML slides often use overflow:hidden; Playwright still reports boxes that
    // spill past the canvas. Clamp so PPTX shapes never paint outside the slide.
    let x = element.x;
    let y = element.y - slideStartY;
    let w = element.width;
    let h = element.height;
    const maxW = getSlideWidthPx();
    const maxH = getSlideHeightPx();
    if (x < 0) {
      w += x;
      x = 0;
    }
    if (y < 0) {
      h += y;
      y = 0;
    }
    if (x + w > maxW) w = Math.max(1, maxW - x);
    if (y + h > maxH) h = Math.max(1, maxH - y);
    const clip = element.overflowClipRect;
    if (clip && clip.width > 0 && clip.height > 0) {
      const cx = clip.x;
      const cy = clip.y - slideStartY;
      const x2 = Math.min(x + w, cx + clip.width);
      const y2 = Math.min(y + h, cy + clip.height);
      x = Math.max(x, cx);
      y = Math.max(y, cy);
      w = Math.max(1, x2 - x);
      h = Math.max(1, y2 - y);
    }
    w = Math.max(1, w);
    h = Math.max(1, h);

    const base: any = {
      x: pxToInchX(x),
      y: pxToInchY(y),
      w: pxToInchX(w),
      h: pxToInchY(h),
    };
    const rotate = parseTransformRotate(element.styles?.transform);
    if (rotate !== undefined) {
      base.rotate = rotate;
    }
    return base;
  }

  /**
   * Placeholder text box for OMML equation injection (Phase 2 XML).
   */
  private convertMathElement(element: ElementInfo, baseProps: any): any | null {
    if (!element.ommlXml) {
      return null;
    }
    const presentation = getMathPresentationMeta(element);
    const w =
      element.width < 20 ? pxToInch(Math.max(element.width, element.height * 2, 48)) : baseProps.w;
    const h =
      element.height < 12 ? pxToInch(Math.max(element.height, 20)) : baseProps.h;
    // Prefer host fill (formula plate) when layout host carried a background.
    const fill = getFillOptions(element.styles, element);
    const hasFill =
      fill &&
      fill.fill &&
      fill.fill.type !== 'none' &&
      fill.fill.color;
    const radius = parseFloat(String(element.styles?.borderRadius || '0')) || 0;
    // Keep OMML off the plate edge (CSS padding → pptxgen margin [l,r,b,t]).
    const padL = parseFloat(String(element.styles?.paddingLeft || '0')) || 0;
    const padR = parseFloat(String(element.styles?.paddingRight || '0')) || 0;
    const padT = parseFloat(String(element.styles?.paddingTop || '0')) || 0;
    const padB = parseFloat(String(element.styles?.paddingBottom || '0')) || 0;
    const airPx = Math.max(6, (Number(element.height) || 0) * 0.06);
    const margin = [
      pxToPoints(Math.max(padL, 8)),
      pxToPoints(Math.max(padR, 8)),
      pxToPoints(Math.max(padB, airPx)),
      pxToPoints(Math.max(padT, airPx)),
    ];
    return {
      type: 'text',
      text: '\u200B',
      options: {
        ...baseProps,
        w,
        h,
        margin,
        fill: hasFill ? fill.fill : { type: 'none' },
        line: { type: 'none' },
        valign: 'middle',
        align: presentation.mathJc === 'left' ? 'left' : presentation.mathJc === 'right' ? 'right' : 'center',
        ...(radius > 0 ? { shape: 'roundRect', rectRadius: pxToInch(Math.min(radius, element.height / 2)) } : {}),
      },
      _equationOmml: element.ommlXml,
      _mathDisplayMode: element.mathDisplayMode ?? 'inline',
      _mathJc: presentation.mathJc,
      _mathColorHex: presentation.colorHex,
      _mathSzHalfPt: presentation.szHalfPt,
      _mathFallbackText: element.mathFallbackText,
      _sourceElement: element,
    };
  }

  /**
   * Get line options for the "common" sides when one side is special
   * Returns style from the majority (top/right/bottom when left is special)
   * Returns undefined when only one side has border (no common)
   */
  private getCommonLineOptions(_styles: any): { color: string; width: number; dashType?: string; transparency?: number } | undefined {
    // pptxgenjs applies line to all four sides of a shape; partial borders use strip decorations only.
    return undefined;
  }

  /**
   * Determine border type: uniform (4 sides equal), single (some sides), none
   */
  private getBorderType(styles: any): 'uniform' | 'single' | 'none' {
    const parseBorderWidth = (width: string | undefined): number => {
      if (!width) return 0;
      return parseFloat(width) || 0;
    };

    const leftWidth = parseBorderWidth(styles.borderLeftWidth);
    const rightWidth = parseBorderWidth(styles.borderRightWidth);
    const topWidth = parseBorderWidth(styles.borderTopWidth);
    const bottomWidth = parseBorderWidth(styles.borderBottomWidth);

    // Include hairlines (<1px); outline chips often use 1px but some themes use 0.5–0.8px.
    const sidesWithBorder = [leftWidth, rightWidth, topWidth, bottomWidth]
      .filter(w => w > 0).length;

    if (sidesWithBorder === 0) return 'none';

    // All 4 sides equal width and color?
    if (sidesWithBorder === 4 &&
        leftWidth === rightWidth &&
        rightWidth === topWidth &&
        topWidth === bottomWidth &&
        styles.borderLeftColor === styles.borderRightColor &&
        styles.borderRightColor === styles.borderTopColor &&
        styles.borderTopColor === styles.borderBottomColor) {
      return 'uniform';
    }

    return 'single';
  }

  /**
   * Convert icon element (Font Awesome icons)
   */
  private convertIconElement(element: ElementInfo, baseProps: any): any {
    const textOptions = getTextOptions(element.styles, this.platformFontContext);
    const textContent = sanitizeTextForXml(element.content || '');

    const options: any = {
      ...baseProps,
      ...textOptions,
      // Disable wrap for icons
      wrap: false,
    };

    return {
      type: 'text',
      options,
      text: textContent,
    };
  }

  /**
   * Convert text element
   */
  private convertTextElement(element: ElementInfo, baseProps: any): any {
    // L1: freeze Chromium line breaks before wrap heuristics run.
    let layoutFaithfulActive = false;
    /** Set where a line break is written into the runs; read by the wrap decision. */
    let emittedFrozenBreaks = false;

    const pillProbe = isInlinePillBox(element.styles, {
      width: element.width,
      height: element.height,
    });
    const gate = classifyLayoutFaithfulEligibility(element, { isPillBox: pillProbe });
    if (gate.eligible) {
      layoutFaithfulActive = true;
      const lines = element.layoutLines || [];
      if (lines.length >= 2) {
        if (element.richText && element.richText.length > 0) {
          const broken = applyChromiumSoftBreaks(
            element.richText,
            element.layoutLines,
            element.content
          );
          const gotBreaks =
            !!broken && broken.some((r: any) => r.softBreakBefore);
          if (gotBreaks) {
            element.richText = broken;
            // The breaks are written onto the element, and any later emission
            // path inherits them. Record it here so the wrap decision cannot
            // be reached without knowing: one paragraph shipped with Chromium's
            // breaks inside a wrap="square" body, free to be re-broken by the
            // reader's renderer at its own metrics.
            element.layoutFaithfulFrozen = true;
          } else {
            layoutFaithfulActive = false;
            this.layoutFaithfulNotes.push({
              elementId: element.elementId,
              reason: 'break_mapping_failed',
              message: 'layout-faithful fallback: could not map Chromium breaks to runs',
            });
          }
        } else {
          // Single-style host: synthesize one run per Chromium line.
          const synthesized = buildRunsFromLines(
            element.styles as any,
            element.layoutLines,
            element.content
          );
          if (synthesized) {
            element.richText = synthesized as any;
            element.layoutFaithfulFrozen = true;
          } else {
            layoutFaithfulActive = false;
            this.layoutFaithfulNotes.push({
              elementId: element.elementId,
              reason: 'line_synthesis_failed',
              message: 'layout-faithful fallback: line/content mismatch',
            });
          }
        }
      } else {
        // Single line: geometry freeze is enough.
        layoutFaithfulActive = true;
      }
    } else if (gate.reason && gate.reason !== 'pill_path' && gate.reason !== 'not_text') {
      const mismatch = element.layoutFaithfulMismatch;
      this.layoutFaithfulNotes.push({
        elementId: element.elementId,
        reason: gate.reason,
        message: mismatch
          ? `layout-faithful fallback: ${gate.reason} — lines "${mismatch.lines}" vs host "${mismatch.host}"`
          : `layout-faithful fallback: ${gate.reason}`,
      });
    }

    const textOptions = getTextOptions(element.styles, this.platformFontContext, undefined, {
      width: element.width,
      height: element.height,
    });
    const lineOptions = getLineOptions(element.styles);

    // Only add fill if there's an actual background color
    const fillOptions = getFillOptions(element.styles, element);
    const backgroundClip = element.styles.backgroundClip ?? element.styles.webkitBackgroundClip;
    const textGradientData =
      backgroundClip === 'text'
        ? parseGradientFull(element.styles.backgroundImage, element, element.styles.backgroundSize)
        : undefined;
    const options: any = {
      ...baseProps,
      ...textOptions,
    };

    let scriptFontFaces = this.resolveScriptFontFaces(element.styles);
    if (scriptFontFaces !== undefined) options.fontFace = scriptFontFaces.latin;

    // li: padding/border already in margin; add in-flow ::before width + horizontal margins so text clears the bullet
    if (
      element.tag === 'li' &&
      element.beforePseudoWidthPx != null &&
      element.beforePseudoWidthPx > 0 &&
      Array.isArray(options.margin)
    ) {
      const extraPt = pxToPoints(element.beforePseudoWidthPx);
      options.margin = [
        options.margin[0] + extraPt,
        options.margin[1],
        options.margin[2],
        options.margin[3],
      ];
    }

    if (
      element.textFlowExtraMarginLeftPx != null &&
      element.textFlowExtraMarginLeftPx > 0 &&
      Array.isArray(options.margin)
    ) {
      const extraPt = pxToPoints(element.textFlowExtraMarginLeftPx);
      options.margin = [
        options.margin[0] + extraPt,
        options.margin[1],
        options.margin[2],
        options.margin[3],
      ];
    }

    if (textGradientData && !options.color && textGradientData.stops?.length) {
      options.color = textGradientData.stops[0].color;
    }

    // Native list markers (disc/circle/decimal/…) are not ::before — extractPseudoElements does not
    // capture them. Emit pptx bullets for those. When an in-flow ::before already reserves width
    // (inspector `beforePseudoWidthPx`), a custom bullet is handled separately — skip to avoid doubles.
    if (element.tag === 'li') {
      const hasInFlowBeforeBulletGap =
        element.beforePseudoWidthPx != null && element.beforePseudoWidthPx > 0;
      if (!hasInFlowBeforeBulletGap) {
        const listStyleType = (element.styles.listStyleType || '').toLowerCase().trim();
        const bulletIndentPt = 8;
        if (listStyleType && listStyleType !== 'none') {
          const numberedTypes = [
            'decimal',
            'decimal-leading-zero',
            'lower-alpha',
            'upper-alpha',
            'lower-roman',
            'upper-roman',
          ];
          if (numberedTypes.includes(listStyleType)) {
            options.bullet = { type: 'number', indent: bulletIndentPt };
          } else {
            options.bullet = { indent: bulletIndentPt };
          }
        }
      }
    }

    // Add fill only if it exists
    if (fillOptions.fill) {
      options.fill = fillOptions.fill;
    }

    // Add transparency if exists
    if (fillOptions.transparency !== undefined) {
      options.transparency = fillOptions.transparency;
    }

    // Add line if it exists (only for uniform borders)
    const borderType = this.getBorderType(element.styles);
    if (borderType === 'uniform' && lineOptions) {
      options.line = lineOptions;
    }

    // Thin bottom border (= underline rule on the text box): leave room for
    // serif descenders (q/g/y) so PPT does not paint glyphs through the rule.
    {
      const bbPx = parseFloat(String(element.styles.borderBottomWidth || '0')) || 0;
      const btPx = parseFloat(String(element.styles.borderTopWidth || '0')) || 0;
      const blPx = parseFloat(String(element.styles.borderLeftWidth || '0')) || 0;
      const brPx = parseFloat(String(element.styles.borderRightWidth || '0')) || 0;
      if (
        bbPx > 0 &&
        bbPx <= 6 &&
        btPx < 0.5 &&
        blPx < 0.5 &&
        brPx < 0.5 &&
        Array.isArray(options.margin)
      ) {
        const fontPx = parseFloat(String(element.styles.fontSize || '16')) || 16;
        const extraPt = pxToPoints(
          Math.max(ElementConverter.ACCENT_DESCENDER_CLEAR_PX, fontPx * 0.2)
        );
        options.margin = [
          options.margin[0],
          options.margin[1],
          (Number(options.margin[2]) || 0) + extraPt,
          options.margin[3],
        ];
      }
    }

    // Handle box-shadow: classify as glow (3-4 sides) or directional shadow (1-2 sides)
    const textBoxShadowInfo = parseBoxShadowClassified(element.styles.boxShadow);
    if (textBoxShadowInfo?.effect === 'shadow') {
      options.shadow = parseBoxShadow(element.styles.boxShadow);
    }
    const textGlowData = textBoxShadowInfo?.effect === 'glow' ? {
      radiusPt: Math.max(1, Math.min(500, pxToPoints(textBoxShadowInfo.blur))),
      color: textBoxShadowInfo.color,
      alpha: textBoxShadowInfo.alpha,
    } : undefined;

    // Check if element has border-radius with background/border
    // If yes, we need to render as a roundRect shape instead of text box
    // because PowerPoint text boxes don't support rounded corners
    const hasFill = fillOptions.fill !== undefined;
    const hasLine = lineOptions !== undefined;
    const borderRadius = parseBorderRadius(
      element.styles.borderRadius,
      element.width,
      element.height
    );
    const shouldUseRoundedShape = (hasFill || hasLine) && borderRadius;

    const applyHorizontalAlign = (value?: string) => {
      if (value === 'center') {
        options.align = 'center';
      } else if (value === 'flex-end' || value === 'end' || value === 'right') {
        options.align = 'right';
      } else if (value === 'flex-start' || value === 'start' || value === 'left') {
        options.align = 'left';
      }
    };
    const applyVerticalAlign = (value?: string) => {
      if (value === 'center') {
        options.valign = 'middle';
      } else if (value === 'flex-end' || value === 'end' || value === 'bottom') {
        options.valign = 'bottom';
      } else if (value === 'flex-start' || value === 'start' || value === 'top') {
        options.valign = 'top';
      }
    };

    // Add flexbox alignment support
    // Map CSS flexbox properties to PowerPoint text alignment
    const display = element.styles.display;
    const flexDirection = element.styles.flexDirection || 'row';

    if (display === 'flex' || display === 'inline-flex') {
      const justifyContent = element.styles.justifyContent;
      const alignItems = element.styles.alignItems;

      // For flex-direction: row (default), justify-content controls horizontal (align), align-items controls vertical (valign)
      // For flex-direction: column, justify-content controls vertical (valign), align-items controls horizontal (align)
      if (flexDirection === 'row' || flexDirection === 'row-reverse') {
        // Horizontal alignment from justify-content
        applyHorizontalAlign(justifyContent);

        // Vertical alignment from align-items
        applyVerticalAlign(alignItems);
      } else if (flexDirection === 'column' || flexDirection === 'column-reverse') {
        // Vertical alignment from justify-content
        applyVerticalAlign(justifyContent);

        // Horizontal alignment from align-items
        applyHorizontalAlign(alignItems);
      }
    }

    // Add grid alignment support (e.g. display:grid + place-items:center)
    if (display === 'grid' || display === 'inline-grid') {
      const placeItemsRaw = element.styles.placeItems;
      const justifyItems = element.styles.justifyItems;
      const alignItems = element.styles.alignItems;
      const placeItemsParts = placeItemsRaw?.trim().split(/\s+/).filter(Boolean) ?? [];
      const placeAlign = placeItemsParts[0];
      const placeJustify = placeItemsParts[1] ?? placeItemsParts[0];
      applyHorizontalAlign(placeJustify);
      applyVerticalAlign(placeAlign);
      applyHorizontalAlign(justifyItems);
      applyVerticalAlign(alignItems);
    }

    // When vertical alignment was not set by flex, default to top (HTML block default)
    if (options.valign === undefined) {
      options.valign = 'top';
    }

    // Circular flex-centered glyph badges must stay centered even when a parent
    // space-between row stamps flexItemTextAlign left/right on the last/first child.
    const ownFlexCenters =
      (display === 'flex' || display === 'inline-flex') &&
      element.styles.justifyContent === 'center' &&
      element.styles.alignItems === 'center';
    if (element.circleGlyphBadge || ownFlexCenters) {
      options.align = 'center';
      options.valign = 'middle';
    }

    // Flex space-* stamps align for bare text in a stretched flex slot (e.g. header label).
    // Skip when the element paints its own box (border/fill chip/card) — flex already placed
    // that box; forcing right/left inside a shrink-wrapped chip overflows the outline.
    const hasOwnPaintedBox =
      isVisibleTextBackgroundColor(element.styles.backgroundColor) ||
      hasVisibleBorder(element.styles);
    if (
      element.flexItemTextAlign &&
      !element.circleGlyphBadge &&
      !ownFlexCenters &&
      !hasOwnPaintedBox
    ) {
      options.align = element.flexItemTextAlign;
    }

    // Check if this is rich text (multiple styled runs)
    let textContent: any;
    const containerText = this.getContainerText(element);
    const containerHints = detectContainerScriptHints(containerText);

    if (element.richText && element.richText.length > 0) {
      // Convert rich text runs to pptxgenjs format
      textContent = element.richText.flatMap((run: any, index: number) => {
        const scriptRuns = this.splitTextRunByScript(run, containerHints);
        return scriptRuns.flatMap((scriptRun) => {
        const textScript = scriptRun.textScript ?? 'latin';
        const runOptions = getTextOptions(run.styles, this.platformFontContext, scriptRun.text);
        // Line spacing is paragraph-level (host element.options); per-run values stack badly on <a:br/>.
        delete runOptions.lineSpacing;
        delete runOptions.lineSpacingMultiple;
        const runScriptFaces = this.resolveScriptFontFaces(run.styles, textScript);
        if (runScriptFaces !== undefined) {
          runOptions.fontFace = runScriptFaces.latin;
          if (!scriptFontFaces) scriptFontFaces = runScriptFaces;
        }
        if (textGradientData && !runOptions.color && textGradientData.stops?.length) {
          runOptions.color = textGradientData.stops[0].color;
        }
        let runText = sanitizeTextForXml(scriptRun.text);
        if (element.styles.textTransform === 'uppercase') {
          runText = localeUpperCase(runText, run.styles?.lang ?? element.styles.lang);
        }
        runText = expandRunTextForInlineHighlightPadding(runText, run.styles);
        // HTML collapses consecutive whitespace to one space (do not strip single leading/trailing gaps).
        runText = runText.replace(/[\s\u00A0]{2,}/g, ' ');
        // Prepend space(s) for margin-left on inline/inline-block runs (e.g. indented <span>).
        // Block-level margin-left on the text host is already reflected in ElementInfo x/width — do not
        // inject spaces between rich-text runs (e.g. .title-line-2 { margin-left: 60px }).
        if (index > 0 && run.styles?.marginLeft) {
          const runDisplay = run.styles.display;
          const marginIsInline =
            runDisplay === 'inline' || runDisplay === 'inline-block';
          const marginLeftPx = marginIsInline
            ? parseFloat(String(run.styles.marginLeft)) || 0
            : 0;
          if (marginLeftPx > 0) {
            const fontSizePx =
              parseFloat(String(run.styles.fontSize || element.styles.fontSize || '16')) || 16;
            const spaces = marginLeftPxToLeadingSpaces(marginLeftPx, fontSizePx);
            if (spaces > 0) {
              runText = ' '.repeat(spaces) + runText;
            }
          }
        }
        // <br> is already softBreakBefore; leading \n in the same run (DOM whitespace after <br>) would
        // split to ['', '…'] and set softBreak on both pieces → duplicate <a:br/> in OOXML.
        if (scriptRun.softBreakBefore) {
          runText = runText.replace(/^\r?\n+/, '');
        }
        // pptxgen treats "\n" in run text as new a:p; split to soft breaks (a:br) within one paragraph
        let segments = runText.split(/\r?\n/);
        if (scriptRun.softBreakBefore) {
          while (segments.length > 1 && segments[0] === '') {
            segments.shift();
          }
        }
        const lastSi = segments.length - 1;
        return segments.map((seg, si) => {
          const pieceOpts: any = { ...runOptions };
          // <a:br/> lines without an explicit run sz use PPT default (~18pt) for line-height → oversized gaps.
          if (scriptRun.softBreakBefore && si === 0) {
            emittedFrozenBreaks = true;
            pieceOpts.softBreakBefore = true;
            pieceOpts.fontSize = options.fontSize;
            pieceOpts.fontFace = pieceOpts.fontFace ?? options.fontFace;
          }
          if (seg === '\u200b' || seg === '') {
            pieceOpts.fontSize = options.fontSize;
            pieceOpts.fontFace = pieceOpts.fontFace ?? options.fontFace;
          }
          if (si > 0) {
            pieceOpts.softBreakBefore = true;
          }
          if (scriptRun.breakLine && si === lastSi) {
            pieceOpts.breakLine = true;
          }
          return {
            text: seg,
            options: pieceOpts,
          };
        });
        });
      });
      // Remove color from base options when using rich text runs
      // Each run has its own color
      if (!textGradientData) {
        delete options.color;
      }
    } else {
      // Simple text (e.g. <p>…<br>…</p> from getTextContent as "\n") — use soft breaks so pptxgen emits a:br, not multiple a:p
      let simpleTextContent = sanitizeTextForXml(element.content || '');
      if (element.styles.textTransform === 'uppercase') {
        simpleTextContent = localeUpperCase(simpleTextContent, element.styles.lang);
      }
      const softBreakOpts = {
        softBreakBefore: true,
        fontSize: options.fontSize,
        fontFace: options.fontFace,
        ...(options.color ? { color: options.color } : {}),
      };
      if (/\r?\n/.test(simpleTextContent)) {
        // Every line's end is now stated in the runs, so no renderer may
        // re-break them. Recorded at the point of emission because the wrap
        // decision below cannot tell from the finished pieces which mechanism
        // produced them, and one paragraph shipped with an <a:br/> inside a
        // wrap="square" body — free to re-wrap on the reader's metrics.
        emittedFrozenBreaks = true;
        const normalized = simpleTextContent.replace(/\r?\n{2,}/g, '\n');
        const parts = normalized.split(/\r?\n/);
        textContent = parts.flatMap((part, i) => {
          const scriptPieces = this.buildScriptSplitTextPieces(
            part,
            element.styles,
            options,
            containerHints
          );
          if (typeof scriptPieces === 'string') {
            return i === 0
              ? [{ text: scriptPieces, options: {} }]
              : [{ text: scriptPieces, options: softBreakOpts }];
          }
          return scriptPieces.map((piece, pi) => ({
            text: piece.text,
            options: {
              ...piece.options,
              ...(i > 0 && pi === 0 ? softBreakOpts : {}),
            },
          }));
        });
      } else {
        const scriptPieces = this.buildScriptSplitTextPieces(
          simpleTextContent,
          element.styles,
          options,
          containerHints
        );
        textContent = scriptPieces;
      }
    }

    // Count paragraphs: in OOXML each paragraph becomes one a:p. Multiple paragraphs come from
    // display:block children (breakLine in richText), not from HTML <br> (handled as softBreakBefore / a:br).
    let paragraphCount: number;
    let visualLineCount: number;
    if (element.richText && element.richText.length > 0) {
      paragraphCount = 1 + element.richText.filter((r: any) => r.breakLine).length;
      visualLineCount = Math.max(
        paragraphCount,
        1 + element.richText.filter((r: any) => r.softBreakBefore).length
      );
    } else if (Array.isArray(textContent)) {
      const softBreakCount = textContent.filter((r: any) => r.options?.softBreakBefore).length;
      paragraphCount = 1;
      visualLineCount = 1 + softBreakCount;
    } else if (typeof textContent === 'string') {
      paragraphCount = textContent.split(/\r?\n/).length;
      visualLineCount = paragraphCount;
    } else {
      paragraphCount = 1;
      visualLineCount = 1;
    }

    // Detect wraps from content height vs line-height. Prefer computed px from inspector.
    const fontSizeStr = String(element.styles.fontSize || '16');
    const fontSize = parseFloat(fontSizeStr);
    const lineHeightStr = String(element.styles.lineHeight || 'normal').trim();
    const lineHeightIsPx = lineHeightStr !== 'normal' && /px\s*$/i.test(lineHeightStr);
    const lineHeightUnitless =
      lineHeightStr !== 'normal' && !lineHeightIsPx && /^[\d.]+$/.test(lineHeightStr);
    // Computed style often yields px; unitless → fontSize * N; normal ≈ 1.2× (CSS typical).
    const lineHeightPx = lineHeightIsPx
      ? parseFloat(lineHeightStr)
      : lineHeightUnitless
        ? fontSize * (parseFloat(lineHeightStr) || 1.2)
        : fontSize * 1.2;

    // foreignObject hybrid labels: derive line spacing from rendered box height (viewBox scale baked in).
    if (element.svgForeignObjectText && visualLineCount > 1 && element.height > 0) {
      const cssPx = parseFloat(fontSizeStr) || 16;
      const fontSizePx =
        cssPx > element.height * 1.08 ? element.height : cssPx;
      const perLinePx = element.height / visualLineCount;
      const multiple = perLinePx / fontSizePx;
      if (multiple >= 0.5 && multiple <= 10) {
        delete options.lineSpacing;
        options.lineSpacingMultiple = Math.round(multiple * 1000) / 1000;
      }
    } else if (lineHeightIsPx && visualLineCount >= 1) {
      // Match element.height → inch mapping (not font-calibrated 0.58×), else last line clips.
      const lhPt = pxToSlidePointsY(lineHeightPx);
      if (lhPt >= 1 && lhPt <= 256) {
        delete options.lineSpacingMultiple;
        options.lineSpacing = lhPt;
      }
    }

    // Subtract vertical padding and border to get pure text content height
    const paddingTopPx = parseFloat(String(element.styles.paddingTop || '0')) || 0;
    const paddingBottomPx = parseFloat(String(element.styles.paddingBottom || '0')) || 0;
    const borderTopPx = parseFloat(String(element.styles.borderTopWidth || '0')) || 0;
    const borderBottomPx = parseFloat(String(element.styles.borderBottomWidth || '0')) || 0;
    const verticalChromePx = paddingTopPx + paddingBottomPx + borderTopPx + borderBottomPx;

    const elementHeightPx = element.height; // original px height from inspector
    const textContentHeightPx = elementHeightPx - verticalChromePx;
    const allParagraphsSingleLine =
      textContentHeightPx <= visualLineCount * lineHeightPx * 1.2;
    const isMultiLineByHeight = textContentHeightPx > lineHeightPx * 1.35;

    // Fit fixed lineSpacing into the measured content box (HTML flush cards / 3-line wraps).
    if (
      typeof options.lineSpacing === 'number' &&
      options.lineSpacing > 0 &&
      textContentHeightPx > 0 &&
      lineHeightPx > 0
    ) {
      const approxLines = Math.max(
        visualLineCount,
        Math.round(textContentHeightPx / lineHeightPx)
      );
      if (approxLines >= 2) {
        const contentHPt = pxToSlidePointsY(textContentHeightPx);
        const needed = options.lineSpacing * approxLines;
        if (needed > contentHPt + 0.05) {
          options.lineSpacing = Math.max(1, Math.round((contentHPt / approxLines) * 100) / 100);
        }
      }
    }

    // listMarkerOffset logic removed - bullets are now handled via ::before pseudo-elements
    // if (element.tag === 'li' && element.listMarkerOffset) {
    //   const offsetInch = pxToInch(element.listMarkerOffset);
    //   options.x = (options.x ?? baseProps.x) - offsetInch;
    //   options.w = (options.w ?? baseProps.w) + offsetInch;
    // }

    // Frozen breaks and renderer wrapping are contradictory: the runs already
    // say where every line ends, so leaving wrap on invites the reader's
    // PowerPoint to re-break them at its own metrics — the drift the whole
    // capture exists to prevent. The breaks are applied as a side effect on the
    // element, so an emission path that never runs the layout-faithful block
    // still inherits them; this asks the element instead of the path.
    // Frozen breaks and renderer wrapping are contradictory: the runs already
    // state where every line ends, so leaving wrap on invites the reader's
    // PowerPoint to re-break them at its own metrics — the drift this whole
    // capture exists to prevent. Guarded at each site that writes a break:
    // the layout-faithful mutation (`layoutFaithfulFrozen`) and the two
    // emission paths (`emittedFrozenBreaks`).
    //
    // The split-background path further down spreads these options and then
    // sets its own wrap, so it has to make the same check; that override was
    // the last producer of a break-inside-a-wrapping-body.
    if (element.layoutFaithfulFrozen || emittedFrozenBreaks) {
      options.wrap = false;
    } else if (isMultiLineByHeight || !allParagraphsSingleLine) {
      options.wrap = true;
    } else {
      options.wrap = false;
    }
    // Explicit <br> / softBreak runs already define line breaks — do not re-wrap (causes overflow).
    if (element.svgForeignObjectText && visualLineCount > 1) {
      options.wrap = false;
    }
    // L1: Chromium already chose the line breaks (explicit <a:br/>).
    // Emit wrap:none so PowerPoint cannot re-solve layout (no normAutofit).
    // Metric drift is absorbed by embedded fonts + bounded pre-export shrink.
    if (layoutFaithfulActive) {
      const lines = element.layoutLines || [];
      options.wrap = false;
      delete options.fit;
      if (lines.length >= 2) {
        // Line pitch is the distance between line boxes, not the height of one.
        // A captured line's `height` is its glyph box (ascent+descent), which for
        // a 64px Georgia is ~73px against a 67.8px CSS line-height. Using it as
        // the pitch stretched every multi-line block by ~8%, so three lines no
        // longer fit the three-line frame Chromium measured and the text walked
        // down out of its box. Consecutive tops give the true pitch directly.
        const pitch = layoutLinePitchPx(lines);
        if (pitch > 0) {
          options.lineSpacing = pxToSlidePointsY(pitch);
          delete options.lineSpacingMultiple;
        }
      }
      // Geometry stays frozen at Chromium box (baseProps already applied).
      options.x = baseProps.x;
      options.y = baseProps.y;
      options.w = baseProps.w;
      options.h = baseProps.h;

      // Drift headroom for *widening* only: giving the widest Chromium line ~8%
      // extra width is free when there is empty space to the right.
      //
      // It must not drive a font shrink. These lines are emitted with
      // wrap="none" and an explicit <a:br/> per Chromium line, so no amount of
      // font-metric drift can re-wrap them — the worst case is a line reaching
      // a few percent past its frame into empty space. Shrinking to buy
      // headroom against that pays with a visible size change on every heading
      // (a measured cover title lost 7%, and its raster match fell from 0.40 to
      // 0.25 SSIM) and moves every baseline under it. Fit the line as measured;
      // shrink only when it genuinely does not fit.
      const DRIFT = 1.08;
      const marginArr = Array.isArray(options.margin) ? options.margin : [0, 0, 0, 0];
      const marginWIn =
        (Math.max(0, Number(marginArr[0]) || 0) + Math.max(0, Number(marginArr[1]) || 0)) / 72;
      const widestIn = lines.reduce(
        (mx, l) => Math.max(mx, pxToInchX(Number(l.width) || 0)),
        0
      );
      if (widestIn > 0) {
        const neededIn = widestIn * DRIFT + marginWIn;
        const alignLeft = !options.align || options.align === 'left';
        // Identity-bearing objects participate in semantic geometry QA. Their
        // box is a contract: absorb font-metric drift with the bounded shrink
        // below instead of widening across a Scene boundary or safe inset.
        //
        // "Identity-bearing" has to mean an identity the deck authored -- a
        // data-layout-id, a semantic host, a real id. The inspector synthesises
        // a structural path (`dh-auto__body-1__...__span-2`) for *every*
        // element, so reading this as "has an elementId" made it true of
        // everything: the widen branch below became dead code and font shrink
        // became the only response to PowerPoint measuring a line wider than
        // Chromium did. Each element negotiated that alone, so a row of
        // identical chips left as 8.4pt, 6.5pt, 8.4pt, 8.4pt -- while the HTML
        // had them all at 15px.
        const identity = String(element.elementId || '');
        const preserveIdentityBox = Boolean(identity) && !identity.startsWith('dh-auto');
        if (neededIn > options.w + 1e-4 && alignLeft && !preserveIdentityBox) {
          const rightLimit = this.layoutDriftRightLimit(
            options.x,
            options.y,
            options.w,
            options.h
          );
          options.w = Math.min(neededIn, Math.max(options.w, rightLimit - options.x));
        }
        if (widestIn + marginWIn > options.w + 1e-4) {
          const avail = Math.max(0.02, options.w - marginWIn);
          const measuredScale = Math.max(
            1 - LAYOUT_FAITHFUL_MAX_FONT_SHRINK,
            avail / widestIn
          );
          const peerScale = element.elementId
            ? this.peerTypographyScales.get(element.elementId)
            : undefined;
          const scale = Math.min(measuredScale, peerScale ?? 1);
          if (scale < 0.999) {
            element.layoutFaithfulFontScale = scale;
            if (typeof options.fontSize === 'number' && options.fontSize > 0) {
              options.fontSize = Math.round(options.fontSize * scale * 100) / 100;
            }
            if (Array.isArray(textContent)) {
              for (const piece of textContent) {
                const fs = piece?.options?.fontSize;
                if (typeof fs === 'number' && fs > 0) {
                  piece.options.fontSize = Math.round(fs * scale * 100) / 100;
                }
              }
            }
          }
        }
      }
    }


    const bodyPrVert = getOoxmlBodyPrVert(element.styles.writingMode);

    const createTextElement = (customOptions?: any, skipGlow?: boolean): any => {
      const textElement: any = {
        type: 'text',
        options: customOptions ?? options,
        text: textContent,
      };
      if (textGradientData) {
        textElement._textGradientData = textGradientData;
        textElement._sourceElement = element;
      }
      if (textGlowData && !skipGlow) {
        textElement._glowData = textGlowData;
      }
      if (scriptFontFaces || element.styles.fontFamily || this.platformFontContext) {
        textElement._scriptFontsMeta = {
          fontFamily: element.styles.fontFamily,
          fontFamilySpecified: element.styles.fontFamilySpecified,
          platform: this.platformFontContext?.platform,
          scriptFontFaces,
        };
      }
      if (bodyPrVert) {
        textElement._bodyPrVert = bodyPrVert;
      }
      return textElement;
    };

    // clip-path polygon + background: text box cannot use custGeom — rect (gradient/solid) + text on top
    if (
      element.clipPathPolygonPx &&
      element.clipPathPolygonPx.length >= 3 &&
      fillOptions.fill
    ) {
      const wPx = element.width;
      const hPx = element.height;
      if (wPx > 0 && hPx > 0) {
        const normalized = element.clipPathPolygonPx.map((p) => ({
          x: Math.round(Math.min(21600, Math.max(0, (p.x / wPx) * 21600))),
          y: Math.round(Math.min(21600, Math.max(0, (p.y / hPx) * 21600))),
        }));
        const bt = this.getBorderType(element.styles);
        const backgroundOptions: any = {
          x: baseProps.x,
          y: baseProps.y,
          w: baseProps.w,
          h: baseProps.h,
          fill: fillOptions.fill,
        };
        if (baseProps.rotate !== undefined) {
          backgroundOptions.rotate = baseProps.rotate;
        }
        if (fillOptions.transparency !== undefined) {
          backgroundOptions.transparency = fillOptions.transparency;
        }
        if (bt === 'uniform' && lineOptions) {
          backgroundOptions.line = lineOptions;
        } else if (bt === 'single') {
          const commonLine = this.getCommonLineOptions(element.styles);
          if (commonLine) backgroundOptions.line = commonLine;
        }
        const bgShape: any = {
          type: 'rect',
          options: backgroundOptions,
          _clipPathPolygonNormalized: normalized,
        };
        if (parseGradientFull(element.styles.backgroundImage, element, element.styles.backgroundSize)) {
          bgShape._prefersGradient = true;
        }
        if (textGlowData) {
          bgShape._glowData = textGlowData;
        }
        const textBoxOptions: any = {
          ...options,
          x: baseProps.x,
          y: baseProps.y,
          w: baseProps.w,
          h: baseProps.h,
        };
        delete textBoxOptions.fill;
        delete textBoxOptions.transparency;
        delete textBoxOptions.line;
        delete textBoxOptions.shadow;
        textContent = stripTextHighlights(textBoxOptions, textContent);

        return [
          bgShape,
          createTextElement(textBoxOptions, true),
        ];
      }
    }

    const intentionalLines = (() => {
      if (Array.isArray(textContent)) {
        const lines: string[] = [];
        let cur = '';
        for (const piece of textContent as any[]) {
          if (piece?.options?.softBreakBefore && cur) {
            lines.push(cur);
            cur = '';
          }
          cur += typeof piece === 'string' ? piece : piece?.text || '';
        }
        if (cur) lines.push(cur);
        return lines.length ? lines : [''];
      }
      if (typeof textContent === 'string') {
        return textContent.split(/\r?\n/);
      }
      return [this.getContainerText(element)];
    })();

    const applyFontSizeToTextContent = (sizePt: number) => {
      if (!Array.isArray(textContent)) return;
      textContent = (textContent as any[]).map((piece) => {
        if (typeof piece === 'string') return piece;
        return {
          ...piece,
          options: { ...piece.options, fontSize: sizePt },
        };
      });
    };

    // If another member of this semantic peer group needed a bounded shrink,
    // apply the same factor here even when this particular line was shorter.
    // Scale existing run sizes by the delta so relative rich-text hierarchy is
    // preserved and width/height fitting never compounds the factor.
    const sharedPeerScale = element.elementId
      ? this.peerTypographyScales.get(element.elementId)
      : undefined;
    const currentScale = element.layoutFaithfulFontScale ?? 1;
    if (layoutFaithfulActive && sharedPeerScale && sharedPeerScale < currentScale - 1e-4) {
      const ratio = sharedPeerScale / currentScale;
      if (typeof options.fontSize === 'number' && options.fontSize > 0) {
        options.fontSize = Math.round(options.fontSize * ratio * 100) / 100;
      }
      if (Array.isArray(textContent)) {
        textContent = (textContent as any[]).map((piece) => {
          if (typeof piece === 'string') return piece;
          const fs = piece?.options?.fontSize;
          return typeof fs === 'number' && fs > 0
            ? {
                ...piece,
                options: {
                  ...piece.options,
                  fontSize: Math.round(fs * ratio * 100) / 100,
                },
              }
            : piece;
        });
      }
      element.layoutFaithfulFontScale = sharedPeerScale;
    }

    // Pill/chip badges: one roundRect + text (filled or outline; matches HTML shrink-to-fit box)
    // Multi-line / <br> callouts must NOT take this path (wrap:none spills below the box).
    // Exception: short labels ("Insert here") that Chromium wrapped inside a tight circle
    // still use the pill path so we grow width and keep a single centered line.
    const pillPlainPreview = (() => {
      if (typeof textContent === 'string') return textContent;
      if (!Array.isArray(textContent)) return '';
      let out = '';
      for (const p of textContent as any[]) {
        const t = typeof p === 'string' ? p : p?.text || '';
        const soft = typeof p === 'object' && p?.options?.softBreakBefore;
        if (soft && out && !/\s$/.test(out) && !/^\s/.test(t)) out += ' ';
        out += t;
      }
      return out;
    })();
    const shortChipLabel =
      pillPlainPreview.trim().length > 0 &&
      pillPlainPreview.trim().length <= 28 &&
      pillPlainPreview.trim().split(/\s+/).filter(Boolean).length <= 3;
    if (
      shouldUseRoundedShape &&
      isInlinePillBox(
        element.styles,
        { width: element.width, height: element.height },
        {
          multiLine: visualLineCount > 1 && !shortChipLabel,
          shortLabel: shortChipLabel,
        }
      )
    ) {
      const pillOptions: any = {
        ...options,
        x: baseProps.x,
        y: baseProps.y,
        w: baseProps.w,
        h: baseProps.h,
        shape: 'roundRect',
        rectRadius: borderRadius,
        fit: 'none',
        wrap: false,
        // Chip glyphs center in the roundRect; never inherit flexItemTextAlign.
        align: parseTextAlign(element.styles.textAlign) || 'center',
        valign: 'middle',
      };
      textContent = stripTextHighlights(pillOptions, textContent);
      if (fillOptions.fill) {
        pillOptions.fill = fillOptions.fill;
        if (fillOptions.transparency !== undefined) {
          pillOptions.transparency = fillOptions.transparency;
        }
      } else {
        // Outline chips: no CSS fill — keep shape hollow (default white fill would flash).
        pillOptions.fill = { type: 'none' };
      }
      if (borderType === 'uniform' && lineOptions) {
        pillOptions.line = lineOptions;
      } else if (lineOptions) {
        pillOptions.line = lineOptions;
      } else {
        pillOptions.line = { type: 'none' };
      }

      // PPT metrics are wider than the browser face that shrink-wrapped the chip.
      // Grow the roundRect first (keeps CSS padding air); shrink font only as last resort.
      const plain =
        typeof textContent === 'string'
          ? textContent
          : Array.isArray(textContent)
            ? (() => {
                let out = '';
                for (const p of textContent as any[]) {
                  const t = typeof p === 'string' ? p : p?.text || '';
                  const soft = typeof p === 'object' && p?.options?.softBreakBefore;
                  if (soft && out && !/\s$/.test(out) && !/^\s/.test(t)) out += ' ';
                  out += t;
                }
                return out;
              })()
            : '';
      const margin = Array.isArray(pillOptions.margin) ? pillOptions.margin : [0, 0, 0, 0];
      const xInch = Number(pillOptions.x) || 0;
      const yInch = Number(pillOptions.y) || 0;
      const wInch = Number(pillOptions.w) || 0;
      const hInch = Number(pillOptions.h) || 0;
      const collision = this.pillCollisionBounds(xInch, yInch, wInch, hInch);
      // Short flex chips (HNSW/LNS): prefer shrink over eating the 10px gap.
      const compactChip = wInch > 0 && wInch <= 1.35 && hInch > 0 && hInch <= 0.55;
      // L1 layout-faithful: the pill box is frozen at its Chromium rect, so it
      // must not wander into a sibling whose position is frozen too. That is
      // what `collision` below is for -- it caps growth at the neighbours' own
      // edges. Forbidding growth outright instead made the font the only thing
      // that could give, and since each chip negotiated alone, one row of
      // identical chips exported at 6.4pt, 7.9pt and 9.0pt. A chip two pixels
      // wider than Chromium measured it is invisible; a chip in the wrong type
      // size is the first thing a reader notices. Allow a few pixels of growth
      // within the gap that actually exists, and keep shrink as the last resort
      // it was always described as.
      const frozenPill = !shortChipLabel;
      const frozenPillGrowInch = pxToInchX(12);
      const laidOut = fitPillBox({
        fontSizePt: Number(pillOptions.fontSize) || 12,
        text: plain,
        xInch,
        yInch,
        wInch,
        hInch,
        marginLeftPt: Number(margin[0]) || 0,
        marginRightPt: Number(margin[1]) || 0,
        marginTopPt: Number(margin[3]) || 0,
        marginBottomPt: Number(margin[2]) || 0,
        bold: !!pillOptions.bold,
        charSpacingPt:
          typeof pillOptions.charSpacing === 'number' ? pillOptions.charSpacing : undefined,
        preferShrinkFont: frozenPill || (compactChip && !shortChipLabel),
        maxGrowInch: frozenPill
          ? frozenPillGrowInch
          : shortChipLabel
            ? pxToInchX(80)
            : compactChip
              ? pxToInchX(10)
              : undefined,
        ...collision,
      });
      if (
        laidOut.marginLeftPt !== (Number(margin[0]) || 0)
        || laidOut.marginRightPt !== (Number(margin[1]) || 0)
      ) {
        pillOptions.margin = [laidOut.marginLeftPt, laidOut.marginRightPt, margin[2], margin[3]];
      }
      // A row settles on one size. `laidOut` answered for this chip alone; the
      // shared factor is the strictest answer across its siblings, so applying
      // it can only make this chip smaller than what already fit.
      const pillPeerKey = this.semanticPeerKey(element);
      const sharedPillScale = pillPeerKey
        ? this.pillPeerScales.get(pillPeerKey)
        : undefined;
      if (sharedPillScale !== undefined) {
        const authoredPt = pxToPoints(
          parseFloat(String(element.styles?.fontSize || '0')) || 0
        );
        if (authoredPt > 0) {
          const shared = Math.round(authoredPt * sharedPillScale * 100) / 100;
          if (shared > 0 && shared < laidOut.fontSizePt) {
            laidOut.fontSizePt = shared;
          }
        }
      }
      pillOptions.x = laidOut.x;
      pillOptions.y = laidOut.y;
      pillOptions.w = laidOut.w;
      pillOptions.h = laidOut.h;
      pillOptions.fontSize = laidOut.fontSizePt;
      // Flatten soft breaks — chip is single-line after grow/shrink.
      if (Array.isArray(textContent) && shortChipLabel) {
        textContent = plain;
      }
      // Single-line chips: keep line box from eating vertical padding.
      delete pillOptions.lineSpacingMultiple;
      pillOptions.lineSpacing = Math.max(
        laidOut.fontSizePt,
        Math.round(laidOut.fontSizePt * 1.15 * 10) / 10
      );

      this.recordTextBand(laidOut.x, laidOut.y, laidOut.w, laidOut.h);
      return createTextElement(pillOptions);
    }

    // If element has rounded corners with background/border, render as roundRect shape
    // PowerPoint shapes with text inside support rounded corners better than text boxes
    // We return TWO elements: background shape + text on top
    if (shouldUseRoundedShape) {
      const margin = Array.isArray(options.margin) ? options.margin : [0, 0, 0, 0];
      const lineSpacingPt =
        typeof options.lineSpacing === 'number' && options.lineSpacing > 0
          ? options.lineSpacing
          : (Number(options.fontSize) || 12) *
            (typeof options.lineSpacingMultiple === 'number' && options.lineSpacingMultiple > 0
              ? options.lineSpacingMultiple
              : 1.35);
      const leftBorderPx =
        parseFloat(String(element.styles.borderLeftWidth || '0')) || 0;
      // L1: never move/grow the Chromium box (left-grow was drifting text past accent bars).
      const fitted = {
        x: Number(baseProps.x) || 0,
        y: Number(baseProps.y) || 0,
        w: Number(baseProps.w) || 0,
        h: Number(baseProps.h) || 0,
        fontSizePt: Number(options.fontSize) || 12,
        lineSpacingPt:
          typeof options.lineSpacing === 'number' && options.lineSpacing > 0
            ? options.lineSpacing
            : lineSpacingPt,
      };
      applyFontSizeToTextContent(fitted.fontSizePt);

      // Background: rounded rectangle shape with fill
      const backgroundOptions: any = {
        x: fitted.x,
        y: fitted.y,
        w: fitted.w,
        h: fitted.h,
        fill: fillOptions.fill,
        rectRadius: borderRadius,
        line: { type: 'none' }, // No border by default
      };
      if (baseProps.rotate !== undefined) {
        backgroundOptions.rotate = baseProps.rotate;
      }

      // Add transparency if exists
      if (fillOptions.transparency !== undefined) {
        backgroundOptions.transparency = fillOptions.transparency;
      }

      // Add border if exists
      if (borderType === 'uniform' && lineOptions) {
        backgroundOptions.line = lineOptions;
      } else if (!fillOptions.fill && lineOptions) {
        backgroundOptions.line = lineOptions;
      }
      if (!fillOptions.fill) {
        backgroundOptions.fill = { type: 'none' };
      }

      // Foreground: text box on top with same position
      const textBoxOptions: any = {
        ...options,
        x: fitted.x,
        y: fitted.y,
        w: fitted.w,
        h: fitted.h,
        fontSize: fitted.fontSizePt,
        lineSpacing: fitted.lineSpacingPt,
        // This split-background path spread `...options` and then hard-coded
        // wrap:true, overriding the decision above. For runs that carry
        // Chromium's line breaks that is a contradiction — the breaks say where
        // each line ends and wrap invites the renderer to disagree — and it is
        // how one paragraph shipped with an <a:br/> inside a wrap="square"
        // body, free to re-wrap on the reader's metrics.
        wrap: element.layoutFaithfulFrozen || emittedFrozenBreaks ? false : true,
        valign: options.valign || 'middle',
      };
      delete textBoxOptions.lineSpacingMultiple;
      delete textBoxOptions.fill;
      delete textBoxOptions.line;
      delete textBoxOptions.rectRadius;
      delete textBoxOptions.shadow;
      // Background is the roundRect shape — glyph highlight duplicates fill and breaks sizing
      textContent = stripTextHighlights(textBoxOptions, textContent);

      // Return both elements: shape first (background), then text (foreground)
      const bgShape: any = {
        type: 'roundRect',
        options: backgroundOptions,
      };
      // Glow goes on the background shape (visual container), not text overlay
      if (textGlowData) {
        bgShape._glowData = textGlowData;
      }
      this.recordTextBand(fitted.x, fitted.y, fitted.w, fitted.h);
      return [
        bgShape,
        createTextElement(textBoxOptions, true /* skipGlow: background handles it */),
      ];
    }

    // Wrapping titles/body: keep estimated wrap height inside the measured box /
    // before later accent bars (negative letter-spacing alone is not enough).
    // L1 frozen path: never grow/move boxes — optional bounded in-box font shrink only.
    if (options.wrap && !layoutFaithfulActive) {
      const plain =
        typeof textContent === 'string'
          ? textContent
          : Array.isArray(textContent)
            ? textContent.map((p: any) => (typeof p === 'string' ? p : p?.text || '')).join('')
            : this.getContainerText(element);
      const margin = Array.isArray(options.margin) ? options.margin : [0, 0, 0, 0];
      const lineSpacingPt =
        typeof options.lineSpacing === 'number' && options.lineSpacing > 0
          ? options.lineSpacing
          : (Number(options.fontSize) || 12) *
            (typeof options.lineSpacingMultiple === 'number' && options.lineSpacingMultiple > 0
              ? options.lineSpacingMultiple
              : 1.2);
      const xInch = Number(options.x ?? baseProps.x) || 0;
      const yInch = Number(options.y ?? baseProps.y) || 0;
      const wInch = Number(options.w ?? baseProps.w) || 0;
      const hInch = Number(options.h ?? baseProps.h) || 0;
      const ceiling = this.accentCeilingBelow(xInch, yInch, wInch);
      const chromeCeil = this.chromeCeilingBelow(xInch, yInch, wInch);
      const maxBottom =
        ceiling !== undefined && chromeCeil !== undefined
          ? Math.min(ceiling, chromeCeil)
          : ceiling ?? chromeCeil;
      const walls = this.columnWallsBeside(xInch, yInch, wInch, hInch);
      const fitted = {
        x: xInch,
        y: yInch,
        w: wInch,
        h: hInch,
        fontSizePt: Number(options.fontSize) || 12,
        lineSpacingPt,
      };
      options.x = fitted.x;
      options.y = fitted.y;
      options.w = fitted.w;
      options.h = fitted.h;
      options.fontSize = fitted.fontSizePt;
      options.lineSpacing = fitted.lineSpacingPt;
      delete options.lineSpacingMultiple;
      applyFontSizeToTextContent(fitted.fontSizePt);
      this.recordTextBand(fitted.x, fitted.y, fitted.w, fitted.h);
    } else if (layoutFaithfulActive) {
      // Bounded shrink only when Chromium lines are taller than the frozen box.
      const lines = element.layoutLines || [];
      if (lines.length >= 2) {
        // What the renderer stacks is N line boxes at the pitch we emit, not N
        // glyph boxes. Summing glyph heights over-reported the need by ~8% and
        // shrank headings that already fit their measured frame exactly.
        const needH = lines.length * layoutLinePitchPx(lines);
        const boxH = Number(element.height) || 0;
        if (boxH > 0 && needH > boxH + 1) {
          const requiredScale = Math.max(
            1 - LAYOUT_FAITHFUL_MAX_FONT_SHRINK,
            boxH / needH
          );
          const existingScale = element.layoutFaithfulFontScale ?? 1;
          const peerScale = element.elementId
            ? this.peerTypographyScales.get(element.elementId)
            : undefined;
          const targetScale = Math.min(existingScale, requiredScale, peerScale ?? 1);
          if (targetScale < existingScale - 1e-4) {
            const ratio = targetScale / existingScale;
            const fontSizePt = Math.round((Number(options.fontSize) || 12) * ratio * 100) / 100;
            options.fontSize = fontSizePt;
            if (Array.isArray(textContent)) {
              textContent = (textContent as any[]).map((piece) => {
                if (typeof piece === 'string') return piece;
                const fs = piece?.options?.fontSize;
                return typeof fs === 'number' && fs > 0
                  ? {
                      ...piece,
                      options: {
                        ...piece.options,
                        fontSize: Math.round(fs * ratio * 100) / 100,
                      },
                    }
                  : piece;
              });
            }
            element.layoutFaithfulFontScale = targetScale;
            this.layoutFaithfulNotes.push({
              elementId: element.elementId,
              reason: 'font_shrink',
              message: `layout-faithful bounded font shrink scale=${targetScale.toFixed(3)}`,
            });
          }
        }
      }
      this.recordTextBand(
        Number(options.x ?? baseProps.x) || 0,
        Number(options.y ?? baseProps.y) || 0,
        Number(options.w ?? baseProps.w) || 0,
        Number(options.h ?? baseProps.h) || 0
      );
    } else {
      this.recordTextBand(
        Number(options.x ?? baseProps.x) || 0,
        Number(options.y ?? baseProps.y) || 0,
        Number(options.w ?? baseProps.w) || 0,
        Number(options.h ?? baseProps.h) || 0
      );
    }

    return createTextElement();
  }

  private buildPlaceholderImage(baseProps: any, mediaType: PlaceholderMediaType): any {
    return {
      type: 'image',
      options: {
        ...baseProps,
        data: getPlaceholderForMediaType(mediaType),
      },
    };
  }

  /**
   * Convert chart element (data-chart-payload on data-pptx="chart" hosts).
   */
  private convertChartElement(element: ElementInfo, baseProps: any): any {
    const prepared = prepareChartPayload(element.chartPayload ?? {});
    const options: {
      x: number;
      y: number;
      w: number;
      h: number;
      chartType: 'bar' | 'col' | 'line' | 'pie';
      categories: string[];
      series: Array<{ name: string; values: Array<number | null>; secondary?: boolean }>;
      dualAxis: boolean;
      mixedScale: boolean;
      colors?: string[];
    } = {
      x: baseProps.x,
      y: baseProps.y,
      w: baseProps.w,
      h: baseProps.h,
      chartType: prepared.chartType,
      categories: prepared.categories,
      series: prepared.series,
      dualAxis: prepared.dualAxis,
      mixedScale: prepared.mixedScale,
      colors: prepared.colors,
    };

    return {
      type: 'chart',
      options,
    };
  }

  /**
   * Convert image element
   */
  private convertImageElement(element: ElementInfo, baseProps: any): any {
    const imageSrc = element.src || element.dataUrl;
    if (!imageSrc || element.resourceUnavailable) {
      return this.buildPlaceholderImage(baseProps, 'image');
    }

    // CSS padding is inside the border box; pptxgen imageSizing uses the full box and
    // ignores padding — formula/figure plates with object-fit:contain + padding then overflow.
    const padL = parseFloat(String(element.styles?.paddingLeft || '0')) || 0;
    const padR = parseFloat(String(element.styles?.paddingRight || '0')) || 0;
    const padT = parseFloat(String(element.styles?.paddingTop || '0')) || 0;
    const padB = parseFloat(String(element.styles?.paddingBottom || '0')) || 0;
    const contentProps = { ...baseProps };
    if (padL + padR + padT + padB > 0.5) {
      contentProps.x = (baseProps.x ?? 0) + pxToInchX(padL);
      contentProps.y = (baseProps.y ?? 0) + pxToInchY(padT);
      contentProps.w = Math.max(pxToInchX(1), (baseProps.w ?? 0) - pxToInchX(padL + padR));
      contentProps.h = Math.max(pxToInchY(1), (baseProps.h ?? 0) - pxToInchY(padT + padB));
    }

    const options: any = { ...contentProps };
    if (imageSrc.startsWith('data:')) {
      options.data = imageSrc;
    } else {
      options.path = imageSrc;
    }

    // SVG from emitSvgAsImage bakes opacity into the data URL — do not apply twice.
    if (element.tag !== 'svg') {
      const transparency = parseTransparency(element.styles?.opacity);
      if (transparency > 0) {
        options.transparency = transparency;
      }
    }

    // Handle object-fit. Force contain for formula/figure plates.
    // IMPORTANT: do not emit pptxgen `sizing: contain` — the imageSizing enhancer
    // strips <a:stretch> and leaves a zero srcRect, which PowerPoint often paints
    // as a duplicated/ghosted image (formula double-paint). Letterbox in geometry.
    let objectFit = element.styles.objectFit?.toLowerCase();
    if ((element as ElementInfo & { forceObjectFitContain?: boolean }).forceObjectFitContain) {
      objectFit = 'contain';
    }
    const natW = element.imageNaturalWidth || 0;
    const natH = element.imageNaturalHeight || 0;
    const boxW = Number(contentProps.w) || 0;
    const boxH = Number(contentProps.h) || 0;
    if (objectFit === 'contain' && natW > 0 && natH > 0 && boxW > 0 && boxH > 0) {
      const imgAspect = natW / natH;
      const boxAspect = boxW / boxH;
      let drawW = boxW;
      let drawH = boxH;
      if (imgAspect > boxAspect) {
        drawW = boxW;
        drawH = boxW / imgAspect;
      } else {
        drawH = boxH;
        drawW = boxH * imgAspect;
      }
      options.x = (contentProps.x ?? 0) + (boxW - drawW) / 2;
      options.y = (contentProps.y ?? 0) + (boxH - drawH) / 2;
      options.w = drawW;
      options.h = drawH;
    } else if (objectFit === 'cover') {
      options.sizing = {
        type: 'cover',
        w: contentProps.w,
        h: contentProps.h,
      };
    }

    return {
      type: 'image',
      options,
    };
  }

  /**
   * Convert video/audio to a slide image (placeholder when media unavailable).
   */
  private convertMediaPlaceholderElement(
    element: ElementInfo,
    baseProps: any,
    mediaType: 'video' | 'audio'
  ): any {
    if (!element.resourceUnavailable) {
      if (
        mediaType === 'video' &&
        element.poster &&
        !element.poster.startsWith('file:')
      ) {
        return {
          type: 'image',
          options: { ...baseProps, path: element.poster },
        };
      }
    }
    return this.buildPlaceholderImage(baseProps, mediaType);
  }

  /**
   * Convert canvas/SVG element (dataUrl is PNG from canvas or from SVG export) -> slide image
   */
  private convertCanvasElement(element: ElementInfo, baseProps: any): any {
    if (!element.dataUrl || element.resourceUnavailable) {
      return this.buildPlaceholderImage(baseProps, 'image');
    }

    const options: any = {
      ...baseProps,
      data: element.dataUrl,
    };

    // Native <canvas> pixels do not include element-level CSS opacity.
    // Playwright isolated screenshots already bake opacity into the PNG — do not apply twice.
    if (element.type === 'canvas' && !element.screenshotBakesOpacity) {
      const transparency = parseTransparency(element.styles?.opacity);
      if (transparency > 0) {
        options.transparency = transparency;
      }
    }

    return {
      type: 'image',
      options,
    };
  }

  /**
   * Convert table element
   */
  private convertTableElement(element: ElementInfo, baseProps: any): any {
    if (!element.tableData || element.tableData.rows.length === 0) {
      return null;
    }

    // Sample CSS cell padding for OOXML tcPr (pptxgen often drops margin:0).
    let samplePadPt = 0;

    const mapValign = (v: string | undefined): 'top' | 'middle' | 'bottom' => {
      const s = String(v || '').toLowerCase();
      if (s === 'top' || s === 'text-top' || s === 'baseline') return 'top';
      if (s === 'bottom' || s === 'text-bottom') return 'bottom';
      return 'middle';
    };

    const rows = element.tableData.rows.map((row) =>
      row.cells.map((cell) => {
        const cellStyles = cell.styles || {};
        const cellText = sanitizeTextForXml(cell.text);
        const cellHints = detectContainerScriptHints(cellText);
        const scriptSegments = splitTextByScript(cellText, cellHints);
        const primaryScript = scriptSegments[0]?.script ?? 'latin';
        const cellOptions = getTextOptions(cellStyles, this.platformFontContext, cellText);
        const cellFaces = this.resolveScriptFontFaces(cellStyles, primaryScript);
        if (cellFaces !== undefined) cellOptions.fontFace = cellFaces.latin;
        // Slide-space pt from CSS px (no arbitrary floor — host-fit may scale later).
        const fontPx = parseFloat(String(cellStyles.fontSize || '')) || 0;
        if (fontPx > 0) {
          cellOptions.fontSize = Math.round(inchToPoints(pxToInchY(fontPx)) * 10) / 10;
        }
        cellOptions.valign = mapValign(cellStyles.verticalAlign);
        // pptxgen margin = [left, right, bottom, top] in points
        const padL = parseFloat(String(cellStyles.paddingLeft || '0')) || 0;
        const padR = parseFloat(String(cellStyles.paddingRight || '0')) || 0;
        const padT = parseFloat(String(cellStyles.paddingTop || '0')) || 0;
        const padB = parseFloat(String(cellStyles.paddingBottom || '0')) || 0;
        const mL = inchToPoints(pxToInchX(padL));
        const mR = inchToPoints(pxToInchX(padR));
        const mT = inchToPoints(pxToInchY(padT));
        const mB = inchToPoints(pxToInchY(padB));
        cellOptions.margin = [mL, mR, mB, mT];
        samplePadPt = Math.max(samplePadPt, (mL + mR + mT + mB) / 4);

        const cellFill = getFillOptions(cellStyles);
        const cellBorder = getTableCellBorderOptions(
          cellStyles,
          cellStyles.effectiveBackgroundColor
        );

        const options: any = {
          ...cellOptions,
          ...cellFill,
          colspan: cell.colSpan,
          rowspan: cell.rowSpan,
        };
        if (cellBorder) options.border = cellBorder;

        let cellTextContent: string | Array<{ text: string; options: Record<string, unknown> }> =
          cellText;
        // Chromium's own wrap points, stated outright. Left to PowerPoint, a
        // cell that needs one more line grows its row and the table spills past
        // the height we declared, over whatever is under it. Frozen breaks plus
        // wrap:false remove that decision from the renderer.
        const frozenCellRuns = buildRunsFromLines(cellStyles, cell.lines, cellText);
        if (frozenCellRuns && scriptSegments.length <= 1) {
          cellTextContent = frozenCellRuns.map((run, index) => ({
            text: run.text,
            options: {
              ...cellOptions,
              ...(index > 0 ? { breakLine: true } : {}),
            },
          }));
          cellOptions.wrap = false;
        }
        if (scriptSegments.length > 1) {
          cellTextContent = scriptSegments.map((seg) => {
            const segOptions = getTextOptions(cellStyles, this.platformFontContext, seg.text);
            const segFaces = this.resolveScriptFontFaces(cellStyles, seg.script);
            if (segFaces !== undefined) segOptions.fontFace = segFaces.latin;
            if (fontPx > 0) {
              segOptions.fontSize = cellOptions.fontSize;
            }
            segOptions.margin = cellOptions.margin;
            return { text: seg.text, options: segOptions };
          });
        }

        return {
          text: cellTextContent,
          options,
        };
      })
    );

    const opts: any = {
      ...baseProps,
      // pptxgenjs addTable corrupts any negative x/y (multi-pass inch→EMU).
      x: clampPptxTablePositionInch(baseProps.x),
      y: clampPptxTablePositionInch(baseProps.y),
      rows,
    };

    // Prefer host origin so overflow tables sit inside the chrome card.
    if (element.tableHostBounds) {
      opts.x = clampPptxTablePositionInch(pxToInchX(element.tableHostBounds.x));
      opts.y = clampPptxTablePositionInch(pxToInchY(element.tableHostBounds.y));
    }

    // Pass column widths and row heights for compact layout (in inches)
    if (element.tableData.colW?.length) {
      const colW = element.tableData.colW.map((w: number) => Number(w) || 0);
      const sumW = colW.reduce((a, b) => a + b, 0);
      const hostW = element.tableHostBounds?.width || element.width;
      // Normalize columns to the host/table width so cells don't overlap.
      if (sumW > 0 && hostW > 0) {
        const scaleW = hostW / sumW;
        opts.colW = colW.map((w) => pxToInchX(w * scaleW));
        opts.w = pxToInchX(hostW);
      } else {
        opts.colW = colW.map((w) => pxToInchX(w));
      }
    }

    const rowHPx = (element.tableData.rowH || []).map((h: number) => Number(h) || 0);
    if (rowHPx.length) {
      const sumH = rowHPx.reduce((a, b) => a + b, 0);
      opts.rowH = rowHPx.map((h) => pxToInchY(h));
      opts.h = pxToInchY(sumH);
    }

    return {
      type: 'table',
      options: opts,
      // Post-process tcPr margins to match HTML padding (pptxgen often emits 0).
      _tableCellMarginPt: samplePadPt > 0 ? samplePadPt : undefined,
    };
  }

  /**
   * Box used for single-side border strips. Prefer the emitted fill/text geometry so
   * accent bars stay glued to callout plates after any fit/grow.
   */
  private resolveBorderDecorationBase(
    results: any[],
    baseProps: { x: number; y: number; w: number; h: number }
  ): { x: number; y: number; w: number; h: number } {
    const pick = (el: any): { x: number; y: number; w: number; h: number } | null => {
      const o = el?.options;
      if (!o) return null;
      const x = Number(o.x);
      const y = Number(o.y);
      const w = Number(o.w);
      const h = Number(o.h);
      if (![x, y, w, h].every((n) => Number.isFinite(n)) || w <= 0 || h <= 0) return null;
      return { x, y, w, h };
    };
    for (const el of results) {
      if (
        el?.type === 'roundRect' ||
        el?.type === 'rect' ||
        el?.type === 'shape' ||
        el?.type === 'ellipse'
      ) {
        const box = pick(el);
        if (box) return box;
      }
    }
    for (const el of results) {
      if (el?.type === 'text') {
        const box = pick(el);
        if (box) return box;
      }
    }
    return {
      x: Number(baseProps.x) || 0,
      y: Number(baseProps.y) || 0,
      w: Number(baseProps.w) || 0,
      h: Number(baseProps.h) || 0,
    };
  }

  /**
   * Get which sides are "special" (differ from majority) for single-side border
   * Returns array of { side: 0|1|2|3, widthPx, colorResult, borderStyle } for sides needing decorations
   */
  private getSpecialBorderSides(styles: any): { side: 0 | 1 | 2 | 3; widthPx: number; colorResult: any; borderStyle: string | undefined }[] {
    const parseW = (w: string | undefined) => (w ? parseFloat(w) || 0 : 0);
    const key = (w: number, c: string) => `${w}-${c || ''}`;
    const getColor = (side: number) => (side === 0 ? styles.borderLeftColor : side === 1 ? styles.borderTopColor : side === 2 ? styles.borderRightColor : styles.borderBottomColor);
    const sides: { side: 0 | 1 | 2 | 3; w: number; c: string; s: string | undefined }[] = [
      { side: 0 as const, w: parseW(styles.borderLeftWidth), c: styles.borderLeftColor, s: styles.borderLeftStyle },
      { side: 1 as const, w: parseW(styles.borderTopWidth), c: styles.borderTopColor, s: styles.borderTopStyle },
      { side: 2 as const, w: parseW(styles.borderRightWidth), c: styles.borderRightColor, s: styles.borderRightStyle },
      { side: 3 as const, w: parseW(styles.borderBottomWidth), c: styles.borderBottomColor, s: styles.borderBottomStyle },
    ].filter((x) => x.w >= 1) as { side: 0 | 1 | 2 | 3; w: number; c: string; s: string | undefined }[];
    const toResult = (x: (typeof sides)[0]) => ({ side: x.side, widthPx: x.w, colorResult: parseColorUtil(getColor(x.side)), borderStyle: x.s });
    // L/T/U partial borders: every bordered side needs its own strip (not a full-rect outline).
    if (sides.length < 4) return sides.map(toResult);
    const counts: Record<string, number> = {};
    for (const x of sides) {
      const k = key(x.w, x.c);
      counts[k] = (counts[k] || 0) + 1;
    }
    const majority = Object.entries(counts).sort((a, b) => b[1] - a[1])[0];
    if (!majority || majority[1] < 2) return sides.map(toResult);
    const commonKey = majority[0];
    const special = sides.filter((x) => key(x.w, x.c) !== commonKey);
    return special.map(toResult);
  }

  /**
   * Create border decoration elements for special single-side borders only
   * Main element gets common border; special sides get separate shapes (custGeom when rounded)
   */
  private createBorderDecorations(element: ElementInfo, baseProps: any): any[] {
    const decorations: any[] = [];
    const styles = element.styles;
    const cornerRadii = parseCornerRadii(styles.borderRadius, element.width, element.height);
    const hasBorderRadius = cornerRadii.some((r) => r > 0);
    const elementOpacity = parseFloat(String(styles.opacity ?? '1')) || 1;

    const effectiveAlpha = (alpha: number | undefined) => {
      const base = alpha !== undefined ? alpha : 1;
      return Math.min(1, Math.max(0, base * elementOpacity));
    };

    const toBorderFill = (colorResult: { color: string; alpha?: number } | undefined) => {
      if (!colorResult) return undefined;
      const fill: { color: string; transparency?: number } = { color: colorResult.color };
      const alpha = effectiveAlpha(colorResult.alpha);
      if (alpha < 1) {
        fill.transparency = Math.round((1 - alpha) * 100);
      }
      return fill;
    };

    const toLineOptions = (colorResult: { color: string; alpha?: number } | undefined, widthPt: number, dashType: string) => {
      if (!colorResult) return undefined;
      const line: { color: string; width: number; dashType?: string; transparency?: number } = {
        color: colorResult.color,
        width: Math.max(0.5, widthPt),
      };
      if (dashType !== 'solid') line.dashType = dashType as any;
      const alpha = effectiveAlpha(colorResult.alpha);
      if (alpha < 1) {
        line.transparency = Math.round((1 - alpha) * 100);
      }
      return line;
    };

    const specialSides = this.getSpecialBorderSides(styles);
    for (const { side, widthPx, colorResult, borderStyle } of specialSides) {
      if (!colorResult) continue;
      const dashType = parseBorderStyleToDashType(borderStyle);
      const widthInch =
        side === 0 || side === 2 ? pxToInchX(widthPx) : pxToInchY(widthPx);

      if (dashType !== 'solid') {
        const lineOpts = toLineOptions(colorResult, widthPx * 0.5, dashType);
        if (!lineOpts) continue;
        if (side === 0 || side === 2) {
          const x = side === 0 ? baseProps.x : baseProps.x + baseProps.w - widthInch;
          decorations.push({ type: 'line', options: { x, y: baseProps.y + baseProps.h / 2, w: 0, h: baseProps.h, line: lineOpts } });
        } else {
          let y = side === 1 ? baseProps.y : baseProps.y + baseProps.h - widthInch;
          // Text underline strip: sit below descenders, not through q/g/y.
          if (
            side === 3 &&
            element.type === 'text' &&
            widthPx <= 6 &&
            specialSides.length === 1
          ) {
            y += pxToInchY(ElementConverter.ACCENT_DESCENDER_CLEAR_PX);
          }
          decorations.push({ type: 'line', options: { x: baseProps.x + baseProps.w / 2, y, w: baseProps.w, h: 0, line: lineOpts } });
        }
      } else {
        const fill = toBorderFill(colorResult);
        if (!fill) continue;
        let rectOpts: any;
        if (side === 0) rectOpts = { x: baseProps.x, y: baseProps.y, w: widthInch, h: baseProps.h, fill, line: { type: 'none' as const } };
        else if (side === 1) rectOpts = { x: baseProps.x, y: baseProps.y, w: baseProps.w, h: widthInch, fill, line: { type: 'none' as const } };
        else if (side === 2) rectOpts = { x: baseProps.x + baseProps.w - widthInch, y: baseProps.y, w: widthInch, h: baseProps.h, fill, line: { type: 'none' as const } };
        else {
          let y = baseProps.y + baseProps.h - widthInch;
          if (
            element.type === 'text' &&
            widthPx <= 6 &&
            specialSides.length === 1
          ) {
            y += pxToInchY(ElementConverter.ACCENT_DESCENDER_CLEAR_PX);
          }
          rectOpts = { x: baseProps.x, y, w: baseProps.w, h: widthInch, fill, line: { type: 'none' as const } };
        }

        if (hasBorderRadius) {
          const shape = { type: 'rect' as const, options: rectOpts };
          (shape as any)._singleSideBorder = {
            side,
            borderWidthInch: widthInch,
            elementWidthInch: baseProps.w,
            elementHeightInch: baseProps.h,
            cornerRadiiInch: cornerRadii,
          };
          decorations.push(shape);
        } else {
          decorations.push({ type: 'rect', options: rectOpts });
        }
      }
    }
    return decorations;
  }

  /**
   * Convert shape element (div with background/border)
   */
  private convertShapeElement(
    element: ElementInfo,
    baseProps: any,
    slideIndex: number = 0,
    elementIndex: number = 0,
    slideStartY: number = 0
  ): any {
    // clip-path polygon ∩ box → rect placeholder + custGeom via post-processing
    // Table chrome must stay a circular roundRect (never custGeom ellipse-ish arcs).
    if (
      !element.tableChrome &&
      element.clipPathPolygonPx &&
      element.clipPathPolygonPx.length >= 3
    ) {
      const wPx = element.width;
      const hPx = element.height;
      if (wPx > 0 && hPx > 0) {
        const fillOptions = getFillOptions(element.styles, element);
        const lineOptions = getLineOptions(element.styles);
        const options: any = {
          ...baseProps,
          ...fillOptions,
        };
        const borderType = this.getBorderType(element.styles);
        if (borderType === 'uniform' && lineOptions) {
          options.line = lineOptions;
        } else if (borderType === 'single') {
          const commonLine = this.getCommonLineOptions(element.styles);
          if (commonLine) options.line = commonLine;
        }
        const normalized = element.clipPathPolygonPx.map((p) => ({
          x: Math.round(Math.min(21600, Math.max(0, (p.x / wPx) * 21600))),
          y: Math.round(Math.min(21600, Math.max(0, (p.y / hPx) * 21600))),
        }));
        const shapeResult: any = {
          type: 'rect',
          options,
          _clipPathPolygonNormalized: normalized,
          _clipPathPolygonClosed: true,
        };
        if (options.fill) {
          shapeResult._prefersGradient = true;
        }
        return shapeResult;
      }
    }

    const fillOptions = getFillOptions(element.styles, element);
    const lineOptions = getLineOptions(element.styles);
    const boxShadowInfo = parseBoxShadowClassified(element.styles.boxShadow);
    // Table cards use directional outer shadow (HTML elevation), not soft glow.
    let shadow = element.tableChrome
      ? parseBoxShadow(element.styles.boxShadow)
      : boxShadowInfo?.effect === 'shadow'
        ? parseBoxShadow(element.styles.boxShadow)
        : undefined;
    // Glow data will be registered as an enhancement (injected as XML post-processing)
    const glowData =
      !element.tableChrome && boxShadowInfo?.effect === 'glow'
        ? {
            radiusPt: Math.max(1, Math.min(500, pxToPoints(boxShadowInfo.blur))),
            color: boxShadowInfo.color,
            alpha: boxShadowInfo.alpha,
          }
        : undefined;
    const cornerRadii = parseCornerRadii(
      element.styles.borderRadius,
      element.width,
      element.height
    );
    const isUniformCorner =
      cornerRadii.every((radius) => Math.abs(radius - cornerRadii[0]) < 0.0001);
    const borderRadius = isUniformCorner ? cornerRadii[0] : undefined;

    const options: any = {
      ...baseProps,
      ...fillOptions,
    };
    // Geometry is owned by Chromium; thin rules and connectors are never nudged.

    // Add line if it exists: uniform = all sides; single = common sides (main el), special sides as decorations on top
    const borderType = this.getBorderType(element.styles);
    if (borderType === 'uniform' && lineOptions) {
      options.line = lineOptions;
    } else if (borderType === 'single') {
      const commonLine = this.getCommonLineOptions(element.styles);
      if (commonLine) options.line = commonLine;
    }

    const blurPx = parseBlurFilter(element.styles.filter);
    let softEdgeRadiusPt: number | undefined;
    let softEdgeShadow:
      | {
          blurPt: number;
          distPt: number;
          angleDeg: number;
          color: string;
          opacity: number;
        }
      | undefined;

    if (blurPx && blurPx > 0) {
      const expandInch = pxToInch(blurPx);
      if (expandInch > 0) {
        const originalX = options.x ?? 0;
        const originalY = options.y ?? 0;
        const originalW = options.w ?? 0;
        const originalH = options.h ?? 0;

        const newX = originalX - expandInch;
        const newY = originalY - expandInch;
        const newW = originalW + expandInch * 2;
        const newH = originalH + expandInch * 2;

        options.x = newX;
        options.y = newY;
        options.w = newW;
        options.h = newH;

        baseProps.x = newX;
        baseProps.y = newY;
        baseProps.w = newW;
        baseProps.h = newH;
      }
    }

    if (!shadow) {
      if (blurPx && blurPx > 0) {
        // 1:1 CSS blur → softEdge radius (no *2.15 inflate / opacity invention).
        const blurPt = Math.max(1, Math.min(500, pxToPoints(blurPx)));
        const fillColor =
          (options.fill &&
            typeof options.fill === 'object' &&
            typeof (options.fill as any).color === 'string')
            ? (options.fill as any).color
            : parseColorUtil(element.styles.backgroundColor)?.color;

        const fillTransparency =
          options.fill &&
          typeof options.fill === 'object' &&
          typeof (options.fill as any).transparency === 'number'
            ? Math.min(Math.max((options.fill as any).transparency, 0), 100)
            : undefined;
        const styleOpacity =
          typeof element.styles.opacity === 'number' && !Number.isNaN(element.styles.opacity)
            ? Math.min(Math.max(element.styles.opacity, 0), 1)
            : undefined;

        const opacityFromFill =
          fillTransparency !== undefined ? 1 - Math.min(Math.max(fillTransparency / 100, 0), 1) : undefined;
        const resolvedOpacity = opacityFromFill ?? styleOpacity ?? 1.0;
        const opacity = Math.max(0, Math.min(1, resolvedOpacity));

        shadow = undefined;
        softEdgeRadiusPt = blurPt;
        softEdgeShadow = {
          blurPt,
          distPt: 0,
          angleDeg: 0,
          color: fillColor ?? '000000',
          opacity,
        };
      }
    }

    if (shadow) {
      options.shadow = shadow;
    }

    // Check for single-corner rounded (e.g. border-bottom-left-radius: 100%)
    const nonZeroCorners = cornerRadii.filter((r) => r > 0).length;

    if (nonZeroCorners === 1) {
      // Use rect; enhancer will replace with custGeom path
      const wInch = baseProps.w ?? pxToInchX(element.width);
      const hInch = baseProps.h ?? pxToInchY(element.height);

      const singleCornerResult: any = {
        type: 'rect',
        options,
        _singleCornerRadii: cornerRadii,
        _shapeWidthInch: wInch,
        _shapeHeightInch: hInch,
      };
      if (glowData) {
        singleCornerResult._glowData = glowData;
      }
      if (softEdgeRadiusPt !== undefined) {
        singleCornerResult._softEdge = { radiusPt: softEdgeRadiusPt, shadow: softEdgeShadow };
      }
      return singleCornerResult;
    }

    // Determine shape type based on border radius (uniform or multiple corners)
    let shapeType = 'rect';

    if (borderRadius) {
      const widthInch = baseProps.w ?? pxToInchX(element.width);
      const heightInch = baseProps.h ?? pxToInchY(element.height);
      const minDimension = Math.min(widthInch, heightInch);
      const maxCorner = Math.max(...cornerRadii);

      // Ellipse only for CSS circles (border-radius ≥ 50% of both axes).
      const wRatio = widthInch > 0 ? maxCorner / (widthInch / 2) : 0;
      const hRatio = heightInch > 0 ? maxCorner / (heightInch / 2) : 0;

      if (!element.tableChrome && wRatio >= 1.0 && hRatio >= 1.0) {
        shapeType = 'ellipse';
        delete options.rectRadius;
      } else {
        shapeType = 'roundRect';
        const maxAllowed = minDimension / 2;
        options.rectRadius = Math.min(borderRadius, maxAllowed);
      }
    }

    const shapeResult: any = {
      type: shapeType,
      options,
    };
    if (options.fill) {
      shapeResult._prefersGradient = true;
    }
    if (glowData) {
      shapeResult._glowData = glowData;
    }
    if (softEdgeRadiusPt !== undefined) {
      shapeResult._softEdge = { radiusPt: softEdgeRadiusPt, shadow: softEdgeShadow };
    }

    return shapeResult;
  }
}
