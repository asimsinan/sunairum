import { StyleEnhancement, StyleEnhancementType } from '../types';
/**
 * Registry for tracking style enhancements that need post-processing
 * after initial PPTX generation via pptxgenjs
 */
export declare class StyleEnhancementRegistry {
    private enhancements;
    /**
     * Register a style enhancement for an element
     */
    register(enhancement: StyleEnhancement): void;
    /**
     * Get all enhancements for a specific slide
     */
    getForSlide(slideIndex: number): StyleEnhancement[];
    /**
     * Get all enhancements of a specific type
     */
    getByType(type: StyleEnhancementType): StyleEnhancement[];
    /**
     * Get all registered enhancements
     */
    getAll(): StyleEnhancement[];
    /**
     * Get count of registered enhancements
     */
    count(): number;
    /**
     * Clear all registered enhancements
     */
    clear(): void;
}
