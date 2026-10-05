"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.applyImageRoundRectToXml = applyImageRoundRectToXml;
/**
 * Apply border-radius to image (p:pic) by changing preset shape from rect to roundRect.
 * In OOXML, roundRect's adj value is corner radius as percentage (0-100000) of min(width, height).
 * adj = (radiusInch / min(w_inch, h_inch)) * 100000
 */
function applyImageRoundRectToXml(slideXml, enhancement) {
    const { imageBorderRadiusPx, imageWidthInch, imageHeightInch, picIndex } = enhancement;
    if (!imageBorderRadiusPx || imageBorderRadiusPx <= 0 || !imageWidthInch || !imageHeightInch) {
        return slideXml;
    }
    const radiusInch = imageBorderRadiusPx / 128;
    const minDim = Math.min(imageWidthInch, imageHeightInch);
    if (minDim <= 0)
        return slideXml;
    const adj = Math.round((radiusInch / minDim) * 100000);
    const adjClamped = Math.min(50000, Math.max(0, adj)); // OOXML typically 0-50000
    const picMatches = Array.from(slideXml.matchAll(/<p:pic>[\s\S]*?<\/p:pic>/g));
    if (picMatches.length === 0)
        return slideXml;
    // Enhancements are registered against the p:pic ordinal produced by
    // PptxGenJS. Applying the radius to the first picture corrupts slides where
    // a page-background raster precedes a rounded card/image.
    const targetIndex = Number.isInteger(picIndex) ? Number(picIndex) : -1;
    if (targetIndex < 0 || targetIndex >= picMatches.length)
        return slideXml;
    const picMatch = picMatches[targetIndex];
    const picXml = picMatch[0];
    if (!picXml.includes('<a:prstGeom'))
        return slideXml;
    // Replace rect with roundRect and add adj only on the registered picture.
    const modifiedPicXml = picXml.replace(/<a:prstGeom prst="rect">([\s\S]*?)<\/a:prstGeom>/, `<a:prstGeom prst="roundRect"><a:avLst><a:gd name="adj" fmla="val ${adjClamped}"/></a:avLst></a:prstGeom>`);
    if (modifiedPicXml === picXml)
        return slideXml;
    const start = picMatch.index ?? -1;
    if (start < 0)
        return slideXml;
    return slideXml.slice(0, start) + modifiedPicXml + slideXml.slice(start + picXml.length);
}
