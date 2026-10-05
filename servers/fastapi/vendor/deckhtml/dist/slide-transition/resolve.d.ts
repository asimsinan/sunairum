/**
 * Resolve ConversionOptions.slideTransitions into per-slide transition specs.
 *
 * - Named effect → same transition on every slide
 * - Comma-separated names → cycle through the list in order
 * - random / default → a fresh random catalog effect per slide
 * - false / none → disabled
 */
import type { ConversionOptions } from '../types';
import { type ResolvedSlideTransition, type TransitionSpeed } from './catalog';
export type { ResolvedSlideTransition };
/** Split a comma-separated effect list; empty tokens dropped. */
export declare function parseEffectNameList(raw: string): string[];
export type SlideTransitionPlan = {
    mode: 'disabled';
} | {
    /** Same concrete (or PPT meta-random) effect on every slide. */
    mode: 'fixed';
    transition: ResolvedSlideTransition;
} | {
    /** Cycle through a named list in order (wraps). */
    mode: 'cycle';
    effects: string[];
    next: () => ResolvedSlideTransition;
} | {
    /** Fresh random catalog effect for each slide. */
    mode: 'random';
    speed: TransitionSpeed;
    next: () => ResolvedSlideTransition;
};
/**
 * Resolve the conversion-level slide-transition option into a plan.
 *
 * Default (undefined / true / 'random'): each slide gets its own random effect.
 * Single named effect: that effect on every slide.
 * Comma-separated names (or `effects: [...]`): cycle through the list.
 * false / 'none': disabled.
 */
export declare function resolveSlideTransitionPlan(raw: ConversionOptions['slideTransitions']): SlideTransitionPlan;
/**
 * Resolve a single transition (for fixed mode / tests).
 * In random/cycle mode returns one sample draw — prefer `resolveSlideTransitionPlan`
 * when applying across multiple slides.
 */
export declare function resolveSlideTransition(raw: ConversionOptions['slideTransitions']): ResolvedSlideTransition | null;
