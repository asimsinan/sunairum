"use strict";
/**
 * Apply presentation hints (color, size) to OMML produced by mathml2omml.
 *
 * PowerPoint is strict: use only valid children inside m:rPr (w:color, m:sz).
 * Do NOT insert DrawingML a:solidFill or a sibling w:rPr block — both can trigger repair.
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.PPT_MATH_A_RPR_SZ_FACTOR = void 0;
exports.mathFractionDepth = mathFractionDepth;
exports.fitMathFontSizePx = fitMathFontSizePx;
exports.isLightTextColor = isLightTextColor;
exports.getMathPresentationMeta = getMathPresentationMeta;
exports.rewriteLimUppAccentsToOmmlAcc = rewriteLimUppAccentsToOmmlAcc;
exports.sanitizeOmmlForPptx = sanitizeOmmlForPptx;
exports.stripUndeclaredWordMlFromSlide = stripUndeclaredWordMlFromSlide;
const style_1 = require("./style");
/**
 * Legacy dampening factor (no longer applied when host-box scaling is used).
 * Kept for callers/tests that import the constant.
 */
exports.PPT_MATH_A_RPR_SZ_FACTOR = 1.0;
/** Nested `<mfrac>` depth in MathML (0 = no fraction). */
function mathFractionDepth(mathml) {
    if (!mathml)
        return 0;
    let depth = 0;
    let max = 0;
    const re = /<\/?mfrac\b[^>]*>/gi;
    let m;
    while ((m = re.exec(mathml))) {
        if (m[0].startsWith('</'))
            depth = Math.max(0, depth - 1);
        else {
            depth += 1;
            max = Math.max(max, depth);
        }
    }
    return max;
}
/**
 * Font size so Office Math (esp. fractions) fits inside the formula plate with air.
 *
 * Prior `0.38 * hostH` assumed single-line glyphs; a fraction paints ~2.5–3.4× that
 * tall and clipped the blue host. Scale from usable height after padding + breathing room.
 */
function fitMathFontSizePx(opts) {
    const hostH = Math.max(0, Number(opts.hostH) || 0);
    const hostW = Math.max(0, Number(opts.hostW) || 0);
    const padT = Math.max(0, Number(opts.paddingTopPx) || 0);
    const padB = Math.max(0, Number(opts.paddingBottomPx) || 0);
    // Keep visible air even when CSS padding is missing on the host styles.
    const air = Math.max(14, hostH * 0.12);
    const usable = Math.max(20, hostH - padT - padB - air);
    const depth = mathFractionDepth(opts.mathml);
    const heightMul = depth >= 2 ? 3.4 : depth === 1 ? 2.7 : 1.4;
    let fs = usable / heightMul;
    if (hostW > 40)
        fs = Math.min(fs, hostW / 17);
    fs = Math.min(64, Math.max(13, fs));
    const computed = Number(opts.computedFs) || 0;
    if (computed >= 13) {
        // Never enlarge past what fits; allow a slightly smaller author size.
        return Math.round(Math.min(computed, fs));
    }
    return Math.round(fs);
}
/** True when CSS text color is light (e.g. #f8fafc on dark slides). */
function isLightTextColor(styles) {
    const c = (0, style_1.parseColor)(styles.color);
    if (!c?.color || c.color.length < 6)
        return false;
    const r = parseInt(c.color.slice(0, 2), 16);
    const g = parseInt(c.color.slice(2, 4), 16);
    const b = parseInt(c.color.slice(4, 6), 16);
    const lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
    return lum > 0.72;
}
/**
 * Derive OMML color/size/alignment from the inspected <math> element.
 */
function getMathPresentationMeta(element) {
    const colorRes = (0, style_1.parseColor)(element.styles.color);
    const boxH = Number(element.height) || 0;
    const boxW = Number(element.width) || 0;
    const computedFs = Math.max(1, parseFloat(String(element.styles.fontSize ?? '')) || 16);
    const padT = parseFloat(String(element.styles.paddingTop ?? '0')) || 0;
    const padB = parseFloat(String(element.styles.paddingBottom ?? '0')) || 0;
    let fontSizePx = computedFs;
    if (boxH >= 48) {
        fontSizePx = fitMathFontSizePx({
            hostH: boxH,
            hostW: boxW,
            computedFs,
            mathml: element.mathml,
            paddingTopPx: padT,
            paddingBottomPx: padB,
        });
    }
    const cssPt = (fontSizePx * 72) / 96;
    // OOXML a:rPr@sz expects 1/100 pt; we pass half-points downstream and convert later.
    const szHalfPt = Math.max(2, Math.round(cssPt * 2));
    const align = element.styles.textAlign;
    // Office Math behaves like "center" by default (when m:jc is omitted).
    // In browsers, computed `text-align` often resolves to `left/start` even when authors
    // did not explicitly set it. Treat `left/start` as "unspecified" here.
    let mathJc = 'center';
    if (align === 'right' || align === 'end')
        mathJc = 'right';
    else if (align === 'center')
        mathJc = 'center';
    else
        mathJc = 'center';
    return {
        colorHex: colorRes?.color,
        szHalfPt,
        mathJc,
    };
}
/**
 * Prepare OMML from mathml2omml for PowerPoint.
 * - Strip WordprocessingML `w:*` (e.g. `<w:rPr/>`) — slide has no xmlns:w → corrupt XML.
 * - Strip redundant xmlns on `<m:oMath>` (declared on `m:oMathPara` wrapper).
 * - Unwrap outer `<m:oMathPara>` if converter already wrapped (avoid double wrap).
 */
const OMML_TEXT_CONTAINER = /<(m:e|m:num|m:den|m:sub|m:sup|m:lim|m:limLow|m:limUpp)>([\s\S]*?)<\/\1>/g;
function hasBareTextOutsideMt(inner) {
    const withoutMt = inner.replace(/<m:t\b[^>]*>[\s\S]*?<\/m:t>/g, '');
    return withoutMt.replace(/<[^>]+>/g, '').trim().length > 0;
}
/** Wrap only top-level stray text in OMML containers (do not touch text inside m:t). */
function wrapTopLevelBareOmmlText(inner) {
    const parts = inner.split(/(<[^>]+>)/);
    let depth = 0;
    let result = '';
    for (const part of parts) {
        if (!part)
            continue;
        if (part.startsWith('<')) {
            const selfClose = /\/>\s*$/.test(part);
            const closing = /^<\//.test(part);
            if (closing)
                depth = Math.max(0, depth - 1);
            result += part;
            if (!selfClose && !closing)
                depth++;
        }
        else if (depth === 0 && part.trim()) {
            const escaped = part
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;');
            result += `<m:r><m:t xml:space="preserve">${escaped}</m:t></m:r>`;
        }
        else {
            result += part;
        }
    }
    return result;
}
/** Wrap stray character data inside OMML containers in m:r/m:t (PowerPoint rejects bare text). */
function wrapBareOmmlTextInMathContainers(omml) {
    return omml.replace(OMML_TEXT_CONTAINER, (_match, tag, inner) => {
        if (!hasBareTextOutsideMt(inner))
            return `<${tag}>${inner}</${tag}>`;
        const wrapped = wrapTopLevelBareOmmlText(inner);
        return `<${tag}>${wrapped}</${tag}>`;
    });
}
/**
 * Safety net: hat/dot overscripts that still arrived as limUpp (limit) → m:acc.
 * PowerPoint draws limUpp marks far above the base; accents sit tight.
 */
function rewriteLimUppAccentsToOmmlAcc(omml) {
    // <m:limUpp><m:e>BASE</m:e><m:lim><m:r>…<m:t>^|ˆ|˙|…</m:t></m:r></m:lim></m:limUpp>
    return omml.replace(/<m:limUpp>\s*<m:e>([\s\S]*?)<\/m:e>\s*<m:lim>\s*<m:r>([\s\S]*?)<m:t[^>]*>([\s\S]*?)<\/m:t>([\s\S]*?)<\/m:r>\s*<\/m:lim>\s*<\/m:limUpp>/gi, (full, base, _pre, chrRaw, _post) => {
        const chr = chrRaw
            .replace(/&amp;/g, '&')
            .replace(/&#x0*5E;/gi, '^')
            .replace(/&#94;/g, '^')
            .trim();
        const accentMap = {
            '^': 'ˆ',
            'ˆ': 'ˆ',
            '̂': '̂',
            '˙': '˙',
            '.': '˙',
            '·': '˙',
            '¯': '¯',
            '˜': '˜',
            'ˇ': 'ˇ',
            '˘': '˘',
        };
        const acc = accentMap[chr];
        if (!acc)
            return full;
        return `<m:acc><m:accPr><m:chr m:val="${acc}"/></m:accPr><m:e>${base}</m:e></m:acc>`;
    });
}
function sanitizeOmmlForPptx(omml) {
    let result = rewriteLimUppAccentsToOmmlAcc(omml.trim());
    result = result.replace(/<w:rPr\b[^>]*\/>/g, '');
    result = result.replace(/<w:rPr\b[^>]*>[\s\S]*?<\/w:rPr>/g, '');
    result = result.replace(/<w:[a-zA-Z]+[^>]*\/>/g, '');
    result = result.replace(/<w:[a-zA-Z]+[^>]*>[\s\S]*?<\/w:[a-zA-Z]+>/g, '');
    result = result.replace(/<m:sty\b[^>]*m:val="undefined"[^>]*\/?>/g, '');
    result = result.replace(/<m:rPr>\s*<m:nor\s*\/>\s*<\/m:rPr>/g, '');
    // Mathematical Italic Nabla (U+1D6FB) → Nabla operator (U+2207)
    result = result.replace(/\u{1D6FB}/gu, '\u2207');
    // KaTeX `<mi mathvariant="normal">∇</mi>`: force upright nabla in PPT (not italic 𝛻 glyph)
    result = result.replace(/<m:r>\s*(?:<m:rPr>[\s\S]*?<\/m:rPr>\s*)?<m:t(\b[^>]*)>([^<]*∇[^<]*)<\/m:t>\s*<\/m:r>/g, (_match, tAttrs, text) => `<m:r><m:rPr><m:sty m:val="p"/></m:rPr><m:t${tAttrs}>${text}</m:t></m:r>`);
    // mathml2omml may emit empty nary integrand; PPT rejects <m:e/>
    result = result.replace(/<m:e\s*\/>(?=\s*<\/m:nary>)/g, '<m:e><m:r><m:t xml:space="preserve"> </m:t></m:r></m:e>');
    // KaTeX mhchem reaction arrows → <m:limUpp>…<m:lim/>; empty lim breaks PPT
    result = result.replace(/<m:lim\s*\/>/g, '<m:lim><m:r><m:t xml:space="preserve"> </m:t></m:r></m:lim>');
    // mathml2omml may leave summand text (e.g. p(x)) outside <m:t> — invalid in PPT
    result = wrapBareOmmlTextInMathContainers(result);
    // Repair: sometimes OMML is (incorrectly) serialized into text as `&lt;m:r&gt;&lt;m:t...&gt;...`
    // but the closing `</m:t></m:r>` is real markup. That both corrupts XML *and* shows OOXML
    // source in PowerPoint. Collapse those serialized runs back to plain text.
    result = result.replace(/&lt;m:r&gt;&lt;m:t\b[^&]*?&gt;([\s\S]*?)<\/m:t>\s*<\/m:r>/gi, '$1');
    // Some pipelines accidentally serialize OMML fragments into text by escaping only the
    // opening tags (`&lt;m:r&gt;...`) but leaving closing tags as real markup (`</m:t></m:r>`),
    // which corrupts the XML tree (m:t closes early, following tags mismatch).
    //
    // If we see an escaped OMML opener, force the corresponding closers to be escaped too.
    result = result.replace(/(&lt;m:r&gt;&lt;m:t\b[^&]*?&gt;[\s\S]*?)<\/m:t>\s*<\/m:r>/gi, '$1&lt;/m:t&gt;&lt;/m:r&gt;');
    // Hidden upper limit / sqrt degree still need a child element
    result = result.replace(/<m:sup\s*\/>/g, '<m:sup><m:r><m:t xml:space="preserve"> </m:t></m:r></m:sup>');
    result = result.replace(/<m:deg\s*\/>/g, '<m:deg><m:r><m:t xml:space="preserve"> </m:t></m:r></m:deg>');
    if (/^<m:oMathPara\b/i.test(result)) {
        result = result
            .replace(/^<m:oMathPara\b[^>]*>/i, '')
            .replace(/<\/m:oMathPara>\s*$/i, '')
            .trim();
    }
    // PowerPoint (and XML parsers) require `<` and bare `&` in `<m:t>` text to be escaped.
    // Keep this narrowly scoped: only escape plain text runs (no embedded serialized OMML).
    result = result.replace(/<m:t\b([^>]*)>([\s\S]*?)<\/m:t>/gi, (_m, attrs, text) => {
        // If `<m:t>` contains serialized OMML tags, it's not meant to show up in PPT.
        // Strip the serialized tags but keep the actual characters (e.g. `⋮` in matrices).
        let t = text;
        if (/&lt;\s*\/?\s*m:/i.test(t)) {
            t = t.replace(/&lt;\s*\/?\s*m:[^&]*?&gt;/gi, '');
            return `<m:t${attrs}>${t}</m:t>`;
        }
        // First, escape bare ampersands (do not double-escape existing entities).
        t = t.replace(/&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9a-fA-F]+;)/g, '&amp;');
        // Then escape angle brackets defensively.
        t = t.replace(/</g, '&lt;').replace(/>/g, '&gt;');
        return `<m:t${attrs}>${t}</m:t>`;
    });
    return result.replace(/<m:oMath(\s[^>]*)>/i, (_match, attrs) => {
        const cleaned = attrs
            .replace(/\s+xmlns:m="[^"]*"/gi, '')
            .replace(/\s+xmlns:w="[^"]*"/gi, '');
        return `<m:oMath${cleaned}>`;
    });
}
/** Remove WordprocessingML tags when slide root has no xmlns:w (post-equation safety net). */
function stripUndeclaredWordMlFromSlide(slideXml) {
    if (/xmlns:w=/.test(slideXml))
        return slideXml;
    if (!/<w:[a-zA-Z]/.test(slideXml))
        return slideXml;
    let xml = slideXml;
    xml = xml.replace(/<w:rPr\b[^>]*\/>/g, '');
    xml = xml.replace(/<w:rPr\b[^>]*>[\s\S]*?<\/w:rPr>/g, '');
    xml = xml.replace(/<w:[a-zA-Z]+[^>]*\/>/g, '');
    xml = xml.replace(/<w:[a-zA-Z]+[^>]*>[\s\S]*?<\/w:[a-zA-Z]+>/g, '');
    return xml;
}
