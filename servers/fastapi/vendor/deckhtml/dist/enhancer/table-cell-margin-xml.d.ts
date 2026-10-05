import { StyleEnhancement } from '../types';
/**
 * Apply table cell margin to slide XML
 * Replaces marL, marR, marT, marB in a:tcPr with target value (EMUs)
 * pptxgenjs ignores margin:0, so we post-process to achieve compact cells
 */
export declare function applyTableCellMarginToXml(slideXml: string, enhancement: StyleEnhancement): string;
