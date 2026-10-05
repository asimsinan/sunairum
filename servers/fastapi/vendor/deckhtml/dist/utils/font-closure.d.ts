/**
 * L1 font closure — require resolved faces before claiming layout-faithful fidelity.
 */
import type { ElementInfo, LayoutFaithfulMode } from '../types';
import { type Diagnostic } from './diagnostics';
export interface FontClosureResult {
    ok: boolean;
    diagnostics: Diagnostic[];
    unresolved: Array<{
        elementId?: string;
        face?: string;
    }>;
}
/**
 * Probe ElementInfo.layoutFontReady stamps from the inspector.
 * In strict mode, any text host with layoutFontReady === false is an error.
 * System fonts (Arial, Georgia, …) that browsers report as ready pass.
 */
export declare function checkFontClosure(elements: ElementInfo[], mode: LayoutFaithfulMode): FontClosureResult;
