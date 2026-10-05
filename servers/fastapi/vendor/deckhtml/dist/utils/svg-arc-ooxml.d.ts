/**
 * Map an SVG elliptical arc (same coordinate space as custGeom path, e.g. 0–21600)
 * to OOXML arcTo radii and angles.
 */
export declare function svgArcToOoxmlArcTo(x0: number, y0: number, rx: number, ry: number, xAxisRotationDeg: number, largeArc: boolean, sweep: boolean, x1: number, y1: number): {
    wR: number;
    hR: number;
    stAng: number;
    swAng: number;
} | null;
