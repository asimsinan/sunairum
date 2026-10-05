import { StyleEnhancement } from '../types';
/** Side index: 0=left, 1=top, 2=right, 3=bottom */
export type BorderSide = 0 | 1 | 2 | 3;
export interface SingleSideBorderEnhancement extends StyleEnhancement {
    type: 'singleSideBorder';
    elementIndex: number;
    side: BorderSide;
    borderWidthInch: number;
    elementWidthInch: number;
    elementHeightInch: number;
    cornerRadiiInch: [number, number, number, number];
}
export declare function applySingleSideBorderToXml(slideXml: string, enhancement: SingleSideBorderEnhancement): string;
