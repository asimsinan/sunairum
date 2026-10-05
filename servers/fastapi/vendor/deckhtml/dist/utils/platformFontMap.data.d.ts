/**
 * AUTO-GENERATED in html2pptx — synced copy; do not edit by hand.
 * Source of truth: html2pptx/docs/css_generic_font_os_map_simplified.csv
 */
import type { GenericFontName, PlatformFontLang, PlatformTarget } from './platformFontMap';
export interface PlatformFontMappingEntry {
    primary: string;
    fallbacks: string[];
}
export type PlatformFontOsMap = Record<PlatformTarget, Record<PlatformFontLang, Record<GenericFontName, PlatformFontMappingEntry>>>;
export declare const GENERIC_FONT_OS_MAP: PlatformFontOsMap;
