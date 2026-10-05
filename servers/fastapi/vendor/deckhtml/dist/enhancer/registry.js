"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.StyleEnhancementRegistry = void 0;
/**
 * Registry for tracking style enhancements that need post-processing
 * after initial PPTX generation via pptxgenjs
 */
class StyleEnhancementRegistry {
    constructor() {
        this.enhancements = [];
    }
    /**
     * Register a style enhancement for an element
     */
    register(enhancement) {
        this.enhancements.push(enhancement);
    }
    /**
     * Get all enhancements for a specific slide
     */
    getForSlide(slideIndex) {
        return this.enhancements.filter(e => e.slideIndex === slideIndex);
    }
    /**
     * Get all enhancements of a specific type
     */
    getByType(type) {
        return this.enhancements.filter(e => e.type === type);
    }
    /**
     * Get all registered enhancements
     */
    getAll() {
        return [...this.enhancements];
    }
    /**
     * Get count of registered enhancements
     */
    count() {
        return this.enhancements.length;
    }
    /**
     * Clear all registered enhancements
     */
    clear() {
        this.enhancements = [];
    }
}
exports.StyleEnhancementRegistry = StyleEnhancementRegistry;
