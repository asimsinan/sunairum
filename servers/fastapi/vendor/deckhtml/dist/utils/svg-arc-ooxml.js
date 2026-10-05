"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.svgArcToOoxmlArcTo = svgArcToOoxmlArcTo;
const OOXML_DEG = 60000;
/** OOXML path angle: 0°=east, 90°=south, clockwise; in 60000ths of a degree */
function ooxmlAngleFromVector(dx, dy) {
    let deg = (Math.atan2(dy, dx) * 180) / Math.PI;
    if (deg < 0)
        deg += 360;
    return Math.round(deg * OOXML_DEG);
}
function arcAngle(ux, uy, vx, vy) {
    const dot = ux * vx + uy * vy;
    const det = ux * vy - uy * vx;
    return Math.atan2(det, dot);
}
/**
 * Map an SVG elliptical arc (same coordinate space as custGeom path, e.g. 0–21600)
 * to OOXML arcTo radii and angles.
 */
function svgArcToOoxmlArcTo(x0, y0, rx, ry, xAxisRotationDeg, largeArc, sweep, x1, y1) {
    if (rx === 0 || ry === 0)
        return null;
    const phi = (xAxisRotationDeg * Math.PI) / 180;
    const sinPhi = Math.sin(phi);
    const cosPhi = Math.cos(phi);
    const dx = (x0 - x1) / 2;
    const dy = (y0 - y1) / 2;
    const x1p = cosPhi * dx + sinPhi * dy;
    const y1p = -sinPhi * dx + cosPhi * dy;
    let rxAbs = Math.abs(rx);
    let ryAbs = Math.abs(ry);
    const lambda = (x1p * x1p) / (rxAbs * rxAbs) + (y1p * y1p) / (ryAbs * ryAbs);
    if (lambda > 1) {
        const s = Math.sqrt(lambda);
        rxAbs *= s;
        ryAbs *= s;
    }
    const rxSq = rxAbs * rxAbs;
    const rySq = ryAbs * ryAbs;
    const sign = largeArc === sweep ? -1 : 1;
    const numer = rxSq * rySq - rxSq * y1p * y1p - rySq * x1p * x1p;
    const denom = rxSq * y1p * y1p + rySq * x1p * x1p;
    const coef = denom === 0 ? 0 : sign * Math.sqrt(Math.max(0, numer / denom));
    const cxp = coef * ((rxAbs * y1p) / ryAbs);
    const cyp = coef * (-(ryAbs * x1p) / rxAbs);
    const cx = cosPhi * cxp - sinPhi * cyp + (x0 + x1) / 2;
    const cy = sinPhi * cxp + cosPhi * cyp + (y0 + y1) / 2;
    const wR = Math.max(1, Math.round(rxAbs));
    const hR = Math.max(1, Math.round(ryAbs));
    const v1x = (x1p - cxp) / rxAbs;
    const v1y = (y1p - cyp) / ryAbs;
    const v2x = (-x1p - cxp) / rxAbs;
    const v2y = (-y1p - cyp) / ryAbs;
    let theta1 = arcAngle(1, 0, v1x, v1y);
    let deltaTheta = arcAngle(v1x, v1y, v2x, v2y);
    if (!sweep && deltaTheta > 0)
        deltaTheta -= 2 * Math.PI;
    if (sweep && deltaTheta < 0)
        deltaTheta += 2 * Math.PI;
    const stAng = ooxmlAngleFromVector((x0 - cx) * cosPhi + (y0 - cy) * sinPhi, -(x0 - cx) * sinPhi + (y0 - cy) * cosPhi);
    const swAng = Math.max(1, Math.round((-deltaTheta * 180 * OOXML_DEG) / Math.PI));
    return { wR, hR, stAng, swAng };
}
