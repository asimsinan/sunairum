/**
 * L1 font closure — require resolved faces before claiming layout-faithful fidelity.
 */

import type { ElementInfo, LayoutFaithfulMode } from '../types';
import { RULE_IDS, type Diagnostic } from './diagnostics';
import { isLayoutFaithfulStrict } from './layout-faithful';

export interface FontClosureResult {
  ok: boolean;
  diagnostics: Diagnostic[];
  unresolved: Array<{ elementId?: string; face?: string }>;
}

/**
 * Probe ElementInfo.layoutFontReady stamps from the inspector.
 * In strict mode, any text host with layoutFontReady === false is an error.
 * System fonts (Arial, Georgia, …) that browsers report as ready pass.
 */
export function checkFontClosure(
  elements: ElementInfo[],
  mode: LayoutFaithfulMode
): FontClosureResult {
  const diagnostics: Diagnostic[] = [];
  const unresolved: Array<{ elementId?: string; face?: string }> = [];
  const strict = isLayoutFaithfulStrict(mode);

  for (const el of elements) {
    if (el.type !== 'text') continue;
    if (!el.layoutLines?.length) continue;
    if (el.layoutFontReady === false) {
      unresolved.push({ elementId: el.elementId, face: el.layoutFontFace });
      diagnostics.push({
        rule_id: RULE_IDS.LAYOUT_FAITHFUL_FONT,
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
