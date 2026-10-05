import { StyleEnhancement, GradientData } from '../types';
/**
 * Apply gradient fill to an element in slide XML
 * Locates the element by index and replaces <a:solidFill> with <a:gradFill>
 */
export declare function applyGradientToXml(slideXml: string, enhancement: StyleEnhancement): string;
/**
 * Generate Office Open XML format gradient fill element
 *
 * Format example:
 * <a:gradFill>
 *   <a:gsLst>
 *     <a:gs pos="0">
 *       <a:srgbClr val="FF0000">
 *         <a:alpha val="100000"/>
 *       </a:srgbClr>
 *     </a:gs>
 *     <a:gs pos="100000">
 *       <a:srgbClr val="0000FF"/>
 *     </a:gs>
 *   </a:gsLst>
 *   <a:lin ang="5400000" scaled="0"/>
 * </a:gradFill>
 */
export declare function generateGradientXml(gradientData: GradientData, elementOpacity?: number, angleAdjustment?: number): string;
