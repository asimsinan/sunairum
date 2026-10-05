/**
 * Clear text that would sit under later opaque panels/tables in PPTX.
 *
 * HTML absolute layouts sometimes place a claim/table host through a title or
 * subtitle. In the browser the later paint wins; deckhtml would otherwise emit
 * both shapes and leave “ghost” text under the panel. Push the occluder down
 * (and shrink height to stay on-slide) so body content clears the text stack.
 */
import { ElementInfo } from '../types';
export interface OcclusionRepairResult {
    changed: boolean;
    nudged: number;
}
/**
 * Mutates element geometry so opaque hosts clear earlier text they would cover.
 */
export declare function repairTextOcclusions(elements: ElementInfo[]): OcclusionRepairResult;
