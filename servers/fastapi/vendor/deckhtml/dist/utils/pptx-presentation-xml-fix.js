"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.fixPresentationXmlElementOrder = fixPresentationXmlElementOrder;
exports.fixPresentationXmlOrderInPptx = fixPresentationXmlOrderInPptx;
const jszip_1 = __importDefault(require("jszip"));
const slide_xml_sanitize_1 = require("./slide-xml-sanitize");
const NOTES_MASTER_BLOCK_RE = /<p:notesMasterIdLst\b[^>]*>[\s\S]*?<\/p:notesMasterIdLst>/;
const NOTES_MASTER_REL_TYPE = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesMaster';
const NOTES_SLIDE_REL_TYPE = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesSlide';
/**
 * PowerPoint is strict about element ordering in `ppt/presentation.xml`.
 *
 * ECMA-376 (CT_Presentation) expects (roughly):
 * `p:sldMasterIdLst` → `p:notesMasterIdLst` → `p:handoutMasterIdLst` → `p:sldIdLst` → ...
 *
 * Some generators may emit `p:notesMasterIdLst` later (e.g. after `p:notesSz`),
 * which triggers a repair dialog and schema validation errors.
 */
function fixPresentationXmlElementOrder(presentationXml) {
    const block = presentationXml.match(NOTES_MASTER_BLOCK_RE)?.[0];
    if (!block)
        return presentationXml;
    const without = presentationXml.replace(block, '');
    const masterCloseIdx = without.search(/<\/p:sldMasterIdLst>/i);
    if (masterCloseIdx !== -1) {
        const insertAt = masterCloseIdx + '</p:sldMasterIdLst>'.length;
        return without.slice(0, insertAt) + block + without.slice(insertAt);
    }
    const presOpen = without.match(/<p:presentation\b[^>]*>/i)?.[0];
    if (!presOpen)
        return without;
    const insertAt = without.indexOf(presOpen) + presOpen.length;
    return without.slice(0, insertAt) + block + without.slice(insertAt);
}
async function fixPresentationXmlOrderInPptx(pptxData) {
    const zip = await jszip_1.default.loadAsync(pptxData);
    const presentationPath = 'ppt/presentation.xml';
    const presentationFile = zip.file(presentationPath);
    if (!presentationFile)
        return pptxData;
    const xml = await presentationFile.async('text');
    // Notes master isn't needed for our generated decks. Keeping it around has caused
    // strict validators (and some PowerPoint builds) to complain or prompt for repair.
    // Strip it for maximum compatibility.
    const strippedXml = xml.replace(NOTES_MASTER_BLOCK_RE, '');
    if (strippedXml !== xml) {
        zip.file(presentationPath, strippedXml);
        // Remove any relationships to notesMaster / notesSlide across the package.
        const dropRelTypes = new Set([NOTES_MASTER_REL_TYPE, NOTES_SLIDE_REL_TYPE]);
        const relTagRe = /<Relationship\b[^>]*\/>/gi;
        for (const f of Object.keys(zip.files)) {
            if (!f.endsWith('.rels'))
                continue;
            const relsFile = zip.file(f);
            if (!relsFile)
                continue;
            const relsXml = await relsFile.async('text');
            const relsFixed = relsXml.replace(relTagRe, (tag) => {
                const type = tag.match(/\bType="([^"]+)"/i)?.[1];
                return type && dropRelTypes.has(type) ? '' : tag;
            });
            if (relsFixed !== relsXml)
                zip.file(f, relsFixed);
        }
        // Remove notes master + notes slide parts (safe no-op if absent).
        for (const f of Object.keys(zip.files)) {
            if (f.startsWith('ppt/notesMasters/'))
                zip.remove(f);
            if (f.startsWith('ppt/notesSlides/'))
                zip.remove(f);
            if (f.startsWith('ppt/notesSlides/_rels/'))
                zip.remove(f);
        }
        // Remove [Content_Types].xml overrides that reference notes parts.
        const ctPath = '[Content_Types].xml';
        const ctFile = zip.file(ctPath);
        if (ctFile) {
            const ctXml = await ctFile.async('text');
            const ctFixed = ctXml.replace(/<Override\b[^>]*PartName="\/ppt\/notes(?:Masters|Slides)\/[^"]+"[^>]*\/>/gi, '');
            if (ctFixed !== ctXml)
                zip.file(ctPath, ctFixed);
        }
    }
    else {
        // Fall back to the original "reorder" behavior if no notes master block exists.
        const fixed = fixPresentationXmlElementOrder(xml);
        if (fixed !== xml)
            zip.file(presentationPath, fixed);
    }
    for (const f of Object.keys(zip.files)) {
        if (!/^ppt\/slides\/slide\d+\.xml$/.test(f))
            continue;
        const slideFile = zip.file(f);
        if (!slideFile)
            continue;
        const slideXml = await slideFile.async('text');
        const fixedSlide = (0, slide_xml_sanitize_1.fixDuplicateParagraphPropertiesInSlide)(slideXml);
        if (fixedSlide !== slideXml)
            zip.file(f, fixedSlide);
    }
    return zip.generateAsync({
        type: 'nodebuffer',
        compression: 'DEFLATE',
    });
}
