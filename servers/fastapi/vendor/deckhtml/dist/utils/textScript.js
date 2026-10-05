"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.scriptToOoxmlLang = scriptToOoxmlLang;
exports.detectContainerScriptHints = detectContainerScriptHints;
exports.classifyChar = classifyChar;
exports.splitTextByScript = splitTextByScript;
/** Han chars that strongly indicate Traditional Chinese. */
const TRADITIONAL_HAN_RE = /[臺灣國說這裡與專業麼為體經關開無電圖廠報網藝標樣舊劃壓複極爭萬與東絲兩嚴喪豐臨麗舉義烏樂喬鄉買處務勝勞齒龍龜齊廣醫學陰陽總雲畫會議證當應確價買賣]/u;
const OOXML_LANG = {
    sc: 'zh-CN',
    tc: 'zh-TW',
    jp: 'ja-JP',
    kr: 'ko-KR',
    ar: 'ar-SA',
    he: 'he-IL',
    latin: 'en-US',
};
function scriptToOoxmlLang(script) {
    return OOXML_LANG[script];
}
function detectContainerScriptHints(text) {
    let hasKana = false;
    let hasHangul = false;
    let hasTraditionalHan = false;
    for (const ch of text) {
        const cp = ch.codePointAt(0);
        if (isKana(cp))
            hasKana = true;
        if (isHangul(cp))
            hasHangul = true;
        if (isCjkHan(cp) && TRADITIONAL_HAN_RE.test(ch))
            hasTraditionalHan = true;
        if (hasKana && hasHangul && hasTraditionalHan)
            break;
    }
    return { hasKana, hasHangul, hasTraditionalHan };
}
function isKana(cp) {
    return ((cp >= 0x3040 && cp <= 0x309f) ||
        (cp >= 0x30a0 && cp <= 0x30ff) ||
        (cp >= 0x31f0 && cp <= 0x31ff));
}
function isHangul(cp) {
    return ((cp >= 0xac00 && cp <= 0xd7af) ||
        (cp >= 0x1100 && cp <= 0x11ff) ||
        (cp >= 0x3130 && cp <= 0x318f));
}
function isArabic(cp) {
    return ((cp >= 0x0600 && cp <= 0x06ff) ||
        (cp >= 0x0750 && cp <= 0x077f) ||
        (cp >= 0x08a0 && cp <= 0x08ff) ||
        (cp >= 0xfb50 && cp <= 0xfdff) ||
        (cp >= 0xfe70 && cp <= 0xfeff));
}
function isHebrew(cp) {
    return cp >= 0x0590 && cp <= 0x05ff;
}
function isCjkHan(cp) {
    return ((cp >= 0x4e00 && cp <= 0x9fff) ||
        (cp >= 0x3400 && cp <= 0x4dbf) ||
        (cp >= 0xf900 && cp <= 0xfaff));
}
function isLatinLike(cp) {
    if (cp <= 0x007f)
        return true;
    if (cp >= 0x00a0 && cp <= 0x00ff)
        return true;
    if (cp >= 0x0100 && cp <= 0x024f)
        return true;
    return false;
}
function isNeutral(cp) {
    if (cp === 0x200b || cp === 0xfeff)
        return true;
    const cat = /\s/u.test(String.fromCodePoint(cp));
    return cat;
}
function isCjkPunctuation(cp) {
    if (cp >= 0x3000 && cp <= 0x303f)
        return true;
    if (cp >= 0xfe30 && cp <= 0xfe4f)
        return true;
    if (cp >= 0xff01 && cp <= 0xff0f)
        return true;
    if (cp >= 0xff1a && cp <= 0xff20)
        return true;
    if (cp >= 0xff3b && cp <= 0xff40)
        return true;
    if (cp >= 0xff5b && cp <= 0xff65)
        return true;
    return false;
}
function classifyHan(hints) {
    if (hints.hasKana)
        return 'jp';
    if (hints.hasHangul)
        return 'kr';
    if (hints.hasTraditionalHan)
        return 'tc';
    return 'sc';
}
function classifyChar(cp, hints) {
    if (isHangul(cp))
        return 'kr';
    if (isKana(cp))
        return 'jp';
    if (isArabic(cp))
        return 'ar';
    if (isHebrew(cp))
        return 'he';
    if (isCjkHan(cp) || isCjkPunctuation(cp))
        return classifyHan(hints);
    if (isLatinLike(cp) || isNeutral(cp))
        return 'latin';
    return 'latin';
}
function mergeAdjacentSegments(segments) {
    if (segments.length <= 1)
        return segments;
    const merged = [{ ...segments[0] }];
    for (let i = 1; i < segments.length; i++) {
        const seg = segments[i];
        const last = merged[merged.length - 1];
        if (last.script === seg.script) {
            last.text += seg.text;
        }
        else {
            merged.push({ ...seg });
        }
    }
    return merged;
}
/**
 * Split text into consecutive runs of the same script.
 * Neutral whitespace attaches to the adjacent script when possible.
 */
function splitTextByScript(text, hints) {
    if (!text)
        return [];
    const resolvedHints = hints ?? detectContainerScriptHints(text);
    const segments = [];
    let currentScript = null;
    let currentText = '';
    const flush = () => {
        if (!currentText)
            return;
        segments.push({ text: currentText, script: currentScript ?? 'latin' });
        currentText = '';
    };
    for (const ch of text) {
        const cp = ch.codePointAt(0);
        const script = classifyChar(cp, resolvedHints);
        if (isNeutral(cp)) {
            if (currentScript != null) {
                currentText += ch;
            }
            else if (segments.length > 0) {
                segments[segments.length - 1].text += ch;
            }
            else {
                currentText += ch;
                currentScript = 'latin';
            }
            continue;
        }
        if (currentScript === script) {
            currentText += ch;
        }
        else {
            flush();
            currentScript = script;
            currentText = ch;
        }
    }
    flush();
    const result = segments.length > 0 ? segments : [{ text, script: 'latin' }];
    return mergeAdjacentSegments(result);
}
