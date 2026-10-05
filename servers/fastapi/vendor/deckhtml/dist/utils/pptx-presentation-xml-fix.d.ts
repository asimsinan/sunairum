/**
 * PowerPoint is strict about element ordering in `ppt/presentation.xml`.
 *
 * ECMA-376 (CT_Presentation) expects (roughly):
 * `p:sldMasterIdLst` → `p:notesMasterIdLst` → `p:handoutMasterIdLst` → `p:sldIdLst` → ...
 *
 * Some generators may emit `p:notesMasterIdLst` later (e.g. after `p:notesSz`),
 * which triggers a repair dialog and schema validation errors.
 */
export declare function fixPresentationXmlElementOrder(presentationXml: string): string;
export declare function fixPresentationXmlOrderInPptx(pptxData: Buffer): Promise<Buffer>;
