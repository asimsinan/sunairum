"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.applyStyleEnhancements = applyStyleEnhancements;
const jszip_1 = __importDefault(require("jszip"));
const gradient_xml_1 = require("./gradient-xml");
const text_gradient_xml_1 = require("./text-gradient-xml");
const script_fonts_xml_1 = require("./script-fonts-xml");
const soft_edge_xml_1 = require("./soft-edge-xml");
const table_cell_margin_xml_1 = require("./table-cell-margin-xml");
const image_sizing_xml_1 = require("./image-sizing-xml");
const image_roundrect_xml_1 = require("./image-roundrect-xml");
const single_corner_xml_1 = require("./single-corner-xml");
const single_side_border_xml_1 = require("./single-side-border-xml");
const glow_xml_1 = require("./glow-xml");
const clip_path_polygon_xml_1 = require("./clip-path-polygon-xml");
const writing_mode_xml_1 = require("./writing-mode-xml");
const equation_xml_1 = require("./equation-xml");
const timing_xml_1 = require("./timing-xml");
const animation_group_xml_1 = require("./animation-group-xml");
const transition_xml_1 = require("./transition-xml");
const omml_style_1 = require("../utils/omml-style");
/**
 * Apply all registered style enhancements by modifying PPTX XML
 */
async function applyStyleEnhancements(zipBuffer, registry, pptx) {
    const zip = await jszip_1.default.loadAsync(zipBuffer);
    // Get unique slide indices that need processing
    const slideIndices = new Set(registry.getAll().map(e => e.slideIndex));
    for (const slideIndex of slideIndices) {
        const slideFilePath = `ppt/slides/slide${slideIndex + 1}.xml`;
        const slideXmlFile = zip.file(slideFilePath);
        if (!slideXmlFile) {
            console.warn(`⚠️  Slide XML not found: ${slideFilePath}`);
            continue;
        }
        // Read XML content
        let slideXml = await slideXmlFile.async('text');
        // Get all enhancements for this slide, sorted by element index. The
        // animationGroup enhancer must run before the animation enhancer so the
        // wrapping <p:grpSp> already exists when p:timing resolves spids; enforce
        // that with a secondary type-priority sort.
        const enhancements = registry.getForSlide(slideIndex)
            .sort((a, b) => a.elementIndex - b.elementIndex)
            .sort((a, b) => {
            // animationGroup → slideTransition → animation → others
            // transition must land before timing in the OOXML schema order.
            const pri = (t) => t === 'animationGroup' ? 0 :
                t === 'slideTransition' ? 1 :
                    t === 'animation' ? 2 : 3;
            return pri(a.type) - pri(b.type);
        });
        // Apply each enhancement
        for (const enhancement of enhancements) {
            try {
                slideXml = applyEnhancement(slideXml, enhancement);
            }
            catch (error) {
                console.error(`Failed to apply enhancement:`, error);
            }
        }
        slideXml = (0, omml_style_1.stripUndeclaredWordMlFromSlide)(slideXml);
        // Write back modified XML
        zip.file(slideFilePath, slideXml);
    }
    // Return modified ZIP
    return await zip.generateAsync({
        type: 'arraybuffer',
        compression: 'DEFLATE',
    });
}
/**
 * Apply a single style enhancement to slide XML
 */
function applyEnhancement(slideXml, enhancement) {
    switch (enhancement.type) {
        case 'gradient':
            return (0, gradient_xml_1.applyGradientToXml)(slideXml, enhancement);
        case 'textGradient':
            return (0, text_gradient_xml_1.applyTextGradientToXml)(slideXml, enhancement);
        case 'scriptFonts':
            return (0, script_fonts_xml_1.applyScriptFontsToXml)(slideXml, enhancement);
        case 'softEdge':
            return (0, soft_edge_xml_1.applySoftEdgeToXml)(slideXml, enhancement);
        case 'tableCellMargin':
            return (0, table_cell_margin_xml_1.applyTableCellMarginToXml)(slideXml, enhancement);
        case 'imageSizing':
            return (0, image_sizing_xml_1.applyImageSizingToXml)(slideXml, enhancement);
        case 'imageRoundRect':
            return (0, image_roundrect_xml_1.applyImageRoundRectToXml)(slideXml, enhancement);
        case 'singleCornerRect':
            return (0, single_corner_xml_1.applySingleCornerRectToXml)(slideXml, enhancement);
        case 'singleSideBorder':
            return (0, single_side_border_xml_1.applySingleSideBorderToXml)(slideXml, enhancement);
        case 'glow':
            return (0, glow_xml_1.applyGlowToXml)(slideXml, enhancement);
        case 'clipPathPolygon':
            return (0, clip_path_polygon_xml_1.applyClipPathPolygonToXml)(slideXml, enhancement);
        case 'writingMode':
            return (0, writing_mode_xml_1.applyWritingModeToXml)(slideXml, enhancement);
        case 'equation':
            return (0, equation_xml_1.applyEquationToXml)(slideXml, enhancement);
        case 'animation':
            return (0, timing_xml_1.applyAnimationTimingToXml)(slideXml, enhancement);
        case 'animationGroup':
            return (0, animation_group_xml_1.applyAnimationGroupToXml)(slideXml, enhancement);
        case 'slideTransition':
            return (0, transition_xml_1.applySlideTransitionToXml)(slideXml, enhancement);
        case 'shadow':
            // Future implementation
            return slideXml;
        default:
            return slideXml;
    }
}
