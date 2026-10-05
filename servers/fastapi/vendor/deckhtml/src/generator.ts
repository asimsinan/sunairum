/**
 * PPTX Generator Module
 * Creates PowerPoint presentations using pptxgenjs
 */

import PptxGenJS from 'pptxgenjs';
import { ElementAnimation, ElementInfo, SlideAnimationSpec, UsedFontDescriptor } from './types';
import { ElementConverter } from './converter';
import { SLIDE_WIDTH_INCH, SLIDE_HEIGHT_INCH, getSlideWidthPx, getSlideHeightPx, clampPptxTablePositionInch } from './utils/coordinate';
import { PlatformFontContext } from './utils/platformFontMap';
import { StyleEnhancementRegistry } from './enhancer/registry';
import { applyStyleEnhancements } from './enhancer/processor';
import { parseColor } from './utils/style';
import { fixPresentationXmlOrderInPptx } from './utils/pptx-presentation-xml-fix';
import { resolveImageSourceForPptx, validateDataImageUrl } from './utils/resource-policy';
import { getPlaceholderForMediaType } from './utils/placeholder-assets';
import { ensurePptxgenAllowsHttp } from './utils/pptxgen-http-patch';
import { ReportCollector, type ElementReportRecord, type MappingMode } from './conversion-report';
import { pxToInchX, pxToInchY } from './utils/coordinate';
import { repairTextOcclusions } from './utils/occlusion-repair';
import type { ResolvedSlideTransition, SlideTransitionPlan } from './slide-transition/resolve';
// pptxgenjs must accept plain http:// for all remote media types.
ensurePptxgenAllowsHttp();

export interface PPTXGeneratorOptions {
  fontResolver?: (d: UsedFontDescriptor) => string;
  platformFontContext?: PlatformFontContext;
  /** When true, slide N starts at N × viewport height (long HTML split). */
  splitByHeight?: boolean;
  /** CSS selector grouping multiple slides in one HTML file. */
  slideSelector?: string;
  /** Coordinates already normalized per slide (multi-slide isolation path). */
  slideCoordsNormalized?: boolean;
  /**
   * Slide-to-slide transition plan (disabled / fixed / per-slide random).
   */
  slideTransitionPlan?: SlideTransitionPlan;
  /**
   * When true, nudge opaque covers clear of title/subtitle text.
   * Default false — preserves HTML geometry (pixel fidelity).
   */
  repairTextOcclusions?: boolean;
}

export class PPTXGenerator {
  private pptx: InstanceType<typeof PptxGenJS>;
  private converter: ElementConverter;
  private splitByHeight: boolean;
  private slideSelector?: string;
  private slideCoordsNormalized: boolean;
  private registry: StyleEnhancementRegistry;
  /** Per-slide animation timing specs, registered as enhancements in generate(). */
  private animationSpecs = new Map<number, SlideAnimationSpec>();
  /** Slide-to-slide transition plan (disabled when mode === 'disabled'). */
  private slideTransitionPlan: SlideTransitionPlan;
  /** Opt-in layout mutation to clear text under opaque covers. */
  private repairTextOcclusionsEnabled: boolean;
  /** Per-element report collector (DH-P0-002). */
  readonly report = new ReportCollector();
  /** HTML → PPTX shape attribution for closed-loop visual verify. */
  private shapeMap: import('./types').ShapeMapEntry[] = [];

  constructor(options: PPTXGeneratorOptions = {}) {
    this.pptx = new PptxGenJS();
    this.registry = new StyleEnhancementRegistry();
    this.converter = new ElementConverter(
      this.registry,
      options.fontResolver,
      options.platformFontContext
    );

    // Set presentation layout (16:9 aspect ratio)
    this.pptx.layout = 'LAYOUT_16x9';
    this.pptx.defineLayout({
      name: 'HTML_LAYOUT',
      width: SLIDE_WIDTH_INCH,
      height: SLIDE_HEIGHT_INCH,
    });
    this.pptx.layout = 'HTML_LAYOUT';
    this.splitByHeight = options.splitByHeight ?? false;
    this.slideSelector = options.slideSelector;
    this.slideCoordsNormalized = options.slideCoordsNormalized ?? false;
    this.slideTransitionPlan = options.slideTransitionPlan ?? { mode: 'disabled' };
    this.repairTextOcclusionsEnabled = options.repairTextOcclusions ?? false;
  }

  /** L1 layout-faithful notes collected during text emission. */
  getLayoutFaithfulNotes(): Array<{ elementId?: string; reason: string; message: string }> {
    return this.converter.layoutFaithfulNotes;
  }

  /** Shape map collected during generate() for visual verify attribution. */
  getShapeMap(): import('./types').ShapeMapEntry[] {
    return this.shapeMap;
  }

  /**
   * Generate PPTX from grouped slide elements
   */
  async generate(
    slidesMap: Map<number, ElementInfo[]>,
  ): Promise<Buffer> {
    this.shapeMap = [];
    const slideIndices = Array.from(slidesMap.keys()).sort((a, b) => a - b);

    // Phase 1: Create slides through pptxgenjs
    for (const slideIndex of slideIndices) {
      const elements = slidesMap.get(slideIndex);
      if (!elements || elements.length === 0) continue;
      await this.createSlide(elements, slideIndex);
    }

    // Register one animationGroup enhancement per slide/group: wraps every
    // member shape (sharing the group objectName) into a <p:grpSp> so the
    // entrance animation targets the group as a whole, mirroring HTML subtree
    // animation. Must run before the 'animation' enhancement so the group
    // <p:grpSp> already exists when p:timing resolves spids.
    this.registerAnimationGroupEnhancements(slidesMap);

    // Register one aggregated animation enhancement per animated slide
    for (const [slideIndex, spec] of this.animationSpecs) {
      this.registry.register({
        slideIndex,
        elementIndex: 0,
        type: 'animation',
        animationData: spec,
      });
    }

    // Register slide-to-slide transitions (p:transition) for every created slide.
    // Schema order requires transition before timing; processor priority enforces this.
    const transitionEffects: string[] = [];
    if (this.slideTransitionPlan.mode !== 'disabled') {
      for (const slideIndex of slideIndices) {
        const elements = slidesMap.get(slideIndex);
        if (!elements || elements.length === 0) continue;
        const transition: ResolvedSlideTransition =
          this.slideTransitionPlan.mode === 'fixed'
            ? this.slideTransitionPlan.transition
            : this.slideTransitionPlan.next();
        transitionEffects.push(transition.effect);
        this.registry.register({
          slideIndex,
          elementIndex: 0,
          type: 'slideTransition',
          slideTransitionXml: transition.xml,
        });
      }
      if (transitionEffects.length > 0) {
        const unique = [...new Set(transitionEffects)];
        let summary: string;
        if (this.slideTransitionPlan.mode === 'fixed') {
          summary = `${transitionEffects[0]} × ${transitionEffects.length}`;
        } else if (this.slideTransitionPlan.mode === 'cycle') {
          summary = `cycle [${this.slideTransitionPlan.effects.join(', ')}]`;
        } else {
          summary = `random per slide (${unique.join(', ')})`;
        }
        console.log(`\n🎬 Slide transitions: ${summary}`);
      }
    }

    // Phase 2: Apply style enhancements if needed
    if (this.registry.count() > 0) {
      console.log(`\n🎨 Applying ${this.registry.count()} style enhancements...`);
      return this.generateWithEnhancements();
    } else {
      // No enhancements, write file normally
      const buf = (await this.pptx.write({ outputType: 'nodebuffer' })) as Buffer;
      return fixPresentationXmlOrderInPptx(buf);
    }
  }

  /**
   * Generate PPTX with XML post-processing for style enhancements
   */
  private async generateWithEnhancements(): Promise<Buffer> {
    // Get pptxgenjs generated ZIP content as NodeJS.ReadableStream
    const zipData = await this.pptx.stream() as any;

    // Convert to ArrayBuffer
    const zipBuffer = await this.streamToArrayBuffer(zipData);

    // Apply style enhancements (modify XML)
    const modifiedZipBuffer = await applyStyleEnhancements(
      zipBuffer,
      this.registry,
      this.pptx
    );

    // Write to file
    console.log('✅ Style enhancements applied successfully');
    return fixPresentationXmlOrderInPptx(Buffer.from(modifiedZipBuffer));
  }

  /**
   * Convert stream to ArrayBuffer
   */
  private async streamToArrayBuffer(stream: any): Promise<ArrayBuffer> {
    // If it's already a Buffer or ArrayBuffer, convert directly
    if (Buffer.isBuffer(stream)) {
      const buf = stream.buffer.slice(stream.byteOffset, stream.byteOffset + stream.byteLength);
      return buf as ArrayBuffer;
    }
    if (stream instanceof ArrayBuffer) {
      return stream;
    }
    if (stream instanceof Uint8Array) {
      return stream.buffer as ArrayBuffer;
    }

    // If it's a stream, collect chunks
    const chunks: Buffer[] = [];
    for await (const chunk of stream) {
      chunks.push(Buffer.from(chunk));
    }
    const buffer = Buffer.concat(chunks);
    const buf = buffer.buffer.slice(buffer.byteOffset, buffer.byteOffset + buffer.byteLength);
    return buf as ArrayBuffer;
  }

  /**
   * Embed fonts using pptx-embed-fonts library
   */

  /**
   * Create a single slide from elements
   */
  private async createSlide(
    elements: ElementInfo[],
    slideIndex: number
  ): Promise<void> {
    const slide = this.pptx.addSlide();

    // DH-P0-002: start a per-element report section for this slide.
    const slideId = this.resolveSlideId(elements, slideIndex);
    this.report.startSlide(slideId, slideIndex + 1);

    // Origin Y for this slide's elements. For a single long HTML split by height or
    // slide selector, use the topmost element; for merged multi-file inputs each file
    // starts at y≈0 so slideIndex*height would wrongly offset later slides off-canvas.
    const slideStartY = this.resolveSlideStartY(elements, slideIndex);

    // Opt-in: nudge opaque covers clear of title/subtitle (mutates HTML geometry).
    if (this.repairTextOcclusionsEnabled) {
      repairTextOcclusions(elements);
    }

    // Seed flex-row chip collision walls from measured HTML boxes.
    this.converter.beginSlide(slideIndex, elements, slideStartY);

    // Preserve inspector paint-order DFS (paintOrder), then soft z-index among
    // peers that share the same paintOrder bucket. Avoid raw global z-index sort
    // — that can lift a parent background above its children.
    const sortedElements = [...elements].sort((a, b) => {
      const pa = a.paintOrder ?? 0;
      const pb = b.paintOrder ?? 0;
      if (pa !== pb) return pa - pb;
      const za = typeof a.styles?.zIndex === 'number' ? a.styles.zIndex : 0;
      const zb = typeof b.styles?.zIndex === 'number' ? b.styles.zIndex : 0;
      return za - zb;
    });

    // Add each element to the slide
    let elementCount = 0;
    let elementIndex = 0; // Global index (all slide objects: sp, pic, table, etc.)
    let shapeIndex = 0; // Index among p:sp only - gradient/softEdge/singleCornerRect target p:sp
    let picIndex = 0; // Index among p:pic only - image sizing/roundRect target p:pic
    let drawableOrdinal = 0;

    for (const element of sortedElements) {
      try {
        drawableOrdinal += 1;
        if (!element.elementId) {
          const tag = String(element.tag || element.type || 'drawable')
            .toLowerCase()
            .replace(/[^a-z0-9_-]+/g, '-');
          element.elementId = `dh-slide-${slideIndex + 1}__${tag}__${drawableOrdinal}`;
        }
        const convertedElements = this.converter.convertElement(
          element,
          slideStartY,
          slideIndex,
          elementIndex
        );
        if (!convertedElements || convertedElements.length === 0) continue;

        elementCount++;
        // Add all converted elements (main element + border decorations)
        for (const converted of convertedElements) {
          const semanticConvertedType = converted?._equationOmml
            ? 'math'
            : String(converted.type || element.type || 'unknown');
          // Handle slide background with image + gradient overlay
          if (converted.type === 'slideBackgroundWithGradient') {
            const imagePath = converted.options.path;
            const sourceElement = converted._sourceElement as ElementInfo;
            const fallbackColor = parseColor(sourceElement?.styles?.backgroundColor)?.color ?? '1A1818';

            const resolvedBg = imagePath ? await resolveImageSourceForPptx(imagePath) : null;
            if (imagePath && !resolvedBg) {
              console.warn(`⚠️  Background image unavailable or invalid (404/non-image), using fallback color: ${imagePath}`);
            }
            if (resolvedBg?.kind === 'data') {
              slide.background = { data: resolvedBg.data };
            } else if (resolvedBg?.kind === 'path') {
              slide.background = { path: resolvedBg.path };
            } else {
              slide.background = { color: fallbackColor };
            }
            const gradientData = converted._gradientData;
            const overlayShape = {
              type: 'rect',
              options: {
                x: converted.options.x,
                y: converted.options.y,
                w: converted.options.w,
                h: converted.options.h,
                fill: { color: '000000' }, // Placeholder, will be replaced by gradient enhancement
                line: { type: 'none' },
              },
            };
            if (gradientData) {
              this.registry.register({
                slideIndex,
                elementIndex: shapeIndex,
                type: 'gradient',
                sourceElement: converted._sourceElement,
                gradientData,
              });
            }
            await this.addElementToSlide(slide, overlayShape, shapeIndex);
            elementIndex++;
            shapeIndex++;
            continue;
          }

          // Check if this element has gradient metadata attached
          const isShapeElement =
            converted.type === 'text' ||
            converted.type === 'rect' ||
            converted.type === 'roundRect' ||
            converted.type === 'ellipse' ||
            converted.type === 'round1Rect' ||
            converted.type === 'round2SameRect' ||
            converted.type === 'line';
          const isImageElement = converted.type === 'image';
          const currentShapeIndex = isShapeElement ? shapeIndex : undefined;
          const currentPicIndex = isImageElement ? picIndex : undefined;

          if (converted._gradientData) {
            this.registry.register({
              slideIndex,
              elementIndex: currentShapeIndex ?? elementIndex,
              type: 'gradient',
              sourceElement: converted._sourceElement,
              gradientData: converted._gradientData,
            });
            // Clean up metadata
            delete converted._gradientData;
            delete converted._sourceElement;
          }

          if (converted._textGradientData) {
            this.registry.register({
              slideIndex,
              elementIndex: currentShapeIndex ?? elementIndex,
              type: 'textGradient',
              sourceElement: converted._sourceElement,
              gradientData: converted._textGradientData,
            });
            delete converted._textGradientData;
            delete converted._sourceElement;
          }

          if (converted._scriptFontsMeta) {
            this.registry.register({
              slideIndex,
              elementIndex: currentShapeIndex ?? elementIndex,
              type: 'scriptFonts',
              scriptFontsMeta: converted._scriptFontsMeta,
              scriptFontFaces: converted._scriptFontsMeta.scriptFontFaces,
            });
            delete converted._scriptFontsMeta;
          }

          if (converted._bodyPrVert) {
            this.registry.register({
              slideIndex,
              elementIndex: currentShapeIndex ?? elementIndex,
              type: 'writingMode',
              bodyPrVert: converted._bodyPrVert,
            });
            delete converted._bodyPrVert;
          }

          if (converted._equationOmml) {
            this.registry.register({
              slideIndex,
              elementIndex: currentShapeIndex ?? elementIndex,
              type: 'equation',
              ommlXml: converted._equationOmml,
              mathDisplayMode: converted._mathDisplayMode ?? 'inline',
              mathJc: converted._mathJc,
              mathColorHex: converted._mathColorHex,
              mathSzHalfPt: converted._mathSzHalfPt,
              mathFallbackText: converted._mathFallbackText,
              sourceElement: converted._sourceElement,
            });
            delete converted._equationOmml;
            delete converted._mathDisplayMode;
            delete converted._mathJc;
            delete converted._mathColorHex;
            delete converted._mathSzHalfPt;
            delete converted._mathFallbackText;
            delete converted._sourceElement;
          }

          // Register glow effect (box-shadow wrapping 3-4 sides)
          if (converted._glowData) {
            this.registry.register({
              slideIndex,
              elementIndex: currentShapeIndex ?? elementIndex,
              type: 'glow',
              glowData: converted._glowData,
            });
            delete converted._glowData;
          }

          // Check if this element has single-corner rounded rect
          if (converted._singleCornerRadii && converted.type === 'rect') {
            this.registry.register({
              slideIndex,
              elementIndex: currentShapeIndex ?? elementIndex,
              type: 'singleCornerRect',
              cornerRadii: converted._singleCornerRadii,
              shapeWidthInch: converted._shapeWidthInch,
              shapeHeightInch: converted._shapeHeightInch,
            });
            delete converted._singleCornerRadii;
            delete converted._shapeWidthInch;
            delete converted._shapeHeightInch;
          }

          if (
            (converted._clipPathCommandsNormalized || converted._clipPathPolygonNormalized) &&
            converted.type === 'rect'
          ) {
            this.registry.register({
              slideIndex,
              elementIndex: currentShapeIndex ?? elementIndex,
              type: 'clipPathPolygon',
              clipPathCommandsNormalized: converted._clipPathCommandsNormalized,
              clipPathPolygonNormalized: converted._clipPathPolygonNormalized,
              clipPathPolygonClosed: converted._clipPathPolygonClosed !== false,
            });
            delete converted._clipPathCommandsNormalized;
            delete converted._clipPathPolygonNormalized;
            delete converted._clipPathPolygonClosed;
          }

          // Check if this is a single-side border decoration (custGeom for rounded corners)
          if ((converted as any)._singleSideBorder && converted.type === 'rect') {
            const data = (converted as any)._singleSideBorder;
            this.registry.register({
              slideIndex,
              elementIndex: currentShapeIndex ?? elementIndex,
              type: 'singleSideBorder',
              side: data.side,
              borderWidthInch: data.borderWidthInch,
              elementWidthInch: data.elementWidthInch,
              elementHeightInch: data.elementHeightInch,
              cornerRadiiInch: data.cornerRadiiInch,
            });
            delete (converted as any)._singleSideBorder;
          }

          // Apply HTML cell padding into OOXML tcPr (pptxgen often emits mar*=0).
          if (converted.type === 'table') {
            const padPt = Number((converted as any)._tableCellMarginPt);
            if (Number.isFinite(padPt) && padPt > 0) {
              this.registry.register({
                slideIndex,
                elementIndex,
                type: 'tableCellMargin',
                tableCellMarginPt: padPt,
              });
            }
          }

          // Register imageSizing for images with object-fit (pptxgenjs may not fully support sizing)
          if (converted.type === 'image' && converted.options.sizing) {
            const objectFit = converted.options.sizing.type;
            if (objectFit === 'cover' || objectFit === 'contain') {
              // Get original element info for image dimensions
              const sourceElement = element as any;
              this.registry.register({
                slideIndex,
                elementIndex,
                type: 'imageSizing',
                objectFit: objectFit,
                picIndex: currentPicIndex,
                imageNaturalWidth: sourceElement.imageNaturalWidth,
                imageNaturalHeight: sourceElement.imageNaturalHeight,
                containerWidth: converted.options.w,
                containerHeight: converted.options.h,
              });
            }
          }

          // Register imageRoundRect for images with border-radius (own or from parent with overflow-hidden)
          if (converted.type === 'image') {
            const isNearFullSlide =
              Number(element.width) >= 0.9 * getSlideWidthPx() &&
              Number(element.height) >= 0.9 * getSlideHeightPx();
            const isBackgroundRaster =
              element.rasterReason === 'page-background' ||
              element.tag === 'body.page-bg' ||
              (isNearFullSlide && element.rasterMethod === 'screenshot');
            const ownRadius = (element as any).styles?.borderRadius;
            let radiusPx = ownRadius ? parseFloat(ownRadius) : 0;
            if (radiusPx <= 0) {
              radiusPx = (element as any).parentBorderRadiusPx ?? 0;
            }
            // A full-slide raster is the canvas, not a card. Never mask it as
            // a roundRect: inherited/stale radius metadata exposes white slide
            // corners in PowerPoint even though Chromium rendered a rectangle.
            if (radiusPx > 0 && !isBackgroundRaster) {
              this.registry.register({
                slideIndex,
                elementIndex,
                type: 'imageRoundRect',
                picIndex: currentPicIndex,
                imageBorderRadiusPx: radiusPx,
                imageWidthInch: converted.options.w,
                imageHeightInch: converted.options.h,
              });
            }
          }

          // DH-P0-001: propagate caller-declared identity to the PPTX object name
          // so each shape/picture/table can be looked up in the Selection Pane.
          // When the element belongs to an animation group, the group name wins
          // so the post-processor can wrap all member shapes into one <p:grpSp>.
          const animGroupName = element.animationGroupId
            ? `dh-grp-${element.animationGroupId}`
            : null;
          if (converted.options && typeof converted.options === 'object') {
            if (animGroupName) {
              (converted.options as any).objectName = animGroupName;
            } else if (element.elementId) {
              (converted.options as any).objectName = element.elementId;
            }
          }

          // Animations: the object needs a name the p:timing injector can
          // resolve to a spid. Elements without a caller identity get a
          // deterministic internal name; the per-slide spec is aggregated and
          // registered as a single enhancement in generate(). When the element
          // is an animation-group root, the target is the group name so the
          // whole <p:grpSp> animates together.
          if (
            element.animations &&
            element.animations.length > 0 &&
            converted.options &&
            typeof converted.options === 'object'
          ) {
            const objectName =
              animGroupName ?? element.elementId ?? `dh-anim-${slideIndex}-${elementIndex}`;
            this.registerAnimationEntry(slideIndex, objectName, element.animations);
          }

          await this.addElementToSlide(slide, converted, currentShapeIndex);

          // DH-P0-002: record this element in the per-element report.
          this.recordElement(element, converted, slideIndex);
          this.recordShapeMapEntry(element, converted, slideIndex, semanticConvertedType);

          elementIndex++;
          if (isShapeElement) shapeIndex++;
          if (isImageElement) picIndex++;
        }
      } catch (error) {
        console.warn(`Failed to convert element:`, error);
        // DH-P0-002: record the failed element as unsupported.
        this.recordElement(element, null, slideIndex, error);
      }
    }
    console.log(`Slide ${slideIndex + 1}: Added ${elementCount} source elements (${elementIndex} total elements)`);
  }

  private recordShapeMapEntry(
    element: ElementInfo,
    converted: any,
    slideIndex: number,
    semanticConvertedType?: string
  ): void {
    const opts = converted?.options;
    if (!opts || typeof opts !== 'object') return;
    const x = Number(opts.x);
    const y = Number(opts.y);
    const w = Number(opts.w);
    const h = Number(opts.h);
    if (![x, y, w, h].every((n) => Number.isFinite(n))) return;
    const convertedText = converted?.text;
    let pptxLineCount: number | undefined;
    if (typeof convertedText === 'string') {
      pptxLineCount = Math.max(1, convertedText.split(/\r?\n/).length);
    } else if (Array.isArray(convertedText)) {
      pptxLineCount = 1;
      for (const run of convertedText) {
        const runText = typeof run === 'string' ? run : String(run?.text || '');
        pptxLineCount += Math.max(0, runText.split(/\r?\n/).length - 1);
        if (run?.options?.breakLine || run?.options?.softBreakBefore) pptxLineCount += 1;
      }
    }
    const clip = element.overflowClipRect;
    const sourceElementId = element.elementId || `dh-slide-${slideIndex + 1}__unidentified`;
    const emissionCount = this.shapeMap.filter(
      (entry) => entry.slideIndex === slideIndex &&
        (entry.sourceElementId === sourceElementId || entry.elementId === sourceElementId)
    ).length;
    const emittedElementId = emissionCount === 0
      ? sourceElementId
      : `${sourceElementId}__emission-${emissionCount + 1}`;
    const fragmentOccurrences = new Map<string, number>();
    const stableInlineFragmentIds = element.richText
      ?.map((run) => run.fragmentId || '')
      .filter(Boolean)
      .map((fragmentId) => {
        const occurrence = (fragmentOccurrences.get(fragmentId) || 0) + 1;
        fragmentOccurrences.set(fragmentId, occurrence);
        return occurrence === 1 ? fragmentId : `${fragmentId}__occurrence-${occurrence}`;
      });
    this.shapeMap.push({
      slideIndex,
      elementId: emittedElementId,
      sourceElementId,
      tag: element.tag,
      // OMML equations travel through a temporary pptxgenjs text placeholder
      // and are replaced during XML enhancement. Attribute the final semantic
      // object as math, otherwise the verifier sees zero native formula owners.
      type: semanticConvertedType || String(converted.type || element.type || 'unknown'),
      html: {
        x: Number(element.x) || 0,
        y: Number(element.y) || 0,
        w: Number(element.width) || 0,
        h: Number(element.height) || 0,
      },
      pptx: { x, y, w, h },
      htmlLineCount: element.layoutLines?.length,
      pptxLineCount,
      fontScale: element.layoutFaithfulFontScale ?? 1,
      paintOrder: element.paintOrder,
      zIndex:
        typeof element.styles?.zIndex === 'number'
          ? element.styles.zIndex
          : Number.parseInt(String(element.styles?.zIndex || '0'), 10) || 0,
      fontFamily: element.styles?.fontFamily,
      fontSize: element.styles?.fontSize,
      text: typeof element.content === 'string' ? element.content : undefined,
      inlineFragmentIds: stableInlineFragmentIds,
      objectFit: element.styles?.objectFit,
      rasterReason: element.rasterReason,
      semanticOwner: element.semanticOwner,
      semanticKind: element.semanticKind,
      tableRows: element.tableData?.rows.length,
      tableCols: element.tableData?.rows.reduce(
        (max, row) => Math.max(max, row.cells.reduce((sum, cell) => sum + (cell.colSpan || 1), 0)),
        0
      ),
      tableCells: element.tableData?.rows.flatMap((row) => row.cells.map((cell) => cell.text)),
      tableRowHeights: element.tableData?.rowH,
      tableColumnWidths: element.tableData?.colW,
      pptxTableCells: Array.isArray(opts.rows)
        ? opts.rows.flatMap((row: any[]) =>
            row.map((cell: any) => {
              if (typeof cell?.text === 'string') return cell.text;
              if (Array.isArray(cell?.text)) return cell.text.map((run: any) => String(run?.text || '')).join('');
              return '';
            })
          )
        : undefined,
      pptxTableRowHeights: Array.isArray(opts.rowH)
        ? opts.rowH.map((height: number) => Number(height))
        : undefined,
      pptxTableColumnWidths: Array.isArray(opts.colW)
        ? opts.colW.map((width: number) => Number(width))
        : undefined,
      clip: clip
        ? { x: clip.x, y: clip.y, w: clip.width, h: clip.height }
        : undefined,
    });
  }

  /**
   * Aggregate one element's animations into the per-slide timing spec.
   * A DOM element split into several PPTX shapes (shape background + text
   * box) carries its animationRaw on each ElementInfo; entries are merged by
   * objectName and identical effects deduped so the animation plays once.
   */
  private registerAnimationEntry(
    slideIndex: number,
    objectName: string,
    animations: ElementAnimation[]
  ): void {
    let spec = this.animationSpecs.get(slideIndex);
    if (!spec) {
      spec = { entries: [] };
      this.animationSpecs.set(slideIndex, spec);
    }
    let entry = spec.entries.find((e) => e.objectName === objectName);
    if (!entry) {
      entry = { objectName, animations: [] };
      spec.entries.push(entry);
    }
    for (const animation of animations) {
      const key = `${animation.trigger}|${animation.durationMs}|${animation.delayMs}|${JSON.stringify(animation.effect)}`;
      const dup = entry.animations.some(
        (a) =>
          `${a.trigger}|${a.durationMs}|${a.delayMs}|${JSON.stringify(a.effect)}` === key
      );
      if (!dup) entry.animations.push(animation);
    }
  }

  /**
   * For each slide, find animation groups (sets of elements sharing the same
   * `animationGroupId`) whose root carries mapped entrance animations, and
   * register one `animationGroup` enhancement per group. The post-processor
   * wraps every member shape (all stamped with the group objectName) into a
   * single <p:grpSp> so the entrance animation targets the group as a whole.
   *
   * Groups with only one member (root with no converted descendants) are
   * skipped — there is nothing to wrap, and the root shape already carries
   * the animation target name.
   */
  private registerAnimationGroupEnhancements(
    slidesMap: Map<number, ElementInfo[]>
  ): void {
    for (const [slideIndex, elements] of slidesMap) {
      const byGroup = new Map<string, { count: number; hasAnimation: boolean }>();
      for (const el of elements) {
        const gid = el.animationGroupId;
        if (!gid) continue;
        const acc = byGroup.get(gid) ?? { count: 0, hasAnimation: false };
        acc.count += 1;
        if (el.animations && el.animations.length > 0) acc.hasAnimation = true;
        byGroup.set(gid, acc);
      }
      for (const [gid, acc] of byGroup) {
        if (!acc.hasAnimation) continue;
        if (acc.count <= 1) continue;
        this.registry.register({
          slideIndex,
          elementIndex: 0,
          type: 'animationGroup',
          animationGroupData: { groupName: `dh-grp-${gid}` },
        });
      }
    }
  }

  /**
   * Push a per-element record into the report collector (DH-P0-002).
   */
  private recordElement(
    element: ElementInfo,
    converted: any,
    slideIndex: number,
    error?: unknown,
  ): void {
    const mappingMode = this.resolveMappingMode(element, converted, Boolean(error));
    const objectRef = element.elementId
      ? `ppt/slides/slide${slideIndex + 1}.xml#name:${element.elementId}`
      : null;
    const record: ElementReportRecord = {
      element_id: element.elementId ?? null,
      kind: element.type,
      mapping_mode: mappingMode,
      object_ref: objectRef,
      geometry: {
        x: pxToInchX(element.x),
        y: pxToInchY(element.y),
        w: pxToInchX(element.width),
        h: pxToInchY(element.height),
        unit: 'inch',
      },
      warnings: error
        ? [
            {
              rule_id: 'DECKHTML_MAPPING_CLOSURE_FAILURE',
              severity: 'warning',
              element_id: element.elementId ?? null,
              message: error instanceof Error ? error.message : String(error),
            },
          ]
        : [],
    };
    this.report.addElement(record);
  }

  private resolveMappingMode(
    element: ElementInfo,
    converted: any,
    failed: boolean,
  ): MappingMode {
    if (failed) return 'unsupported';
    if (element.rasterMethod) return 'raster';
    // SVG exported as a native SVG image counts as vector.
    if (element.type === 'svg' && !element.rasterMethod) return 'vector';
    // SVG hybrid raster (foreignObject) is raster, already covered above.
    if (
      element.type === 'text' ||
      element.type === 'image' ||
      element.type === 'shape' ||
      element.type === 'table' ||
      element.type === 'chart'
    ) {
      return 'native';
    }
    // video/audio/canvas without rasterization are unsupported natively.
    if (element.type === 'video' || element.type === 'audio' || element.type === 'canvas') {
      return 'unsupported';
    }
    if (converted && converted.type) return 'native';
    return 'unsupported';
  }

  /**
   * Add converted element to slide
   * @param shapeIndex - Index among p:sp only (for enhancements that target shapes); required for softEdge
   */
  private async addElementToSlide(slide: any, converted: any, shapeIndex?: number): Promise<void> {
    if (converted._prefersGradient) {
      delete converted._prefersGradient;
    }
    if (converted._softEdge) {
      this.registry.register({
        slideIndex: this.getSlideCount() - 1,
        elementIndex: shapeIndex ?? (slide as any)._slideObjects.length,
        type: 'softEdge',
        softEdgeRadiusPt: converted._softEdge.radiusPt,
        softEdgeShadow: converted._softEdge.shadow,
      });
      delete converted._softEdge;
    }

    switch (converted.type) {
      case 'text': {
        const textOpts = { ...converted.options };
        if (textOpts.shape === 'roundRect') {
          textOpts.shape = this.pptx.ShapeType.roundRect;
        } else if (textOpts.shape === 'ellipse') {
          textOpts.shape = this.pptx.ShapeType.ellipse;
        }
        slide.addText(converted.text, textOpts);
        break;
      }

      case 'image': {
        const imageOpts = { ...converted.options };
        if (imageOpts.path) {
          const resolved = await resolveImageSourceForPptx(imageOpts.path);
          if (!resolved) {
            console.warn(
              `⚠️  Image unavailable or invalid, using placeholder: ${imageOpts.path}`
            );
            imageOpts.data = getPlaceholderForMediaType('image');
            delete imageOpts.path;
          } else if (resolved.kind === 'data') {
            imageOpts.data = resolved.data;
            delete imageOpts.path;
          } else {
            imageOpts.path = resolved.path;
          }
        } else if (imageOpts.data) {
          if (!validateDataImageUrl(imageOpts.data)) {
            console.warn('⚠️  Invalid inline image data, using placeholder');
            imageOpts.data = getPlaceholderForMediaType('image');
          }
        } else {
          imageOpts.data = getPlaceholderForMediaType('image');
        }
        slide.addImage(imageOpts);
        break;
      }

      case 'table': {
        const { rows, x, y, w, h, colW, rowH, margin } = converted.options;
        const tableOpts: any = {
          x: clampPptxTablePositionInch(x),
          y: clampPptxTablePositionInch(y),
          w,
          h,
        };
        if (colW?.length) tableOpts.colW = colW;
        if (rowH?.length) tableOpts.rowH = rowH;
        if (margin !== undefined) tableOpts.margin = margin;
        else tableOpts.margin = 0;
        slide.addTable(rows, tableOpts);
        break;
      }

      case 'chart': {
        const o = converted.options;
        const chartTypeEnum =
          o.chartType === 'line'
            ? this.pptx.ChartType.line
            : o.chartType === 'pie'
              ? this.pptx.ChartType.pie
              : this.pptx.ChartType.bar;
        const barDir =
          o.chartType === 'bar' ? 'bar' : o.chartType === 'col' || chartTypeEnum === this.pptx.ChartType.bar ? 'col' : undefined;
        const series = (o.series || []).map(
          (s: { name?: string; values?: Array<number | null>; secondary?: boolean }) => ({
            name: s.name || 'Series',
            labels: o.categories || [],
            values: s.values || [],
            secondary: Boolean(s.secondary),
          })
        );
        // pptxgenjs colours a multi-chart's sub-charts from the start of its
        // default list each time, so two series on two axes both came out
        // C0504D: one red bar hiding another, and two identical legend
        // swatches. The deck's own palette is preferred, but a fallback is not
        // optional -- a chart whose series cannot be told apart is unreadable
        // whatever its source, and decks exported before the palette was
        // carried in the payload must not stay broken.
        const FALLBACK_SERIES_COLORS = [
          '1A365D',
          '3182CE',
          '2F855A',
          'C05621',
          '6B46C1',
          '2C7A7B',
        ];
        const declared: string[] = Array.isArray(o.colors)
          ? (o.colors as string[]).filter((c: string) => Boolean(c))
          : [];
        const palette: string[] =
          declared.length >= series.length
            ? declared
            : series.map(
                (_s: unknown, i: number) =>
                  declared[i] || FALLBACK_SERIES_COLORS[i % FALLBACK_SERIES_COLORS.length]
              );
        const chartOpts: Record<string, unknown> = {
          x: o.x,
          y: o.y,
          w: o.w,
          h: o.h,
          showTitle: false,
          showLegend: series.length > 1,
          showValue: true,
        };
        if (palette.length) chartOpts.chartColors = palette;
        if (barDir) chartOpts.barDir = barDir;
        // Two value axes with different scales say nothing a reader can use --
        // they are two rulers printed over each other, which is how "1400 1.2
        // 0.4" ended up stacked down the left edge of a card. The HTML preview
        // draws no axis at all for a mixed-scale chart: it paints the bars and
        // prints the numbers on them. Match that, and the second ruler stops
        // competing with the first.
        if (o.mixedScale) {
          chartOpts.showValAxis = false;
          chartOpts.valAxisHidden = true;
          chartOpts.showValue = true;
          chartOpts.dataLabelPosition = 'outEnd';
          // Without a format the label rounds to the axis's own precision, so a
          // CV of 0.3439 was printed as "0" -- a chart stating the opposite of
          // its data. Four decimals covers a ratio; the thousands separator
          // keeps a cost readable.
          chartOpts.dataLabelFormatCode = '#,##0.####';
        }

        // O27: Cost (~2e5) + CV (~1.2) on one axis → CV vanishes. Dual-axis combo.
        if (o.dualAxis && series.some((s: { secondary?: boolean }) => s.secondary)) {
          const primary = series.filter((s: { secondary?: boolean }) => !s.secondary);
          const secondary = series.filter((s: { secondary?: boolean }) => s.secondary);
          const toData = (rows: typeof series) =>
            rows.map((s: { name: string; labels: string[]; values: Array<number | null> }) => ({
              name: s.name,
              labels: s.labels,
              values: s.values,
            }));
          // Each sub-chart carries its own slice of the palette. pptxgenjs
          // colours a multi-chart's sub-charts from the *start* of the default
          // list each time, so without this both "Cost" and "CV" were drawn in
          // the same red -- two identical bars, two identical legend swatches.
          const primaryRows = primary.length ? primary : series.slice(0, 1);
          const secondaryRows = secondary.length ? secondary : series.slice(1);
          const colorFor = (rows: typeof series) =>
            rows
              .map((row: { name: string }) => {
                const at = series.findIndex((s: { name: string }) => s.name === row.name);
                return at >= 0 ? palette[at % palette.length] : undefined;
              })
              .filter((c: string | undefined): c is string => Boolean(c));
          const primaryColors = colorFor(primaryRows);
          const secondaryColors = colorFor(secondaryRows);
          // Each axis is scaled to its own metric. Left to auto-fit, renderers
          // gave both axes the larger metric's range, so a CV of 0.34 beside a
          // cost of 1262 drew no bar at all -- the label was the only trace of
          // it. An axis that is hidden still decides the height of what sits on
          // it, so it has to be told what it is measuring.
          const maxOf = (rows: typeof series) =>
            rows.reduce(
              (mx: number, r: { values: Array<number | null> }) =>
                Math.max(
                  mx,
                  ...(r.values || []).map((v: number | null) =>
                    typeof v === 'number' && Number.isFinite(v) ? Math.abs(v) : 0
                  )
                ),
              0
            );
          const primaryMax = maxOf(primaryRows);
          const secondaryMax = maxOf(secondaryRows);
          const multi = [
            {
              type: chartTypeEnum,
              data: toData(primaryRows),
              options: {
                ...(barDir ? { barDir } : {}),
                ...(primaryColors.length ? { chartColors: primaryColors } : {}),
              },
            },
            {
              type: chartTypeEnum,
              data: toData(secondaryRows),
              options: {
                ...(barDir ? { barDir } : {}),
                ...(secondaryColors.length ? { chartColors: secondaryColors } : {}),
                secondaryValAxis: true,
                secondaryCatAxis: true,
              },
            },
          ];
          // pptxgenjs: when type is IChartMulti[], the 2nd arg is options.
          slide.addChart(multi as any, {
            ...chartOpts,
            valAxes: [
              {
                showValAxisTitle: false,
                catAxisHidden: false,
                valAxisHidden: true,
                valAxisMinVal: 0,
                ...(primaryMax > 0 ? { valAxisMaxVal: primaryMax * 1.15 } : {}),
              },
              {
                showValAxisTitle: false,
                valGridLine: { style: 'none' },
                valAxisHidden: true,
                valAxisMinVal: 0,
                ...(secondaryMax > 0 ? { valAxisMaxVal: secondaryMax * 1.15 } : {}),
              },
            ],
            catAxes: [{}, { catAxisHidden: true }],
          } as any);
        } else {
          slide.addChart(
            chartTypeEnum,
            series.map((s: { name: string; labels: string[]; values: Array<number | null> }) => ({
              name: s.name,
              labels: s.labels,
              values: s.values,
            })),
            chartOpts
          );
        }
        break;
      }

      case 'rect':
        slide.addShape(this.pptx.ShapeType.rect, converted.options);
        break;

      case 'roundRect':
        slide.addShape(this.pptx.ShapeType.roundRect, converted.options);
        break;

      case 'ellipse':
        slide.addShape(this.pptx.ShapeType.ellipse, converted.options);
        break;

      case 'round1Rect':
        slide.addShape(this.pptx.ShapeType.round1Rect, converted.options);
        break;

      case 'round2SameRect':
        slide.addShape(this.pptx.ShapeType.round2SameRect, converted.options);
        break;

      case 'line':
        slide.addShape(this.pptx.ShapeType.line, converted.options);
        break;

      default:
        console.warn(`Unknown element type: ${converted.type}`);
    }
  }

  /**
   * Stable slide id for the report (DH-P0-002). Falls back to slide-NN.
   */
  private resolveSlideId(elements: ElementInfo[], slideIndex: number): string {
    for (const el of elements) {
      const sid = (el as ElementInfo & { slideId?: string }).slideId;
      if (sid) return sid;
    }
    return `slide-${String(slideIndex + 1).padStart(2, '0')}`;
  }

  /**
   * Top Y origin for converting element coordinates on this slide.
   */
  private resolveSlideStartY(elements: ElementInfo[], slideIndex: number): number {
    if (this.slideCoordsNormalized) {
      return 0;
    }
    if (this.splitByHeight) {
      return slideIndex * getSlideHeightPx();
    }
    if (this.slideSelector) {
      if (elements.length === 0) {
        return slideIndex * getSlideHeightPx();
      }
      let minY = Infinity;
      for (const el of elements) {
        if (el.y < minY) minY = el.y;
      }
      // Clamp so off-canvas decorations (negative y) on slide 0 do not shift layout down.
      return Number.isFinite(minY) ? Math.max(0, minY) : 0;
    }
    // Single viewport per slide (default multi-file merge): always origin at top.
    return 0;
  }

  /**
   * Get slide count
   */
  getSlideCount(): number {
    return (this.pptx as any).slides?.length || 0;
  }
}
