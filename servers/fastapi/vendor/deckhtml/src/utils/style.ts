/**
 * CSS to PPTX style mapping utilities
 */

import { ComputedStyles, GradientData, GradientStop } from '../types';
import {
  inchToPoints,
  pxToInch,
  pxToInchX,
  pxToPoints,
  pxToSlidePointsY,
  SLIDE_HEIGHT_INCH,
  SLIDE_WIDTH_INCH,
} from './coordinate';
import { isChineseFont, splitFontStack } from './chineseFonts';
import {
  detectStackGenericKind,
  getPlatformMappedFont,
  getPlatformMappedFontByToken,
  isGenericFontToken,
  isPlatformFontContextActive,
  PlatformFontContext,
  PlatformFontLang,
  resolveFontFamilyForPlatform,
} from './platformFontMap';
import { detectContainerScriptHints, splitTextByScript } from './textScript';

/**
 * Sanitize text for XML/PPTX compatibility - remove control characters that cause Office repair
 * XML 1.0 allows: #x9, #xA, #xD, #x20-#xD7FF, #xE000-#xFFFD
 *
 * LLMs often emit vertical tab (U+000B) as a soft line hint. Deleting it glues
 * words ("Insert\u000bhere" → "Inserthere"); map C0 controls to a space instead.
 */
export function sanitizeTextForXml(text: string): string {
  if (!text || typeof text !== 'string') return text;
  return text
    .replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g, ' ')
    .replace(/[ \t\u00A0]{2,}/g, ' ');
}

/** Relative luminance 0–1 for hex RRGGBB (sRGB) */
function hexLuminance(hex6: string): number {
  const r = parseInt(hex6.slice(0, 2), 16) / 255;
  const g = parseInt(hex6.slice(2, 4), 16) / 255;
  const b = parseInt(hex6.slice(4, 6), 16) / 255;
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** HSL (degrees, 0–100, 0–100) → sRGB 0–255 */
function hslToRgb(h: number, s: number, l: number): { r: number; g: number; b: number } {
  let hue = h % 360;
  if (hue < 0) hue += 360;
  const sat = Math.max(0, Math.min(100, s)) / 100;
  const light = Math.max(0, Math.min(100, l)) / 100;
  const a = sat * Math.min(light, 1 - light);
  const f = (n: number) => {
    const k = (n + hue / 30) % 12;
    return light - a * Math.max(Math.min(k - 3, 9 - k, 1), -1);
  };
  return {
    r: Math.round(f(0) * 255),
    g: Math.round(f(8) * 255),
    b: Math.round(f(4) * 255),
  };
}

/**
 * Convert Oklab (L,a,b) to sRGB, returns {r,g,b} 0-255
 * Tailwind v4 and modern CSS use oklab()
 */
function oklabToSrgb(L: number, aVal: number, bVal: number): { r: number; g: number; b: number } {
  const l_ = L + aVal * 0.3963377774 + bVal * 0.2158037573;
  const m_ = L + aVal * -0.1055613458 + bVal * -0.0638541728;
  const s_ = L + aVal * -0.0894841775 + bVal * -1.291485548;
  const l = l_ ** 3;
  const m = m_ ** 3;
  const s = s_ ** 3;
  const linearToGamma = (c: number) =>
    c >= 0.0031308 ? 1.055 * Math.pow(c, 1 / 2.4) - 0.055 : 12.92 * c;
  const rVal = 255 * linearToGamma(l * 4.0767416621 + m * -3.3077115913 + s * 0.2309699292);
  const gVal = 255 * linearToGamma(l * -1.2684380046 + m * 2.6097574011 + s * -0.3413193965);
  const bVal2 = 255 * linearToGamma(l * -0.0041960863 + m * -0.7034186147 + s * 1.707614701);
  return {
    r: Math.round(Math.max(0, Math.min(255, rVal))),
    g: Math.round(Math.max(0, Math.min(255, gVal))),
    b: Math.round(Math.max(0, Math.min(255, bVal2))),
  };
}

/**
 * Parse CSS color to hex format (RRGGBB without #) and extract alpha
 * PowerPoint uses hex colors without the # prefix
 * Returns { color: string, alpha?: number } where alpha is 0-1
 */
export function parseColor(color: string | undefined): { color: string; alpha?: number } | undefined {
  if (!color) return undefined;

  // Handle transparent / none
  if (color === 'transparent' || color === 'none') return undefined;

  // Handle oklch() - Tailwind v4, OKLCH (L chroma hue / alpha)
  const oklchMatch = color.match(/oklch\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)(?:\s*\/\s*([\d.]+))?\)/);
  if (oklchMatch) {
    const L = parseFloat(oklchMatch[1]);
    const C = parseFloat(oklchMatch[2]);
    const H = parseFloat(oklchMatch[3]); // hue in degrees
    const alpha = oklchMatch[4] !== undefined ? parseFloat(oklchMatch[4]) : 1;
    if (alpha === 0) return undefined;
    const Hrad = (H * Math.PI) / 180;
    const aVal = C * Math.cos(Hrad);
    const bVal = C * Math.sin(Hrad);
    const rgb = oklabToSrgb(L, aVal, bVal);
    const hex = [rgb.r, rgb.g, rgb.b]
      .map((v) => v.toString(16).padStart(2, '0').toUpperCase())
      .join('');
    return { color: hex, alpha: alpha < 1 ? alpha : undefined };
  }

  // Handle oklab() - Tailwind v4, modern CSS
  const oklabMatch = color.match(/oklab\(\s*([\d.+-]+)\s+([\d.+-]+)\s+([\d.+-]+)(?:\s*\/\s*([\d.]+))?\)/);
  if (oklabMatch) {
    const L = parseFloat(oklabMatch[1]);
    const a = parseFloat(oklabMatch[2]);
    const b = parseFloat(oklabMatch[3]);
    const alpha = oklabMatch[4] !== undefined ? parseFloat(oklabMatch[4]) : 1;
    if (alpha === 0) return undefined;
    const rgb = oklabToSrgb(L, a, b);
    const hex = [rgb.r, rgb.g, rgb.b]
      .map((v) => v.toString(16).padStart(2, '0').toUpperCase())
      .join('');
    return { color: hex, alpha: alpha < 1 ? alpha : undefined };
  }

  // hsl() / hsla() — comma or space syntax (Tailwind hsl(var(...)))
  const hslComma = color.match(
    /^hsla?\(\s*([\d.]+)\s*,\s*([\d.]+)%\s*,\s*([\d.]+)%(?:\s*,\s*([\d.]+))?\s*\)$/i
  );
  if (hslComma) {
    const alpha = hslComma[4] !== undefined ? parseFloat(hslComma[4]) : 1;
    if (alpha === 0) return undefined;
    const rgb = hslToRgb(parseFloat(hslComma[1]), parseFloat(hslComma[2]), parseFloat(hslComma[3]));
    const hex = [rgb.r, rgb.g, rgb.b]
      .map((v) => v.toString(16).padStart(2, '0').toUpperCase())
      .join('');
    return { color: hex, alpha: alpha < 1 ? alpha : undefined };
  }
  const hslSpace = color.match(
    /^hsla?\(\s*([\d.]+)\s+([\d.]+)%\s+([\d.]+)%(?:\s*\/\s*([\d.]+))?\s*\)$/i
  );
  if (hslSpace) {
    const alpha = hslSpace[4] !== undefined ? parseFloat(hslSpace[4]) : 1;
    if (alpha === 0) return undefined;
    const rgb = hslToRgb(parseFloat(hslSpace[1]), parseFloat(hslSpace[2]), parseFloat(hslSpace[3]));
    const hex = [rgb.r, rgb.g, rgb.b]
      .map((v) => v.toString(16).padStart(2, '0').toUpperCase())
      .join('');
    return { color: hex, alpha: alpha < 1 ? alpha : undefined };
  }

  // rgb() / rgba() — space-separated (CSS Color 4), e.g. rgb(30 64 175 / 1)
  const rgbSpace = color.match(/^rgba?\(\s*(\d+)\s+(\d+)\s+(\d+)(?:\s*\/\s*([\d.]+))?\s*\)$/i);
  if (rgbSpace) {
    const alpha = rgbSpace[4] !== undefined ? parseFloat(rgbSpace[4]) : 1;
    if (alpha === 0) return undefined;
    const r = parseInt(rgbSpace[1], 10).toString(16).padStart(2, '0').toUpperCase();
    const g = parseInt(rgbSpace[2], 10).toString(16).padStart(2, '0').toUpperCase();
    const b = parseInt(rgbSpace[3], 10).toString(16).padStart(2, '0').toUpperCase();
    return { color: `${r}${g}${b}`, alpha: alpha < 1 ? alpha : undefined };
  }

  // Handle rgba - check alpha channel
  const rgbaMatch = color.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)/);
  if (rgbaMatch) {
    const alpha = rgbaMatch[4] ? parseFloat(rgbaMatch[4]) : 1;

    // If fully transparent, return undefined
    if (alpha === 0) return undefined;

    const r = parseInt(rgbaMatch[1]).toString(16).padStart(2, '0').toUpperCase();
    const g = parseInt(rgbaMatch[2]).toString(16).padStart(2, '0').toUpperCase();
    const b = parseInt(rgbaMatch[3]).toString(16).padStart(2, '0').toUpperCase();

    return { color: `${r}${g}${b}`, alpha: alpha < 1 ? alpha : undefined };
  }

  // Already hex
  if (color.startsWith('#')) {
    return color.length === 7 ? { color: color.substring(1).toUpperCase() } : undefined;
  }

  // Named colors - map common ones (without #)
  const namedColors: Record<string, string> = {
    black: '000000',
    white: 'FFFFFF',
    red: 'FF0000',
    green: '008000',
    blue: '0000FF',
    yellow: 'FFFF00',
    gray: '808080',
    transparent: undefined as any,
  };

  const namedColor = namedColors[color.toLowerCase()];
  return namedColor ? { color: namedColor } : undefined;
}

/**
 * Parse font size from CSS to points (1:1 with CSS px via pxToPoints).
 * Viewport scaling (e.g. 1920→1280) is applied transparently inside `pxToPoints`.
 */
export function parseFontSize(fontSize: string | undefined): number {
  if (!fontSize) return 12;

  const px = parseFloat(fontSize);
  if (isNaN(px)) return 12;

  return Math.round(pxToPoints(px));
}

/**
 * Font size for pill/chip badges (roundRect + text).
 * Use slide-space pt so glyph size matches the HTML border-box (px→inch geometry).
 * Preferring the larger font-calibrated size overflows tight chips in PPT.
 */
export function parsePillFontSize(fontSize: string | undefined): number {
  const px = parseFloat(String(fontSize ?? ''));
  if (isNaN(px) || px <= 0) return parseFontSize(fontSize);
  const spatialPt = inchToPoints(pxToInch(px));
  return Math.max(1, Math.round(spatialPt * 10) / 10);
}

/** Conservative PPT glyph width (em) — Arial Bold runs wider than many web faces. */
function pillGlyphEm(bold?: boolean): number {
  return bold ? 0.72 : 0.62;
}

/** Estimated text width in inches for a nowrap pill label at `fontSizePt`. */
export function estimatePillTextWidthInch(opts: {
  fontSizePt: number;
  text: string;
  bold?: boolean;
  charSpacingPt?: number;
}): number {
  const text = (opts.text || '').replace(/\s+/g, ' ').trim();
  const size = opts.fontSizePt;
  if (!text || !(size > 0)) return 0;
  const spacingEm = opts.charSpacingPt && size > 0 ? opts.charSpacingPt / size : 0;
  return (text.length * (pillGlyphEm(opts.bold) + spacingEm) * size) / 72;
}

/**
 * Shrink pill font so estimated text width fits the content box (last resort).
 * Prefer {@link layoutPillBoxForText} (grow chip) so padding/font weight stay HTML-like.
 */
export function fitPillFontSizeToBox(opts: {
  fontSizePt: number;
  text: string;
  boxWidthInch: number;
  marginLeftPt: number;
  marginRightPt: number;
  bold?: boolean;
  charSpacingPt?: number;
}): number {
  const text = (opts.text || '').replace(/\s+/g, ' ').trim();
  let size = opts.fontSizePt;
  if (!text || !(opts.boxWidthInch > 0) || !(size > 0)) return size;

  const marginInch = (Math.max(0, opts.marginLeftPt) + Math.max(0, opts.marginRightPt)) / 72;
  const contentInch = opts.boxWidthInch - marginInch;
  if (!(contentInch > 0.02)) return size;

  const target = contentInch * 0.98;
  for (let i = 0; i < 10; i++) {
    const textInch = estimatePillTextWidthInch({
      fontSizePt: size,
      text,
      bold: opts.bold,
      charSpacingPt: opts.charSpacingPt,
    });
    if (textInch <= target) break;
    size = Math.max(6, size * (target / textInch));
  }
  return Math.max(6, Math.round(size * 10) / 10);
}

/**
 * Settle a chip's box, padding and font in one place.
 *
 * The order matters and is the whole point: the box grows into whatever room
 * the neighbours leave, then the chip's own padding gives way, and only then
 * the type. Padding is air; type is content. Held the other way round, a chip
 * whose growth was capped by the sibling on its right had nothing left but its
 * font, so the middle chips of a row shrank while the last one -- with open
 * space beside it -- kept full size.
 *
 * Both the conversion path and the pre-pass that agrees one size for a row call
 * this. They must, or they answer differently: a pre-pass that skipped the
 * padding step computed a harsher factor and imposed it on the whole row, and
 * chips that had been exporting at their authored size lost 20% of it.
 */
export function fitPillBox(opts: {
  fontSizePt: number;
  text: string;
  xInch: number;
  yInch: number;
  wInch: number;
  hInch: number;
  marginLeftPt: number;
  marginRightPt: number;
  marginTopPt: number;
  marginBottomPt: number;
  bold?: boolean;
  charSpacingPt?: number;
  maxGrowInch?: number;
  minLeftInch?: number;
  maxRightInch?: number;
  preferShrinkFont?: boolean;
}): {
  x: number;
  y: number;
  w: number;
  h: number;
  fontSizePt: number;
  marginLeftPt: number;
  marginRightPt: number;
} {
  const authoredMl = Math.max(0, opts.marginLeftPt);
  const authoredMr = Math.max(0, opts.marginRightPt);
  const needContentInch =
    estimatePillTextWidthInch({
      fontSizePt: opts.fontSizePt,
      text: opts.text,
      bold: opts.bold,
      charSpacingPt: opts.charSpacingPt,
    }) / 0.98;
  const growRoom = Math.max(
    0,
    Math.min(
      (opts.maxRightInch ?? SLIDE_WIDTH_INCH) - (opts.xInch + opts.wInch),
      opts.maxGrowInch ?? pxToInchX(48)
    )
  );
  let usableMl = authoredMl;
  let usableMr = authoredMr;
  const shortfallInch =
    needContentInch + (authoredMl + authoredMr) / 72 - (opts.wInch + growRoom);
  if (shortfallInch > 1e-6 && authoredMl + authoredMr > 0) {
    // The floor keeps a chip from becoming a box drawn tight around its
    // letters: 40% of the authored padding still reads as a chip.
    const trimPt = Math.min(shortfallInch * 72, (authoredMl + authoredMr) * 0.6);
    const share = trimPt / (authoredMl + authoredMr);
    usableMl = authoredMl * (1 - share);
    usableMr = authoredMr * (1 - share);
  }
  const laidOut = layoutPillBoxForText({
    ...opts,
    marginLeftPt: usableMl,
    marginRightPt: usableMr,
  });
  return { ...laidOut, marginLeftPt: usableMl, marginRightPt: usableMr };
}

/**
 * Grow a nowrap pill box so full HTML font size + CSS padding still fit in PPT metrics.
 * Shrinking the font first makes chips look “too tight” (padding air collapses).
 *
 * Optional sibling bounds (`minLeftInch` / `maxRightInch`) keep flex-row chips from
 * growing into neighbors. Compact chips can prefer shrink over large grow.
 */
export function layoutPillBoxForText(opts: {
  fontSizePt: number;
  text: string;
  xInch: number;
  yInch: number;
  wInch: number;
  hInch: number;
  marginLeftPt: number;
  marginRightPt: number;
  marginTopPt: number;
  marginBottomPt: number;
  bold?: boolean;
  charSpacingPt?: number;
  /** Cap how far we expand past the HTML box (default ~48 CSS px). */
  maxGrowInch?: number;
  /** Do not expand left of this edge (prior sibling in a flex row). */
  minLeftInch?: number;
  /** Do not expand right of this edge (next sibling in a flex row). */
  maxRightInch?: number;
  /** Prefer font shrink over growing into a tight flex gap. */
  preferShrinkFont?: boolean;
  /**
   * Chromium's own measurement of the text at the authored size, in inches.
   *
   * The estimator below is a model of PowerPoint's metrics, needed when the
   * reader's machine substitutes a face. This deck embeds its fonts, so
   * PowerPoint lays the text out with the very face Chromium measured, and the
   * model's safety margin becomes pessimism that gets paid for by shrinking
   * type. A measurement, where one exists, beats a model of one.
   */
  measuredContentWidthInch?: number;
}): { x: number; y: number; w: number; h: number; fontSizePt: number } {
  const maxGrow = opts.maxGrowInch ?? pxToInchX(48);
  let fontSize = opts.fontSizePt;
  let x = opts.xInch;
  let y = opts.yInch;
  let w = opts.wInch;
  let h = opts.hInch;
  const ml = Math.max(0, opts.marginLeftPt) / 72;
  const mr = Math.max(0, opts.marginRightPt) / 72;
  const mt = Math.max(0, opts.marginTopPt) / 72;
  const mb = Math.max(0, opts.marginBottomPt) / 72;
  const minLeft = opts.minLeftInch ?? 0;
  const maxRight = opts.maxRightInch ?? SLIDE_WIDTH_INCH;

  const needContentW =
    opts.measuredContentWidthInch !== undefined && opts.measuredContentWidthInch > 0
      ? opts.measuredContentWidthInch
      : estimatePillTextWidthInch({
          fontSizePt: fontSize,
          text: opts.text,
          bold: opts.bold,
          charSpacingPt: opts.charSpacingPt,
        }) / 0.98;
  const needW = needContentW + ml + mr;
  if (needW > w + 1e-6) {
    const roomLeft = Math.max(0, x - minLeft);
    const roomRight = Math.max(0, maxRight - (x + w));
    const growWanted = needW - w;
    // Compact flex chips: avoid eating the ~10px gap between neighbors.
    const allowGrow =
      !opts.preferShrinkFont || growWanted <= Math.max(roomLeft, roomRight, pxToInchX(4));
    if (allowGrow) {
      const grow = Math.min(growWanted, maxGrow, roomLeft + roomRight);
      // Prefer expanding into free side; right-half chips still favor left when both open.
      if (roomLeft > 0 && (roomLeft >= roomRight || x + w / 2 > SLIDE_WIDTH_INCH * 0.45)) {
        const leftGrow = Math.min(grow, roomLeft);
        x -= leftGrow;
        w += leftGrow;
        const rightGrow = Math.min(Math.max(0, grow - leftGrow), roomRight);
        w += rightGrow;
      } else {
        const rightGrow = Math.min(grow, roomRight);
        w += rightGrow;
        const leftGrow = Math.min(Math.max(0, grow - rightGrow), roomLeft);
        x -= leftGrow;
        w += leftGrow;
      }
    }
  }

  // Keep vertical padding air: content box ≥ ~1.22× font (CSS padding must remain visible).
  const minContentH = (fontSize * 1.22) / 72;
  const needH = minContentH + mt + mb;
  if (needH > h + 1e-6) {
    const grow = Math.min(needH - h, maxGrow);
    y -= grow / 2;
    h += grow;
    if (y < 0) {
      h += y;
      y = 0;
    }
  }

  // Clamp to slide; then shrink font only if still overflowing width.
  if (x + w > SLIDE_WIDTH_INCH) w = Math.max(0.05, SLIDE_WIDTH_INCH - x);
  if (y + h > SLIDE_HEIGHT_INCH) h = Math.max(0.05, SLIDE_HEIGHT_INCH - y);
  if (x < 0) {
    w += x;
    x = 0;
  }

  fontSize = fitPillFontSizeToBox({
    fontSizePt: fontSize,
    text: opts.text,
    boxWidthInch: w,
    marginLeftPt: opts.marginLeftPt,
    marginRightPt: opts.marginRightPt,
    bold: opts.bold,
    charSpacingPt: opts.charSpacingPt,
  });

  return {
    x,
    y,
    w,
    h,
    fontSizePt: fontSize,
  };
}

export interface ParseScriptFontFacesOptions {
  platformFontContext?: PlatformFontContext;
  specifiedFontFamily?: string;
  textScript?: PlatformFontLang;
}

/**
 * Parse font family, return first available font
 */
export function parseFontFamily(
  fontFamily: string | undefined,
  ctx?: PlatformFontContext,
  lang: PlatformFontLang = 'latin'
): string {
  if (!fontFamily) {
    return isPlatformFontContextActive(ctx)
      ? getPlatformMappedFont('sans', ctx, lang)
      : 'Arial';
  }

  const firstFont = fontFamily.split(',')[0].trim().replace(/['"]/g, '');
  const lower = firstFont.toLowerCase();

  if (isPlatformFontContextActive(ctx)) {
    const mapped = getPlatformMappedFontByToken(firstFont, ctx, lang);
    if (mapped) return mapped;
  }

  const fontMap: Record<string, string> = {
    'sans-serif': isPlatformFontContextActive(ctx)
      ? getPlatformMappedFont('sans', ctx, lang)
      : 'Arial',
    serif: isPlatformFontContextActive(ctx)
      ? getPlatformMappedFont('serif', ctx, lang)
      : 'Times New Roman',
    monospace: isPlatformFontContextActive(ctx)
      ? getPlatformMappedFont('monospace', ctx, lang)
      : 'Courier New',
    cursive: isPlatformFontContextActive(ctx)
      ? getPlatformMappedFont('cursive', ctx, lang)
      : 'Comic Sans MS',
    fantasy: isPlatformFontContextActive(ctx)
      ? getPlatformMappedFont('fantasy', ctx, lang)
      : 'Impact',
    math: isPlatformFontContextActive(ctx)
      ? getPlatformMappedFont('math', ctx, lang)
      : 'Cambria Math',
    'system-ui': isPlatformFontContextActive(ctx)
      ? getPlatformMappedFontByToken('system-ui', ctx, lang) ?? getPlatformMappedFont('sans', ctx, lang)
      : 'Arial',
    'ui-sans-serif': isPlatformFontContextActive(ctx)
      ? getPlatformMappedFontByToken('ui-sans-serif', ctx, lang) ?? getPlatformMappedFont('sans', ctx, lang)
      : 'Arial',
    'ui-serif': isPlatformFontContextActive(ctx)
      ? getPlatformMappedFontByToken('ui-serif', ctx, lang) ?? getPlatformMappedFont('serif', ctx, lang)
      : 'Times New Roman',
    'ui-monospace': isPlatformFontContextActive(ctx)
      ? getPlatformMappedFontByToken('ui-monospace', ctx, lang) ?? getPlatformMappedFont('monospace', ctx, lang)
      : 'Courier New',
    '-apple-system': isPlatformFontContextActive(ctx)
      ? getPlatformMappedFontByToken('-apple-system', ctx, lang) ?? getPlatformMappedFont('sans', ctx, lang)
      : 'Arial',
  };

  return fontMap[lower] || firstFont;
}

export interface ScriptFontFaces {
  latin: string;
  ea: string;
  cs?: string;
}

/**
 * Parse CSS font-family stack into PPTX script-specific faces.
 * - latin: first font in stack
 * - ea: first Chinese font in stack
 * - cs: only for ar/he scripts (complex script)
 */
export function parseScriptFontFaces(
  fontFamily: string | undefined,
  options?: ParseScriptFontFacesOptions
): ScriptFontFaces {
  const ctx = options?.platformFontContext;
  const specified = options?.specifiedFontFamily;
  const textScript = options?.textScript ?? 'latin';
  const defaultLatin = isPlatformFontContextActive(ctx)
    ? getPlatformMappedFont('sans', ctx, textScript)
    : 'Arial';

  if (!fontFamily && !specified) {
    return applyPlatformScriptSlots(
      buildScriptFontFaces(defaultLatin, defaultLatin, textScript, ctx),
      ctx,
      textScript,
      specified,
      fontFamily
    );
  }

  const stackSource = specified ?? fontFamily;
  const effectiveFamily = isPlatformFontContextActive(ctx)
    ? resolveFontFamilyForPlatform(fontFamily, stackSource, ctx, textScript)
    : stackSource;

  const tokens = splitFontStack(effectiveFamily ?? '')
    .map((x) => x.trim().replace(/['"]/g, ''))
    .filter(Boolean);

  if (tokens.length === 0) {
    return applyPlatformScriptSlots(
      buildScriptFontFaces(defaultLatin, defaultLatin, textScript, ctx),
      ctx,
      textScript,
      specified,
      fontFamily
    );
  }

  const latin = parseFontFamily(tokens[0], ctx, textScript);
  const eaToken = tokens.find((token) => isChineseFont(token));
  const ea = eaToken ? parseFontFamily(eaToken, ctx, textScript) : latin;

  return applyPlatformScriptSlots(
    buildScriptFontFaces(latin, ea, textScript, ctx),
    ctx,
    textScript,
    specified,
    fontFamily
  );
}

function buildScriptFontFaces(
  latin: string,
  ea: string,
  textScript: PlatformFontLang,
  ctx?: PlatformFontContext
): ScriptFontFaces {
  if (textScript === 'ar' || textScript === 'he') {
    const cs = isPlatformFontContextActive(ctx)
      ? getPlatformMappedFont('sans', ctx, textScript)
      : 'Arial';
    return { latin, ea, cs };
  }
  return { latin, ea };
}

function stackHasAnyNamedFont(...stacks: (string | undefined)[]): boolean {
  return stacks.some((stack) => stackHasNamedFontLocal(stack));
}

function applyPlatformScriptSlots(
  faces: ScriptFontFaces,
  ctx?: PlatformFontContext,
  textScript: PlatformFontLang = 'latin',
  specified?: string,
  computed?: string
): ScriptFontFaces {
  if (!isPlatformFontContextActive(ctx)) {
    if (textScript === 'ar' || textScript === 'he') {
      return { ...faces, cs: faces.cs ?? faces.latin };
    }
    return faces;
  }

  if (stackHasAnyNamedFont(specified, computed)) {
    if (textScript === 'ar' || textScript === 'he') {
      const genericKind =
        detectStackGenericKind(specified) ?? detectStackGenericKind(computed) ?? 'sans';
      return { ...faces, cs: getPlatformMappedFont(genericKind, ctx, textScript) };
    }
    return faces;
  }

  const genericKind = detectStackGenericKind(specified) ?? detectStackGenericKind(computed);
  if (!genericKind) return faces;

  const mapped = getPlatformMappedFont(genericKind, ctx, textScript);

  if (textScript === 'ar' || textScript === 'he') {
    return { latin: mapped, ea: mapped, cs: mapped };
  }
  return { latin: mapped, ea: mapped };
}

function stackHasNamedFontLocal(fontFamily: string | undefined): boolean {
  if (!fontFamily) return false;
  return splitFontStack(fontFamily).some((tok) => {
    const core = tok.trim().replace(/^['"]|['"]$/g, '').toLowerCase();
    return core && !isGenericFontToken(tok);
  });
}

/**
 * Check if font weight is bold
 * For numeric values: > 400 is treated as bold (500-900 map to bold in PPTX)
 */
export function isBold(fontWeight: string | undefined): boolean {
  if (!fontWeight) return false;
  const num = parseInt(fontWeight, 10);
  if (!isNaN(num)) return num > 400;
  return fontWeight === 'bold' || fontWeight === 'bolder';
}

/** PPTX / registry face names for Font Awesome 6 Free (Solid vs Regular files). */
const FONT_AWESOME_6_FREE_SOLID = 'Font Awesome 6 Free Solid';
const FONT_AWESOME_6_FREE_REGULAR = 'Font Awesome 6 Free Regular';

/** PPTX face names for Font Awesome Brands (kept in sync with EOT assets). */
const FONT_AWESOME_6_BRANDS = 'Font Awesome 6 Brands';
const FONT_AWESOME_5_BRANDS = 'Font Awesome 5 Brands';
const FONT_AWESOME_V4_COMPATIBILITY = 'Font Awesome v4 Compatibility';

function firstFontFamilyToken(fontFamily: string | undefined): string {
  if (!fontFamily) return '';
  return fontFamily.split(',')[0].trim().replace(/['"]/g, '');
}

/**
 * If the primary font is Font Awesome Free (not Brands), return a discrete family name
 * (Solid vs Regular) from font-weight so multiple TTFs can be embedded without clashing.
 * Brands and non–Free families are left to the caller (returns undefined).
 */
export function normalizeFontAwesomeFreeFamily(
  fontFamily: string | undefined,
  fontWeight: string | undefined
): string | undefined {
  const first = firstFontFamilyToken(fontFamily);
  if (!first) return undefined;
  if (!/^Font Awesome/i.test(first)) return undefined;
  if (/brands/i.test(first)) return undefined;
  if (!/free/i.test(first)) return undefined;

  if (/^Font Awesome 6 Free Regular$/i.test(first)) return FONT_AWESOME_6_FREE_REGULAR;
  if (/^Font Awesome 6 Free Solid$/i.test(first)) return FONT_AWESOME_6_FREE_SOLID;

  return isBold(fontWeight) ? FONT_AWESOME_6_FREE_SOLID : FONT_AWESOME_6_FREE_REGULAR;
}

/**
 * Normalize any Font Awesome family (Free Solid/Regular, Brands, v4 Compatibility) to the
 * discrete PPTX face name that matches a pre-built EOT in assets/fonts/font-awesome/.
 * Returns undefined for non–Font Awesome stacks so the caller can fall back to the
 * normal script-face resolution.
 *
 * Brands bypass normalizeFontAwesomeFreeFamily because they are a separate family (not Free),
 * and their computed fontFamilySpecified can be wrong (e.g. inherited "Arial, sans-serif"),
 * which would otherwise let platform font mapping replace the FA face with Arial.
 */
export function normalizeFontAwesomeFamily(
  fontFamily: string | undefined,
  fontWeight: string | undefined
): string | undefined {
  const free = normalizeFontAwesomeFreeFamily(fontFamily, fontWeight);
  if (free) return free;

  const first = firstFontFamilyToken(fontFamily);
  if (!first || !/^Font Awesome/i.test(first)) return undefined;

  if (/v4\s*compatibility/i.test(first)) return FONT_AWESOME_V4_COMPATIBILITY;
  if (!/brands/i.test(first)) return undefined;

  if (/^Font Awesome 6/i.test(first)) return FONT_AWESOME_6_BRANDS;
  return FONT_AWESOME_5_BRANDS;
}

/**
 * Check if font style is italic
 */
export function isItalic(fontStyle: string | undefined): boolean {
  return fontStyle === 'italic' || fontStyle === 'oblique';
}

/**
 * Check if text has underline
 */
export function hasUnderline(textDecoration: string | undefined): boolean {
  return textDecoration?.includes('underline') || false;
}

export function hasStrikethrough(textDecoration: string | undefined): boolean {
  return textDecoration?.includes('line-through') || false;
}

/**
 * Parse text alignment
 */
export function parseTextAlign(
  textAlign: string | undefined
): 'left' | 'center' | 'right' | undefined {
  if (!textAlign) return undefined;
  if (textAlign === 'left' || textAlign === 'center' || textAlign === 'right') {
    return textAlign;
  }
  return undefined;
}

/**
 * Parse opacity (0-1) to transparency percentage (0-100)
 */
export function parseTransparency(opacity: number | undefined): number {
  if (opacity === undefined || opacity === 1) return 0;
  return Math.round((1 - opacity) * 100);
}

/**
 * Parse border width from CSS
 * Using 0.5 ratio (px to pt) for better visual match
 * Empirically determined: 8px (web) ≈ 4pt (PowerPoint)
 */
export function parseBorderWidth(borderWidth: string | undefined): number {
  if (!borderWidth) return 0;
  const px = parseFloat(borderWidth);
  return isNaN(px) ? 0 : px * 0.5;
}

/**
 * Map CSS border-style to pptxgenjs dashType
 * PowerPoint supports: solid, dash, dashDot, lgDash, lgDashDot, lgDashDotDot, sysDash, sysDot
 */
export function parseBorderStyleToDashType(borderStyle: string | undefined): 'solid' | 'dash' | 'dashDot' | 'lgDash' | 'lgDashDot' | 'lgDashDotDot' | 'sysDash' | 'sysDot' {
  const s = (borderStyle || 'solid').toLowerCase();
  const map: Record<string, 'solid' | 'dash' | 'dashDot' | 'lgDash' | 'lgDashDot' | 'lgDashDotDot' | 'sysDash' | 'sysDot'> = {
    'solid': 'solid',
    'none': 'solid',
    'dashed': 'dash',
    'dotted': 'sysDot',
    'double': 'solid', // double-line not directly supported, fallback to solid
    'groove': 'solid',
    'ridge': 'solid',
    'inset': 'solid',
    'outset': 'solid',
  };
  return map[s] ?? 'solid';
}

/**
 * Parse padding from CSS to points
 * Converts padding values to match PowerPoint margin units
 */
export function parsePadding(padding: string | undefined): number {
  if (!padding) return 0;
  const px = parseFloat(padding);
  return isNaN(px) ? 0 : pxToPoints(px);
}

/** Slide-space padding/border px → pt for text-box insets (not font-calibrated pxToPoints). */
export function parseBoxInsetPt(paddingPx: number, borderPx: number = 0): number {
  const px = paddingPx + borderPx;
  if (px <= 0) return 0;
  return inchToPoints(pxToInch(px));
}

/**
 * Parse letter spacing from CSS to points
 * Converts letter-spacing to PowerPoint character spacing (charSpacing)
 * Supports: normal, px, em (em needs fontSizePx for conversion)
 */
export function parseLetterSpacing(
  letterSpacing: string | undefined,
  fontSizePx?: number,
  pxToPt: (px: number) => number = pxToPoints,
  boost = 1.0
): number | undefined {
  if (!letterSpacing || letterSpacing === 'normal') return undefined;
  const str = letterSpacing.trim();
  let px: number;
  if (str.endsWith('em') || str.endsWith('rem')) {
    const num = parseFloat(str);
    if (isNaN(num) || num === 0) return undefined;
    const basePx = fontSizePx ?? 16;
    px = num * basePx;
  } else {
    px = parseFloat(str);
    if (isNaN(px) || px === 0) return undefined;
  }
  // OOXML a:rPr @spc is hundredths of a point and accepts negatives (tighten tracking).
  // pptxgenjs writes spc when charSpacing is truthy — keep the CSS sign.
  const adjustedPt = pxToPt(px) * boost;
  return Math.abs(adjustedPt) >= 0.5 ? adjustedPt : undefined;
}

/**
 * Parse line height from CSS to pptxgenjs lineSpacing (points) or lineSpacingMultiple
 * CSS line-height: normal | number (1.5) | length (24px, 1.5em) | percentage (150%)
 * pptxgenjs: lineSpacing (points, fixed) | lineSpacingMultiple (e.g. 1.5 = 150%)
 */
export function parseLineHeight(
  lineHeight: string | undefined,
  fontSizePx?: number
): { lineSpacing?: number; lineSpacingMultiple?: number } | undefined {
  if (!lineHeight || lineHeight === 'normal') return undefined;
  const str = lineHeight.trim();
  const num = parseFloat(str);

  if (isNaN(num)) return undefined;

  // Percentage: 150% → lineSpacingMultiple 1.5
  if (str.includes('%')) {
    const multiple = num / 100;
    if (multiple > 0 && multiple <= 10) {
      return { lineSpacingMultiple: multiple };
    }
    return undefined;
  }

  // Unitless number (e.g. 1.5): line-height multiplier
  if (str.endsWith('px') || str.endsWith('em') || str.endsWith('rem')) {
    // Length: convert to slide-space points for lineSpacing so N×lh matches box height.
    let px: number;
    if (str.endsWith('em') || str.endsWith('rem')) {
      const basePx = fontSizePx ?? 16;
      px = num * basePx;
    } else {
      px = num;
    }
    // Browsers expose unitless line-height (e.g. 0.9) as computed px ≈ ratio × font-size.
    // Prefer multiple when it clearly tracks font-size (scales with font pt).
    if (str.endsWith('px') && fontSizePx && fontSizePx > 0) {
      const ratio = px / fontSizePx;
      if (ratio >= 0.25 && ratio <= 10) {
        const rounded = Math.round(ratio * 1000) / 1000;
        if (Math.abs(px - rounded * fontSizePx) < 0.6) {
          return { lineSpacingMultiple: rounded };
        }
      }
    }
    const pt = pxToSlidePointsY(px);
    if (pt >= 1 && pt <= 256) return { lineSpacing: pt };
    return undefined;
  }

  // Unitless: 1.5, 1.8, 2 → lineSpacingMultiple (typical range 0.5-5)
  if (num >= 0.5 && num <= 10) {
    return { lineSpacingMultiple: num };
  }

  // Bare number like "24" (no unit) - treat as px if > 10
  if (num > 10 && num <= 500) {
    return { lineSpacing: pxToSlidePointsY(num) };
  }

  return undefined;
}

/**
 * Parsed box-shadow result with classification
 */
export interface BoxShadowParsed {
  offsetX: number;     // px
  offsetY: number;     // px
  blur: number;        // px
  spread: number;      // px
  color: string;       // hex (RRGGBB)
  alpha: number;       // 0-1
  /** 'glow' when shadow wraps 3-4 sides, 'shadow' when 1-2 sides */
  effect: 'glow' | 'shadow';
}

/** Split CSS box-shadow layers on commas outside parentheses. */
function splitBoxShadowLayers(boxShadow: string): string[] {
  const layers: string[] = [];
  let depth = 0;
  let cur = '';
  for (const ch of boxShadow) {
    if (ch === '(') depth++;
    else if (ch === ')') depth = Math.max(0, depth - 1);
    if (ch === ',' && depth === 0) {
      if (cur.trim()) layers.push(cur.trim());
      cur = '';
      continue;
    }
    cur += ch;
  }
  if (cur.trim()) layers.push(cur.trim());
  return layers;
}

function parseCssLengthPx(token: string): number | undefined {
  const m = token.trim().match(/^([-\d.]+)(px)?$/i);
  if (!m) return undefined;
  const n = parseFloat(m[1]);
  return Number.isFinite(n) ? n : undefined;
}

/**
 * Internal helper: parse a box-shadow string in either format:
 *   Format A (CSS shorthand): "2px 2px 4px 0px rgba(0,0,0,0.5)" / "0 10px 28px rgba(...)"
 *   Format B (computed style): "rgba(0, 0, 0, 0.05) 0px 10px 25px 0px"
 * Multi-layer shadows use the first layer. Spread is optional.
 * Returns { offsetX, offsetY, blur, spread, colorStr } or undefined.
 */
function parseOneBoxShadowLayer(
  layer: string
): { offsetX: number; offsetY: number; blur: number; spread: number; colorStr: string } | undefined {
  if (!layer || layer === 'none') return undefined;

  const colorMatch = layer.match(
    /rgba?\(\s*[\d.,%\s/]+\s*\)|hsla?\(\s*[\d.,%\s/]+\s*\)|#[0-9a-fA-F]{3,8}/i
  );
  if (!colorMatch) return undefined;
  const colorStr = colorMatch[0].trim();
  const withoutColor = (layer.slice(0, colorMatch.index!) + layer.slice(colorMatch.index! + colorMatch[0].length))
    .replace(/inset/gi, ' ')
    .trim();
  const lengthTokens = withoutColor.split(/\s+/).filter(Boolean);
  const lengths: number[] = [];
  for (const tok of lengthTokens) {
    const n = parseCssLengthPx(tok);
    if (n === undefined) return undefined;
    lengths.push(n);
  }
  if (lengths.length < 2) return undefined;

  return {
    offsetX: lengths[0],
    offsetY: lengths[1],
    blur: lengths[2] ?? 0,
    spread: lengths[3] ?? 0,
    colorStr,
  };
}

/**
 * Parse box-shadow parts. Multi-layer shadows: prefer the layer with the largest blur
 * (strongest elevation), since PPT exposes a single shadow API.
 */
function parseBoxShadowParts(boxShadow: string): { offsetX: number; offsetY: number; blur: number; spread: number; colorStr: string } | undefined {
  const layers = splitBoxShadowLayers(boxShadow.trim());
  let best:
    | { offsetX: number; offsetY: number; blur: number; spread: number; colorStr: string }
    | undefined;
  for (const layer of layers) {
    const parts = parseOneBoxShadowLayer(layer);
    if (!parts) continue;
    if (!best || parts.blur > best.blur) best = parts;
  }
  return best;
}

/**
 * Parse box-shadow and classify as glow (all-around) or shadow (directional).
 *
 * Classification: count the sides where blur extends beyond the offset.
 *   visible extent on a side = blur - abs(offset towards that side)
 *   3-4 visible sides → glow, 1-2 → shadow
 */
export function parseBoxShadowClassified(boxShadow: string | undefined): BoxShadowParsed | undefined {
  if (!boxShadow || boxShadow === 'none') return undefined;

  const parts = parseBoxShadowParts(boxShadow.trim());
  if (!parts) return undefined;

  const { offsetX, offsetY, blur, spread, colorStr } = parts;
  const colorResult = parseColor(colorStr);
  if (!colorResult) return undefined;

  // Count visible sides: blur extends past the offset on that side?
  let visibleSides = 0;
  if (blur - Math.abs(Math.min(0, offsetX)) > 0) visibleSides++; // left  (offsetX < 0 pushes right)
  if (blur - Math.abs(Math.max(0, offsetX)) > 0) visibleSides++; // right (offsetX > 0 pushes right)
  if (blur - Math.abs(Math.min(0, offsetY)) > 0) visibleSides++; // top
  if (blur - Math.abs(Math.max(0, offsetY)) > 0) visibleSides++; // bottom

  const effect: 'glow' | 'shadow' = visibleSides >= 3 ? 'glow' : 'shadow';

  return {
    offsetX,
    offsetY,
    blur,
    spread,
    color: colorResult.color,
    alpha: colorResult.alpha ?? 1.0,
    effect,
  };
}

/**
 * Parse box shadow to PPTX shadow options (for directional shadows)
 */
export function parseBoxShadow(boxShadow: string | undefined): any {
  if (!boxShadow || boxShadow === 'none') return undefined;

  const parts = parseBoxShadowParts(boxShadow.trim());
  if (!parts) return undefined;

  const { offsetX, offsetY, blur, colorStr } = parts;
  const colorResult = parseColor(colorStr);

  return {
    type: 'outer',
    angle: Math.atan2(offsetY, offsetX) * (180 / Math.PI),
    // Generous safety ceilings only (avoid corrupt XML); preserve typical CSS values.
    blur: Math.max(0, Math.min(500, pxToPoints(blur))),
    offset: Math.max(0, Math.min(500, pxToPoints(Math.sqrt(offsetX ** 2 + offsetY ** 2)))),
    color: colorResult?.color || '000000',
    opacity:
      colorResult?.alpha !== undefined
        ? Math.max(0, Math.min(1, colorResult.alpha))
        : 1.0,
  };
}

/**
 * Extract blur radius (in px) from CSS filter string (e.g., "blur(20px) brightness(1.1)")
 */
export function parseBlurFilter(filter: string | undefined): number | undefined {
  if (!filter) return undefined;
  const match = filter.match(/blur\(\s*([^)]+)\)/i);
  if (!match) return undefined;

  const rawValue = match[1].trim();
  const unitMatch = rawValue.match(/^([-\d.]+)([a-z%]*)$/i);
  if (!unitMatch) return undefined;

  const numeric = parseFloat(unitMatch[1]);
  if (isNaN(numeric) || numeric <= 0) return undefined;

  const unit = unitMatch[2].toLowerCase();
  if (unit === '' || unit === 'px') {
    return numeric;
  }

  // Unsupported units (em/rem/etc.) - return undefined to avoid incorrect scaling
  return undefined;
}

/**
 * Extract rotation in degrees from CSS transform.
 * Handles:
 * - Literal: "rotate(45deg)", "rotate(-0.25turn)"
 * - Computed: "matrix(a, b, c, d, e, f)" (browser returns this for rotate(45deg))
 * Returns value in range [-360, 360] for pptxgenjs, or undefined if no rotation.
 */
export function parseTransformRotate(transform: string | undefined): number | undefined {
  if (!transform || typeof transform !== 'string') return undefined;

  // 1) Literal rotate() from author CSS
  const rotateMatch = transform.match(/rotate\s*\(\s*([-\d.]+)\s*(deg|turn|rad)\s*\)/i);
  if (rotateMatch) {
    const value = parseFloat(rotateMatch[1]);
    const unit = (rotateMatch[2] || 'deg').toLowerCase();
    if (isNaN(value)) return undefined;
    let degrees: number;
    if (unit === 'deg') degrees = value;
    else if (unit === 'turn') degrees = value * 360;
    else if (unit === 'rad') degrees = (value * 180) / Math.PI;
    else return undefined;
    return normalizeRotateDegrees(degrees);
  }

  // 2) Computed value: matrix(a, b, c, d, e, f) — browser converts rotate(θ) to matrix(cos θ, sin θ, -sin θ, cos θ, 0, 0)
  const matrixMatch = transform.match(/matrix\s*\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)/);
  if (matrixMatch) {
    const a = parseFloat(matrixMatch[1]);
    const b = parseFloat(matrixMatch[2]);
    if (isNaN(a) || isNaN(b)) return undefined;
    // Rotation angle: atan2(b, a) in radians → degrees
    const radians = Math.atan2(b, a);
    const degrees = (radians * 180) / Math.PI;
    return normalizeRotateDegrees(degrees);
  }

  // 3) matrix3d(...) — use upper-left 2x2 for rotation (rotateZ)
  const matrix3dMatch = transform.match(/matrix3d\s*\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)/);
  if (matrix3dMatch) {
    const m11 = parseFloat(matrix3dMatch[1]);
    const m12 = parseFloat(matrix3dMatch[2]);
    if (isNaN(m11) || isNaN(m12)) return undefined;
    const radians = Math.atan2(m12, m11);
    const degrees = (radians * 180) / Math.PI;
    return normalizeRotateDegrees(degrees);
  }

  return undefined;
}

function normalizeRotateDegrees(degrees: number): number | undefined {
  if (degrees === 0) return undefined;
  degrees = degrees % 360;
  if (degrees > 360) degrees -= 360;
  if (degrees < -360) degrees += 360;
  return Math.round(degrees * 100) / 100;
}

/**
 * Map CSS `-webkit-text-stroke` to pptxgen `outline` (text stroke in PPT).
 */
export function parseWebkitTextStroke(styles: ComputedStyles): { widthPt: number; colorHex: string } | undefined {
  const raw = styles.webkitTextStroke?.trim();
  let widthPx = 0;
  let colorStr: string | undefined;

  if (raw && raw !== 'none' && raw !== '0px') {
    const m = raw.match(/^([\d.]+)\s*px\s+([\s\S]+)$/);
    if (m) {
      widthPx = parseFloat(m[1]) || 0;
      colorStr = m[2].trim();
    }
  }
  if (widthPx <= 0 && styles.webkitTextStrokeWidth) {
    const w = styles.webkitTextStrokeWidth.trim();
    if (w && w !== 'none') {
      widthPx = parseFloat(w) || 0;
    }
  }
  if (!colorStr && styles.webkitTextStrokeColor) {
    const c = styles.webkitTextStrokeColor.trim();
    if (c && c !== 'none') colorStr = c;
  }

  if (widthPx <= 0 || !colorStr) return undefined;

  const colorResult = parseColor(colorStr);
  if (!colorResult?.color) return undefined;

  return {
    widthPt: Math.max(0.25, pxToPoints(widthPx)),
    colorHex: colorResult.color,
  };
}

/**
 * Get text options for pptxgenjs
 */
/**
 * Map CSS writing-mode to OOXML a:bodyPr @vert (ST_TextVerticalType).
 * vertical-rl: columns progress right-to-left → eaVert (East Asian vertical).
 * vertical-lr: columns progress left-to-right → vert.
 */
export function getOoxmlBodyPrVert(writingMode: string | undefined): string | undefined {
  if (!writingMode) return undefined;
  const wm = writingMode.trim().toLowerCase();
  if (wm === 'vertical-rl') return 'eaVert';
  if (wm === 'vertical-lr') return 'vert';
  return undefined;
}

export type TextBoxHint = { width?: number; height?: number };

export function getTextOptions(
  styles: ComputedStyles,
  platformFontContext?: PlatformFontContext,
  text?: string,
  box?: TextBoxHint
): any {
  const options: any = {};

  const textScript =
    text != null && text.length > 0
      ? splitTextByScript(text, detectContainerScriptHints(text))[0]?.script ?? 'latin'
      : 'latin';

  const backgroundClip = styles.backgroundClip ?? styles.webkitBackgroundClip;
  const isTextClip = backgroundClip === 'text';

  const textStroke = parseWebkitTextStroke(styles);

  let colorResult: ReturnType<typeof parseColor>;
  if (isTextClip) {
    // Gradient/solid text via background-clip:text — inherited `color` is irrelevant; webkit fill may be transparent.
    const fillColor = parseColor(styles.webkitTextFillColor);
    if (fillColor && fillColor.alpha !== 0) {
      colorResult = fillColor;
    } else {
      const gradientResult = parseGradientSolidApproximation(styles.backgroundImage);
      colorResult = gradientResult ? { color: gradientResult.color } : undefined;
    }
  } else {
    colorResult = parseColor(styles.color) ?? parseColor(styles.webkitTextFillColor);
  }

  if (textStroke) {
    options.outline = { color: textStroke.colorHex, size: textStroke.widthPt };
  }

  if (colorResult) {
    options.color = colorResult.color;
  } else if (textStroke) {
    // Hollow text (color/nofill transparent): PPT defaults to black if no solidFill — use full transparency
    options.color = 'FFFFFF';
    options.transparency = 100;
  }

  // Apply opacity as text transparency when color has no alpha
  // e.g. opacity-20 (0.2) on text-[#A63437] → transparency 80
  if (colorResult && colorResult.alpha === undefined && styles.opacity !== undefined) {
    const transparency = parseTransparency(styles.opacity);
    if (transparency > 0) options.transparency = transparency;
  } else if (colorResult?.alpha !== undefined && colorResult.alpha < 1) {
    // rgba() alpha takes precedence over opacity when both exist
    options.transparency = Math.round((1 - colorResult.alpha) * 100);
  }

  const isPillBoxEarly = isInlinePillBox(styles, box);
  const fontSize = isPillBoxEarly
    ? parsePillFontSize(styles.fontSize?.toString())
    : parseFontSize(styles.fontSize?.toString());
  options.fontSize = fontSize;

  const faFreeFace = normalizeFontAwesomeFreeFamily(
    styles.fontFamily,
    styles.fontWeight?.toString()
  );
  const faFace =
    faFreeFace ??
    normalizeFontAwesomeFamily(styles.fontFamily, styles.fontWeight?.toString());
  options.fontFace =
    faFace ??
    parseScriptFontFaces(styles.fontFamily, {
      platformFontContext,
      specifiedFontFamily: styles.fontFamilySpecified,
      textScript,
    }).latin;

  if (!faFace && isBold(styles.fontWeight)) options.bold = true;

  if (isItalic(styles.fontStyle)) options.italic = true;
  if (hasUnderline(styles.textDecoration)) options.underline = true;
  if (hasStrikethrough(styles.textDecoration)) options.strike = true;

  const align = parseTextAlign(styles.textAlign);
  if (align) options.align = align;

  // Add letter spacing (character spacing in PowerPoint)
  // fontSizePx is the raw browser-reported size; viewport scaling is applied
  // downstream inside pxToPoints (called by parseLetterSpacing/parseLineHeight).
  const fontSizePx = parseFloat(String(styles.fontSize || '16')) || 16;
  const charSpacing = parseLetterSpacing(styles.letterSpacing, fontSizePx);
  if (charSpacing !== undefined) options.charSpacing = charSpacing;

  // Add line spacing (line height in PowerPoint)
  const lineHeightResult = parseLineHeight(styles.lineHeight, fontSizePx);
  if (lineHeightResult) {
    if (lineHeightResult.lineSpacing !== undefined) {
      options.lineSpacing = lineHeightResult.lineSpacing;
    }
    if (lineHeightResult.lineSpacingMultiple !== undefined) {
      options.lineSpacingMultiple = lineHeightResult.lineSpacingMultiple;
    }
  }

  // HTML/CSS default vertical alignment is top; pill chips are optically centered via padding.
  options.valign = isPillBoxEarly ? 'middle' : 'top';

  const display = styles.display;
  const isInlineBox =
    display === 'inline' || display === 'inline-block' || display === 'inline-flex';
  const hasTextHighlight = isVisibleTextBackgroundColor(styles.glyphHighlightColor);
  const isPillBox = isPillBoxEarly;

  // Parse padding and border, convert to margin for PowerPoint text box
  // PowerPoint margin = internal space between text and box edge (like CSS padding)
  // Include border width so text aligns with HTML content box (content starts after border+padding)
  const parseSide = (padding: string | undefined, borderWidth: string | undefined): number => {
    const padPx = parseFloat(String(padding || '0')) || 0;
    const borderPx = parseFloat(String(borderWidth || '0')) || 0;
    if (isPillBox) return parseBoxInsetPt(padPx, borderPx);
    const pad = parsePadding(padding);
    return pad + pxToPoints(borderPx);
  };
  const marginTop = parseSide(styles.paddingTop, styles.borderTopWidth);
  const marginRight = parseSide(styles.paddingRight, styles.borderRightWidth);
  const marginBottom = parseSide(styles.paddingBottom, styles.borderBottomWidth);
  const marginLeft = parseSide(styles.paddingLeft, styles.borderLeftWidth);

  // CSS 500 is medium; isBold treats >400 as bold and widens glyphs vs browser
  if (isPillBox && options.bold) {
    const fw = parseInt(String(styles.fontWeight ?? ''), 10);
    if (!isNaN(fw) && fw >= 500 && fw < 600) delete options.bold;
  }

  // Inline highlight padding is simulated with spaces in the converter; PPT run margin would
  // affect the whole text box, not just the highlighted phrase.
  // Pill badges (fill or outline + border-radius) use a roundRect — keep padding margin.
  if (!(isInlineBox && hasTextHighlight && !isPillBox)) {
    // Always set margin - when web has 0 padding/border, use [0,0,0,0] to override pptxgenjs default
    // pptxgenjs expects margin as [left, right, bottom, top] (maps to lIns, rIns, bIns, tIns)
    options.margin = [marginLeft, marginRight, marginBottom, marginTop];
  } else {
    options.margin = [0, 0, 0, 0];
  }

  const highlight = styles.glyphHighlightColor
    ? parseTextHighlightColor(styles.glyphHighlightColor, styles.highlightBackdropColor)
    : undefined;
  if (highlight) options.highlight = highlight;

  return options;
}

/** Visible CSS border on any side (outline chips use border without fill). */
export function hasVisibleBorder(styles: ComputedStyles): boolean {
  const sides: Array<[string | undefined, string | undefined]> = [
    [styles.borderTopWidth, styles.borderTopColor],
    [styles.borderRightWidth, styles.borderRightColor],
    [styles.borderBottomWidth, styles.borderBottomColor],
    [styles.borderLeftWidth, styles.borderLeftColor],
  ];
  for (const [width, color] of sides) {
    const px = parseFloat(String(width || '0')) || 0;
    if (px <= 0) continue;
    if (!color || color === 'transparent' || color === 'rgba(0, 0, 0, 0)' || color === 'rgba(0,0,0,0)') {
      continue;
    }
    return true;
  }
  const aggregate = parseFloat(String(styles.borderWidth ?? '0')) || 0;
  if (aggregate > 0 && isVisibleTextBackgroundColor(styles.borderColor)) return true;
  // borderColor may be hex/rgb even when not a "background"; treat non-transparent as visible.
  if (aggregate > 0 && styles.borderColor && styles.borderColor !== 'transparent') return true;
  return false;
}

export type PillBoxFlags = {
  /** Explicit <br> / soft breaks / multi-line wrap — not a nowrap chip. */
  multiLine?: boolean;
  /** Short label (≤3 words) that may have wrapped inside a tight circle. */
  shortLabel?: boolean;
};

/**
 * Pill/chip badge: rounded box with fill and/or outline that should map to one roundRect+text.
 * Covers filled inline pills, outline chips, and compact flex-item badges (blockified flex children).
 * Multi-line callouts (`<br>`, wrapping body) are excluded — they need wrap + height fit.
 */
export function isInlinePillBox(
  styles: ComputedStyles,
  box?: TextBoxHint,
  flags?: PillBoxFlags
): boolean {
  if (flags?.multiLine && !flags?.shortLabel) return false;

  const br = styles.borderRadius;
  if (!br || br === '0' || br === '0px') return false;

  const hasFill = isVisibleTextBackgroundColor(styles.backgroundColor);
  const hasBorder = hasVisibleBorder(styles);
  if (!hasFill && !hasBorder) return false;

  const display = String(styles.display || 'block').toLowerCase();
  const inlineLike =
    display === 'inline' || display === 'inline-block' || display === 'inline-flex';
  const ws = String(styles.whiteSpace || '').toLowerCase();
  const nowrap = ws === 'nowrap';

  // Wrapping block callouts (min-width cards with padding) are not chips.
  if (!inlineLike && !nowrap && ws && ws !== 'normal') {
    /* pre/pre-wrap etc. — still may be a chip; fall through */
  }

  const h = Number(box?.height) || 0;
  const w = Number(box?.width) || 0;

  // "Insert here" style nodes: Chromium may wrap inside a round flex chip taller than 56px.
  if (
    flags?.shortLabel &&
    (hasFill || hasBorder) &&
    h > 0 &&
    h <= 88 &&
    w > 0 &&
    w <= 200
  ) {
    return true;
  }

  if (inlineLike && (nowrap || h <= 0 || h <= 56)) return true;

  // Compact shrink-wrapped flex chips (HNSW/LNS/Equity): often display:block, no nowrap,
  // and w/h < 2.2 — still single-line badges, not tall callout cards (plan: h≤56).
  if (h > 0 && h <= 56 && w > 0 && w <= 220 && (hasFill || hasBorder)) return true;

  // Compact nowrap / short chips only (aspect-ratio path used to catch tall callouts).
  if (h > 0 && h <= 56 && (nowrap || inlineLike || w / Math.max(h, 1) >= 2.2)) return true;
  if (nowrap && h > 0 && h <= 64) return true;

  // Filled flex-centered chips without measured box.
  if (
    (display === 'flex' || display === 'inline-flex') &&
    hasFill &&
    (styles.alignItems === 'center' || styles.justifyContent === 'center') &&
    (h <= 0 || h <= 56)
  ) {
    return true;
  }

  return false;
}

/**
 * Keep intentional soft-break lines on one line each (HTML `<br>` callouts) and ensure
 * the box height fits N×lineSpacing + padding — otherwise PPT wraps further and spills.
 */
export function fitTextBoxToIntentionalLines(opts: {
  lines: string[];
  fontSizePt: number;
  lineSpacingPt: number;
  xInch: number;
  yInch: number;
  wInch: number;
  hInch: number;
  marginLeftPt: number;
  marginRightPt: number;
  marginTopPt: number;
  marginBottomPt: number;
  bold?: boolean;
  charSpacingPt?: number;
  maxGrowInch?: number;
  /** Prefer expanding to the right (left-border callouts must not drift past their accent). */
  preferGrowRight?: boolean;
}): { x: number; y: number; w: number; h: number; fontSizePt: number; lineSpacingPt: number } {
  const lines = (opts.lines || []).map((l) => l.replace(/\s+/g, ' ').trim()).filter(Boolean);
  const lineCount = Math.max(1, lines.length);
  const maxGrow = opts.maxGrowInch ?? pxToInchX(64);
  let fontSize = opts.fontSizePt;
  let lineSpacing = opts.lineSpacingPt > 0 ? opts.lineSpacingPt : fontSize * 1.35;
  let x = opts.xInch;
  let y = opts.yInch;
  let w = opts.wInch;
  let h = opts.hInch;
  const ml = Math.max(0, opts.marginLeftPt) / 72;
  const mr = Math.max(0, opts.marginRightPt) / 72;
  const mt = Math.max(0, opts.marginTopPt) / 72;
  const mb = Math.max(0, opts.marginBottomPt) / 72;

  const widest = () => {
    if (lines.length === 0) return 0.01;
    return Math.max(
      0.01,
      ...lines.map((line) =>
        estimatePillTextWidthInch({
          fontSizePt: fontSize,
          text: line,
          bold: opts.bold,
          charSpacingPt: opts.charSpacingPt,
        })
      )
    );
  };

  // 1) Widen so each intentional line stays on one line (match HTML `<br>` layout).
  let needW = widest() / 0.98 + ml + mr;
  if (needW > w + 1e-6) {
    const grow = Math.min(needW - w, maxGrow);
    // Left-border / accent callouts: never grow left — that drifts text past the rule.
    if (!opts.preferGrowRight && x + w / 2 > SLIDE_WIDTH_INCH * 0.45) {
      const leftGrow = Math.min(grow, Math.max(0, x));
      x -= leftGrow;
      w += leftGrow;
      w += Math.max(0, grow - leftGrow);
    } else {
      w += grow;
    }
  }

  // 2) Still too wide → shrink font (and line spacing in proportion).
  const contentW = Math.max(0.05, w - ml - mr);
  for (let i = 0; i < 10; i++) {
    const maxLine = Math.max(
      ...lines.map((line) =>
        estimatePillTextWidthInch({
          fontSizePt: fontSize,
          text: line,
          bold: opts.bold,
          charSpacingPt: opts.charSpacingPt,
        })
      ),
      0
    );
    if (maxLine <= contentW * 0.98) break;
    const scale = (contentW * 0.98) / maxLine;
    fontSize = Math.max(6, fontSize * scale);
    lineSpacing = Math.max(fontSize, lineSpacing * scale);
  }

  // 3) Height must fit N intentional lines (no extra PPT wraps).
  lineSpacing = Math.max(lineSpacing, fontSize * 1.15);
  const needH = (lineSpacing * lineCount) / 72 + mt + mb;
  if (needH > h + 1e-6) {
    const grow = Math.min(needH - h, maxGrow);
    // Prefer growing downward so headers above stay put; clamp to slide.
    const roomBelow = Math.max(0, SLIDE_HEIGHT_INCH - (y + h));
    const down = Math.min(grow, roomBelow);
    h += down;
    const rem = grow - down;
    if (rem > 0) {
      const up = Math.min(rem, y);
      y -= up;
      h += up;
    }
  }

  if (x + w > SLIDE_WIDTH_INCH) w = Math.max(0.05, SLIDE_WIDTH_INCH - x);
  if (y + h > SLIDE_HEIGHT_INCH) h = Math.max(0.05, SLIDE_HEIGHT_INCH - y);
  if (x < 0) {
    w += x;
    x = 0;
  }
  if (y < 0) {
    h += y;
    y = 0;
  }

  return {
    x,
    y,
    w,
    h,
    fontSizePt: Math.round(fontSize * 10) / 10,
    lineSpacingPt: Math.round(lineSpacing * 10) / 10,
  };
}

/**
 * Fit auto-wrapping titles/body so estimated wrap height stays inside the measured
 * HTML box (and optional sibling ceiling — e.g. a later accent bar). Widen first,
 * then shrink font; prefer not growing downward into decorative bands.
 */
export function fitWrappedTextBox(opts: {
  text: string;
  fontSizePt: number;
  lineSpacingPt: number;
  xInch: number;
  yInch: number;
  wInch: number;
  hInch: number;
  marginLeftPt?: number;
  marginRightPt?: number;
  marginTopPt?: number;
  marginBottomPt?: number;
  bold?: boolean;
  charSpacingPt?: number;
  /** Do not let text bottom exceed this (later accent / sibling). */
  maxBottomInch?: number;
  maxGrowInch?: number;
  /** Do not expand left of this edge (opaque panel to the left). */
  minLeftInch?: number;
  /** Do not expand right of this edge (opaque panel to the right). */
  maxRightInch?: number;
  /** Prefer font shrink over growing into a nearby column wall. */
  preferShrinkFont?: boolean;
}): { x: number; y: number; w: number; h: number; fontSizePt: number; lineSpacingPt: number } {
  const text = (opts.text || '').replace(/\s+/g, ' ').trim();
  let fontSize = opts.fontSizePt;
  let lineSpacing = opts.lineSpacingPt > 0 ? opts.lineSpacingPt : fontSize * 1.2;
  let x = opts.xInch;
  let y = opts.yInch;
  let w = opts.wInch;
  let h = opts.hInch;
  const ml = Math.max(0, opts.marginLeftPt || 0) / 72;
  const mr = Math.max(0, opts.marginRightPt || 0) / 72;
  const mt = Math.max(0, opts.marginTopPt || 0) / 72;
  const mb = Math.max(0, opts.marginBottomPt || 0) / 72;
  const maxGrow = opts.maxGrowInch ?? pxToInchX(96);
  const minLeft = opts.minLeftInch ?? 0;
  const maxRight = opts.maxRightInch ?? SLIDE_WIDTH_INCH;
  const preferShrink = !!opts.preferShrinkFont;
  const maxBottom =
    opts.maxBottomInch !== undefined
      ? opts.maxBottomInch
      : SLIDE_HEIGHT_INCH;

  if (!text || !(w > 0) || !(fontSize > 0)) {
    return {
      x,
      y,
      w,
      h,
      fontSizePt: fontSize,
      lineSpacingPt: lineSpacing,
    };
  }

  const words = text.split(/\s+/).filter(Boolean);

  const estimateLines = (contentW: number, size: number, tracking?: number): number => {
    if (words.length === 0) return 1;
    let lines = 1;
    let lineW = 0;
    const space =
      estimatePillTextWidthInch({
        fontSizePt: size,
        text: ' ',
        bold: opts.bold,
        charSpacingPt: tracking,
      }) || size * 0.3 / 72;
    for (const word of words) {
      const ww = estimatePillTextWidthInch({
        fontSizePt: size,
        text: word,
        bold: opts.bold,
        charSpacingPt: tracking,
      });
      if (lineW > 0 && lineW + space + ww > contentW * 0.98) {
        lines += 1;
        lineW = ww;
      } else {
        lineW = lineW > 0 ? lineW + space + ww : ww;
      }
    }
    return Math.max(1, lines);
  };

  const needHFor = (lines: number, spc: number) => (spc * lines) / 72 + mt + mb;

  // 1) If wrap height exceeds box (or sibling ceiling), widen content width first.
  for (let pass = 0; pass < 8; pass++) {
    const contentW = Math.max(0.05, w - ml - mr);
    const lines = estimateLines(contentW, fontSize, opts.charSpacingPt);
    const needH = needHFor(lines, lineSpacing);
    const ceiling = Math.min(h, Math.max(0.05, maxBottom - y));
    if (needH <= ceiling + 1e-4) break;

    // Prefer widening to reduce wrap count, but never into an opaque column wall.
    const growWanted = Math.min(maxGrow, pxToInchX(48));
    const roomRight = Math.max(0, Math.min(SLIDE_WIDTH_INCH, maxRight) - (x + w));
    const roomLeft = Math.max(0, x - minLeft);
    const wallIsClose = preferShrink && roomRight < pxToInchX(48) && roomLeft < pxToInchX(48);
    if (!wallIsClose && growWanted > 0.01 && (roomLeft > 0.01 || roomRight > 0.01)) {
      if (x + w / 2 > SLIDE_WIDTH_INCH * 0.45 && roomLeft > 0) {
        const g = Math.min(growWanted, roomLeft);
        x -= g;
        w += g;
      } else {
        const g = Math.min(growWanted, roomRight || roomLeft);
        if (roomRight >= g) w += g;
        else {
          x -= g;
          w += g;
        }
      }
      continue;
    }

    // 2) Shrink font / lineSpacing to fit the available ceiling.
    const scale = Math.sqrt(Math.max(0.5, ceiling / needH));
    fontSize = Math.max(8, fontSize * scale);
    lineSpacing = Math.max(fontSize * 1.05, lineSpacing * scale);
  }

  // Final height: grow box downward only up to maxBottom (never through accent band).
  {
    const contentW = Math.max(0.05, w - ml - mr);
    const lines = estimateLines(contentW, fontSize, opts.charSpacingPt);
    const needH = needHFor(lines, lineSpacing);
    if (needH > h + 1e-6) {
      const room = Math.max(0, maxBottom - (y + h));
      h += Math.min(needH - h, room, maxGrow);
    }
  }

  if (x + w > SLIDE_WIDTH_INCH) w = Math.max(0.05, SLIDE_WIDTH_INCH - x);
  if (x + w > maxRight) w = Math.max(0.05, maxRight - x);
  if (y + h > maxBottom) h = Math.max(0.05, maxBottom - y);
  if (x < minLeft) {
    w -= minLeft - x;
    x = minLeft;
  }
  if (x < 0) {
    w += x;
    x = 0;
  }
  if (y < 0) {
    h += y;
    y = 0;
  }

  return {
    x,
    y,
    w,
    h,
    fontSizePt: Math.round(fontSize * 10) / 10,
    lineSpacingPt: Math.round(lineSpacing * 10) / 10,
  };
}

/** True when background-color is a visible fill (not transparent). */
export function isVisibleTextBackgroundColor(backgroundColor: string | undefined): boolean {
  if (!backgroundColor) return false;
  return (
    backgroundColor !== 'rgba(0, 0, 0, 0)' &&
    backgroundColor !== 'rgba(0,0,0,0)' &&
    backgroundColor !== 'transparent' &&
    backgroundColor !== 'none'
  );
}

/**
 * Blend rgba foreground onto an opaque background to get perceived solid color.
 */
function blendRgbaOnBackground(
  r: number,
  g: number,
  b: number,
  alpha: number,
  bgR: number,
  bgG: number,
  bgB: number
): string {
  const inv = 1 - alpha;
  const R = Math.round(r * alpha + bgR * inv);
  const G = Math.round(g * alpha + bgG * inv);
  const B = Math.round(b * alpha + bgB * inv);
  return [R, G, B].map((v) => v.toString(16).padStart(2, '0').toUpperCase()).join('');
}

function resolveBackdropRgb(backdropColor?: string): { r: number; g: number; b: number } {
  if (!backdropColor || !isVisibleTextBackgroundColor(backdropColor)) {
    return { r: 255, g: 255, b: 255 };
  }
  const parsed = parseColor(backdropColor);
  if (!parsed) return { r: 255, g: 255, b: 255 };
  let r = parseInt(parsed.color.slice(0, 2), 16);
  let g = parseInt(parsed.color.slice(2, 4), 16);
  let b = parseInt(parsed.color.slice(4, 6), 16);
  if (parsed.alpha !== undefined && parsed.alpha < 1) {
    const blended = blendRgbaOnBackground(r, g, b, parsed.alpha, 255, 255, 255);
    r = parseInt(blended.slice(0, 2), 16);
    g = parseInt(blended.slice(2, 4), 16);
    b = parseInt(blended.slice(4, 6), 16);
  }
  return { r, g, b };
}

/**
 * Map CSS inline/element background-color to pptxgenjs text highlight (OOXML a:highlight).
 * PPT highlight is opaque; semi-transparent CSS backgrounds are composited on the backdrop.
 */
export function parseTextHighlightColor(
  backgroundColor: string | undefined,
  backdropColor?: string
): string | undefined {
  if (!isVisibleTextBackgroundColor(backgroundColor)) return undefined;

  const parsed = parseColor(backgroundColor);
  if (!parsed) return undefined;

  if (parsed.alpha !== undefined && parsed.alpha < 1) {
    const r = parseInt(parsed.color.slice(0, 2), 16);
    const g = parseInt(parsed.color.slice(2, 4), 16);
    const b = parseInt(parsed.color.slice(4, 6), 16);
    const bg = resolveBackdropRgb(backdropColor);
    return blendRgbaOnBackground(r, g, b, parsed.alpha, bg.r, bg.g, bg.b);
  }

  return parsed.color;
}

/**
 * Approximate how many spaces emulate CSS margin-left on an inline run (proportional to font size).
 */
export function marginLeftPxToLeadingSpaces(marginLeftPx: number, fontSizePx: number): number {
  if (marginLeftPx <= 0) return 0;
  const pxPerSpace = Math.max(fontSizePx * 0.25, 1);
  return Math.max(1, Math.round(marginLeftPx / pxPerSpace));
}

/**
 * PPT a:highlight only covers glyphs — pad inline highlighted runs with spaces (same run options).
 */
export function expandRunTextForInlineHighlightPadding(text: string, styles: ComputedStyles): string {
  if (
    !text ||
    (!isVisibleTextBackgroundColor(styles.backgroundColor) &&
      !isVisibleTextBackgroundColor(styles.glyphHighlightColor))
  ) {
    return text;
  }
  const display = styles.display;
  if (display !== 'inline' && display !== 'inline-block') return text;

  const fontSizePx = parseFloat(String(styles.fontSize || '16')) || 16;
  const padL = parseFloat(String(styles.paddingLeft || '0')) || 0;
  const padR = parseFloat(String(styles.paddingRight || '0')) || 0;
  if (padL <= 0 && padR <= 0) return text;

  // ~0.25em per regular space; use non-breaking spaces so padding is not collapsed.
  const pxPerSpace = Math.max(fontSizePx * 0.25, 1);
  const left = padL > 0 ? '\u00A0'.repeat(Math.max(1, Math.round(padL / pxPerSpace))) : '';
  const right = padR > 0 ? '\u00A0'.repeat(Math.max(1, Math.round(padR / pxPerSpace))) : '';
  return left + text + right;
}

function backgroundImageHasGradientToken(backgroundImage: string | undefined): boolean {
  if (!backgroundImage) return false;
  return (
    backgroundImage.includes('linear-gradient') ||
    backgroundImage.includes('repeating-linear-gradient') ||
    backgroundImage.includes('radial-gradient') ||
    backgroundImage.includes('repeating-radial-gradient') ||
    backgroundImage.includes('conic-gradient') ||
    backgroundImage.includes('repeating-conic-gradient')
  );
}

/** Coverage at or above which a gradient is the element's fill rather than an overlay. */
const GRADIENT_OPAQUE_COVERAGE = 0.9;
/** Coverage below which a gradient paints nothing worth exporting as a fill. */
const GRADIENT_INVISIBLE_COVERAGE = 0.04;

type GradientAreaStop = { r: number; g: number; b: number; a: number; start: number; end: number };

/** The element box a background paints into, in CSS px. */
export type GradientBox = { width: number; height: number };

/** Area coverage of a background-image: the color it paints and how much of the box it covers. */
export type GradientCoverage = { color: string; alpha: number };

const GRADIENT_FUNCTION_RE =
  /^(?:repeating-)?(?:linear|radial|conic)-gradient\s*\(([\s\S]*)\)$/i;
const GRADIENT_COLOR_TOKEN_RE =
  /^(?:(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color|color-mix|light-dark)\s*\([\s\S]*?\)|#[0-9A-Fa-f]{3,8}|[A-Za-z][A-Za-z-]*)/;
const GRADIENT_POSITION_RE = /(-?[\d.]+)\s*(%|px|pt|rem|em|vw|vh|vmin|vmax|ch|cm|mm|in|q)?/gi;

/** Split a background-image into its layers (CSS paints the first layer on top). */
function splitBackgroundImageLayers(backgroundImage: string): string[] {
  return splitGradientCommaParts(backgroundImage).filter((layer) => layer.length > 0);
}

/**
 * Parse one gradient layer into positioned stops normalized to 0..1 along the gradient line.
 *
 * Positions matter: `linear-gradient(90deg, rgba(...,.5) 0 1px, transparent 1px 80px)` is a
 * hairline grid, not a tint — it paints 1px in 80 and leaves the rest to the layer beneath.
 * Length positions are normalized against the largest authored length in the same layer, which
 * is the only extent available without the element box and is exactly the pattern tile for
 * hairline/stripe backgrounds. Percentages are already box-relative.
 */
function parseGradientAreaStops(layer: string, extent?: number): GradientAreaStop[] | undefined {
  const match = layer.trim().match(GRADIENT_FUNCTION_RE);
  if (!match) return undefined;
  const parts = splitGradientCommaParts(match[1]);
  if (!parts.length) return undefined;

  type RawStop = { r: number; g: number; b: number; a: number; positions: Array<{ value: number; relative: boolean }> };
  const raw: RawStop[] = [];
  for (const [index, part] of parts.entries()) {
    const colorMatch = part.match(GRADIENT_COLOR_TOKEN_RE);
    const parsed = colorMatch ? parseGradientStopColor(colorMatch[0]) : undefined;
    if (!parsed) {
      // Only the first argument may be configuration (`to right`, `135deg`,
      // `circle at 50%`, `in oklab`). A later stop we cannot resolve would
      // silently redistribute everyone else's area, so refuse to measure.
      if (index === 0) continue;
      return undefined;
    }
    const positions: Array<{ value: number; relative: boolean }> = [];
    const rest = part.slice((colorMatch as RegExpMatchArray)[0].length);
    GRADIENT_POSITION_RE.lastIndex = 0;
    let position: RegExpExecArray | null;
    while ((position = GRADIENT_POSITION_RE.exec(rest)) !== null) {
      const value = parseFloat(position[1]);
      if (!Number.isFinite(value)) continue;
      const unit = (position[2] || '').toLowerCase();
      positions.push({ value: unit === '%' ? value / 100 : value, relative: unit === '%' });
      if (positions.length === 2) break;
    }
    raw.push({
      r: parseInt(parsed.color.slice(0, 2), 16),
      g: parseInt(parsed.color.slice(2, 4), 16),
      b: parseInt(parsed.color.slice(4, 6), 16),
      a: parsed.alpha ?? 1,
      positions,
    });
  }
  if (!raw.length) return undefined;

  let longest = 0;
  let hasRelative = false;
  for (const stop of raw) {
    for (const position of stop.positions) {
      if (position.relative) hasRelative = true;
      else longest = Math.max(longest, position.value);
    }
  }
  // A length is box-relative only through the gradient line, which is not part of the computed
  // style. When the layer is expressed purely in lengths they are self-describing — the largest
  // one is the pattern tile — but mixed with percentages their fraction is unknowable, so those
  // stops fall back to CSS's even distribution rather than skewing every other stop's area.
  // The gradient line spans the background *tile* (background-size), so a 1px stop inside a
  // 40px tile covers 1/40 of the paint — that is what makes a grid a grid. Without a tile the
  // stops describe themselves: the largest authored length is the pattern extent. Mixed with
  // percentages and with no tile, a length's fraction is unknowable.
  const tile = extent && extent > 0 ? extent : undefined;
  const lengthsAreMeasurable = tile !== undefined || (longest > 0 && !hasRelative);
  const lengthScale = tile ?? longest;
  const normalize = (position: { value: number; relative: boolean }): number | undefined => {
    if (position.relative || position.value === 0) return position.value;
    return lengthsAreMeasurable ? position.value / lengthScale : undefined;
  };

  const stops: GradientAreaStop[] = [];
  raw.forEach((stop, index) => {
    const authored = stop.positions
      .map(normalize)
      .filter((value): value is number => value !== undefined);
    // CSS defaults: first stop at 0, last at 1, the rest spread evenly.
    const fallback = raw.length === 1 ? 0 : index / (raw.length - 1);
    const from = authored.length ? authored[0] : fallback;
    const to = authored.length > 1 ? authored[1] : from;
    stops.push({
      r: stop.r,
      g: stop.g,
      b: stop.b,
      a: stop.a,
      start: Math.min(Math.max(from, 0), 1),
      end: Math.min(Math.max(Math.max(to, from), 0), 1),
    });
  });
  return stops;
}

/**
 * Resolve one gradient stop color, keeping fully transparent stops.
 *
 * `parseColor` drops alpha-0 colors because an invisible *fill* is not a fill. A gradient stop
 * is different: `transparent` is what makes a stripe a stripe, and discarding it turns a
 * hairline into a flood.
 */
function parseGradientStopColor(token: string): { color: string; alpha: number } | undefined {
  const value = token.trim();
  if (/^(?:transparent|none)$/i.test(value)) return { color: '000000', alpha: 0 };
  const parsed = parseColor(value);
  if (parsed) return { color: parsed.color, alpha: parsed.alpha ?? 1 };
  // A functional color whose alpha component is zero, e.g. Chromium's computed `rgba(0, 0, 0, 0)`.
  const functional = value.match(/^[A-Za-z-]+\(([\s\S]*)\)$/);
  if (functional) {
    const components = functional[1].split(/[,/]/).map((part) => part.trim()).filter(Boolean);
    const alpha = parseFloat(components[components.length - 1] ?? '');
    if (components.length >= 4 && alpha === 0) return { color: '000000', alpha: 0 };
  }
  return undefined;
}

/**
 * Length of the gradient line inside one background tile, in px, or undefined when the tile is
 * not an explicit pair of lengths (`auto`, `cover`, `contain`, percentages of an unknown box).
 * The axis follows the gradient's own direction, which is what the stop lengths run along.
 */
function gradientLineExtent(
  layer: string,
  tile: string | undefined,
  box?: GradientBox
): number | undefined {
  const lengths = (tile ?? '')
    .trim()
    .split(/\s+/)
    .map((token) => (/^-?[\d.]+px$/i.test(token) ? parseFloat(token) : NaN));
  const tiled =
    lengths.length > 0 && lengths.every((value) => Number.isFinite(value) && value > 0);
  // No explicit tile (`auto`, `cover`, a percentage): the gradient line spans the element box.
  if (!tiled && (!box || !(box.width > 0) || !(box.height > 0))) return undefined;
  const width = tiled ? lengths[0] : box!.width;
  const height = tiled ? (lengths.length > 1 ? lengths[1] : lengths[0]) : box!.height;
  const inner = layer.trim().match(GRADIENT_FUNCTION_RE);
  const direction = inner ? (splitGradientCommaParts(inner[1])[0] ?? '') : '';
  if (/^(?:repeating-)?(?:radial|conic)-gradient/i.test(layer.trim())) {
    return Math.max(width, height);
  }
  const angle = direction.match(/(-?[\d.]+)deg/i);
  if (angle) {
    const normalized = ((parseFloat(angle[1]) % 180) + 180) % 180;
    return normalized > 45 && normalized < 135 ? width : height;
  }
  if (/\bto\s+(?:left|right)\b/i.test(direction) && !/\b(?:top|bottom)\b/i.test(direction)) {
    return width;
  }
  // `to bottom` is the CSS default when no direction is given.
  if (/\bto\s+(?:top|bottom)\b/i.test(direction) || !/\bto\b|deg|turn|rad/i.test(direction)) {
    return height;
  }
  return Math.sqrt(width * width + height * height);
}

/** Premultiplied area average of one gradient layer over the box (0..1 coverage in `a`). */
function gradientLayerAverage(
  layer: string,
  extent?: number
): { r: number; g: number; b: number; a: number } | undefined {
  const stops = parseGradientAreaStops(layer, extent);
  if (!stops) return undefined;
  let r = 0;
  let g = 0;
  let b = 0;
  let a = 0;
  // A radial gradient's stops run along a radius, so a ring's share of the box grows with r:
  // weighting by span alone made a 120px glow read as a full-slide wash.
  const radial = /^(?:repeating-)?radial-gradient/i.test(layer.trim());
  const span = (from: number, to: number): number =>
    radial ? Math.max(0, to * to - from * from) : Math.max(0, to - from);
  const add = (weight: number, first: GradientAreaStop, second: GradientAreaStop = first) => {
    if (weight <= 0) return;
    // A transition ramps linearly, so its mean is the mean of its endpoints.
    const alpha = (first.a + second.a) / 2;
    r += ((first.r * first.a + second.r * second.a) / 2) * weight;
    g += ((first.g * first.a + second.g * second.a) / 2) * weight;
    b += ((first.b * first.a + second.b * second.a) / 2) * weight;
    a += alpha * weight;
  };
  add(span(0, stops[0].start), stops[0]);
  for (let index = 0; index < stops.length; index += 1) {
    const stop = stops[index];
    add(span(stop.start, stop.end), stop);
    const next = stops[index + 1];
    if (next) add(span(stop.end, next.start), stop, next);
  }
  const last = stops[stops.length - 1];
  add(span(last.end, 1), last);
  return { r, g, b, a: Math.min(Math.max(a, 0), 1) };
}

/**
 * Measure what a background-image actually paints: its average color and the fraction of the
 * box that color covers. Layers composite source-over, first layer on top, exactly as CSS
 * paints them. Callers can then honour `background-color` showing through instead of guessing
 * from stop alpha alone.
 */
export function parseGradientCoverage(
  backgroundImage: string | undefined,
  backgroundSize?: string,
  box?: GradientBox
): GradientCoverage | undefined {
  if (!backgroundImage) return undefined;
  if (!backgroundImageHasGradientToken(backgroundImage)) return undefined;
  const tiles = backgroundSize ? splitGradientCommaParts(backgroundSize) : [];
  let r = 0;
  let g = 0;
  let b = 0;
  let a = 0;
  let measured = false;
  const layers = splitBackgroundImageLayers(backgroundImage);
  for (const [index, layer] of layers.entries()) {
    // background-size repeats over the layer list when it is shorter than background-image.
    const tile = tiles.length ? tiles[index % tiles.length] : undefined;
    const average = gradientLayerAverage(layer, gradientLineExtent(layer, tile, box));
    if (!average) continue;
    measured = true;
    // `average` is already premultiplied; composite it *under* what is above it.
    const keep = 1 - a;
    r += average.r * keep;
    g += average.g * keep;
    b += average.b * keep;
    a += average.a * keep;
  }
  if (!measured) return undefined;
  const hex = (channel: number): string => {
    const value = a > 0 ? Math.round(channel / a) : 0;
    return Math.min(Math.max(value, 0), 255).toString(16).padStart(2, '0').toUpperCase();
  };
  return { color: `${hex(r)}${hex(g)}${hex(b)}`, alpha: a };
}

/** Composite `color` at `alpha` over an opaque `base`, both six-digit hex. */
function compositeHexOver(color: string, alpha: number, base: string): string {
  const mix = (offset: number): string => {
    const top = parseInt(color.slice(offset, offset + 2), 16);
    const bottom = parseInt(base.slice(offset, offset + 2), 16);
    if (!Number.isFinite(top) || !Number.isFinite(bottom)) return base.slice(offset, offset + 2);
    return Math.round(top * alpha + bottom * (1 - alpha))
      .toString(16)
      .padStart(2, '0')
      .toUpperCase();
  };
  return `${mix(0)}${mix(2)}${mix(4)}`;
}

/**
 * Parse linear- or radial-gradient to approximate solid color before XML gradient enhancement.
 * Area-weighted (see parseGradientCoverage), then flattened onto white for callers that need a
 * single opaque color (e.g. background-clip:text fills).
 */
function parseGradientSolidApproximation(backgroundImage: string | undefined): { color: string } | undefined {
  const coverage = parseGradientCoverage(backgroundImage);
  if (!coverage) return undefined;
  return { color: compositeHexOver(coverage.color, coverage.alpha, 'FFFFFF') };
}

/**
 * Extract first url() from background-image (e.g. "linear-gradient(...), url('...')")
 * Returns the URL string or undefined if no url found
 */
export function parseBackgroundImageUrl(backgroundImage: string | undefined): string | undefined {
  if (!backgroundImage) return undefined;
  const match = backgroundImage.match(/url\s*\(\s*['"]?([^'")\s]+)['"]?\s*\)/);
  return match ? match[1].trim() : undefined;
}

/** Split gradient argument list on commas, respecting parentheses (rgb(), etc.). */
function splitGradientCommaParts(content: string): string[] {
  const parts: string[] = [];
  let currentPart = '';
  let parenDepth = 0;
  for (let i = 0; i < content.length; i++) {
    const char = content[i];
    if (char === '(') parenDepth++;
    if (char === ')') parenDepth--;
    if (char === ',' && parenDepth === 0) {
      parts.push(currentPart.trim());
      currentPart = '';
    } else {
      currentPart += char;
    }
  }
  if (currentPart) parts.push(currentPart.trim());
  return parts;
}

function extractGradientInner(
  backgroundImage: string,
  prefix: 'linear-gradient(' | 'radial-gradient('
): string | undefined {
  const startIdx = backgroundImage.indexOf(prefix);
  if (startIdx === -1) return undefined;
  let openParens = 0;
  const contentStart = startIdx + prefix.length;
  let endIdx = contentStart;
  for (let i = contentStart; i < backgroundImage.length; i++) {
    if (backgroundImage[i] === '(') openParens++;
    if (backgroundImage[i] === ')') {
      if (openParens === 0) {
        endIdx = i;
        break;
      }
      openParens--;
    }
  }
  return backgroundImage.substring(contentStart, endIdx);
}

/** CSS background-position pair → radial center as % 0–100 (OOXML fillToRect). */
function parseBackgroundPositionPair(pos: string): { cx: number; cy: number } {
  const d = { cx: 50, cy: 50 };
  const p = pos.trim();
  if (!p) return d;
  const tokens = p.split(/\s+/).filter(Boolean);
  const kw: Record<string, number> = {
    left: 0,
    center: 50,
    right: 100,
    top: 0,
    bottom: 100,
  };
  const pct = (t: string): number | undefined =>
    t.endsWith('%') ? parseFloat(t) : undefined;

  if (tokens.length >= 2) {
    const x = pct(tokens[0]) ?? kw[tokens[0].toLowerCase()] ?? 50;
    const y = pct(tokens[1]) ?? kw[tokens[1].toLowerCase()] ?? 50;
    return { cx: x, cy: y };
  }
  if (tokens.length === 1) {
    const t = tokens[0];
    const n = pct(t);
    if (n !== undefined) return { cx: n, cy: 50 };
    const k = kw[t.toLowerCase()];
    if (k !== undefined) {
      if (['left', 'center', 'right'].includes(t.toLowerCase())) return { cx: k, cy: 50 };
      if (['top', 'bottom'].includes(t.toLowerCase())) return { cx: 50, cy: k };
    }
  }
  return d;
}

function parseRadialCenterFromPreamble(preamble: string): { cx: number; cy: number } {
  const d = { cx: 50, cy: 50 };
  const p = preamble.trim();
  if (!p) return d;
  const atMatch = p.match(/\bat\s+(.+)$/is);
  if (!atMatch) return d;
  return parseBackgroundPositionPair(atMatch[1].trim());
}

function normalizeGradientStops(
  parsedStops: { color: string; position?: number; alpha?: number }[]
): GradientStop[] {
  type Draft = { color: string; position: number; alpha?: number; sourceOrder: number };
  const drafts: Draft[] = parsedStops.map((stop, index) => {
    let position: number;
    if (stop.position !== undefined) {
      position = stop.position;
    } else if (index === 0) {
      position = 0;
    } else if (index === parsedStops.length - 1) {
      position = 100;
    } else {
      const step = 100 / (parsedStops.length - 1);
      position = step * index;
    }
    return { color: stop.color, position, alpha: stop.alpha, sourceOrder: index };
  });
  drafts.sort((a, b) => (a.position !== b.position ? a.position - b.position : a.sourceOrder - b.sourceOrder));
  const stops: GradientStop[] = drafts.map(({ color, position, alpha }) => ({ color, position, alpha }));
  const last = stops[stops.length - 1];
  // CSS extends the last color to the edge; OOXML needs an explicit 100% stop
  if (last.position < 99.999) {
    stops.push({ color: last.color, position: 100, alpha: last.alpha });
  }
  return stops;
}

function parseRadialGradientInner(content: string): GradientData | undefined {
  const parts = splitGradientCommaParts(content);
  if (parts.length < 2) return undefined;

  let preamble: string;
  let stopParts: string[];
  const firstStop = parseGradientStop(parts[0]);
  if (!firstStop) {
    preamble = parts[0];
    stopParts = parts.slice(1);
  } else {
    preamble = '';
    stopParts = parts;
  }

  const { cx, cy } = parseRadialCenterFromPreamble(preamble);

  const parsedStops: { color: string; position?: number; alpha?: number }[] = [];
  for (const sp of stopParts) {
    const stop = parseGradientStop(sp);
    if (stop) parsedStops.push(stop);
  }
  if (parsedStops.length < 2) return undefined;

  const stops = normalizeGradientStops(parsedStops);

  return {
    type: 'radial',
    radialCenterX: cx,
    radialCenterY: cy,
    stops,
  };
}

/**
 * Stop positions written as lengths, as a percentage of the gradient line.
 *
 * Returns one entry per authored position, so the CSS two-position form
 * (`colour 0 14px`) becomes the two stops it actually means. Percentages are
 * left to the caller; without a known extent a length cannot be placed at all,
 * and guessing is worse than leaving the stop unpositioned.
 */
function lengthStopPositions(stopStr: string, extent?: number): number[] {
  if (!extent || extent <= 0) return [];
  const rest = stopStr.replace(
    /^\s*(?:(?:rgba?|hsla?|oklch|oklab|color|color-mix)\s*\([\s\S]*?\)|#[0-9A-Fa-f]{3,8}|[A-Za-z][A-Za-z-]*)/,
    ''
  );
  const positions: number[] = [];
  const pattern = /(-?[\d.]+)\s*(px|pt|rem|em|vw|vh|cm|mm|in|%)?/g;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(rest)) !== null) {
    const value = parseFloat(match[1]);
    if (!Number.isFinite(value)) continue;
    const unit = (match[2] || '').toLowerCase();
    if (unit === '%') {
      positions.push(value);
    } else if (value === 0) {
      positions.push(0);
    } else if (unit) {
      positions.push(Math.min(100, Math.max(0, (value / extent) * 100)));
    }
    if (positions.length === 2) break;
  }
  // Only meaningful when at least one position was a length; a pure-percentage
  // stop is already handled by the caller.
  return /(-?[\d.]+)\s*(?:px|pt|rem|em|vw|vh|cm|mm|in)/.test(rest) ? positions : [];
}

function parseLinearGradientInner(
  content: string,
  extent?: number
): GradientData | undefined {
  const parts = splitGradientCommaParts(content);

  let angle = 180;
  let colorStartIndex = 0;

  if (parts[0].includes('deg')) {
    const parsedAngle = parseFloat(parts[0]);
    angle = isNaN(parsedAngle) ? 180 : parsedAngle;
    colorStartIndex = 1;
  } else if (parts[0].startsWith('to ')) {
    angle = convertDirectionToAngle(parts[0].substring(3).trim());
    colorStartIndex = 1;
  }

  const parsedStops: { color: string; position?: number; alpha?: number }[] = [];
  for (let i = colorStartIndex; i < parts.length; i++) {
    const stop = parseGradientStop(parts[i]);
    if (!stop) continue;
    // A stop's position may be a *length*, and it may be a pair: CSS
    // `#1A365D 0 14px` is one colour spanning 0 to 14px. The old parser read
    // percentages only, so both of those positions were dropped and the
    // normalizer spread the stops evenly — a 14px navy edge stripe exported as
    // a navy half-slide fading to white, painted over the title.
    const lengths = lengthStopPositions(parts[i], extent);
    if (lengths.length) {
      for (const position of lengths) parsedStops.push({ ...stop, position });
      continue;
    }
    parsedStops.push(stop);
  }

  if (parsedStops.length < 2) return undefined;

  const stops = normalizeGradientStops(parsedStops);

  return { type: 'linear', angle, stops };
}

/**
 * Parse complete gradient information (new function for style enhancement)
 * Returns full gradient data with angle, color stops, etc.
 */
export function parseGradientFull(
  backgroundImage: string | undefined,
  box?: GradientBox,
  backgroundSize?: string
): GradientData | undefined {
  if (!backgroundImage) return undefined;

  const linIdx = backgroundImage.indexOf('linear-gradient(');
  const radIdx = backgroundImage.indexOf('radial-gradient(');

  if (radIdx >= 0 && (linIdx < 0 || radIdx < linIdx)) {
    const inner = extractGradientInner(backgroundImage, 'radial-gradient(');
    if (inner !== undefined) {
      const radial = parseRadialGradientInner(inner);
      if (radial) return radial;
    }
  }

  if (linIdx >= 0) {
    const inner = extractGradientInner(backgroundImage, 'linear-gradient(');
    if (inner === undefined) return undefined;
    const layer = `linear-gradient(${inner})`;
    const tiles = backgroundSize ? splitGradientCommaParts(backgroundSize) : [];
    const extent = gradientLineExtent(layer, tiles[0], box);
    return parseLinearGradientInner(inner, extent);
  }

  return undefined;
}

/**
 * Convert CSS gradient direction keyword to angle (CSS: 0°=up, 90°=right, 180°=down)
 * Browsers may return "to X" or "to X Y" - normalize before lookup
 */
function convertDirectionToAngle(direction: string): number {
  const normalized = direction.trim().toLowerCase().replace(/\s+/g, ' ');
  const map: Record<string, number> = {
    'top': 0, 'right': 90, 'bottom': 180, 'left': 270,
    'top right': 45, 'right top': 45,
    'bottom right': 135, 'right bottom': 135,
    'bottom left': 225, 'left bottom': 225,
    'top left': 315, 'left top': 315,
  };
  return map[normalized] ?? 180;
}

/**
 * Parse a gradient color stop
 * Format: "rgba(255, 0, 0, 0.5) 25%" or "oklch(0.5 0.2 180) 50%" or "#FF0000 75%"
 */
function parseGradientStop(stopStr: string): { color: string; position?: number; alpha?: number } | undefined {
  // Extract color: rgba/rgb, oklch, oklab, or #hex
  const rgbaMatch = stopStr.match(/rgba?\([^)]+\)/);
  const oklchMatch = stopStr.match(/oklch\([^)]+\)/);
  const oklabMatch = stopStr.match(/oklab\([^)]+\)/);
  const hexMatch = stopStr.match(/#[0-9A-Fa-f]{6}/);

  let color: string | undefined;
  let alpha: number | undefined;

  // CSS keyword (computed styles may still say "transparent" in authored gradients)
  if (/^\s*transparent\b/i.test(stopStr.trim())) {
    color = '000000';
    alpha = 0;
  }

  const colorStr = rgbaMatch?.[0] ?? oklchMatch?.[0] ?? oklabMatch?.[0];
  if (colorStr) {
    const parsed = parseColor(colorStr);
    if (parsed) {
      color = parsed.color;
      alpha = parsed.alpha;
    } else if (rgbaMatch) {
      // parseColor returns undefined for alpha=0, but gradients need transparent stops
      const rgbaComma = rgbaMatch[0].match(/rgba?\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*([\d.]+))?\)/);
      if (rgbaComma) {
        const r = parseInt(rgbaComma[1]).toString(16).padStart(2, '0').toUpperCase();
        const g = parseInt(rgbaComma[2]).toString(16).padStart(2, '0').toUpperCase();
        const b = parseInt(rgbaComma[3]).toString(16).padStart(2, '0').toUpperCase();
        color = `${r}${g}${b}`;
        alpha = rgbaComma[4] !== undefined ? parseFloat(rgbaComma[4]) : 1;
      } else {
        // Space-separated: rgb(0 0 0 / 0) — parseColor drops alpha=0
        const rgbaSpace = rgbaMatch[0].match(
          /^rgba?\(\s*(\d+)\s+(\d+)\s+(\d+)(?:\s*\/\s*([\d.]+))?\s*\)$/i
        );
        if (rgbaSpace) {
          const r = parseInt(rgbaSpace[1], 10).toString(16).padStart(2, '0').toUpperCase();
          const g = parseInt(rgbaSpace[2], 10).toString(16).padStart(2, '0').toUpperCase();
          const b = parseInt(rgbaSpace[3], 10).toString(16).padStart(2, '0').toUpperCase();
          color = `${r}${g}${b}`;
          alpha = rgbaSpace[4] !== undefined ? parseFloat(rgbaSpace[4]) : 1;
        }
      }
    }
  } else if (hexMatch) {
    color = hexMatch[0].substring(1).toUpperCase();
  }

  if (!color) return undefined;

  // Extract position percentage (leave undefined if not specified)
  const percentMatch = stopStr.match(/(\d+(?:\.\d+)?)%/);
  const position = percentMatch ? parseFloat(percentMatch[1]) : undefined;

  return { color, position, alpha };
}

/**
 * Get shape fill options for pptxgenjs
 */
export function getFillOptions(styles: ComputedStyles, box?: GradientBox): any {
  const options: any = {};

  const backgroundClip = styles.backgroundClip ?? styles.webkitBackgroundClip;
  if (backgroundClip === 'text') {
    return options;
  }

  const bgColorResult = parseColor(styles.backgroundColor);

  // CSS paints background-image over background-color, and a gradient covers only the area its
  // stops describe. Measure that coverage (parseGradientCoverage) instead of inferring it from
  // stop alpha: a hairline grid — `rgba(...,.48) 0 1px, transparent 1px 80px` — has an opaque
  // stop yet paints 0.6% of the box, and flooding the shape with its color tinted whole slides.
  const coverage = parseGradientCoverage(styles.backgroundImage, styles.backgroundSize, box);
  if (coverage) {
    const opacityTransparency = parseTransparency(styles.opacity);
    const applyOpacity = (fill: any): any => {
      if (opacityTransparency > 0 && fill.transparency === undefined) {
        fill.transparency = opacityTransparency;
      }
      return fill;
    };
    if (coverage.alpha >= GRADIENT_OPAQUE_COVERAGE) {
      options.fill = applyOpacity({
        color: compositeHexOver(coverage.color, coverage.alpha, bgColorResult?.color ?? 'FFFFFF'),
      });
      return options;
    }
    if (bgColorResult) {
      // The color layer shows through; composite the gradient onto it and keep its own alpha.
      options.fill = { color: compositeHexOver(coverage.color, coverage.alpha, bgColorResult.color) };
      if (bgColorResult.alpha !== undefined) {
        options.fill.transparency = Math.round((1 - bgColorResult.alpha) * 100);
      }
      applyOpacity(options.fill);
      return options;
    }
    if (coverage.alpha <= GRADIENT_INVISIBLE_COVERAGE) {
      // Decoration only (hairlines, faint diagonals): nothing to fill. A 95%-transparent grey
      // box used to stand in for this and washed out every slide it appeared on.
      return options;
    }
    options.fill = applyOpacity({
      color: coverage.color,
      transparency: Math.round((1 - coverage.alpha) * 100),
    });
    return options;
  }
  if (bgColorResult) {
    options.fill = { color: bgColorResult.color };

    // Use alpha from rgba() if present, otherwise use opacity style
    // pptxgenjs expects transparency INSIDE fill object for createColorElement to add a:alpha
    if (bgColorResult.alpha !== undefined) {
      // Convert alpha (0-1) to transparency percentage (0-100): 0=opaque, 100=fully transparent
      options.fill.transparency = Math.round((1 - bgColorResult.alpha) * 100);
    } else {
      const transparency = parseTransparency(styles.opacity);
      if (transparency > 0) {
        options.fill.transparency = transparency;
      }
    }
  }

  return options;
}

/**
 * CSS used value for a uniform corner radius: min(specified, width/2, height/2).
 * Needed when authors use huge px (e.g. Tailwind `rounded-full` → 9999px); without
 * clamping, downstream logic can mis-classify a pill bar as an ellipse.
 */
function clampCornerRadiusPx(
  rPx: number,
  widthPx?: number,
  heightPx?: number
): number {
  if (
    rPx <= 0 ||
    widthPx === undefined ||
    heightPx === undefined ||
    !Number.isFinite(widthPx) ||
    !Number.isFinite(heightPx) ||
    widthPx <= 0 ||
    heightPx <= 0
  ) {
    return rPx;
  }
  return Math.min(rPx, widthPx / 2, heightPx / 2);
}

/**
 * Parse border radius from CSS to inches
 */
export function parseBorderRadius(
  borderRadius: string | undefined,
  widthPx?: number,
  heightPx?: number
): number | undefined {
  if (!borderRadius) return undefined;
  const trimmed = borderRadius.trim();
  if (!trimmed || trimmed === '0' || trimmed === '0px' || trimmed === '0%') return undefined;

  const firstToken = trimmed.split('/')[0]?.trim().split(/\s+/)[0];
  if (!firstToken) return undefined;

  const minDimensionPx =
    typeof widthPx === 'number' && typeof heightPx === 'number'
      ? Math.min(widthPx, heightPx)
      : undefined;

  if (firstToken.endsWith('%')) {
    if (minDimensionPx === undefined) return undefined;
    const percent = parseFloat(firstToken);
    if (isNaN(percent) || percent <= 0) return undefined;
    const rawPx = (percent / 100) * minDimensionPx;
    return pxToInch(clampCornerRadiusPx(rawPx, widthPx, heightPx));
  }

  const px = parseFloat(firstToken);
  if (isNaN(px) || px <= 0) return undefined;

  return pxToInch(clampCornerRadiusPx(px, widthPx, heightPx));
}

/**
 * Parse individual corner radii from CSS border-radius
 * Returns [topLeft, topRight, bottomRight, bottomLeft] in inches
 * CSS border-radius format:
 * - 1 value: all corners
 * - 2 values: [top-left & bottom-right, top-right & bottom-left]
 * - 3 values: [top-left, top-right & bottom-left, bottom-right]
 * - 4 values: [top-left, top-right, bottom-right, bottom-left]
 */
export function parseCornerRadii(
  borderRadius: string | undefined,
  widthPx?: number,
  heightPx?: number
): [number, number, number, number] {
  if (!borderRadius) {
    return [0, 0, 0, 0];
  }
  const trimmed = borderRadius.trim();
  if (!trimmed || trimmed === '0' || trimmed === '0px' || trimmed === '0%') {
    return [0, 0, 0, 0];
  }

  const [horizontalPart, verticalPart] = trimmed.split('/');
  const horizontalValues = expandRadiusValues(parseRadiusList(horizontalPart, widthPx));
  const verticalValues = expandRadiusValues(parseRadiusList(verticalPart ?? horizontalPart, heightPx));

  const cornerPx = (i: number) =>
    clampCornerRadiusPx(
      Math.min(horizontalValues[i], verticalValues[i]),
      widthPx,
      heightPx
    );

  return [
    pxToInch(cornerPx(0)),
    pxToInch(cornerPx(1)),
    pxToInch(cornerPx(2)),
    pxToInch(cornerPx(3)),
  ];
}

function parseRadiusList(part: string | undefined, referencePx?: number): number[] {
  if (!part) return [0];
  const tokens = part.trim().split(/\s+/).filter(Boolean);
  if (tokens.length === 0) return [0];
  return tokens.map((token) => {
    const value = token.trim();
    if (value.endsWith('%')) {
      if (referencePx === undefined) return 0;
      const percent = parseFloat(value);
      if (isNaN(percent) || percent <= 0) return 0;
      return (percent / 100) * referencePx;
    }
    const px = parseFloat(value);
    return isNaN(px) || px <= 0 ? 0 : px;
  });
}

function expandRadiusValues(values: number[]): [number, number, number, number] {
  if (values.length === 0) return [0, 0, 0, 0];
  if (values.length === 1) return [values[0], values[0], values[0], values[0]];
  if (values.length === 2) return [values[0], values[1], values[0], values[1]];
  if (values.length === 3) return [values[0], values[1], values[2], values[1]];
  return [values[0], values[1], values[2], values[3]];
}

/**
 * Get border/line options for pptxgenjs
 * Handles rgba alpha → PowerPoint transparency (0 = opaque, 100 = full transparent)
 */
export function getLineOptions(styles: ComputedStyles): any {
  let borderWidth = parseBorderWidth(styles.borderWidth?.toString());
  let borderColor = styles.borderColor;
  let borderStyle = styles.borderStyle;

  // Computed `borderWidth` can be empty while per-side widths are set (common on chips).
  if (borderWidth === 0) {
    const sideWidths = [
      styles.borderTopWidth,
      styles.borderRightWidth,
      styles.borderBottomWidth,
      styles.borderLeftWidth,
    ]
      .map((w) => parseFloat(String(w || '0')) || 0)
      .filter((w) => w > 0);
    if (sideWidths.length > 0) {
      const px = Math.max(...sideWidths);
      borderWidth = parseBorderWidth(`${px}px`);
      borderColor =
        styles.borderTopColor ||
        styles.borderRightColor ||
        styles.borderBottomColor ||
        styles.borderLeftColor ||
        borderColor;
      borderStyle =
        styles.borderTopStyle ||
        styles.borderRightStyle ||
        styles.borderBottomStyle ||
        styles.borderLeftStyle ||
        borderStyle;
    }
  }
  if (borderWidth === 0) return undefined;

  const borderColorResult = parseColor(borderColor);
  if (!borderColorResult) return undefined;

  const dashType = parseBorderStyleToDashType(borderStyle);
  const lineOptions: { color: string; width: number; dashType?: string; transparency?: number } = {
    color: borderColorResult.color || '000000',
    width: borderWidth,
    dashType: dashType !== 'solid' ? dashType : undefined,
  };
  if (borderColorResult.alpha !== undefined && borderColorResult.alpha < 1) {
    lineOptions.transparency = Math.round((1 - borderColorResult.alpha) * 100);
  }
  return lineOptions;
}

/**
 * Get table cell border options for pptxgenjs
 * Returns border: [top, right, bottom, left] - each side is {type, pt, color} or null
 * pptxgenjs table borders do not support transparency; semi-transparent CSS borders are
 * composited onto the cell's effective background (from inspector).
 */
export function getTableCellBorderOptions(
  styles: any,
  effectiveBackgroundColor?: string
): any[] | undefined {
  const backdrop = resolveBackdropRgb(effectiveBackgroundColor);

  const parseSide = (width: string | undefined, color: string | undefined) => {
    const px = parseFloat(String(width || '0')) || 0;
    if (px <= 0) return null;
    const colorResult = parseColor(color);
    if (!colorResult) return null;

    let borderColor = colorResult.color;
    if (colorResult.alpha !== undefined && colorResult.alpha < 1) {
      const r = parseInt(colorResult.color.slice(0, 2), 16);
      const g = parseInt(colorResult.color.slice(2, 4), 16);
      const b = parseInt(colorResult.color.slice(4, 6), 16);
      borderColor = blendRgbaOnBackground(
        r,
        g,
        b,
        colorResult.alpha,
        backdrop.r,
        backdrop.g,
        backdrop.b
      );
    }

    const pt = parseBorderWidth(String(px));
    return { type: 'solid' as const, pt, color: borderColor };
  };

  const top = parseSide(styles.borderTopWidth, styles.borderTopColor);
  const right = parseSide(styles.borderRightWidth, styles.borderRightColor);
  const bottom = parseSide(styles.borderBottomWidth, styles.borderBottomColor);
  const left = parseSide(styles.borderLeftWidth, styles.borderLeftColor);

  if (!top && !right && !bottom && !left) return undefined;

  return [top, right, bottom, left];
}
