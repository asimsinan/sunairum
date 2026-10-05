import { StyleEnhancement } from '../types';
/**
 * Apply image sizing (object-fit: cover/contain) to PPTX XML
 *
 * For object-fit: cover:
 * - Replace <a:stretch/> with <a:stretch><a:fillRect/></a:stretch>
 * - fillRect must be wrapped in stretch tag for proper cover behavior
 * - Calculate and set srcRect with only needed crop attributes (l/r or t/b, not both)
 * - Only set attributes that are needed (non-zero), don't set attributes to 0
 *
 * For object-fit: contain, we'd use <a:fit/> but that's less common.
 */
export declare function applyImageSizingToXml(slideXml: string, enhancement: StyleEnhancement & {
    objectFit: 'cover' | 'contain';
    elementIndex: number;
    picIndex?: number;
}): string;
