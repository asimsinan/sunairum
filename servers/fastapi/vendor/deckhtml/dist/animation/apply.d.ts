import { ConversionOptions, ElementInfo } from '../types';
import { Diagnostic } from '../utils/diagnostics';
import { AnimeCallRaw, CssAnimationRaw } from './normalize';
export interface ApplyAnimationsContext {
    /** ConversionOptions.animations verbatim (false disables the whole pipeline). */
    animationsOption: ConversionOptions['animations'];
    /** Per-slide CSS animation capture, keyed by data-dh-anim-css. */
    cssCapture?: ReadonlyMap<string, CssAnimationRaw>;
    /** Intercepted anime.js calls for the page (indices from data-dh-anim-anime). */
    animeCalls?: readonly AnimeCallRaw[];
    /** Slide id (or 1-based index) attached to diagnostics. */
    slideId?: string | null;
}
/**
 * Normalize raw browser-side animation captures into ElementInfo.animations.
 * Runs on the Node side after inspection; clears animationRaw afterwards.
 * Returns DECKHTML_ANIMATION_UNMAPPED diagnostics for effects outside the
 * native PPTX subset (those elements keep their frozen end-state).
 *
 * When several animation groups inherit the same intercepted anime.js call
 * (one `animate([elA, elB], …)` targeting multiple roots), later groups get
 * `withPrevious` so they play together — matching the HTML co-target timing.
 */
export declare function applyAnimationsToElements(elements: ElementInfo[], ctx: ApplyAnimationsContext): Diagnostic[];
