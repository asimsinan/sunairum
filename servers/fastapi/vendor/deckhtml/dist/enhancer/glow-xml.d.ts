import { StyleEnhancement } from '../types';
/**
 * Apply glow effect to a shape element by injecting <a:glow> into <a:effectLst>.
 *
 * OOXML glow XML:
 *   <a:glow rad="184150">
 *     <a:srgbClr val="000000">
 *       <a:alpha val="5000"/>
 *     </a:srgbClr>
 *   </a:glow>
 *
 * Where rad is in EMU (1pt = 12700 EMU).
 */
export declare function applyGlowToXml(slideXml: string, enhancement: StyleEnhancement): string;
