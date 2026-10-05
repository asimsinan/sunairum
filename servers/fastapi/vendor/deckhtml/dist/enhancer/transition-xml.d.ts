/**
 * Inject OOXML `<p:transition>` into a slide XML document.
 *
 * Schema order (ECMA-376): cSld, clrMapOvr, transition, timing, extLst.
 */
import type { StyleEnhancement } from '../types';
/**
 * Insert `transitionXml` into the correct schema slot of a slide.
 * Replaces any existing `<p:transition>…</p:transition>`.
 */
export declare function injectTransitionXml(slideXml: string, transitionXml: string): string;
export declare function applySlideTransitionToXml(slideXml: string, enhancement: StyleEnhancement): string;
