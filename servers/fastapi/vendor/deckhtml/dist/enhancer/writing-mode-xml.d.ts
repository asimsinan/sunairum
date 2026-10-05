import { StyleEnhancement } from '../types';
/**
 * Apply CSS writing-mode via OOXML a:bodyPr @vert (e.g. vertical-rl → eaVert).
 */
export declare function applyWritingModeToXml(slideXml: string, enhancement: StyleEnhancement): string;
