import { StyleEnhancement } from '../types';
/**
 * Apply single-corner rounded rect by replacing prstGeom rect with custGeom path
 */
export declare function applySingleCornerRectToXml(slideXml: string, enhancement: StyleEnhancement & {
    elementIndex: number;
    cornerRadii: [number, number, number, number];
    shapeWidthInch: number;
    shapeHeightInch: number;
}): string;
