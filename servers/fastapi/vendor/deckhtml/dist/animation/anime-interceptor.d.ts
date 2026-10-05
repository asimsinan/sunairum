import type { Page } from 'playwright-core';
/**
 * Install the anime.js interception init script on a page. Must be called
 * before navigation (addInitScript runs ahead of any page script).
 */
export declare function installAnimeInterceptor(page: Page): Promise<void>;
