"use strict";
/**
 * L1 font closure — require resolved faces before claiming layout-faithful fidelity.
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.checkFontClosure = checkFontClosure;
const diagnostics_1 = require("./diagnostics");
const layout_faithful_1 = require("./layout-faithful");
/**
 * Probe ElementInfo.layoutFontReady stamps from the inspector.
 * In strict mode, any text host with layoutFontReady === false is an error.
 * System fonts (Arial, Georgia, …) that browsers report as ready pass.
 */
function checkFontClosure(elements, mode) {
    const diagnostics = [];
    const unresolved = [];
    const strict = (0, layout_faithful_1.isLayoutFaithfulStrict)(mode);
    for (const el of elements) {
        if (el.type !== 'text')
            continue;
        if (!el.layoutLines?.length)
            continue;
        if (el.layoutFontReady === false) {
            unresolved.push({ elementId: el.elementId, face: el.layoutFontFace });
            diagnostics.push({
                rule_id: diagnostics_1.RULE_IDS.LAYOUT_FAITHFUL_FONT,
                severity: strict ? 'error' : 'warning',
                element_id: el.elementId ?? null,
                message: `Font not closed for layout-faithful text: face=${el.layoutFontFace || '?'} weight=${el.layoutFontWeight || '?'}`,
                recovery: 'Install the matching Office-compatible TTF/OTF or embed the face before convert.',
            });
        }
    }
    return {
        ok: !strict || unresolved.length === 0,
        diagnostics,
        unresolved,
    };
}
