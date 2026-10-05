import { StyleEnhancement } from '../types';
/**
 * Apply border-radius to image (p:pic) by changing preset shape from rect to roundRect.
 * In OOXML, roundRect's adj value is corner radius as percentage (0-100000) of min(width, height).
 * adj = (radiusInch / min(w_inch, h_inch)) * 100000
 */
export declare function applyImageRoundRectToXml(slideXml: string, enhancement: StyleEnhancement & {
    imageBorderRadiusPx: number;
    imageWidthInch: number;
    imageHeightInch: number;
    elementIndex: number;
    picIndex?: number;
}): string;
