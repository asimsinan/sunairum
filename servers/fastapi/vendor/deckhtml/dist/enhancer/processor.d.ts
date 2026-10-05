import { StyleEnhancementRegistry } from './registry';
/**
 * Apply all registered style enhancements by modifying PPTX XML
 */
export declare function applyStyleEnhancements(zipBuffer: ArrayBuffer, registry: StyleEnhancementRegistry, pptx: any): Promise<ArrayBuffer>;
