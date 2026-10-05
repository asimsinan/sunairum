/**
 * Text script detection and splitting for mixed-script PPTX runs.
 */
import type { PlatformFontLang } from './platformFontMap';
export interface ContainerScriptHints {
    hasKana: boolean;
    hasHangul: boolean;
    hasTraditionalHan: boolean;
}
export interface TextScriptSegment {
    text: string;
    script: PlatformFontLang;
}
export declare function scriptToOoxmlLang(script: PlatformFontLang): string;
export declare function detectContainerScriptHints(text: string): ContainerScriptHints;
export declare function classifyChar(cp: number, hints: ContainerScriptHints): PlatformFontLang;
/**
 * Split text into consecutive runs of the same script.
 * Neutral whitespace attaches to the adjacent script when possible.
 */
export declare function splitTextByScript(text: string, hints?: ContainerScriptHints): TextScriptSegment[];
