"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.applyTextGradientToXml = applyTextGradientToXml;
const gradient_xml_1 = require("./gradient-xml");
/**
 * Apply gradient fill to text runs by replacing solid fills inside run properties.
 */
function applyTextGradientToXml(slideXml, enhancement) {
    const { elementIndex, gradientData } = enhancement;
    if (!gradientData)
        return slideXml;
    const shapePattern = /<p:sp\b[^>]*>[\s\S]*?<\/p:sp>/g;
    const matches = [...slideXml.matchAll(shapePattern)];
    if (elementIndex >= matches.length) {
        console.warn(`Text gradient: element index ${elementIndex} out of bounds (total: ${matches.length})`);
        return slideXml;
    }
    const targetMatch = matches[elementIndex];
    const targetShape = targetMatch[0];
    const targetStart = targetMatch.index;
    const targetEnd = targetStart + targetShape.length;
    const elementOpacity = enhancement.sourceElement?.styles?.opacity;
    const opacity = typeof elementOpacity === 'number'
        ? elementOpacity
        : parseFloat(String(elementOpacity ?? '1')) || 1;
    const angleAdjustment = enhancement.gradientAngleAdjustment ?? 0;
    const gradientXml = (0, gradient_xml_1.generateGradientXml)(gradientData, opacity, angleAdjustment);
    const tagsToUpdate = ['a:rPr', 'a:endParaRPr', 'a:defRPr'];
    let updatedShape = targetShape;
    for (const tag of tagsToUpdate) {
        updatedShape = replaceSolidFillInTag(updatedShape, tag, gradientXml);
    }
    if (updatedShape === targetShape) {
        console.warn(`Text gradient: no solid fill replaced for element index ${elementIndex}`);
        return slideXml;
    }
    return slideXml.substring(0, targetStart) + updatedShape + slideXml.substring(targetEnd);
}
function replaceSolidFillInTag(shapeXml, tagName, gradientXml) {
    const tagPattern = new RegExp(`<${tagName}\\b[^>]*>[\\s\\S]*?<\\/${tagName}>`, 'g');
    return shapeXml.replace(tagPattern, (tagContent) => {
        if (!/<a:solidFill\b/.test(tagContent))
            return tagContent;
        let replaced = tagContent.replace(/<a:solidFill>[\s\S]*?<\/a:solidFill>/g, gradientXml);
        replaced = replaced.replace(/<a:solidFill\s*\/>/g, gradientXml);
        return replaced;
    });
}
