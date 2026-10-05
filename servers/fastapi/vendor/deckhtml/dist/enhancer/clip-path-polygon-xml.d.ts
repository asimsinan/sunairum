import { StyleEnhancement } from '../types';
type PathCommand = {
    type: 'M' | 'L';
    x: number;
    y: number;
} | {
    type: 'C';
    x1: number;
    y1: number;
    x2: number;
    y2: number;
    x: number;
    y: number;
} | {
    type: 'A';
    rx: number;
    ry: number;
    rot: number;
    large: boolean;
    sweep: boolean;
    x: number;
    y: number;
} | {
    type: 'Z';
};
/**
 * Replace prstGeom rect with custGeom from clip-path intersection polygon (normalized 0–PATH_COORD).
 */
export declare function applyClipPathPolygonToXml(slideXml: string, enhancement: StyleEnhancement & {
    elementIndex: number;
    clipPathPolygonNormalized?: {
        x: number;
        y: number;
    }[];
    clipPathCommandsNormalized?: PathCommand[];
}): string;
export {};
