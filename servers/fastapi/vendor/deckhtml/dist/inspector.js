"use strict";
/**
 * Element Inspector Module
 * Traverses DOM tree and extracts element information
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.ElementInspector = exports.SLIDE_PROBE_RULES = void 0;
const url_1 = require("url");
const coordinate_1 = require("./utils/coordinate");
const mathml_to_omml_1 = require("./utils/mathml-to-omml");
const navigate_1 = require("./utils/navigate");
const resource_policy_1 = require("./utils/resource-policy");
const anime_interceptor_1 = require("./animation/anime-interceptor");
const diagnostics_1 = require("./utils/diagnostics");
const DEFAULT_IFRAME_LOAD_TIMEOUT_MS = 8000;
const DEFAULT_IFRAME_MAX_DEPTH = 3;
const SLIDE_INDEX_ATTR = 'data-deckhtml-slide-index';
const SLIDE_ISOLATION_ATTR = 'data-deckhtml-slide-hidden';
const SLIDE_CANDIDATE_ATTR = 'data-deckhtml-slide-candidate';
/** Pause after isolating a slide so CSS/JS entrance animations can finish. */
const SLIDE_ISOLATION_ANIMATION_SETTLE_MS = 3000;
/** Qualified slide host height must be within [min, max] × viewport slide height. */
const SLIDE_HEIGHT_MIN_RATIO = 0.5;
const SLIDE_HEIGHT_MAX_RATIO = 2.0;
/** Qualified slide host width must be at least this fraction of viewport slide width. */
const SLIDE_WIDTH_MIN_RATIO = 0.8;
const SLIDE_MIN_MATCHES = 2;
/** Stacked deck hosts with nearly identical rects are considered co-located within this tolerance. */
const STACKED_RECT_TOLERANCE_PX = 5;
/** Class names tried first when inferring active-gated deck toggles. */
const ACTIVE_DECK_CLASS_CANDIDATES = [
    'active',
    'is-active',
    'current',
    'show',
    'visible',
    'is-current',
];
/**
 * Ordered probe rules for multi-page HTML. First rule with enough qualified
 * candidates wins; all matches share the same height check, isolation, and inspect pipeline.
 */
exports.SLIDE_PROBE_RULES = [
    { label: '.slide-container', selector: '.slide-container' },
    { label: '.slide-wrap', selector: '.slide-wrap' },
    { label: 'section[class*="slide"]', selector: 'section[class*="slide"]' },
    { label: '.slide', selector: '.slide' },
    { label: '[data-slide]', selector: '[data-slide]' },
    { label: 'section.slide', selector: 'section.slide' },
    {
        // Covers conventions such as .slide-deck, .slide_page, .deck-slide, and
        // .slideDeck without matching unrelated .slideshow / .slider classes.
        // Size qualification in the inspector remains mandatory.
        label: 'semantic slide class',
        selector: '[class]',
        classTokenPattern: '^(?:slide(?:[-_][\\w-]+|[A-Z][\\w-]*)?|[\\w-]+[-_]slide)$',
        requireMeaningfulContent: true,
    },
    {
        label: 'section',
        selector: 'section',
        topLevelAncestorSelector: 'section',
        expandSiblingHosts: true,
    },
];
class ElementInspector {
    constructor(page) {
        this.page = page;
    }
    /**
     * Measure the effective content width of the current page (matches configured viewport width).
     */
    async getPageContentWidth() {
        return (0, coordinate_1.getSlideWidthPx)();
    }
    /**
     * Extract font URLs from @font-face rules in the page
     */
    async extractFontUrls() {
        // First, extract Google Fonts and other external font stylesheet URLs
        const externalFontStylesheets = await this.page.evaluate(() => {
            const links = [];
            document.querySelectorAll('link[rel="stylesheet"]').forEach((link) => {
                const href = link.href;
                if (href) {
                    // Detect Google Fonts and other font services
                    const isFontStylesheet = href.includes('fonts.googleapis.com') ||
                        href.includes('fonts.gstatic.com') ||
                        href.includes('use.typekit.net') ||
                        href.includes('cloud.typography.com') ||
                        href.toLowerCase().includes('font');
                    links.push({ href, isFontStylesheet });
                }
            });
            return links;
        });
        const fontUrls = new Map();
        // Fetch and parse external font stylesheets (bypass CORS)
        for (const { href, isFontStylesheet } of externalFontStylesheets) {
            if (isFontStylesheet) {
                try {
                    console.log(`📥 Fetching font stylesheet: ${href}`);
                    // Navigate to the CSS URL to get its content
                    const response = await this.page.context().request.get(href, {
                        headers: {
                            // Google Fonts needs proper User-Agent to return font URLs
                            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                        }
                    });
                    if (response.ok()) {
                        const cssContent = await response.text();
                        const extracted = this.parseFontFaceRules(cssContent, href);
                        // Merge with existing font URLs
                        extracted.forEach((urlsWithWeight, fontName) => {
                            if (!fontUrls.has(fontName)) {
                                fontUrls.set(fontName, []);
                            }
                            fontUrls.get(fontName).push(...urlsWithWeight);
                        });
                    }
                }
                catch (error) {
                    console.warn(`⚠️  Failed to fetch font stylesheet ${href}:`, error instanceof Error ? error.message : error);
                }
            }
        }
        // Also extract from inline @font-face rules
        const inlineFontUrls = await this.page.evaluate(() => {
            const fonts = new Map();
            // Extract from @font-face rules in stylesheets
            for (const styleSheet of Array.from(document.styleSheets)) {
                try {
                    const rules = Array.from(styleSheet.cssRules || styleSheet.rules || []);
                    for (const rule of rules) {
                        if (rule instanceof CSSFontFaceRule) {
                            const fontFamily = rule.style.getPropertyValue('font-family')
                                .replace(/['"]/g, '')
                                .trim();
                            const src = rule.style.getPropertyValue('src');
                            const fontWeight = rule.style.getPropertyValue('font-weight');
                            const weight = fontWeight ? parseInt(fontWeight, 10) : undefined;
                            if (fontFamily && src) {
                                // Extract URLs from src (url(...))
                                const urlMatches = src.matchAll(/url\(['"]?([^'"()]+)['"]?\)/g);
                                const urlsWithWeight = [];
                                for (const match of urlMatches) {
                                    let url = match[1];
                                    // Convert relative URLs to absolute
                                    if (url && !url.startsWith('data:')) {
                                        if (!url.startsWith('http')) {
                                            url = new URL(url, window.location.href).href;
                                        }
                                        urlsWithWeight.push({ url, weight });
                                    }
                                }
                                if (urlsWithWeight.length > 0) {
                                    if (!fonts.has(fontFamily)) {
                                        fonts.set(fontFamily, []);
                                    }
                                    fonts.get(fontFamily).push(...urlsWithWeight);
                                }
                            }
                        }
                    }
                }
                catch (e) {
                    // Skip inaccessible stylesheets (CORS)
                }
            }
            // Convert Map to Object for serialization
            const result = {};
            fonts.forEach((urlsWithWeight, name) => {
                result[name] = urlsWithWeight;
            });
            return result;
        });
        // Merge inline font URLs
        for (const [name, urls] of Object.entries(inlineFontUrls)) {
            if (!fontUrls.has(name)) {
                fontUrls.set(name, []);
            }
            fontUrls.get(name).push(...urls);
        }
        return fontUrls;
    }
    /**
     * Parse @font-face rules from CSS content
     */
    parseFontFaceRules(cssContent, baseUrl) {
        const fonts = new Map();
        // Match @font-face blocks
        const fontFaceRegex = /@font-face\s*{([^}]+)}/g;
        let match;
        while ((match = fontFaceRegex.exec(cssContent)) !== null) {
            const block = match[1];
            // Extract font-family
            const familyMatch = block.match(/font-family\s*:\s*['"]?([^'";]+)['"]?/);
            if (!familyMatch)
                continue;
            const fontFamily = familyMatch[1].trim();
            // Extract font-weight (optional)
            const weightMatch = block.match(/font-weight\s*:\s*(\d+)/);
            const fontWeight = weightMatch ? parseInt(weightMatch[1], 10) : undefined;
            // Extract src URLs
            const srcMatch = block.match(/src\s*:\s*([^;]+);/);
            if (!srcMatch)
                continue;
            const srcValue = srcMatch[1];
            // Extract all URLs from src
            const urlMatches = srcValue.matchAll(/url\(['"]?([^'"()]+)['"]?\)/g);
            const urlsWithWeight = [];
            for (const urlMatch of urlMatches) {
                let url = urlMatch[1];
                // Skip data URLs
                if (url.startsWith('data:'))
                    continue;
                // Convert relative URLs to absolute
                if (!url.startsWith('http')) {
                    try {
                        url = new URL(url, baseUrl).href;
                    }
                    catch (e) {
                        continue;
                    }
                }
                // Prefer TTF and OTF formats for conversion
                if (url.includes('.ttf') || url.includes('.otf') || url.includes('.woff2')) {
                    urlsWithWeight.push({ url, weight: fontWeight });
                }
            }
            if (urlsWithWeight.length > 0) {
                if (!fonts.has(fontFamily)) {
                    fonts.set(fontFamily, []);
                }
                fonts.get(fontFamily).push(...urlsWithWeight);
            }
        }
        return fonts;
    }
    /**
     * Discover slide container elements in the page.
     * Tags each match with data-deckhtml-slide-index for stable isolation.
     */
    async discoverSlideContainers(selector, autoDetect = true) {
        const explicit = selector?.trim() || '';
        let discovery;
        if (explicit) {
            discovery = await this.page.evaluate(({ explicitSelector, indexAttr }) => {
                const nodes = Array.from(document.querySelectorAll(explicitSelector));
                nodes.forEach((node, i) => node.setAttribute(indexAttr, String(i)));
                return {
                    selector: explicitSelector,
                    count: nodes.length,
                    rule: 'explicit',
                };
            }, { explicitSelector: explicit, indexAttr: SLIDE_INDEX_ATTR });
        }
        else if (autoDetect) {
            discovery = await this.discoverByProbeRules();
        }
        else {
            discovery = this.emptySlideDiscovery();
        }
        return this.enrichDiscoveryWithActiveDeck(discovery);
    }
    /** Attach active-gated deck metadata when tagged slide hosts match deck heuristics. */
    async enrichDiscoveryWithActiveDeck(discovery) {
        if (discovery.count < SLIDE_MIN_MATCHES)
            return discovery;
        const activeDeck = await this.detectActiveGatedDeck();
        if (!activeDeck)
            return discovery;
        return { ...discovery, activeDeck };
    }
    emptySlideDiscovery() {
        return { selector: '', count: 0, rule: 'none' };
    }
    /**
     * Try each {@link SLIDE_PROBE_RULES} entry in order; tag qualified hosts and
     * return a selector that matches only those tagged nodes.
     */
    async discoverByProbeRules() {
        const slideHeight = (0, coordinate_1.getSlideHeightPx)();
        const slideWidth = (0, coordinate_1.getSlideWidthPx)();
        for (const rule of exports.SLIDE_PROBE_RULES) {
            const candidateCount = await this.page.evaluate(({ probeRule, candidateAttr }) => {
                document.querySelectorAll(`[${candidateAttr}]`).forEach((node) => {
                    node.removeAttribute(candidateAttr);
                });
                let nodes = Array.from(document.querySelectorAll(probeRule.selector));
                if (probeRule.classTokenPattern) {
                    const classTokenPattern = new RegExp(probeRule.classTokenPattern);
                    nodes = nodes.filter((node) => Array.from(node.classList).some((className) => classTokenPattern.test(className)));
                }
                if (probeRule.topLevelAncestorSelector) {
                    nodes = nodes.filter((node) => !node.parentElement?.closest(probeRule.topLevelAncestorSelector));
                }
                nodes.forEach((node, i) => node.setAttribute(candidateAttr, String(i)));
                return nodes.length;
            }, { probeRule: rule, candidateAttr: SLIDE_CANDIDATE_ATTR });
            if (candidateCount < SLIDE_MIN_MATCHES) {
                await this.cleanupSlideCandidates();
                continue;
            }
            const discovery = await this.finalizeSlidesFromProbeParents(rule, slideHeight, slideWidth);
            if (discovery.count >= SLIDE_MIN_MATCHES) {
                return discovery;
            }
            await this.cleanupSlideCandidates();
        }
        return this.emptySlideDiscovery();
    }
    /**
     * Qualify slide hosts from probe matches. Named slide-class rules use probe hits
     * only; generic section rule may expand to size-qualified siblings (e.g. header.hero).
     */
    async finalizeSlidesFromProbeParents(probeRule, slideHeight, slideWidth) {
        const minH = slideHeight * SLIDE_HEIGHT_MIN_RATIO;
        const maxH = slideHeight * SLIDE_HEIGHT_MAX_RATIO;
        const minW = slideWidth * SLIDE_WIDTH_MIN_RATIO;
        const expandSiblingHosts = probeRule.expandSiblingHosts === true;
        return this.page.evaluate(({ candidateAttr, indexAttr, ruleLabel, minH, maxH, minW, expandSiblingHosts, requireMeaningfulContent, }) => {
            const sortDocumentOrder = (a, b) => {
                const pos = a.compareDocumentPosition(b);
                if (pos & Node.DOCUMENT_POSITION_FOLLOWING)
                    return -1;
                if (pos & Node.DOCUMENT_POSITION_PRECEDING)
                    return 1;
                return 0;
            };
            const qualifiesSize = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.height >= minH && rect.height <= maxH && rect.width >= minW;
            };
            const hasMeaningfulContent = (el) => {
                if ((el.textContent ?? '').trim().length > 0)
                    return true;
                return !!el.querySelector('img, canvas, svg, table, video, iframe, input:not([type="hidden"]), button, a[href]');
            };
            const isDecorativeDeckOverlay = (el) => {
                if (el.hasAttribute(candidateAttr))
                    return false;
                const style = window.getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden')
                    return true;
                const opacity = parseFloat(style.opacity);
                if (!Number.isNaN(opacity) && opacity <= 0.01)
                    return true;
                const noMeaningful = !hasMeaningfulContent(el);
                if (style.pointerEvents === 'none' && noMeaningful)
                    return true;
                const pos = style.position;
                if (noMeaningful && (pos === 'absolute' || pos === 'fixed'))
                    return true;
                return false;
            };
            const candidates = Array.from(document.querySelectorAll(`[${candidateAttr}]`));
            let qualified;
            if (!expandSiblingHosts) {
                qualified = candidates
                    .filter((candidate) => qualifiesSize(candidate) &&
                    (!requireMeaningfulContent || hasMeaningfulContent(candidate)))
                    .sort(sortDocumentOrder);
            }
            else {
                const seenParents = new Set();
                const parents = [];
                for (const candidate of candidates) {
                    const parent = candidate.parentElement;
                    if (!parent || seenParents.has(parent))
                        continue;
                    seenParents.add(parent);
                    parents.push(parent);
                }
                parents.sort(sortDocumentOrder);
                qualified = [];
                for (const parent of parents) {
                    for (const child of Array.from(parent.children)) {
                        if (!qualifiesSize(child))
                            continue;
                        if (isDecorativeDeckOverlay(child))
                            continue;
                        qualified.push(child);
                    }
                }
            }
            // Prefer outer deck hosts when probe matches nested nodes (e.g. .slide inside .slide-wrap).
            const outerHosts = qualified.filter((node) => !qualified.some((other) => other !== node && other.contains(node)));
            document.querySelectorAll(`[${indexAttr}]`).forEach((node) => {
                node.removeAttribute(indexAttr);
            });
            outerHosts.forEach((node, slideIdx) => {
                node.setAttribute(indexAttr, String(slideIdx));
            });
            document.querySelectorAll(`[${candidateAttr}]`).forEach((node) => {
                node.removeAttribute(candidateAttr);
            });
            return {
                selector: `[${indexAttr}]`,
                count: outerHosts.length,
                rule: ruleLabel,
            };
        }, {
            candidateAttr: SLIDE_CANDIDATE_ATTR,
            indexAttr: SLIDE_INDEX_ATTR,
            ruleLabel: probeRule.label,
            minH,
            maxH,
            minW,
            expandSiblingHosts,
            requireMeaningfulContent: probeRule.requireMeaningfulContent === true,
        });
    }
    async cleanupSlideCandidates() {
        await this.page.evaluate((candidateAttr) => {
            document.querySelectorAll(`[${candidateAttr}]`).forEach((node) => {
                node.removeAttribute(candidateAttr);
            });
        }, SLIDE_CANDIDATE_ATTR);
    }
    /**
     * Detect slide decks where exactly one stacked sibling is visible and a CSS class
     * (e.g. `.active`) gates visibility across co-located hosts.
     */
    async detectActiveGatedDeck() {
        return this.page.evaluate(({ indexAttr, classCandidates, rectTolerance }) => {
            const hosts = Array.from(document.querySelectorAll(`[${indexAttr}]`));
            if (hosts.length < 2)
                return undefined;
            const parent = hosts[0].parentElement;
            if (!parent || !hosts.every((host) => host.parentElement === parent)) {
                return undefined;
            }
            const isStackedHost = (host) => {
                const style = window.getComputedStyle(host);
                if (style.position !== 'absolute' && style.position !== 'fixed') {
                    return false;
                }
                if (!(host instanceof HTMLElement))
                    return false;
                const first = hosts[0];
                if (!(first instanceof HTMLElement))
                    return false;
                // Use layout dimensions — inactive slides may be offset by CSS transform.
                return (Math.abs(host.offsetWidth - first.offsetWidth) <= rectTolerance &&
                    Math.abs(host.offsetHeight - first.offsetHeight) <= rectTolerance);
            };
            if (!hosts.every(isStackedHost))
                return undefined;
            const isVisible = (host) => {
                const style = window.getComputedStyle(host);
                const opacity = parseFloat(style.opacity);
                return style.visibility !== 'hidden' && !Number.isNaN(opacity) && opacity > 0.01;
            };
            const visibleHosts = hosts.filter(isVisible);
            if (visibleHosts.length !== 1)
                return undefined;
            const visible = visibleHosts[0];
            const hidden = hosts.find((host) => host !== visible);
            if (!hidden)
                return undefined;
            const inferActiveClass = () => {
                for (const className of classCandidates) {
                    if (visible.classList.contains(className) && !hidden.classList.contains(className)) {
                        return className;
                    }
                }
                for (const className of Array.from(visible.classList)) {
                    if (!hidden.classList.contains(className))
                        return className;
                }
                return undefined;
            };
            const activeClass = inferActiveClass();
            if (!activeClass)
                return undefined;
            return { activeClass };
        }, {
            indexAttr: SLIDE_INDEX_ATTR,
            classCandidates: ACTIVE_DECK_CLASS_CANDIDATES,
            rectTolerance: STACKED_RECT_TOLERANCE_PX,
        });
    }
    async waitForLayoutSettle() {
        await this.page.evaluate(() => new Promise((resolve) => {
            requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
        }));
        await this.page.waitForTimeout(50);
    }
    /** Wait for slide-local animations after isolation before element inspect. */
    async waitForSlideAnimationSettle() {
        await this.page.waitForTimeout(SLIDE_ISOLATION_ANIMATION_SETTLE_MS);
    }
    /**
     * Multi-slide preprocessing: hide every node outside the slide container
     * (keep the container, its descendants, and ancestor chain visible).
     */
    async isolateOutsideSlideContainer(slideSelector, discovery) {
        const minH = (0, coordinate_1.getSlideHeightPx)() * SLIDE_HEIGHT_MIN_RATIO;
        const minW = (0, coordinate_1.getSlideWidthPx)() * SLIDE_WIDTH_MIN_RATIO;
        await this.page.evaluate(({ slideSelector, hiddenAttr, indexAttr, minH, minW }) => {
            const host = document.querySelector(slideSelector);
            if (!host)
                return;
            const hideNode = (node) => {
                if (!(node instanceof HTMLElement || node instanceof SVGElement))
                    return;
                node.setAttribute(hiddenAttr, '1');
                node.style.setProperty('display', 'none', 'important');
            };
            const isSlideUiControl = (node) => {
                if (!(node instanceof HTMLElement))
                    return false;
                if (node.matches('input[type="radio"], input[type="checkbox"]'))
                    return true;
                if (node.matches('.slide-nav, .controls, .nav-dots'))
                    return true;
                if (node.closest('.slide-nav, .controls'))
                    return true;
                return false;
            };
            const hasVisibleBackground = (el) => {
                const style = window.getComputedStyle(el);
                const bg = style.backgroundImage;
                if (bg && bg !== 'none')
                    return true;
                const bgColor = style.backgroundColor;
                return !!(bgColor &&
                    bgColor !== 'transparent' &&
                    bgColor !== 'rgba(0, 0, 0, 0)');
            };
            const isSharedDeckDecoration = (node) => {
                if (!(node instanceof HTMLElement))
                    return false;
                if (node.hasAttribute(indexAttr))
                    return false;
                const hostParent = host.parentElement;
                if (!hostParent || node.parentElement !== hostParent)
                    return false;
                const rect = node.getBoundingClientRect();
                const fullBleed = rect.width >= minW && rect.height >= minH;
                const partialDecor = hasVisibleBackground(node) && rect.height >= minH * 0.5;
                return fullBleed || partialDecor;
            };
            const shouldKeepVisible = (node) => {
                if (node === host || host.contains(node))
                    return true;
                if (node.contains(host))
                    return true;
                if (isSharedDeckDecoration(node))
                    return true;
                return false;
            };
            const shouldHide = (node) => {
                if (isSlideUiControl(node))
                    return true;
                return !shouldKeepVisible(node);
            };
            const roots = [];
            if (document.body)
                roots.push(document.body);
            if (document.documentElement && document.documentElement !== document.body) {
                roots.push(document.documentElement);
            }
            for (const root of roots) {
                for (const node of Array.from(root.querySelectorAll('*'))) {
                    if (!shouldHide(node))
                        continue;
                    hideNode(node);
                }
            }
            if (document.body) {
                for (const child of Array.from(document.body.children)) {
                    if (!shouldHide(child))
                        continue;
                    hideNode(child);
                }
            }
            window.scrollTo(0, 0);
        }, {
            slideSelector,
            hiddenAttr: SLIDE_ISOLATION_ATTR,
            indexAttr: SLIDE_INDEX_ATTR,
            minH,
            minW,
        });
        await this.captureCssAnimations(slideSelector);
        await this.prepareSlideContainerForInspect(slideSelector, discovery);
        await this.waitForLayoutSettle();
        await this.waitForSlideAnimationSettle();
    }
    /**
     * Capture CSS animation declarations before styles are frozen for inspection:
     * - `@keyframes` first/last frames (computed animation-* props)
     * - class-gated entrance `transition`s (opacity/transform) via enter-class replay
     *
     * Elements get a data-dh-anim-css marker; raw data lives on
     * window.__deckhtmlCssAnimations and is folded into animationRaw.cssRaw by
     * readAnimationRaw during inspect.
     */
    async captureCssAnimations(slideSelector) {
        await this.page
            .evaluate((rootSel) => {
            const WIN_KEY = '__deckhtmlCssAnimations';
            const MARK_ATTR = 'data-dh-anim-css';
            window[WIN_KEY] = {};
            /** Enter / reveal classes that gate opacity/transform transitions (not deck nav). */
            const ENTER_CLASS_CANDIDATES = [
                'is-entered',
                'entered',
                'has-entered',
                'animate-in',
                'is-revealed',
                'revealed',
                'in-view',
                'is-visible',
            ];
            const parseCssTime = (v) => {
                const m = v.trim().match(/^(-?\d+(?:\.\d+)?)(ms|s)?$/);
                if (!m)
                    return 0;
                const n = parseFloat(m[1]);
                if (isNaN(n) || n < 0)
                    return 0;
                return m[2] === 's' ? Math.round(n * 1000) : Math.round(n);
            };
            const parseTransformMotion = (transform) => {
                const motion = {
                    translateXPx: 0,
                    translateYPx: 0,
                    scaleX: 1,
                    scaleY: 1,
                    rotateDeg: 0,
                };
                const t = (transform || '').trim();
                if (!t || t === 'none')
                    return motion;
                const len = (v) => {
                    const n = parseFloat(v);
                    return isNaN(n) ? 0 : n; // px units; percentages treated as px (approximation)
                };
                if (/^matrix3?\(/.test(t)) {
                    try {
                        const m = new DOMMatrix(t);
                        motion.translateXPx = m.e;
                        motion.translateYPx = m.f;
                        motion.scaleX = Math.sqrt(m.a * m.a + m.b * m.b) || 1;
                        motion.scaleY = Math.sqrt(m.c * m.c + m.d * m.d) || 1;
                        motion.rotateDeg = (Math.atan2(m.b, m.a) * 180) / Math.PI;
                        return motion;
                    }
                    catch {
                        return motion;
                    }
                }
                const fn = /([a-zA-Z0-9]+)\(([^)]*)\)/g;
                let m;
                while ((m = fn.exec(t)) !== null) {
                    const name = m[1];
                    const args = m[2].split(',').map((s) => s.trim());
                    switch (name) {
                        case 'translate':
                        case 'translate3d':
                            motion.translateXPx += len(args[0] ?? '0');
                            motion.translateYPx += len(args[1] ?? '0');
                            break;
                        case 'translateX':
                            motion.translateXPx += len(args[0] ?? '0');
                            break;
                        case 'translateY':
                            motion.translateYPx += len(args[0] ?? '0');
                            break;
                        case 'scale':
                        case 'scale3d': {
                            const sx = parseFloat(args[0] ?? '1');
                            const sy = parseFloat(args[1] ?? args[0] ?? '1');
                            if (!isNaN(sx))
                                motion.scaleX *= sx;
                            if (!isNaN(sy))
                                motion.scaleY *= sy;
                            break;
                        }
                        case 'scaleX': {
                            const s = parseFloat(args[0] ?? '1');
                            if (!isNaN(s))
                                motion.scaleX *= s;
                            break;
                        }
                        case 'scaleY': {
                            const s = parseFloat(args[0] ?? '1');
                            if (!isNaN(s))
                                motion.scaleY *= s;
                            break;
                        }
                        case 'rotate':
                        case 'rotateZ': {
                            const deg = parseFloat(args[0] ?? '0');
                            if (!isNaN(deg))
                                motion.rotateDeg += deg;
                            break;
                        }
                        default:
                            break;
                    }
                }
                return motion;
            };
            const parseKeyframeFrame = (cssText) => {
                const open = cssText.indexOf('{');
                const close = cssText.lastIndexOf('}');
                const body = open >= 0 && close > open ? cssText.slice(open + 1, close) : '';
                const holder = document.createElement('div');
                holder.style.cssText = body;
                const s = holder.style;
                const opacity = s.opacity === '' ? null : parseFloat(s.opacity);
                let hasNonMotionProps = false;
                for (let i = 0; i < s.length; i++) {
                    const prop = s[i];
                    if (prop !== 'opacity' && prop !== 'transform') {
                        hasNonMotionProps = true;
                        break;
                    }
                }
                return { opacity, ...parseTransformMotion(s.transform || ''), hasNonMotionProps };
            };
            const snapshotComputedMotion = (el) => {
                const cs = window.getComputedStyle(el);
                const opacity = parseFloat(cs.opacity);
                return {
                    opacity: Number.isFinite(opacity) ? opacity : null,
                    ...parseTransformMotion(cs.transform || ''),
                    hasNonMotionProps: false,
                };
            };
            /** Max duration/delay among opacity|transform|all transition entries. */
            const readMotionTransitionTiming = (cs) => {
                const props = cs.transitionProperty.split(',').map((s) => s.trim());
                if (props.length === 0 || (props.length === 1 && props[0] === 'none'))
                    return null;
                const durs = cs.transitionDuration.split(',').map((s) => s.trim());
                const delays = cs.transitionDelay.split(',').map((s) => s.trim());
                let maxDur = 0;
                let matchedDelay = 0;
                let hasMotion = false;
                for (let i = 0; i < props.length; i++) {
                    const prop = props[i];
                    if (prop !== 'all' &&
                        prop !== 'opacity' &&
                        prop !== 'transform' &&
                        !prop.startsWith('transform')) {
                        continue;
                    }
                    const dur = parseCssTime(durs[Math.min(i, durs.length - 1)] ?? durs[0] ?? '0s');
                    if (dur <= 0)
                        continue;
                    hasMotion = true;
                    const delay = parseCssTime(delays[Math.min(i, delays.length - 1)] ?? delays[0] ?? '0s');
                    if (dur > maxDur) {
                        maxDur = dur;
                        matchedDelay = delay;
                    }
                    else if (dur === maxDur && delay > matchedDelay) {
                        matchedDelay = delay;
                    }
                }
                return hasMotion ? { durationMs: maxDur, delayMs: matchedDelay } : null;
            };
            const looksLikeEntrance = (first, last) => {
                const fadesIn = first.opacity !== null &&
                    first.opacity <= 0.01 &&
                    (last.opacity === null || last.opacity > first.opacity + 0.05);
                const dx = last.translateXPx - first.translateXPx;
                const dy = last.translateYPx - first.translateYPx;
                const moves = Math.abs(dx) > 1 || Math.abs(dy) > 1;
                const scales = Math.abs(last.scaleX - first.scaleX) > 0.01 ||
                    Math.abs(last.scaleY - first.scaleY) > 0.01;
                const rotates = Math.abs(last.rotateDeg - first.rotateDeg) > 0.5;
                return fadesIn || moves || scales || rotates;
            };
            const forceReflow = (node) => {
                void node.offsetWidth;
            };
            // Index @keyframes rules (Chromium maps -webkit-keyframes to type 7 too).
            const keyframes = new Map();
            for (const sheet of Array.from(document.styleSheets)) {
                let rules = null;
                try {
                    rules = sheet.cssRules;
                }
                catch {
                    continue; // cross-origin sheet
                }
                if (!rules)
                    continue;
                for (const rule of Array.from(rules)) {
                    if (rule.type !== CSSRule.KEYFRAMES_RULE)
                        continue;
                    const kfRule = rule;
                    const frames = {
                        first: null,
                        last: null,
                    };
                    for (const kf of Array.from(kfRule.cssRules)) {
                        const keyframe = kf;
                        const keys = keyframe.keyText.split(',').map((s) => s.trim());
                        if (keys.some((k) => k === 'from' || k === '0%'))
                            frames.first = keyframe.cssText;
                        if (keys.some((k) => k === 'to' || k === '100%'))
                            frames.last = keyframe.cssText;
                    }
                    keyframes.set(kfRule.name, frames);
                }
            }
            const root = rootSel ? document.querySelector(rootSel) : document.body;
            if (!root)
                return;
            const elements = [root, ...Array.from(root.querySelectorAll('*'))];
            let seq = 0;
            const captured = {};
            // --- 1) @keyframes captures ---
            for (const el of elements) {
                if (!(el instanceof HTMLElement || el instanceof SVGElement))
                    continue;
                const cs = window.getComputedStyle(el);
                const nameList = cs.animationName;
                if (!nameList || nameList === 'none')
                    continue;
                const name = nameList.split(',')[0].trim();
                const frames = keyframes.get(name);
                if (!frames || !frames.first || !frames.last)
                    continue;
                const iterStr = cs.animationIterationCount.split(',')[0].trim();
                const raw = {
                    name,
                    durationMs: parseCssTime(cs.animationDuration.split(',')[0] ?? ''),
                    delayMs: parseCssTime(cs.animationDelay.split(',')[0] ?? ''),
                    iterationCount: iterStr === 'infinite' ? null : parseFloat(iterStr) || 1,
                    first: parseKeyframeFrame(frames.first),
                    last: parseKeyframeFrame(frames.last),
                };
                const key = String(seq++);
                el.setAttribute(MARK_ATTR, key);
                captured[key] = raw;
            }
            // --- 2) Class-gated entrance transitions (opacity / transform) ---
            // Replay by stripping (or adding) enter classes with transitions forced off,
            // then diff computed motion into the same CssAnimationRaw shape as keyframes.
            const freezeTransitions = () => {
                const style = document.createElement('style');
                style.setAttribute('data-deckhtml-transition-probe', '1');
                style.textContent =
                    '*, *::before, *::after { transition: none !important; animation: none !important; }';
                document.head.appendChild(style);
                return style;
            };
            const collectEnterToggles = () => {
                const toggles = [];
                for (const el of elements) {
                    if (!(el instanceof Element))
                        continue;
                    for (const cls of ENTER_CLASS_CANDIDATES) {
                        if (el.classList.contains(cls))
                            toggles.push({ el, cls });
                    }
                }
                return toggles;
            };
            const recordTransitionCaptures = (startByEl, endByEl) => {
                for (const [el, end] of endByEl) {
                    if (el.hasAttribute(MARK_ATTR))
                        continue;
                    const first = startByEl.get(el);
                    if (!first)
                        continue;
                    if (!looksLikeEntrance(first, end.frame))
                        continue;
                    const key = String(seq++);
                    el.setAttribute(MARK_ATTR, key);
                    captured[key] = {
                        name: 'css-transition',
                        durationMs: end.durationMs,
                        delayMs: end.delayMs,
                        iterationCount: 1,
                        first,
                        last: end.frame,
                    };
                }
            };
            const snapshotTransitionEnds = () => {
                const endByEl = new Map();
                for (const el of elements) {
                    if (!(el instanceof HTMLElement || el instanceof SVGElement))
                        continue;
                    if (el.hasAttribute(MARK_ATTR))
                        continue;
                    const cs = window.getComputedStyle(el);
                    const timing = readMotionTransitionTiming(cs);
                    if (!timing)
                        continue;
                    endByEl.set(el, {
                        frame: snapshotComputedMotion(el),
                        durationMs: timing.durationMs,
                        delayMs: timing.delayMs,
                    });
                }
                return endByEl;
            };
            const snapshotTransitionStarts = (candidates) => {
                const startByEl = new Map();
                for (const el of candidates) {
                    startByEl.set(el, snapshotComputedMotion(el));
                }
                return startByEl;
            };
            // Phase A: enter class already applied (typical after page-runtime enter()).
            const presentToggles = collectEnterToggles();
            if (presentToggles.length > 0) {
                const endByEl = snapshotTransitionEnds();
                const probeStyle = freezeTransitions();
                for (const { el, cls } of presentToggles)
                    el.classList.remove(cls);
                forceReflow(root);
                const startByEl = snapshotTransitionStarts(endByEl.keys());
                for (const { el, cls } of presentToggles)
                    el.classList.add(cls);
                forceReflow(root);
                probeStyle.remove();
                recordTransitionCaptures(startByEl, endByEl);
            }
            // Phase B: no enter class yet — try adding candidates on the slide root so
            // inactive / pre-enter slides still yield entrance diffs. Keep a class that
            // produces captures so inspect sees the visible end-state.
            // Timing must be read with the enter class applied and without the freeze
            // stylesheet (delays often live under `.is-entered …` rules).
            if (presentToggles.length === 0) {
                const hosts = [root];
                const pageHost = root.querySelector('.slide-page, .slide, [data-slide]');
                if (pageHost && pageHost !== root)
                    hosts.push(pageHost);
                let kept = false;
                for (const host of hosts) {
                    for (const cls of ENTER_CLASS_CANDIDATES) {
                        if (host.classList.contains(cls))
                            continue;
                        const candidateEls = elements.filter((el) => (el instanceof HTMLElement || el instanceof SVGElement) &&
                            !el.hasAttribute(MARK_ATTR) &&
                            Boolean(readMotionTransitionTiming(window.getComputedStyle(el))));
                        if (candidateEls.length === 0)
                            continue;
                        const startByEl = snapshotTransitionStarts(candidateEls);
                        const probeStyle = freezeTransitions();
                        host.classList.add(cls);
                        forceReflow(root);
                        const endFrames = new Map();
                        for (const el of startByEl.keys()) {
                            endFrames.set(el, snapshotComputedMotion(el));
                        }
                        probeStyle.remove();
                        forceReflow(root);
                        // Read duration/delay in the entered state (freeze stylesheet removed).
                        const endByEl = new Map();
                        for (const [el, frame] of endFrames) {
                            const timing = readMotionTransitionTiming(window.getComputedStyle(el));
                            if (!timing)
                                continue;
                            endByEl.set(el, {
                                frame,
                                durationMs: timing.durationMs,
                                delayMs: timing.delayMs,
                            });
                        }
                        const beforeCount = Object.keys(captured).length;
                        recordTransitionCaptures(startByEl, endByEl);
                        if (Object.keys(captured).length > beforeCount) {
                            kept = true;
                            break;
                        }
                        host.classList.remove(cls);
                        forceReflow(root);
                    }
                    if (kept)
                        break;
                }
            }
            /**
             * Freeze captured animations to their end-state before inspect.
             *
             * Phase B's transition probe injects `animation: none !important` on `*`,
             * which clears fill-mode(forwards) and snaps entrance classes like
             * `.animate-fade-up { opacity: 0; animation: … forwards }` back to opacity 0.
             * Removing the probe stylesheet restarts those animations from the first
             * frame. Single-slide inspectElements then measures immediately — so the
             * whole card subtree is treated as invisible and the PPTX looks blank.
             * Pin last-frame opacity/transform + disable animation/transition so
             * inspect sees the final visual (PPTX entrance timing still uses `captured`).
             */
            const motionToTransform = (frame) => {
                const parts = [];
                if (frame.translateXPx || frame.translateYPx) {
                    parts.push(`translate(${frame.translateXPx}px, ${frame.translateYPx}px)`);
                }
                if (frame.scaleX !== 1 || frame.scaleY !== 1) {
                    parts.push(`scale(${frame.scaleX}, ${frame.scaleY})`);
                }
                if (frame.rotateDeg) {
                    parts.push(`rotate(${frame.rotateDeg}deg)`);
                }
                return parts.length > 0 ? parts.join(' ') : 'none';
            };
            for (const el of elements) {
                if (!(el instanceof HTMLElement || el instanceof SVGElement))
                    continue;
                const key = el.getAttribute(MARK_ATTR);
                if (!key)
                    continue;
                const raw = captured[key];
                const last = raw?.last;
                if (!last)
                    continue;
                if (last.opacity !== null && Number.isFinite(last.opacity)) {
                    el.style.setProperty('opacity', String(last.opacity), 'important');
                }
                el.style.setProperty('transform', motionToTransform(last), 'important');
                el.style.setProperty('animation', 'none', 'important');
                el.style.setProperty('transition', 'none', 'important');
                el.style.setProperty('visibility', 'visible', 'important');
            }
            window[WIN_KEY] = captured;
        }, slideSelector ?? null)
            .catch(() => { });
    }
    /** Scroll-reveal hooks leave `.reveal` at opacity:0 until scrolled; fix before inspect. */
    async prepareSlideContainerForInspect(slideSelector, discovery) {
        await this.page.evaluate(({ sel, activeClass }) => {
            const host = document.querySelector(sel);
            if (!(host instanceof HTMLElement))
                return;
            if (activeClass) {
                const deckParent = host.parentElement;
                if (deckParent) {
                    for (const sibling of Array.from(deckParent.children)) {
                        sibling.classList.remove(activeClass);
                    }
                    host.classList.add(activeClass);
                }
            }
            host.scrollIntoView({ block: 'start', inline: 'nearest' });
            // scrollIntoView can shift the viewport (esp. when content overflows).
            // Inspect uses getBoundingClientRect() (viewport space); a non-zero
            // scrollX makes every x look ~scrollX too small — even slightly
            // negative — which then blows up in pptxgenjs addTable. Always reset.
            window.scrollTo(0, 0);
            document.documentElement.scrollTop = 0;
            document.documentElement.scrollLeft = 0;
            if (document.body) {
                document.body.scrollTop = 0;
                document.body.scrollLeft = 0;
            }
            const nodes = [
                host,
                ...Array.from(host.querySelectorAll('.reveal')),
            ].filter((n) => n instanceof HTMLElement);
            for (const node of nodes) {
                let current = node;
                while (current) {
                    if (current instanceof HTMLElement || current instanceof SVGElement) {
                        current.style.setProperty('transition', 'none', 'important');
                        current.style.setProperty('animation', 'none', 'important');
                        current.style.setProperty('visibility', 'visible', 'important');
                        current.style.setProperty('opacity', '1', 'important');
                        current.style.setProperty('transform', 'none', 'important');
                    }
                    current = current.parentElement;
                }
                node.classList.add('show');
            }
            host.querySelectorAll('[data-target]').forEach((el) => {
                if (!(el instanceof HTMLElement))
                    return;
                const target = parseFloat(el.dataset.target ?? '');
                if (Number.isNaN(target))
                    return;
                const decimals = parseInt(el.dataset.decimals ?? '0', 10);
                const suffix = el.dataset.suffix ?? '';
                const prefix = el.dataset.prefix ?? '';
                el.textContent = `${prefix}${target.toFixed(decimals)}${suffix}`;
                delete el.dataset.done;
            });
        }, {
            sel: slideSelector,
            activeClass: discovery?.activeDeck?.activeClass ?? null,
        });
    }
    async clearPptxMappedAttributes() {
        await this.page.evaluate((mappedAttr) => {
            document.querySelectorAll(`[${mappedAttr}]`).forEach((node) => {
                node.removeAttribute(mappedAttr);
            });
        }, 'data-html2pptx-mapped');
    }
    async restoreSlideIsolation() {
        await this.page.evaluate(({ hiddenAttr, pageBgAttr }) => {
            document.querySelectorAll(`[${hiddenAttr}]`).forEach((node) => {
                if (!(node instanceof HTMLElement || node instanceof SVGElement))
                    return;
                node.style.removeProperty('display');
                node.removeAttribute(hiddenAttr);
            });
            // Raster page-bg helpers are appended to <body> during inspect and must not
            // leak into the next slide on the same Playwright page (multi-file batch path).
            document.querySelectorAll(`[${pageBgAttr}]`).forEach((node) => {
                node.remove();
            });
        }, { hiddenAttr: SLIDE_ISOLATION_ATTR, pageBgAttr: 'data-html2pptx-page-bg' });
    }
    async cleanupSlideContainerTags() {
        await this.page.evaluate((indexAttr) => {
            document.querySelectorAll(`[${indexAttr}]`).forEach((node) => {
                node.removeAttribute(indexAttr);
            });
        }, SLIDE_INDEX_ATTR);
    }
    async getSlideContainerOrigin(slideIndex, selector) {
        return this.page.evaluate(({ slideIndex, selector, indexAttr }) => {
            const node = document.querySelector(`${selector}[${indexAttr}="${slideIndex}"]`) ?? document.querySelectorAll(selector)[slideIndex];
            if (!node)
                return { x: 0, y: 0 };
            const rect = node.getBoundingClientRect();
            return { x: 0, y: rect.top };
        }, { slideIndex, selector, indexAttr: SLIDE_INDEX_ATTR });
    }
    normalizeElementCoords(elements, origin) {
        if (origin.y === 0)
            return;
        for (const el of elements) {
            el.y -= origin.y;
        }
    }
    /**
     * Body page-bg is emitted at the viewport origin (0,0). After subtracting the
     * slide container origin it drifts off-slide and PowerPoint prompts for repair.
     */
    anchorFullSlidePageBg(elements) {
        const w = (0, coordinate_1.getSlideWidthPx)();
        const h = (0, coordinate_1.getSlideHeightPx)();
        for (const el of elements) {
            if (el.tag !== 'body.page-bg')
                continue;
            el.x = 0;
            el.y = 0;
            el.width = w;
            el.height = h;
        }
    }
    /**
     * Inspect one slide after isolation (multi-slide path).
     */
    async inspectOneSlideIsolated(slideIndex, discovery, options) {
        const slideSelector = `[${SLIDE_INDEX_ATTR}="${slideIndex}"]`;
        await this.clearPptxMappedAttributes();
        await this.isolateOutsideSlideContainer(slideSelector, discovery);
        const origin = await this.getSlideContainerOrigin(slideIndex, discovery.selector);
        const elements = await this.inspectElements(undefined, options);
        this.normalizeElementCoords(elements, origin);
        this.anchorFullSlidePageBg(elements);
        if (elements.length === 0) {
            elements.push({
                type: 'text',
                tag: 'p',
                x: 0,
                y: 0,
                width: 0,
                height: 0,
                styles: {},
                content: '',
            });
        }
        return elements;
    }
    /**
     * Inspect each slide container in isolation and return per-slide element maps.
     */
    async inspectSlidesIsolated(discovery, options) {
        const slidesMap = new Map();
        for (let i = 0; i < discovery.count; i++) {
            try {
                const elements = await this.inspectOneSlideIsolated(i, discovery, options);
                slidesMap.set(i, elements);
            }
            finally {
                await this.restoreSlideIsolation();
            }
        }
        await this.cleanupSlideContainerTags();
        return slidesMap;
    }
    /**
     * Isolate one slide for raster capture (PNG multi-slide / active-gated decks).
     */
    async prepareSlideForRasterExport(slideIndex, discovery) {
        const slideSelector = this.slideIndexSelector(slideIndex);
        await this.isolateOutsideSlideContainer(slideSelector, discovery);
    }
    /** Restore DOM after {@link prepareSlideForRasterExport}. */
    async restoreSlideForRasterExport() {
        await this.restoreSlideIsolation();
    }
    /**
     * Clip the document to one viewport-height slice for splitByHeight raster export.
     */
    async applyViewportClipForRaster(offsetY, viewport) {
        const styleId = 'deckhtml-raster-clip-style';
        await this.page.evaluate(({ styleId, offsetY, width, height }) => {
            document.getElementById(styleId)?.remove();
            const style = document.createElement('style');
            style.id = styleId;
            style.textContent = `
          html, body {
            width: ${width}px !important;
            height: ${height}px !important;
            overflow: hidden !important;
            margin: 0 !important;
            padding: 0 !important;
          }
        `;
            document.head.appendChild(style);
            if (document.body) {
                document.body.style.setProperty('transform', `translateY(-${offsetY}px)`, 'important');
                document.body.style.setProperty('transform-origin', 'top left', 'important');
                document.body.style.setProperty('width', `${width}px`, 'important');
            }
            window.scrollTo(0, 0);
        }, { styleId, offsetY, width: viewport.width, height: viewport.height });
        await this.waitForLayoutSettle();
    }
    /** Restore DOM after {@link applyViewportClipForRaster}. */
    async restoreViewportClipForRaster() {
        await this.page.evaluate((styleId) => {
            document.getElementById(styleId)?.remove();
            if (document.body) {
                document.body.style.removeProperty('transform');
                document.body.style.removeProperty('transform-origin');
                document.body.style.removeProperty('width');
            }
        }, 'deckhtml-raster-clip-style');
        await this.waitForLayoutSettle();
    }
    /**
     * Pin the visible page to the export viewport so screenshots match slide layout.
     * Returns the CSS selector of the slide host used for capture.
     */
    async applyRasterExportFrame(viewport, slideSelector) {
        const styleId = 'deckhtml-raster-frame-style';
        const slideHostSelectors = [
            slideSelector,
            '[data-deckhtml-slide-index]',
            '.slide-canvas',
            '.slide-container',
            '.slide-wrap',
            '.slide',
            '[data-slide]',
            'section.slide',
        ].filter((value) => Boolean(value));
        const resolvedSelector = await this.page.evaluate(({ styleId, width, height, slideHostSelectors }) => {
            document.getElementById(styleId)?.remove();
            const style = document.createElement('style');
            style.id = styleId;
            style.textContent = `
          html, body {
            width: ${width}px !important;
            height: ${height}px !important;
            min-height: ${height}px !important;
            max-height: ${height}px !important;
            overflow: hidden !important;
            margin: 0 !important;
            padding: 0 !important;
          }
        `;
            document.head.appendChild(style);
            if (document.body) {
                document.body.style.setProperty('display', 'block', 'important');
                document.body.style.setProperty('width', `${width}px`, 'important');
                document.body.style.setProperty('height', `${height}px`, 'important');
                document.body.style.setProperty('overflow', 'hidden', 'important');
                document.body.style.setProperty('margin', '0', 'important');
                document.body.style.setProperty('padding', '0', 'important');
            }
            let matchedSelector = null;
            let slide = null;
            for (const candidate of slideHostSelectors) {
                slide = document.querySelector(candidate);
                if (slide) {
                    matchedSelector = candidate;
                    break;
                }
            }
            if (!slide) {
                slide = document.body?.firstElementChild ?? null;
            }
            if (slide instanceof HTMLElement) {
                const bg = window.getComputedStyle(slide).backgroundColor;
                if (document.body && bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent') {
                    document.body.style.setProperty('background-color', bg, 'important');
                }
                slide.style.setProperty('margin', '0', 'important');
                slide.style.setProperty('position', 'relative', 'important');
                slide.style.setProperty('top', '0', 'important');
                slide.style.setProperty('left', '0', 'important');
                slide.style.setProperty('width', `${width}px`, 'important');
                slide.style.setProperty('height', `${height}px`, 'important');
                slide.style.setProperty('box-shadow', 'none', 'important');
            }
            document.querySelectorAll('.reveal').forEach((node) => {
                if (!(node instanceof HTMLElement))
                    return;
                node.style.setProperty('opacity', '1', 'important');
                node.style.setProperty('visibility', 'visible', 'important');
                node.classList.add('show');
            });
            // Finish animations at end-state, then bake computed paint props before
            // clearing animation. Otherwise `animation: none` drops fill-mode:forwards
            // back to base styles (often opacity:0) and PNG captures go blank.
            const FROZEN_ATTR = 'data-deckhtml-raster-frozen';
            const bakeProps = [
                'opacity',
                'transform',
                'visibility',
                'filter',
                'clip-path',
                'translate',
                'rotate',
                'scale',
            ];
            try {
                const root = document.documentElement;
                const animations = typeof root.getAnimations === 'function'
                    ? root.getAnimations({ subtree: true })
                    : document.getAnimations();
                for (const anim of animations) {
                    try {
                        anim.finish();
                    }
                    catch {
                        try {
                            anim.cancel();
                        }
                        catch {
                            /* infinite / already settled */
                        }
                    }
                }
            }
            catch {
                /* getAnimations unavailable */
            }
            document.querySelectorAll('*').forEach((node) => {
                if (!(node instanceof HTMLElement || node instanceof SVGElement))
                    return;
                const cs = window.getComputedStyle(node);
                const hasAnim = Boolean(cs.animationName && cs.animationName !== 'none');
                const hasTransition = Boolean(cs.transitionDuration &&
                    cs.transitionDuration !== '0s' &&
                    cs.transitionProperty !== 'none');
                if (hasAnim || hasTransition) {
                    node.setAttribute(FROZEN_ATTR, 'bake');
                    for (const prop of bakeProps) {
                        const value = cs.getPropertyValue(prop);
                        if (value)
                            node.style.setProperty(prop, value, 'important');
                    }
                }
                else {
                    node.setAttribute(FROZEN_ATTR, 'anim-only');
                }
                node.style.setProperty('animation', 'none', 'important');
                node.style.setProperty('transition', 'none', 'important');
            });
            window.scrollTo(0, 0);
            return matchedSelector;
        }, {
            styleId,
            width: viewport.width,
            height: viewport.height,
            slideHostSelectors,
        });
        await this.waitForLayoutSettle();
        return resolvedSelector;
    }
    slideIndexSelector(slideIndex) {
        return `[${SLIDE_INDEX_ATTR}="${slideIndex}"]`;
    }
    /** Restore DOM after {@link applyRasterExportFrame}. */
    async restoreRasterExportFrame() {
        await this.page.evaluate((styleId) => {
            document.getElementById(styleId)?.remove();
            const FROZEN_ATTR = 'data-deckhtml-raster-frozen';
            const bakeProps = [
                'opacity',
                'transform',
                'visibility',
                'filter',
                'clip-path',
                'translate',
                'rotate',
                'scale',
            ];
            document.querySelectorAll(`[${FROZEN_ATTR}]`).forEach((node) => {
                if (!(node instanceof HTMLElement || node instanceof SVGElement))
                    return;
                const el = node;
                const mode = node.getAttribute(FROZEN_ATTR);
                el.style.removeProperty('animation');
                el.style.removeProperty('transition');
                if (mode === 'bake') {
                    for (const prop of bakeProps) {
                        el.style.removeProperty(prop);
                    }
                }
                node.removeAttribute(FROZEN_ATTR);
            });
            document.querySelectorAll('[data-deckhtml-slide-index], .slide-container, .slide-canvas, .slide-wrap, .slide, [data-slide]').forEach((node) => {
                if (!(node instanceof HTMLElement))
                    return;
                for (const prop of ['margin', 'position', 'top', 'left', 'width', 'height', 'box-shadow']) {
                    node.style.removeProperty(prop);
                }
            });
            if (document.body) {
                for (const prop of [
                    'display',
                    'width',
                    'height',
                    'overflow',
                    'margin',
                    'padding',
                    'background-color',
                ]) {
                    document.body.style.removeProperty(prop);
                }
            }
            if (document.documentElement) {
                for (const prop of ['width', 'height', 'overflow', 'margin', 'padding']) {
                    document.documentElement.style.removeProperty(prop);
                }
            }
        }, 'deckhtml-raster-frame-style');
        await this.waitForLayoutSettle();
    }
    /**
     * Inspect all visible elements in the page
     */
    async inspectElements(slideSelector, options) {
        const inputIsSvg = options?.inputIsSvg ?? false;
        // Single-page path: capture CSS animation declarations before inspection.
        // (Multi-slide paths capture per slide inside isolateOutsideSlideContainer.)
        await this.captureCssAnimations(slideSelector);
        // Guaranteed origin before measuring — scrollIntoView / focus may have moved it.
        await this.page.evaluate(() => {
            window.scrollTo(0, 0);
            document.documentElement.scrollTop = 0;
            document.documentElement.scrollLeft = 0;
            if (document.body) {
                document.body.scrollTop = 0;
                document.body.scrollLeft = 0;
            }
        });
        const elements = await this.page.evaluate(async ({ slideSelector, slideHeight, inputIsSvg, excludeSelector, slideIdAttribute, identityAttribute }) => {
            // Re-assert inside the measure world (defensive against late layout scroll).
            window.scrollTo(0, 0);
            // L1: wait for webfonts so line boxes match final typography.
            try {
                if (document.fonts?.ready)
                    await document.fonts.ready;
            }
            catch {
                /* ignore */
            }
            const result = [];
            const _debugInfo = [];
            const _excludedCount = { value: 0 };
            const _excludedSamples = [];
            const _identityWarnings = [];
            const _kindDiagnostics = [];
            const _seenElementIds = new Map();
            const _identityCache = new WeakMap();
            const _identityAttr = identityAttribute || 'data-element-id';
            // Counter for synthesized animation-group root ids (when the author did
            // not give the carrying element a data-element-id). Stamped as
            // data-dh-anim-gid so descendants can inherit via closest().
            let _animRootCounter = 0;
            /** Locale-aware uppercasing for `text-transform: uppercase`.
             *  CSS casing follows the element's language, and JS `toUpperCase()`
             *  does not: Turkish maps "i" to "İ" while the default maps it to "I".
             *  Re-applying the transform without the locale is why a kicker authored
             *  as "Tek mimari · iki yönelim" reached PPTX as "TEK MIMARI · IKI
             *  YÖNELIM" although Chromium rendered "TEK MİMARİ · İKİ YÖNELİM". */
            const documentLanguage = (el) => {
                const own = el && el.closest('[lang]')?.getAttribute('lang');
                return String(own || document.documentElement.lang || '').trim();
            };
            const localeUpperCase = (value, lang) => {
                const tag = String(lang || '').trim();
                if (!tag)
                    return value.toUpperCase();
                try {
                    return value.toLocaleUpperCase(tag);
                }
                catch {
                    return value.toUpperCase();
                }
            };
            /** Document-space box from a viewport rect (scroll-safe). */
            function docBox(rect) {
                const left = rect.left + window.scrollX;
                const top = rect.top + window.scrollY;
                const width = rect.width;
                const height = rect.height;
                return {
                    x: left,
                    y: top,
                    left,
                    top,
                    width,
                    height,
                    right: left + width,
                    bottom: top + height,
                    toJSON() {
                        return {
                            x: left,
                            y: top,
                            left,
                            top,
                            width,
                            height,
                            right: left + width,
                            bottom: top + height,
                        };
                    },
                };
            }
            function deterministicDomPath(element) {
                const parts = [];
                let cur = element;
                while (cur && cur !== document.documentElement) {
                    const parent = cur.parentElement;
                    if (!parent)
                        break;
                    const siblings = Array.from(parent.children).filter((child) => child.tagName === cur.tagName);
                    const index = Math.max(0, siblings.indexOf(cur));
                    parts.push(`${cur.tagName.toLowerCase()}-${index + 1}`);
                    cur = parent;
                }
                return parts.reverse().join('__') || element.tagName.toLowerCase();
            }
            /** Stable identity for every drawable, declared or synthesized. */
            function readElementIdentity(element) {
                if (!(element instanceof Element))
                    return undefined;
                const cached = _identityCache.get(element);
                if (cached)
                    return cached;
                const declared = (element.getAttribute(_identityAttr) || '').trim();
                const base = declared || `dh-auto__${deterministicDomPath(element)}`;
                const used = _seenElementIds.get(base) || 0;
                const id = used === 0 ? base : `${base}__duplicate-${used + 1}`;
                if (used > 0) {
                    _identityWarnings.push(`Duplicate element identity "${base}"; exported as unique identity "${id}".`);
                }
                _seenElementIds.set(base, used + 1);
                _identityCache.set(element, id);
                return id;
            }
            function readFragmentIdentity(element, fragment) {
                return `${readElementIdentity(element) || `dh-auto__${deterministicDomPath(element)}`}__${fragment}`;
            }
            /** Parse "600" | "600ms" | "0.6s" into milliseconds. */
            function parseAnimTimeMs(v) {
                if (!v)
                    return undefined;
                const m = String(v).trim().match(/^(-?\d+(?:\.\d+)?)(ms|s)?$/);
                if (!m)
                    return undefined;
                const n = parseFloat(m[1]);
                if (isNaN(n) || n < 0)
                    return undefined;
                return m[2] === 's' ? Math.round(n * 1000) : Math.round(n);
            }
            /**
             * Read raw animation capture from attributes on this element only
             * (no ancestor inheritance).
             */
            function readOwnAnimationRaw(element) {
                if (!(element instanceof Element))
                    return undefined;
                const raw = {};
                const effect = element.getAttribute('data-animation');
                if (effect && effect.trim()) {
                    raw.declaredEffect = effect.trim();
                    const dur = parseAnimTimeMs(element.getAttribute('data-animation-duration'));
                    if (dur !== undefined)
                        raw.declaredDurationMs = dur;
                    const delay = parseAnimTimeMs(element.getAttribute('data-animation-delay'));
                    if (delay !== undefined)
                        raw.declaredDelayMs = delay;
                    const trigger = element.getAttribute('data-animation-trigger');
                    if (trigger && trigger.trim())
                        raw.declaredTrigger = trigger.trim();
                }
                const cssKey = element.getAttribute('data-dh-anim-css');
                if (cssKey) {
                    raw.cssAnimationKey = cssKey;
                    const cssMap = window.__deckhtmlCssAnimations;
                    const cssRaw = cssMap && typeof cssMap === 'object' ? cssMap[cssKey] : undefined;
                    if (cssRaw)
                        raw.cssRaw = cssRaw;
                }
                const animeIdx = element.getAttribute('data-dh-anim-anime');
                if (animeIdx) {
                    const indices = animeIdx
                        .split(',')
                        .map((s) => parseInt(s, 10))
                        .filter((n) => !isNaN(n));
                    if (indices.length) {
                        raw.animeCallIndices = indices;
                        const animeCalls = window.__deckhtmlAnimeCalls;
                        if (Array.isArray(animeCalls)) {
                            const raws = indices
                                .map((i) => animeCalls[i])
                                .filter((c) => c && typeof c === 'object');
                            if (raws.length)
                                raw.animeRaws = raws;
                        }
                    }
                }
                return Object.keys(raw).length > 0 ? raw : undefined;
            }
            /**
             * Read raw animation capture for an element: explicit data-animation*
             * declaration, CSS capture key (data-dh-anim-css, stamped before styles
             * are frozen) and intercepted anime.js call indices (data-dh-anim-anime).
             * Normalized into ElementInfo.animations on the Node side.
             *
             * Layout-only group roots (type=container) are stamped with
             * data-dh-anim-gid but never emitted as ElementInfo. Descendants
             * therefore inherit the root's capture so the generator can still wrap
             * them into one <p:grpSp> and attach p:timing.
             */
            function readAnimationRaw(element) {
                if (!(element instanceof Element))
                    return undefined;
                const own = readOwnAnimationRaw(element);
                if (own)
                    return own;
                const owner = element.closest?.('[data-dh-anim-gid]');
                if (!owner || owner === element)
                    return undefined;
                if (!elementCarriesAnimation(owner))
                    return undefined;
                return readOwnAnimationRaw(owner);
            }
            /**
             * Resolve the animation group id for an element: the nearest ancestor
             * (including self) carrying a stamped data-dh-anim-gid. Group roots are
             * stamped in processElement so descendants inherit the same id, letting
             * the generator wrap all member shapes into one PPTX <p:grpSp> whose
             * entrance animation targets the group (matches HTML subtree animation).
             */
            function readAnimationGroupId(element) {
                if (!(element instanceof Element))
                    return undefined;
                const owner = element.closest?.('[data-dh-anim-gid]');
                if (!owner)
                    return undefined;
                const gid = owner.getAttribute('data-dh-anim-gid');
                return gid && gid.length > 0 ? gid : undefined;
            }
            /** True when element carries any animation declaration (declared/css/animejs). */
            function elementCarriesAnimation(element) {
                if (!(element instanceof Element))
                    return false;
                return (element.hasAttribute('data-animation') ||
                    element.hasAttribute('data-dh-anim-css') ||
                    element.hasAttribute('data-dh-anim-anime'));
            }
            /** Stamp a data-dh-anim-gid on a group root so descendants can inherit it. */
            function stampAnimationGroupId(element) {
                if (!(element instanceof Element))
                    return undefined;
                if (element.hasAttribute('data-dh-anim-gid')) {
                    return element.getAttribute('data-dh-anim-gid') || undefined;
                }
                if (!elementCarriesAnimation(element))
                    return undefined;
                const gid = readElementIdentity(element) ?? `dh-animroot-${++_animRootCounter}`;
                element.setAttribute('data-dh-anim-gid', gid);
                return gid;
            }
            /**
             * Check if element is a Font Awesome icon (helper for visibility check)
             */
            function isFAIcon(element) {
                if (!(element instanceof HTMLElement))
                    return false;
                const classList = element.classList;
                return (element.tagName.toLowerCase() === 'i' &&
                    (classList.contains('fa') ||
                        classList.contains('fas') ||
                        classList.contains('far') ||
                        classList.contains('fab') ||
                        classList.contains('fal') ||
                        classList.contains('fad') ||
                        classList.contains('fa-solid') ||
                        classList.contains('fa-regular') ||
                        classList.contains('fa-brands')));
            }
            function isSvgNamespace(el) {
                return el.namespaceURI === 'http://www.w3.org/2000/svg';
            }
            /** CSS opacity is not inherited; multiply ancestor opacities for painted result. */
            function getEffectiveOpacity(element) {
                let effective = parseFloat(window.getComputedStyle(element).opacity) || 1;
                for (let parent = element.parentElement; parent && parent !== document.body; parent = parent.parentElement) {
                    effective *= parseFloat(window.getComputedStyle(parent).opacity) || 1;
                }
                return effective;
            }
            /** Mark element for isolated Playwright screenshot fallback (complex CSS / SVG). */
            function assignScreenshotFallback(host, info, reason) {
                const screenshotId = `screenshot-${Math.random().toString(36).slice(2, 10)}`;
                host.setAttribute('data-screenshot', screenshotId);
                info.needsScreenshot = true;
                info.screenshotSelector = `[data-screenshot="${screenshotId}"]`;
                info.rasterMethod = 'screenshot';
                info.rasterReason = reason;
            }
            function isTransparentCssColor(c) {
                if (!c)
                    return true;
                const t = c.trim().toLowerCase();
                return t === 'transparent' || t === 'rgba(0, 0, 0, 0)' || t === 'rgba(0,0,0,0)';
            }
            function nearestOverflowClipRect(element) {
                let clip;
                for (let p = element.parentElement; p && p !== document.body; p = p.parentElement) {
                    const st = window.getComputedStyle(p);
                    const ov = `${st.overflow} ${st.overflowX} ${st.overflowY}`;
                    if (ov.includes('hidden') || ov.includes('clip')) {
                        const r = p.getBoundingClientRect();
                        const next = { x: r.left, y: r.top, width: r.width, height: r.height };
                        if (!clip)
                            clip = next;
                        else {
                            const x = Math.max(clip.x, next.x);
                            const y = Math.max(clip.y, next.y);
                            const x2 = Math.min(clip.x + clip.width, next.x + next.width);
                            const y2 = Math.min(clip.y + clip.height, next.y + next.height);
                            clip = { x, y, width: Math.max(0, x2 - x), height: Math.max(0, y2 - y) };
                        }
                    }
                    const cls = p.className || '';
                    if (typeof cls === 'string' && /\bslide\b/.test(cls))
                        break;
                    if (p.tagName.toLowerCase() === 'section')
                        break;
                }
                return clip && clip.width > 1 && clip.height > 1 ? clip : undefined;
            }
            function canvasInkDelta(ctx, before) {
                const after = ctx.getImageData(0, 0, ctx.canvas.width, ctx.canvas.height);
                let diff = 0;
                const a = after.data;
                const b = before.data;
                for (let i = 0; i < a.length; i += 4) {
                    if (Math.abs(a[i] - b[i]) +
                        Math.abs(a[i + 1] - b[i + 1]) +
                        Math.abs(a[i + 2] - b[i + 2]) +
                        Math.abs(a[i + 3] - b[i + 3]) >
                        18) {
                        diff += 1;
                    }
                }
                return diff;
            }
            function isCssBorderTriangle(style, rect) {
                if (rect.width > 48 || rect.height > 48)
                    return false;
                const sides = [
                    {
                        w: parseFloat(style.borderTopWidth) || 0,
                        c: style.borderTopColor,
                        t: style.borderTopStyle,
                    },
                    {
                        w: parseFloat(style.borderRightWidth) || 0,
                        c: style.borderRightColor,
                        t: style.borderRightStyle,
                    },
                    {
                        w: parseFloat(style.borderBottomWidth) || 0,
                        c: style.borderBottomColor,
                        t: style.borderBottomStyle,
                    },
                    {
                        w: parseFloat(style.borderLeftWidth) || 0,
                        c: style.borderLeftColor,
                        t: style.borderLeftStyle,
                    },
                ];
                const painted = sides.filter((s) => s.w >= 4 && s.t !== 'none' && !isTransparentCssColor(s.c));
                const ghost = sides.filter((s) => s.w >= 4 && s.t !== 'none' && isTransparentCssColor(s.c));
                return painted.length === 1 && ghost.length >= 2;
            }
            /** Bake explicit pixel width/height so embedded SVG is not sized from width="100%". */
            function bakeSvgCloneDimensions(clone, original, rect) {
                const svgRoot = original;
                const vb = svgRoot.viewBox?.baseVal;
                if (vb && vb.width > 0 && vb.height > 0) {
                    clone.setAttribute('viewBox', `${vb.x} ${vb.y} ${vb.width} ${vb.height}`);
                    clone.setAttribute('width', String(vb.width));
                    clone.setAttribute('height', String(vb.height));
                }
                else {
                    const w = parseFloat(original.getAttribute('width') || '') || rect.width;
                    const h = parseFloat(original.getAttribute('height') || '') || rect.height;
                    if (w > 0 && h > 0) {
                        clone.setAttribute('width', String(w));
                        clone.setAttribute('height', String(h));
                    }
                }
                clone.removeAttribute('style');
            }
            /** Serialize SVG as inline SVG image (data URL). */
            function emitSvgAsImage(svgEl, rect) {
                try {
                    const isStandaloneRoot = inputIsSvg && svgEl === getStandaloneSvgRoot();
                    const styles = getComputedStyles(svgEl);
                    // Opacity is baked into serialized SVG / PNG — avoid double-fading in convertImageElement.
                    styles.opacity = 1;
                    const layout = {
                        x: isStandaloneRoot ? 0 : rect.left,
                        y: isStandaloneRoot ? 0 : rect.top,
                        width: isStandaloneRoot ? window.innerWidth : rect.width,
                        height: isStandaloneRoot ? window.innerHeight : rect.height,
                    };
                    // Mermaid and similar libs render labels in <foreignObject> HTML. PowerPoint's SVG
                    // engine does not faithfully render foreignObject (often clips top labels) and
                    // width="100%" collapses intrinsic size — rasterize via Playwright instead.
                    if (svgEl.querySelector('foreignObject')) {
                        const info = {
                            type: 'image',
                            tag: 'svg',
                            elementId: readElementIdentity(svgEl),
                            animationRaw: readAnimationRaw(svgEl),
                            animationGroupId: readAnimationGroupId(svgEl),
                            ...layout,
                            styles,
                        };
                        assignScreenshotFallback(svgEl, info, 'svg-flowchart');
                        result.push(info);
                        markDomAsPptxMapped(svgEl, true);
                        return;
                    }
                    const clone = svgEl.cloneNode(true);
                    if (!clone.getAttribute('xmlns')) {
                        clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
                    }
                    bakeSvgCloneDimensions(clone, svgEl, rect);
                    // Clone loses page CSS — bake currentColor / var() / inherited stroke into attributes.
                    const computedColor = window.getComputedStyle(svgEl).color;
                    const fallbackColorHex = cssColorToHex(computedColor) || '000000';
                    applyStylesToSvgClone(clone, svgEl, fallbackColorHex);
                    const effectiveOpacity = getEffectiveOpacity(svgEl);
                    if (effectiveOpacity < 1 - 1e-6) {
                        clone.setAttribute('opacity', String(effectiveOpacity));
                    }
                    else {
                        clone.removeAttribute('opacity');
                    }
                    const svgString = new XMLSerializer().serializeToString(clone);
                    const encoded = btoa(unescape(encodeURIComponent(svgString)));
                    result.push({
                        type: 'image',
                        tag: 'svg',
                        ...layout,
                        styles,
                        src: `data:image/svg+xml;base64,${encoded}`,
                        rasterMethod: 'svg-serialize',
                        rasterReason: 'svg-diagram',
                        animationGroupId: readAnimationGroupId(svgEl),
                    });
                    markDomAsPptxMapped(svgEl);
                }
                catch (e) {
                    console.warn('Failed to serialize SVG as image:', e);
                }
            }
            const SVG_NON_RENDER_TAGS = new Set([
                'defs',
                'symbol',
                'clippath',
                'mask',
                'pattern',
                'lineargradient',
                'radialgradient',
                'stop',
                'filter',
                'metadata',
                'title',
                'desc',
                'style',
                'fedropshadow',
                'fegaussianblur',
                'fecomposite',
                'femerge',
                'femergenode',
                'feoffset',
            ]);
            function isSvgNonRenderElement(el) {
                if (!el || !el.tagName)
                    return true;
                const tag = el.tagName.toLowerCase();
                if (SVG_NON_RENDER_TAGS.has(tag))
                    return true;
                if (el.closest('defs'))
                    return true;
                return false;
            }
            function isSvgPaintVisible(style) {
                const fill = style.fill;
                const sw = parseFloat(style.getPropertyValue('stroke-width')) || 0;
                const stroke = style.stroke;
                const fillOk = !!fill &&
                    fill !== 'none' &&
                    fill !== 'transparent' &&
                    fill !== 'rgba(0, 0, 0, 0)' &&
                    fill !== 'rgba(0,0,0,0)';
                const strokeOk = sw > 0 && !!stroke && stroke !== 'none' && stroke !== 'transparent';
                return fillOk || strokeOk;
            }
            function getStandaloneSvgRoot() {
                const docEl = document.documentElement;
                if (docEl instanceof SVGSVGElement)
                    return docEl;
                const bodySvg = document.querySelector('body > svg');
                return bodySvg instanceof SVGSVGElement ? bodySvg : null;
            }
            /** Transform SVG user-space coordinates to viewport (screen) px. */
            function svgUserToScreen(el, ux, uy) {
                if (!Number.isFinite(ux) || !Number.isFinite(uy)) {
                    return { x: Number.isFinite(ux) ? ux : 0, y: Number.isFinite(uy) ? uy : 0 };
                }
                const svg = el.ownerSVGElement;
                if (!svg)
                    return { x: ux, y: uy };
                const pt = svg.createSVGPoint();
                pt.x = ux;
                pt.y = uy;
                const ctm = el.getScreenCTM();
                if (!ctm)
                    return { x: ux, y: uy };
                const sp = pt.matrixTransform(ctm);
                return { x: sp.x, y: sp.y };
            }
            function extractSvgLineEndpoints(lineEl) {
                const x1 = parseFloat(lineEl.getAttribute('x1') || '0');
                const y1 = parseFloat(lineEl.getAttribute('y1') || '0');
                const x2 = parseFloat(lineEl.getAttribute('x2') || '0');
                const y2 = parseFloat(lineEl.getAttribute('y2') || '0');
                const p1 = svgUserToScreen(lineEl, x1, y1);
                const p2 = svgUserToScreen(lineEl, x2, y2);
                return { x1: p1.x, y1: p1.y, x2: p2.x, y2: p2.y };
            }
            function parseSvgPointsAttribute(pointsAttr) {
                const nums = pointsAttr
                    .trim()
                    .split(/[\s,]+/)
                    .map((s) => parseFloat(s))
                    .filter((n) => !Number.isNaN(n));
                const pts = [];
                for (let i = 0; i + 1 < nums.length; i += 2) {
                    pts.push({ x: nums[i], y: nums[i + 1] });
                }
                return pts;
            }
            function sampleSvgPathScreenPoints(pathEl, maxPoints = 96) {
                const len = pathEl.getTotalLength();
                if (!Number.isFinite(len) || len <= 0)
                    return [];
                const steps = Math.min(maxPoints, Math.max(8, Math.ceil(len / 1.5)));
                const pts = [];
                for (let i = 0; i <= steps; i++) {
                    const at = (len * i) / steps;
                    const p = pathEl.getPointAtLength(at);
                    pts.push(svgUserToScreen(pathEl, p.x, p.y));
                }
                return pts;
            }
            function isSvgFillVisible(style) {
                const fill = style.fill;
                return (!!fill &&
                    fill !== 'none' &&
                    fill !== 'transparent' &&
                    fill !== 'rgba(0, 0, 0, 0)' &&
                    fill !== 'rgba(0,0,0,0)');
            }
            /** Open stroke-only path that is geometrically a straight segment → line endpoints. */
            function extractStraightPathLineEndpoints(pathEl) {
                const d = (pathEl.getAttribute('d') || '').trim();
                if (!d || /[zZ]/.test(d))
                    return null;
                if ((d.match(/[Mm]/g) || []).length > 1)
                    return null;
                const style = window.getComputedStyle(pathEl);
                if (isSvgFillVisible(style))
                    return null;
                const len = pathEl.getTotalLength();
                if (!Number.isFinite(len) || len <= 0)
                    return null;
                const p0 = pathEl.getPointAtLength(0);
                const pEnd = pathEl.getPointAtLength(len);
                const dx = pEnd.x - p0.x;
                const dy = pEnd.y - p0.y;
                if (Math.hypot(dx, dy) < 0.5)
                    return null;
                const cross = (px, py) => (px - p0.x) * dy - (py - p0.y) * dx;
                for (let i = 1; i <= 8; i++) {
                    const pt = pathEl.getPointAtLength((len * i) / 9);
                    if (Math.abs(cross(pt.x, pt.y)) > 0.75)
                        return null;
                }
                const s0 = svgUserToScreen(pathEl, p0.x, p0.y);
                const s1 = svgUserToScreen(pathEl, pEnd.x, pEnd.y);
                return { x1: s0.x, y1: s0.y, x2: s1.x, y2: s1.y };
            }
            function resolveSvgMarkerAttr(value) {
                if (!value || value === 'none')
                    return false;
                return /url\s*\(/i.test(value);
            }
            function getSvgLineEndpointAndAngle(el, atStart) {
                const tag = el.tagName.toLowerCase();
                if (tag === 'line') {
                    const lineEl = el;
                    const x1 = parseFloat(lineEl.getAttribute('x1') || '0');
                    const y1 = parseFloat(lineEl.getAttribute('y1') || '0');
                    const x2 = parseFloat(lineEl.getAttribute('x2') || '0');
                    const y2 = parseFloat(lineEl.getAttribute('y2') || '0');
                    if (atStart) {
                        return { x: x1, y: y1, angle: Math.atan2(y1 - y2, x1 - x2) };
                    }
                    return { x: x2, y: y2, angle: Math.atan2(y2 - y1, x2 - x1) };
                }
                if (tag === 'path') {
                    const pathEl = el;
                    const len = pathEl.getTotalLength();
                    if (!Number.isFinite(len) || len <= 0)
                        return null;
                    const eps = Math.min(1, len * 0.05);
                    if (atStart) {
                        const p0 = pathEl.getPointAtLength(0);
                        const p1 = pathEl.getPointAtLength(Math.min(len, eps));
                        return { x: p0.x, y: p0.y, angle: Math.atan2(p1.y - p0.y, p1.x - p0.x) };
                    }
                    const pEnd = pathEl.getPointAtLength(len);
                    const pBefore = pathEl.getPointAtLength(Math.max(0, len - eps));
                    return {
                        x: pEnd.x,
                        y: pEnd.y,
                        angle: Math.atan2(pEnd.y - pBefore.y, pEnd.x - pBefore.x),
                    };
                }
                return null;
            }
            function resolveMarkerOrientAngle(orient, pathAngle, atStart) {
                const o = (orient || 'auto').trim();
                // Marker path tip points +X. At marker-end, align with path tangent (outward);
                // at marker-start, flip 180° (outward away from the segment).
                // SVG2: auto-start-reverse at marker-end matches auto; at marker-start it differs,
                // but our previous end handling (+π) pointed tips into the line — flip to match browser.
                if (o === 'auto' || o === 'auto-start-reverse') {
                    return atStart ? pathAngle + Math.PI : pathAngle;
                }
                const deg = parseFloat(o);
                if (!Number.isNaN(deg))
                    return (deg * Math.PI) / 180;
                return atStart ? pathAngle + Math.PI : pathAngle;
            }
            function parseMarkerViewBox(marker) {
                const vb = marker.getAttribute('viewBox');
                if (vb) {
                    const parts = vb.trim().split(/[\s,]+/).map(parseFloat);
                    if (parts.length >= 4 && parts.every((n) => !Number.isNaN(n))) {
                        return { minX: parts[0], minY: parts[1], w: parts[2], h: parts[3] };
                    }
                }
                return { minX: 0, minY: 0, w: 3, h: 3 };
            }
            function getMarkerShapePoints(marker) {
                const child = marker.querySelector('path, polygon, polyline');
                if (!child)
                    return [];
                const tag = child.tagName.toLowerCase();
                if (tag === 'polygon' || tag === 'polyline') {
                    return parseSvgPointsAttribute(child.getAttribute('points') || '');
                }
                if (tag === 'path') {
                    const cmds = parseSvgPathPolylineCommands(child.getAttribute('d') || '');
                    if (!cmds)
                        return [];
                    return cmds
                        .filter((c) => c.type !== 'Z')
                        .map((c) => ({ x: c.x, y: c.y }));
                }
                return [];
            }
            function decomposeSvgMarkerAt(el, markerUrl, atStart) {
                const idMatch = markerUrl.match(/url\(#([^)]+)\)/);
                if (!idMatch)
                    return null;
                const marker = el.ownerSVGElement?.getElementById(idMatch[1]);
                if (!marker || marker.tagName.toLowerCase() !== 'marker')
                    return null;
                const shapeChild = marker.querySelector('path, polygon, polyline');
                if (!shapeChild)
                    return null;
                const endpoint = getSvgLineEndpointAndAngle(el, atStart);
                if (!endpoint)
                    return null;
                const localPts = getMarkerShapePoints(marker);
                if (localPts.length < 3)
                    return null;
                const vb = parseMarkerViewBox(marker);
                const refX = parseFloat(marker.getAttribute('refX') || String(vb.w / 2));
                const refY = parseFloat(marker.getAttribute('refY') || String(vb.h / 2));
                const markerW = parseFloat(marker.getAttribute('markerWidth') || '3');
                const markerH = parseFloat(marker.getAttribute('markerHeight') || '3');
                const sx = vb.w > 0 ? markerW / vb.w : 1;
                const sy = vb.h > 0 ? markerH / vb.h : 1;
                const anchorX = (refX - vb.minX) * sx;
                const anchorY = (refY - vb.minY) * sy;
                const angle = resolveMarkerOrientAngle(marker.getAttribute('orient') || 'auto', endpoint.angle, atStart);
                const cos = Math.cos(angle);
                const sin = Math.sin(angle);
                const screenAnchor = svgUserToScreen(el, endpoint.x, endpoint.y);
                const shapeStyle = window.getComputedStyle(shapeChild);
                let fillColor = shapeStyle.fill;
                if (!fillColor || fillColor === 'none' || fillColor === 'transparent') {
                    const attrFill = shapeChild.getAttribute('fill');
                    if (attrFill && attrFill !== 'none')
                        fillColor = attrFill;
                    else
                        fillColor = '#000000';
                }
                let opacity = parseFloat(shapeStyle.opacity || '1');
                const fillOpacityRaw = shapeStyle.getPropertyValue('fill-opacity');
                if (fillOpacityRaw) {
                    const fillOpacity = parseFloat(fillOpacityRaw);
                    if (!Number.isNaN(fillOpacity))
                        opacity *= fillOpacity;
                }
                const screenPts = localPts.map((p) => {
                    const lx = (p.x - vb.minX) * sx - anchorX;
                    const ly = (p.y - vb.minY) * sy - anchorY;
                    const rx = lx * cos - ly * sin;
                    const ry = lx * sin + ly * cos;
                    return { x: screenAnchor.x + rx, y: screenAnchor.y + ry };
                });
                const xs = screenPts.map((p) => p.x);
                const ys = screenPts.map((p) => p.y);
                const minX = Math.min(...xs);
                const minY = Math.min(...ys);
                const maxX = Math.max(...xs);
                const maxY = Math.max(...ys);
                const width = Math.max(maxX - minX, 0.5);
                const height = Math.max(maxY - minY, 0.5);
                return {
                    x: minX,
                    y: minY,
                    width,
                    height,
                    atStart,
                    clipPathPolygonPx: screenPts.map((p) => ({ x: p.x - minX, y: p.y - minY })),
                    styles: {
                        backgroundColor: fillColor,
                        opacity,
                    },
                };
            }
            function extractSvgMarkers(element, info) {
                const cs = window.getComputedStyle(element);
                const markerStart = element.getAttribute('marker-start') ||
                    element.getAttribute('markerStart') ||
                    cs.getPropertyValue('marker-start') ||
                    cs.markerStart ||
                    '';
                const markerEnd = element.getAttribute('marker-end') ||
                    element.getAttribute('markerEnd') ||
                    cs.getPropertyValue('marker-end') ||
                    cs.markerEnd ||
                    '';
                if (resolveSvgMarkerAttr(markerStart)) {
                    info.svgMarkerStart = true;
                    const startShape = decomposeSvgMarkerAt(element, markerStart, true);
                    if (startShape) {
                        info.svgMarkerShapes = info.svgMarkerShapes || [];
                        info.svgMarkerShapes.push(startShape);
                    }
                }
                if (resolveSvgMarkerAttr(markerEnd)) {
                    info.svgMarkerEnd = true;
                    const endShape = decomposeSvgMarkerAt(element, markerEnd, false);
                    if (endShape) {
                        info.svgMarkerShapes = info.svgMarkerShapes || [];
                        info.svgMarkerShapes.push(endShape);
                    }
                }
            }
            function parseSvgPathPolylineCommands(d) {
                const cmds = parseSvgPathCommands(d);
                if (!cmds)
                    return null;
                const hasNonLine = cmds.some((c) => c.type === 'C' || c.type === 'A');
                if (hasNonLine)
                    return null;
                return cmds;
            }
            function parseSvgPathCommands(d) {
                const tokens = [];
                const re = /([MmLlHhVvCcSsQqTtAaZz])|([-+]?[\d]*\.?[\d]+(?:[eE][-+]?\d+)?)/g;
                let m;
                while ((m = re.exec(d)) !== null) {
                    if (m[1])
                        tokens.push(m[1]);
                    else if (m[2])
                        tokens.push(m[2]);
                }
                if (tokens.length === 0)
                    return null;
                let x = 0;
                let y = 0;
                let startX = 0;
                let startY = 0;
                let cmd = '';
                let i = 0;
                let lastCtrlX = x;
                let lastCtrlY = y;
                let lastCmd = '';
                const commands = [];
                const readNum = () => parseFloat(tokens[i++]);
                // Arc large/sweep flags are single 0|1 digits and may be glued together or to
                // the next coordinate (e.g. "00-5.356", "019.288"). readNum() mis-parses these.
                let arcTail = '';
                const readArcFlag = () => {
                    if (arcTail.length > 0) {
                        const ch = arcTail[0];
                        arcTail = arcTail.slice(1);
                        return ch === '1';
                    }
                    const token = tokens[i++];
                    if (!token)
                        return false;
                    const ch = token[0];
                    if (ch !== '0' && ch !== '1') {
                        arcTail = token;
                        return false;
                    }
                    arcTail = token.slice(1);
                    return ch === '1';
                };
                const readArcCoord = () => {
                    if (arcTail.length > 0) {
                        const num = parseFloat(arcTail);
                        arcTail = '';
                        return num;
                    }
                    return readNum();
                };
                const pushM = (px, py) => {
                    x = px;
                    y = py;
                    commands.push({ type: 'M', x, y });
                };
                const pushL = (px, py) => {
                    x = px;
                    y = py;
                    commands.push({ type: 'L', x, y });
                };
                const pushC = (x1, y1, x2, y2, px, py) => {
                    commands.push({ type: 'C', x1, y1, x2, y2, x: px, y: py });
                    lastCtrlX = x2;
                    lastCtrlY = y2;
                    x = px;
                    y = py;
                };
                const quadToCubic = (qx, qy, px, py) => {
                    const c1x = x + (2 / 3) * (qx - x);
                    const c1y = y + (2 / 3) * (qy - y);
                    const c2x = px + (2 / 3) * (qx - px);
                    const c2y = py + (2 / 3) * (qy - py);
                    pushC(c1x, c1y, c2x, c2y, px, py);
                };
                const reflectCtrl = () => ({
                    x: 2 * x - lastCtrlX,
                    y: 2 * y - lastCtrlY,
                });
                const arcAngle = (ux, uy, vx, vy) => {
                    const dot = ux * vx + uy * vy;
                    const det = ux * vy - uy * vx;
                    return Math.atan2(det, dot);
                };
                const arcToCubics = (x0, y0, rx, ry, xAxisRotationDeg, largeArc, sweep, x1, y1) => {
                    if (rx === 0 || ry === 0) {
                        return [{ x1: x0, y1: y0, x2: x1, y2: y1, x: x1, y: y1 }];
                    }
                    const phi = (xAxisRotationDeg * Math.PI) / 180;
                    const sinPhi = Math.sin(phi);
                    const cosPhi = Math.cos(phi);
                    const dx = (x0 - x1) / 2;
                    const dy = (y0 - y1) / 2;
                    const x1p = cosPhi * dx + sinPhi * dy;
                    const y1p = -sinPhi * dx + cosPhi * dy;
                    let rxAbs = Math.abs(rx);
                    let ryAbs = Math.abs(ry);
                    const lambda = (x1p * x1p) / (rxAbs * rxAbs) + (y1p * y1p) / (ryAbs * ryAbs);
                    if (lambda > 1) {
                        const s = Math.sqrt(lambda);
                        rxAbs *= s;
                        ryAbs *= s;
                    }
                    const rxSq = rxAbs * rxAbs;
                    const rySq = ryAbs * ryAbs;
                    const sign = largeArc === sweep ? -1 : 1;
                    const numer = rxSq * rySq - rxSq * y1p * y1p - rySq * x1p * x1p;
                    const denom = rxSq * y1p * y1p + rySq * x1p * x1p;
                    const coef = denom === 0 ? 0 : sign * Math.sqrt(Math.max(0, numer / denom));
                    const cxp = coef * ((rxAbs * y1p) / ryAbs);
                    const cyp = coef * (-(ryAbs * x1p) / rxAbs);
                    const cx = cosPhi * cxp - sinPhi * cyp + (x0 + x1) / 2;
                    const cy = sinPhi * cxp + cosPhi * cyp + (y0 + y1) / 2;
                    const v1x = (x1p - cxp) / rxAbs;
                    const v1y = (y1p - cyp) / ryAbs;
                    const v2x = (-x1p - cxp) / rxAbs;
                    const v2y = (-y1p - cyp) / ryAbs;
                    let theta1 = arcAngle(1, 0, v1x, v1y);
                    let deltaTheta = arcAngle(v1x, v1y, v2x, v2y);
                    if (!sweep && deltaTheta > 0)
                        deltaTheta -= 2 * Math.PI;
                    if (sweep && deltaTheta < 0)
                        deltaTheta += 2 * Math.PI;
                    const segments = Math.max(1, Math.ceil(Math.abs(deltaTheta) / (Math.PI / 2)));
                    const curves = [];
                    for (let seg = 0; seg < segments; seg++) {
                        const t1 = theta1 + (deltaTheta * seg) / segments;
                        const t2 = theta1 + (deltaTheta * (seg + 1)) / segments;
                        const alpha = (Math.sin(t2 - t1) * (Math.sqrt(4 + 3 * Math.tan((t2 - t1) / 2) ** 2) - 1)) / 3;
                        const cosT1 = Math.cos(t1);
                        const sinT1 = Math.sin(t1);
                        const cosT2 = Math.cos(t2);
                        const sinT2 = Math.sin(t2);
                        const ex = cx + rxAbs * cosT2 * cosPhi - ryAbs * sinT2 * sinPhi;
                        const ey = cy + rxAbs * cosT2 * sinPhi + ryAbs * sinT2 * cosPhi;
                        const c1x = cx +
                            rxAbs * cosT1 * cosPhi -
                            ryAbs * sinT1 * sinPhi -
                            alpha * (rxAbs * sinT1 * cosPhi + ryAbs * cosT1 * sinPhi);
                        const c1y = cy +
                            rxAbs * cosT1 * sinPhi +
                            ryAbs * sinT1 * cosPhi +
                            alpha * (rxAbs * sinT1 * sinPhi - ryAbs * cosT1 * cosPhi);
                        const c2x = cx +
                            rxAbs * cosT2 * cosPhi -
                            ryAbs * sinT2 * sinPhi +
                            alpha * (rxAbs * sinT2 * cosPhi + ryAbs * cosT2 * sinPhi);
                        const c2y = cy +
                            rxAbs * cosT2 * sinPhi +
                            ryAbs * sinT2 * cosPhi -
                            alpha * (rxAbs * sinT2 * sinPhi - ryAbs * cosT2 * cosPhi);
                        curves.push({ x1: c1x, y1: c1y, x2: c2x, y2: c2y, x: ex, y: ey });
                    }
                    return curves;
                };
                while (i < tokens.length) {
                    const t = tokens[i];
                    if (/^[A-Za-z]$/.test(t)) {
                        cmd = t;
                        i++;
                    }
                    switch (cmd) {
                        case 'M':
                            pushM(readNum(), readNum());
                            startX = x;
                            startY = y;
                            lastCtrlX = x;
                            lastCtrlY = y;
                            lastCmd = 'M';
                            cmd = 'L';
                            break;
                        case 'm':
                            pushM(x + readNum(), y + readNum());
                            startX = x;
                            startY = y;
                            lastCtrlX = x;
                            lastCtrlY = y;
                            lastCmd = 'm';
                            cmd = 'l';
                            break;
                        case 'L':
                            pushL(readNum(), readNum());
                            lastCmd = 'L';
                            break;
                        case 'l':
                            pushL(x + readNum(), y + readNum());
                            lastCmd = 'l';
                            break;
                        case 'H':
                            pushL(readNum(), y);
                            lastCmd = 'H';
                            break;
                        case 'h':
                            pushL(x + readNum(), y);
                            lastCmd = 'h';
                            break;
                        case 'V':
                            pushL(x, readNum());
                            lastCmd = 'V';
                            break;
                        case 'v':
                            pushL(x, y + readNum());
                            lastCmd = 'v';
                            break;
                        case 'C': {
                            const x1 = readNum();
                            const y1 = readNum();
                            const x2 = readNum();
                            const y2 = readNum();
                            const px = readNum();
                            const py = readNum();
                            pushC(x1, y1, x2, y2, px, py);
                            lastCmd = 'C';
                            break;
                        }
                        case 'c': {
                            const x1 = x + readNum();
                            const y1 = y + readNum();
                            const x2 = x + readNum();
                            const y2 = y + readNum();
                            const px = x + readNum();
                            const py = y + readNum();
                            pushC(x1, y1, x2, y2, px, py);
                            lastCmd = 'c';
                            break;
                        }
                        case 'S': {
                            const ref = lastCmd === 'C' || lastCmd === 'c' || lastCmd === 'S' || lastCmd === 's'
                                ? reflectCtrl()
                                : { x, y };
                            const x2 = readNum();
                            const y2 = readNum();
                            const px = readNum();
                            const py = readNum();
                            pushC(ref.x, ref.y, x2, y2, px, py);
                            lastCmd = 'S';
                            break;
                        }
                        case 's': {
                            const ref = lastCmd === 'C' || lastCmd === 'c' || lastCmd === 'S' || lastCmd === 's'
                                ? reflectCtrl()
                                : { x, y };
                            const x2 = x + readNum();
                            const y2 = y + readNum();
                            const px = x + readNum();
                            const py = y + readNum();
                            pushC(ref.x, ref.y, x2, y2, px, py);
                            lastCmd = 's';
                            break;
                        }
                        case 'Q': {
                            const qx = readNum();
                            const qy = readNum();
                            const px = readNum();
                            const py = readNum();
                            quadToCubic(qx, qy, px, py);
                            lastCtrlX = qx;
                            lastCtrlY = qy;
                            lastCmd = 'Q';
                            break;
                        }
                        case 'q': {
                            const qx = x + readNum();
                            const qy = y + readNum();
                            const px = x + readNum();
                            const py = y + readNum();
                            quadToCubic(qx, qy, px, py);
                            lastCtrlX = qx;
                            lastCtrlY = qy;
                            lastCmd = 'q';
                            break;
                        }
                        case 'T': {
                            const ref = lastCmd === 'Q' || lastCmd === 'q' || lastCmd === 'T' || lastCmd === 't'
                                ? reflectCtrl()
                                : { x, y };
                            const px = readNum();
                            const py = readNum();
                            quadToCubic(ref.x, ref.y, px, py);
                            lastCtrlX = ref.x;
                            lastCtrlY = ref.y;
                            lastCmd = 'T';
                            break;
                        }
                        case 't': {
                            const ref = lastCmd === 'Q' || lastCmd === 'q' || lastCmd === 'T' || lastCmd === 't'
                                ? reflectCtrl()
                                : { x, y };
                            const px = x + readNum();
                            const py = y + readNum();
                            quadToCubic(ref.x, ref.y, px, py);
                            lastCtrlX = ref.x;
                            lastCtrlY = ref.y;
                            lastCmd = 't';
                            break;
                        }
                        case 'A': {
                            arcTail = '';
                            const rx = readNum();
                            const ry = readNum();
                            const rot = readNum();
                            const large = readArcFlag();
                            const sweep = readArcFlag();
                            const px = readArcCoord();
                            const py = readArcCoord();
                            commands.push({ type: 'A', rx, ry, rot, large, sweep, x: px, y: py });
                            x = px;
                            y = py;
                            lastCmd = 'A';
                            break;
                        }
                        case 'a': {
                            arcTail = '';
                            const rx = readNum();
                            const ry = readNum();
                            const rot = readNum();
                            const large = readArcFlag();
                            const sweep = readArcFlag();
                            const px = x + readArcCoord();
                            const py = y + readArcCoord();
                            commands.push({ type: 'A', rx, ry, rot, large, sweep, x: px, y: py });
                            x = px;
                            y = py;
                            lastCmd = 'a';
                            break;
                        }
                        case 'Z':
                        case 'z':
                            commands.push({ type: 'Z' });
                            x = startX;
                            y = startY;
                            lastCmd = cmd;
                            break;
                        default:
                            return null;
                    }
                }
                if (commands.length < 2)
                    return null;
                const coordsFinite = commands.every((c) => {
                    if (c.type === 'Z')
                        return true;
                    if (c.type === 'M' || c.type === 'L') {
                        return Number.isFinite(c.x) && Number.isFinite(c.y);
                    }
                    if (c.type === 'C') {
                        return [c.x1, c.y1, c.x2, c.y2, c.x, c.y].every(Number.isFinite);
                    }
                    if (c.type === 'A') {
                        return [c.rx, c.ry, c.rot, c.x, c.y].every(Number.isFinite);
                    }
                    return true;
                });
                return coordsFinite ? commands : null;
            }
            function extractSvgPathGeometry(el) {
                const tag = el.tagName.toLowerCase();
                if (tag === 'line') {
                    const ep = extractSvgLineEndpoints(el);
                    return {
                        screenPoints: [
                            { x: ep.x1, y: ep.y1 },
                            { x: ep.x2, y: ep.y2 },
                        ],
                        closed: false,
                    };
                }
                if (tag === 'polygon' || tag === 'polyline') {
                    const raw = parseSvgPointsAttribute(el.getAttribute('points') || '');
                    const screenPoints = raw.map((p) => svgUserToScreen(el, p.x, p.y));
                    return { screenPoints, closed: tag === 'polygon' };
                }
                if (tag === 'path') {
                    const pathEl = el;
                    const d = pathEl.getAttribute('d') || '';
                    const pathCmds = parseSvgPathCommands(d);
                    if (pathCmds) {
                        const screenPoints = pathCmds
                            .filter((c) => c.type !== 'Z')
                            .map((c) => c.type === 'C'
                            ? svgUserToScreen(pathEl, c.x, c.y)
                            : svgUserToScreen(pathEl, c.x, c.y));
                        return { screenPoints, closed: /[zZ]/.test(d) };
                    }
                    const closed = /[zZ]\s*$/.test(d.trim()) || /[zZ]/.test(d);
                    return { screenPoints: sampleSvgPathScreenPoints(pathEl), closed };
                }
                return { screenPoints: [], closed: false };
            }
            /** Resolve url(#linearGradient) / url(#radialGradient) paint servers into CSS-like gradient strings. */
            function resolveSvgGradientPaint(el, styles) {
                const fillAttr = el.getAttribute('fill') || '';
                const fillComputed = window.getComputedStyle(el).fill || '';
                const paintRef = [fillAttr, fillComputed].find((v) => v.includes('url(#'));
                if (!paintRef)
                    return;
                const idMatch = paintRef.match(/url\(#([^)]+)\)/);
                if (!idMatch)
                    return;
                const ref = el.ownerSVGElement?.getElementById(idMatch[1]) ||
                    document.getElementById(idMatch[1]);
                if (!ref)
                    return;
                const hexToRgb = (hex) => {
                    const m = hex.match(/^#?([0-9a-fA-F]{6})$/);
                    if (!m)
                        return null;
                    const v = m[1];
                    const r = parseInt(v.slice(0, 2), 16);
                    const g = parseInt(v.slice(2, 4), 16);
                    const b = parseInt(v.slice(4, 6), 16);
                    return { r, g, b };
                };
                const refTag = ref.tagName.toLowerCase();
                if (refTag === 'lineargradient') {
                    const stops = Array.from(ref.querySelectorAll('stop'))
                        .map((s) => {
                        const offset = s.getAttribute('offset') || '0%';
                        let color = s.getAttribute('stop-color') ||
                            window.getComputedStyle(s).stopColor ||
                            '#000000';
                        if (color.startsWith('var(')) {
                            color = resolveCssVarFromRoot(color) || color;
                        }
                        const stopOpacityRaw = s.getAttribute('stop-opacity') || window.getComputedStyle(s).stopOpacity || '1';
                        const stopOpacity = Math.max(0, Math.min(1, parseFloat(stopOpacityRaw) || 1));
                        const rgbaAlpha = parseColorAlpha(color);
                        const hex = cssColorToHex(color);
                        const rgb = hex ? hexToRgb('#' + hex) : null;
                        const a = Math.max(0, Math.min(1, rgbaAlpha * stopOpacity));
                        if (rgb && a < 1 - 1e-6) {
                            return `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${a}) ${offset}`;
                        }
                        return `${hex ? '#' + hex : color} ${offset}`;
                    })
                        .filter(Boolean);
                    if (stops.length < 2)
                        return;
                    const x1 = parseFloat(ref.getAttribute('x1') || '0');
                    const y1 = parseFloat(ref.getAttribute('y1') || '0');
                    const x2 = parseFloat(ref.getAttribute('x2') || '100');
                    const y2 = parseFloat(ref.getAttribute('y2') || '0');
                    const angleRad = Math.atan2(y2 - y1, x2 - x1);
                    const angleDeg = Math.round((angleRad * 180) / Math.PI + 90);
                    styles.backgroundImage = `linear-gradient(${angleDeg}deg, ${stops.join(', ')})`;
                }
            }
            function applySvgShapeMetadata(info, element) {
                if (!isSvgNamespace(element))
                    return;
                const svgTag = element.tagName.toLowerCase();
                info.svgTag = svgTag;
                const cs = window.getComputedStyle(element);
                let dash = cs.getPropertyValue('stroke-dasharray') || cs.strokeDasharray || '';
                if (!dash || dash === 'none') {
                    const dashAttr = element.getAttribute('stroke-dasharray');
                    if (dashAttr && dashAttr !== 'none')
                        dash = dashAttr;
                }
                if (dash && dash !== 'none')
                    info.svgStrokeDasharray = dash.trim();
                extractSvgMarkers(element, info);
                resolveSvgGradientPaint(element, info.styles);
                // Preserve solid SVG fill + fill-opacity as backgroundColor so converter can emit a fill with transparency.
                // (Gradients are handled via resolveSvgGradientPaint -> styles.backgroundImage.)
                if (!info.styles.backgroundImage || info.styles.backgroundImage === 'none') {
                    const fillRaw = cs.fill || '';
                    const hasFill = !!fillRaw &&
                        fillRaw !== 'none' &&
                        fillRaw !== 'transparent' &&
                        fillRaw !== 'rgba(0, 0, 0, 0)' &&
                        fillRaw !== 'rgba(0,0,0,0)';
                    if (hasFill) {
                        const fillOpacityRaw = cs.getPropertyValue('fill-opacity') || cs.fillOpacity || '1';
                        const fo = Math.max(0, Math.min(1, parseFloat(fillOpacityRaw) || 1));
                        const a = Math.max(0, Math.min(1, parseColorAlpha(fillRaw) * fo));
                        const hex = cssColorToHex(fillRaw);
                        if (hex) {
                            const r = parseInt(hex.slice(0, 2), 16);
                            const g = parseInt(hex.slice(2, 4), 16);
                            const b = parseInt(hex.slice(4, 6), 16);
                            info.styles.backgroundColor =
                                a < 1 - 1e-6 ? `rgba(${r}, ${g}, ${b}, ${a})` : `rgb(${r}, ${g}, ${b})`;
                            info.styles.backgroundImage = 'none';
                        }
                    }
                }
                if (svgTag === 'line') {
                    info.svgLineEndpoints = extractSvgLineEndpoints(element);
                    return;
                }
                if (svgTag === 'path') {
                    const pathEl = element;
                    const d = pathEl.getAttribute('d') || '';
                    const pathCmds = parseSvgPathCommands(d);
                    if (pathCmds) {
                        const bboxLeft = info.x;
                        const bboxTop = info.y;
                        const hasArc = pathCmds.some((c) => c.type === 'A');
                        // PowerPoint custGeom arcTo does not reliably fill elliptical-arc regions
                        // (cylinder DB icons show white gaps between bands). Sample the browser path instead.
                        if (hasArc && isSvgFillVisible(cs)) {
                            const len = pathEl.getTotalLength();
                            const maxPts = Math.min(160, Math.max(32, Math.ceil(Number.isFinite(len) ? len / 1.2 : 48)));
                            const screenPoints = sampleSvgPathScreenPoints(pathEl, maxPts);
                            if (screenPoints.length >= 3) {
                                info.clipPathPolygonPx = screenPoints.map((p) => ({
                                    x: p.x - bboxLeft,
                                    y: p.y - bboxTop,
                                }));
                                info.svgPathClosed = /[zZ]/.test(d);
                                return;
                            }
                        }
                        info.svgPathCommandsPx = pathCmds.map((cmd) => {
                            if (cmd.type === 'Z')
                                return { type: 'Z' };
                            const ctm = pathEl.getScreenCTM();
                            const scaleX = ctm ? Math.hypot(ctm.a, ctm.b) : 1;
                            const scaleY = ctm ? Math.hypot(ctm.c, ctm.d) : 1;
                            if (cmd.type === 'A') {
                                const end = svgUserToScreen(pathEl, cmd.x, cmd.y);
                                return {
                                    type: 'A',
                                    rx: cmd.rx * scaleX,
                                    ry: cmd.ry * scaleY,
                                    rot: cmd.rot,
                                    large: cmd.large,
                                    sweep: cmd.sweep,
                                    x: end.x - bboxLeft,
                                    y: end.y - bboxTop,
                                };
                            }
                            if (cmd.type === 'C') {
                                const s1 = svgUserToScreen(pathEl, cmd.x1, cmd.y1);
                                const s2 = svgUserToScreen(pathEl, cmd.x2, cmd.y2);
                                const s = svgUserToScreen(pathEl, cmd.x, cmd.y);
                                return {
                                    type: 'C',
                                    x1: s1.x - bboxLeft,
                                    y1: s1.y - bboxTop,
                                    x2: s2.x - bboxLeft,
                                    y2: s2.y - bboxTop,
                                    x: s.x - bboxLeft,
                                    y: s.y - bboxTop,
                                };
                            }
                            const s = svgUserToScreen(pathEl, cmd.x, cmd.y);
                            return { type: cmd.type, x: s.x - bboxLeft, y: s.y - bboxTop };
                        });
                        info.svgPathClosed = /[zZ]/.test(d);
                        return;
                    }
                    const straight = extractStraightPathLineEndpoints(pathEl);
                    if (straight) {
                        info.svgLineEndpoints = straight;
                        return;
                    }
                }
                const geomTags = new Set(['path', 'polygon', 'polyline']);
                if (!geomTags.has(svgTag))
                    return;
                const { screenPoints, closed } = extractSvgPathGeometry(element);
                if (screenPoints.length < 2)
                    return;
                const bboxLeft = info.x;
                const bboxTop = info.y;
                info.clipPathPolygonPx = screenPoints.map((p) => ({
                    x: p.x - bboxLeft,
                    y: p.y - bboxTop,
                }));
                info.svgPathClosed = closed;
            }
            /**
             * Check if element is visible
             */
            function getElementSelector(element) {
                if (!(element instanceof HTMLElement))
                    return element.tagName;
                const parts = [];
                let current = element;
                while (current && current.tagName !== 'BODY') {
                    let part = current.tagName;
                    if (current.id)
                        part += `#${current.id}`;
                    if (current.className) {
                        part += `.${Array.from(current.classList).join('.')}`;
                    }
                    parts.unshift(part);
                    current = current.parentElement;
                }
                return `BODY > ${parts.join(' > ')}`;
            }
            /**
             * Check if element is visible
             */
            function isVisible(element) {
                // SVG elements (svg, path, etc.) are not HTMLElement but are Element
                if (!(element instanceof Element) || typeof element.getBoundingClientRect !== 'function')
                    return false;
                const style = window.getComputedStyle(element);
                const rect = element.getBoundingClientRect();
                // For debugging specific element (disabled)
                // if (element instanceof HTMLElement && element.matches('body > div > header > div')) {
                //   _debugInfo.push(`[DEBUG] isVisible for element: ${element.tagName}.${element.className}`);
                //   _debugInfo.push(`[DEBUG]   display: ${style.display}, visibility: ${style.visibility}, opacity: ${style.opacity}`);
                //   _debugInfo.push(`[DEBUG]   rect: w=${rect.width}, h=${rect.height}`);
                //   _debugInfo.push(`[DEBUG]   textContent: '${element.textContent?.trim()}'`);
                //   _debugInfo.push(`[DEBUG]   fontSize: ${parseFloat(style.fontSize)}`);
                // }
                // Special case: Font Awesome icons should be included even with opacity: 0
                // because they often have CSS animations that start with opacity: 0
                const isFontAwesome = isFAIcon(element);
                // Basic visibility checks
                if (style.display === 'none' || style.visibility === 'hidden')
                    return false;
                if (!isFontAwesome && style.opacity === '0')
                    return false;
                // SVG stroke-only shapes may have zero width or height in getBoundingClientRect().
                if (isSvgNamespace(element)) {
                    const svgTag = element.tagName.toLowerCase();
                    if (svgTag === 'line' && isSvgPaintVisible(style))
                        return true;
                    if (isSvgPaintVisible(style) && (rect.width > 0 || rect.height > 0))
                        return true;
                }
                if (rect.width <= 0)
                    return false;
                // Special case: Elements with text content and font size > 0 are visible
                // even if height is 0 (e.g., line-height: 0 with large font-size)
                if (rect.height <= 0) {
                    const hasTextContent = element.textContent && element.textContent.trim().length > 0;
                    const fontSize = parseFloat(style.fontSize);
                    if (hasTextContent && fontSize > 0) {
                        return true; // Visible text with zero line-height
                    }
                    return false; // No text or zero font size with zero height
                }
                return true;
            }
            /**
             * Returns true if the element has a rotation in its computed transform
             * (rotate(...), matrix(...), or matrix3d(...)). Used to pass unrotated
             * size/position so PPTX doesn't double-apply rotation to AABB.
             */
            function hasTransformRotation(element) {
                const t = window.getComputedStyle(element).transform;
                if (!t || t === 'none')
                    return false;
                return /rotate\s*\(/i.test(t) || /^matrix\s*\(/i.test(t) || /^matrix3d\s*\(/i.test(t);
            }
            /**
             * CSS hard color stops use the same % twice (e.g. `transparent 45%, orange 45%`).
             * PowerPoint/OOXML smears these; tiled radial dot grids (e.g. `gold 15%, transparent 15%`
             * with small background-size) cannot be expressed as one shape gradFill — raster fallback.
             */
            function gradientInnerHasAdjacentDuplicatePercentHardStop(inner) {
                const pairRe = /\b(\d+(?:\.\d+)?)%\s*,([\s\S]+?)\s+\1%/g;
                pairRe.lastIndex = 0;
                return pairRe.test(inner);
            }
            function hasAdjacentDuplicatePercentHardStopInGradients(bg) {
                const needles = ['linear-gradient(', 'radial-gradient(', 'repeating-radial-gradient('];
                for (const needle of needles) {
                    let from = 0;
                    while (true) {
                        const start = bg.indexOf(needle, from);
                        if (start === -1)
                            break;
                        let depth = 0;
                        let i = start + needle.length;
                        let end = -1;
                        for (; i < bg.length; i++) {
                            const c = bg[i];
                            if (c === '(')
                                depth++;
                            else if (c === ')') {
                                if (depth === 0) {
                                    end = i;
                                    break;
                                }
                                depth--;
                            }
                        }
                        if (end === -1)
                            break;
                        const inner = bg.slice(start + needle.length, end);
                        if (gradientInnerHasAdjacentDuplicatePercentHardStop(inner))
                            return true;
                        from = end + 1;
                    }
                }
                return false;
            }
            function hasTiledRadialGradientBackground(bgImg, bgSize) {
                if (!/radial-gradient\(|repeating-radial-gradient\(/i.test(bgImg))
                    return false;
                const isDefaultSize = !bgSize || bgSize === 'auto' || bgSize === 'auto auto' || bgSize === '100% 100%';
                return !isDefaultSize;
            }
            const CLIP_EPS = 1e-5;
            function parseLengthForClip(token, refSize) {
                const t = token.trim();
                if (t.endsWith('%'))
                    return (parseFloat(t) / 100) * refSize;
                return parseFloat(t);
            }
            function parsePolygonClipPath(cssValue, refW, refH, refLeft, refTop) {
                const m = cssValue.match(/polygon\s*\(\s*([\s\S]*?)\s*\)/i);
                if (!m)
                    return null;
                const raw = m[1].trim();
                const parts = raw.split(/\s*,\s*/).map((s) => s.trim()).filter(Boolean);
                const pts = [];
                for (const part of parts) {
                    const tokens = part.split(/\s+/).filter(Boolean);
                    if (tokens.length < 2)
                        continue;
                    const x = parseLengthForClip(tokens[0], refW);
                    const y = parseLengthForClip(tokens[1], refH);
                    pts.push({ x: refLeft + x, y: refTop + y });
                }
                return pts.length >= 3 ? pts : null;
            }
            function intersectSegVertical(a, b, x) {
                const dx = b.x - a.x;
                if (Math.abs(dx) < CLIP_EPS)
                    return null;
                const t = (x - a.x) / dx;
                if (t < -CLIP_EPS || t > 1 + CLIP_EPS)
                    return null;
                return { x, y: a.y + t * (b.y - a.y) };
            }
            function intersectSegHorizontal(a, b, y) {
                const dy = b.y - a.y;
                if (Math.abs(dy) < CLIP_EPS)
                    return null;
                const t = (y - a.y) / dy;
                if (t < -CLIP_EPS || t > 1 + CLIP_EPS)
                    return null;
                return { x: a.x + t * (b.x - a.x), y };
            }
            function clipPolygonHalfPlane(poly, inside, intersect) {
                const n = poly.length;
                if (n === 0)
                    return [];
                const out = [];
                for (let i = 0; i < n; i++) {
                    const a = poly[i];
                    const b = poly[(i + 1) % n];
                    const aIn = inside(a);
                    const bIn = inside(b);
                    if (aIn && bIn) {
                        out.push(b);
                    }
                    else if (aIn && !bIn) {
                        const p = intersect(a, b);
                        if (p)
                            out.push(p);
                    }
                    else if (!aIn && bIn) {
                        const p = intersect(a, b);
                        if (p)
                            out.push(p);
                        out.push(b);
                    }
                }
                return out;
            }
            function intersectConvexPolygonWithRect(poly, left, top, right, bottom) {
                if (poly.length < 3)
                    return null;
                let out = poly;
                out = clipPolygonHalfPlane(out, (p) => p.x >= left - CLIP_EPS, (a, b) => intersectSegVertical(a, b, left));
                out = clipPolygonHalfPlane(out, (p) => p.x <= right + CLIP_EPS, (a, b) => intersectSegVertical(a, b, right));
                out = clipPolygonHalfPlane(out, (p) => p.y >= top - CLIP_EPS, (a, b) => intersectSegHorizontal(a, b, top));
                out = clipPolygonHalfPlane(out, (p) => p.y <= bottom + CLIP_EPS, (a, b) => intersectSegHorizontal(a, b, bottom));
                return out.length >= 3 ? out : null;
            }
            function sortConvexPolygonVertices(pts) {
                const cx = pts.reduce((s, p) => s + p.x, 0) / pts.length;
                const cy = pts.reduce((s, p) => s + p.y, 0) / pts.length;
                return [...pts].sort((a, b) => Math.atan2(a.y - cy, a.x - cx) - Math.atan2(b.y - cy, b.x - cx));
            }
            function dedupePolygonVertices(pts) {
                const out = [];
                for (const p of pts) {
                    const last = out[out.length - 1];
                    if (!last || Math.hypot(p.x - last.x, p.y - last.y) > CLIP_EPS)
                        out.push(p);
                }
                if (out.length >= 2) {
                    const first = out[0];
                    const last = out[out.length - 1];
                    if (Math.hypot(first.x - last.x, first.y - last.y) < CLIP_EPS)
                        out.pop();
                }
                return out;
            }
            function findPolygonClipPathOwner(element) {
                let node = element;
                while (node) {
                    const style = window.getComputedStyle(node);
                    const cp = style.clipPath && style.clipPath !== 'none'
                        ? style.clipPath
                        : style.webkitClipPath || '';
                    if (cp && cp !== 'none' && /polygon\s*\(/i.test(cp)) {
                        return { owner: node, cssValue: cp };
                    }
                    node = node.parentElement;
                }
                return null;
            }
            /** Map clip-path polygon from owner's local border box to viewport coordinates. */
            function clipPolygonLocalToViewport(owner, localPoly, localW, localH) {
                const rect = owner.getBoundingClientRect();
                const cx = rect.left + rect.width / 2;
                const cy = rect.top + rect.height / 2;
                const style = window.getComputedStyle(owner);
                const t = style.transform;
                if (!t || t === 'none') {
                    return localPoly.map((p) => ({ x: rect.left + p.x, y: rect.top + p.y }));
                }
                const matrixMatch = t.match(/matrix(?:3d)?\s*\(\s*([-\d.e]+)\s*,\s*([-\d.e]+)\s*,\s*([-\d.e]+)\s*,\s*([-\d.e]+)/);
                let a = 1;
                let b = 0;
                let c = 0;
                let d = 1;
                if (matrixMatch) {
                    a = parseFloat(matrixMatch[1]);
                    b = parseFloat(matrixMatch[2]);
                    c = parseFloat(matrixMatch[3]);
                    d = parseFloat(matrixMatch[4]);
                }
                else {
                    const rotMatch = t.match(/rotate\s*\(\s*([-\d.]+)\s*(deg|turn|rad)?\s*\)/i);
                    if (rotMatch) {
                        let deg = parseFloat(rotMatch[1]);
                        const unit = (rotMatch[2] || 'deg').toLowerCase();
                        if (unit === 'turn')
                            deg *= 360;
                        else if (unit === 'rad')
                            deg = (deg * 180) / Math.PI;
                        const rad = (deg * Math.PI) / 180;
                        a = Math.cos(rad);
                        b = Math.sin(rad);
                        c = -b;
                        d = a;
                    }
                }
                const origin = (style.transformOrigin || '50% 50%').trim().split(/\s+/);
                const ox = parseLengthForClip(origin[0] || '50%', localW);
                const oy = parseLengthForClip(origin[1] || origin[0] || '50%', localH);
                const layoutLeft = cx - localW / 2;
                const layoutTop = cy - localH / 2;
                return localPoly.map((p) => {
                    const lx = p.x - ox;
                    const ly = p.y - oy;
                    return {
                        x: layoutLeft + ox + a * lx + c * ly,
                        y: layoutTop + oy + b * lx + d * ly,
                    };
                });
            }
            function computeClipPathIntersection(element, box) {
                const found = findPolygonClipPathOwner(element);
                if (!found)
                    return null;
                const { owner, cssValue } = found;
                const isSelf = owner === element;
                // clip-path % are relative to the owner's border box (pre-transform). For a rotated
                // owner, getBoundingClientRect() is the axis-aligned bounding box — wrong for % refs.
                if (isSelf) {
                    const w = box.width;
                    const h = box.height;
                    if (w <= 0 || h <= 0)
                        return null;
                    const localPoly = parsePolygonClipPath(cssValue, w, h, 0, 0);
                    if (!localPoly || localPoly.length < 3)
                        return null;
                    let inter = intersectConvexPolygonWithRect(localPoly, 0, 0, w, h);
                    if (!inter || inter.length < 3)
                        return null;
                    inter = dedupePolygonVertices(sortConvexPolygonVertices(inter));
                    if (inter.length < 3)
                        return null;
                    let minX = Infinity;
                    let minY = Infinity;
                    let maxX = -Infinity;
                    let maxY = -Infinity;
                    for (const p of inter) {
                        minX = Math.min(minX, p.x);
                        minY = Math.min(minY, p.y);
                        maxX = Math.max(maxX, p.x);
                        maxY = Math.max(maxY, p.y);
                    }
                    const width = maxX - minX;
                    const height = maxY - minY;
                    if (width < 0.5 || height < 0.5)
                        return null;
                    if (hasTransformRotation(element)) {
                        return {
                            bbox: { left: box.x, top: box.y, width: w, height: h },
                            pointsRelative: inter.map((p) => ({ x: p.x, y: p.y })),
                            preserveLayoutBox: true,
                        };
                    }
                    const pointsRelative = inter.map((p) => ({ x: p.x - minX, y: p.y - minY }));
                    return {
                        bbox: { left: box.x + minX, top: box.y + minY, width, height },
                        pointsRelative,
                    };
                }
                let clipPoly = null;
                if (owner instanceof HTMLElement && hasTransformRotation(owner)) {
                    const ow = owner.offsetWidth;
                    const oh = owner.offsetHeight;
                    if (ow > 0 && oh > 0) {
                        const local = parsePolygonClipPath(cssValue, ow, oh, 0, 0);
                        if (local && local.length >= 3) {
                            clipPoly = clipPolygonLocalToViewport(owner, local, ow, oh);
                        }
                    }
                }
                if (!clipPoly) {
                    const r = owner.getBoundingClientRect();
                    clipPoly = parsePolygonClipPath(cssValue, r.width, r.height, r.left, r.top);
                }
                if (!clipPoly || clipPoly.length < 3)
                    return null;
                const left = box.x;
                const top = box.y;
                const right = box.x + box.width;
                const bottom = box.y + box.height;
                let inter = intersectConvexPolygonWithRect(clipPoly, left, top, right, bottom);
                if (!inter || inter.length < 3)
                    return null;
                inter = dedupePolygonVertices(sortConvexPolygonVertices(inter));
                if (inter.length < 3)
                    return null;
                let minX = Infinity;
                let minY = Infinity;
                let maxX = -Infinity;
                let maxY = -Infinity;
                for (const p of inter) {
                    minX = Math.min(minX, p.x);
                    minY = Math.min(minY, p.y);
                    maxX = Math.max(maxX, p.x);
                    maxY = Math.max(maxY, p.y);
                }
                const width = maxX - minX;
                const height = maxY - minY;
                if (width < 0.5 || height < 0.5)
                    return null;
                const pointsRelative = inter.map((p) => ({ x: p.x - minX, y: p.y - minY }));
                return {
                    bbox: { left: minX, top: minY, width, height },
                    pointsRelative,
                };
            }
            function parseRadiusPair(value, width, height) {
                const txt = (value || '').trim();
                if (!txt)
                    return { rx: 0, ry: 0 };
                const parts = txt.split(/\s+/).filter(Boolean);
                const parseToken = (token, base) => {
                    const t = token.trim();
                    if (!t)
                        return 0;
                    if (t.endsWith('%')) {
                        const n = parseFloat(t);
                        return Number.isFinite(n) ? (n / 100) * base : 0;
                    }
                    const n = parseFloat(t);
                    return Number.isFinite(n) ? n : 0;
                };
                const rx = Math.max(0, parseToken(parts[0], width));
                const ry = Math.max(0, parseToken(parts[1] || parts[0], height));
                return { rx, ry };
            }
            function sampleRoundedRectPolygon(element, width, height) {
                if (!(element instanceof HTMLElement))
                    return null;
                if (width <= 0 || height <= 0)
                    return null;
                const s = window.getComputedStyle(element);
                const tl = parseRadiusPair(s.borderTopLeftRadius, width, height);
                const tr = parseRadiusPair(s.borderTopRightRadius, width, height);
                const br = parseRadiusPair(s.borderBottomRightRadius, width, height);
                const bl = parseRadiusPair(s.borderBottomLeftRadius, width, height);
                // CSS border-radius normalization (avoid corner overlap).
                const topSum = tl.rx + tr.rx;
                const bottomSum = bl.rx + br.rx;
                const leftSum = tl.ry + bl.ry;
                const rightSum = tr.ry + br.ry;
                const scale = Math.min(1, topSum > 0 ? width / topSum : 1, bottomSum > 0 ? width / bottomSum : 1, leftSum > 0 ? height / leftSum : 1, rightSum > 0 ? height / rightSum : 1);
                if (scale < 1) {
                    tl.rx *= scale;
                    tl.ry *= scale;
                    tr.rx *= scale;
                    tr.ry *= scale;
                    br.rx *= scale;
                    br.ry *= scale;
                    bl.rx *= scale;
                    bl.ry *= scale;
                }
                const hasComplexRadius = Math.abs(tl.rx - tr.rx) > 0.1 ||
                    Math.abs(tr.rx - br.rx) > 0.1 ||
                    Math.abs(br.rx - bl.rx) > 0.1 ||
                    Math.abs(tl.ry - tr.ry) > 0.1 ||
                    Math.abs(tr.ry - br.ry) > 0.1 ||
                    Math.abs(br.ry - bl.ry) > 0.1 ||
                    Math.abs(tl.rx - tl.ry) > 0.1 ||
                    Math.abs(tr.rx - tr.ry) > 0.1 ||
                    Math.abs(br.rx - br.ry) > 0.1 ||
                    Math.abs(bl.rx - bl.ry) > 0.1;
                if (!hasComplexRadius)
                    return null;
                const points = [];
                const arc = (cx, cy, rx, ry, start, end, segments) => {
                    if (rx <= 0 || ry <= 0) {
                        points.push({ x: cx + rx * Math.cos(end), y: cy + ry * Math.sin(end) });
                        return;
                    }
                    for (let i = 1; i <= segments; i++) {
                        const t = start + ((end - start) * i) / segments;
                        points.push({ x: cx + rx * Math.cos(t), y: cy + ry * Math.sin(t) });
                    }
                };
                points.push({ x: tl.rx, y: 0 });
                points.push({ x: width - tr.rx, y: 0 });
                arc(width - tr.rx, tr.ry, tr.rx, tr.ry, -Math.PI / 2, 0, 8);
                points.push({ x: width, y: height - br.ry });
                arc(width - br.rx, height - br.ry, br.rx, br.ry, 0, Math.PI / 2, 8);
                points.push({ x: bl.rx, y: height });
                arc(bl.rx, height - bl.ry, bl.rx, bl.ry, Math.PI / 2, Math.PI, 8);
                points.push({ x: 0, y: tl.ry });
                arc(tl.rx, tl.ry, tl.rx, tl.ry, Math.PI, (3 * Math.PI) / 2, 8);
                return dedupePolygonVertices(points);
            }
            /** Square-corner chip outside a circular border-radius (masks native table square corners). */
            function sampleCornerChipPolygon(corner, radius) {
                const r = Math.max(0, radius);
                if (r < 2)
                    return null;
                const pts = [];
                const segs = 10;
                if (corner === 'tl') {
                    pts.push({ x: 0, y: 0 });
                    pts.push({ x: r, y: 0 });
                    for (let i = 0; i <= segs; i++) {
                        const a = -Math.PI / 2 - (Math.PI / 2) * (i / segs);
                        pts.push({ x: r + r * Math.cos(a), y: r + r * Math.sin(a) });
                    }
                }
                else if (corner === 'tr') {
                    pts.push({ x: r, y: 0 });
                    pts.push({ x: 0, y: 0 });
                    for (let i = 0; i <= segs; i++) {
                        const a = -Math.PI / 2 + (Math.PI / 2) * (i / segs);
                        pts.push({ x: 0 + r * Math.cos(a), y: r + r * Math.sin(a) });
                    }
                }
                else if (corner === 'bl') {
                    pts.push({ x: 0, y: r });
                    pts.push({ x: 0, y: 0 });
                    for (let i = 0; i <= segs; i++) {
                        const a = Math.PI - (Math.PI / 2) * (i / segs);
                        pts.push({ x: r + r * Math.cos(a), y: 0 + r * Math.sin(a) });
                    }
                }
                else {
                    pts.push({ x: r, y: r });
                    pts.push({ x: r, y: 0 });
                    for (let i = 0; i <= segs; i++) {
                        const a = 0 + (Math.PI / 2) * (i / segs);
                        pts.push({ x: 0 + r * Math.cos(a), y: 0 + r * Math.sin(a) });
                    }
                }
                return dedupePolygonVertices(pts);
            }
            /**
             * Serialize any valid CSS background-color to rgb()/rgba() so Node-side parseColor
             * can read it (e.g. rgb(30 64 175 / 1), lab(), hsl() from Tailwind v4).
             */
            function canonicalizeComputedBackgroundColor(cssColor) {
                if (!cssColor)
                    return cssColor;
                const t = cssColor.trim().toLowerCase();
                if (t === 'transparent' || t === 'rgba(0, 0, 0, 0)' || t === 'rgba(0,0,0,0)') {
                    return cssColor;
                }
                try {
                    const probe = document.createElement('div');
                    probe.style.cssText =
                        'position:absolute;left:-9999px;visibility:hidden;background-color:' + cssColor;
                    document.documentElement.appendChild(probe);
                    const resolved = window.getComputedStyle(probe).backgroundColor;
                    document.documentElement.removeChild(probe);
                    return resolved && resolved !== 'rgba(0, 0, 0, 0)' ? resolved : cssColor;
                }
                catch {
                    return cssColor;
                }
            }
            /**
             * Read cascaded specified font-family (may still contain sans-serif/serif generics).
             * Walks ancestors for inherited stylesheet rules; falls back to computed font-family.
             */
            function getStylesheetFontFamily(el) {
                const matches = [];
                let order = 0;
                try {
                    for (const sheet of Array.from(document.styleSheets)) {
                        let rules;
                        try {
                            rules = sheet.cssRules;
                        }
                        catch {
                            continue;
                        }
                        for (let i = 0; i < rules.length; i++) {
                            const rule = rules[i];
                            if (rule instanceof CSSStyleRule) {
                                try {
                                    if (el.matches(rule.selectorText)) {
                                        const ff = rule.style.getPropertyValue('font-family');
                                        if (ff)
                                            matches.push({ ff, order: order++ });
                                    }
                                }
                                catch {
                                    /* invalid selector */
                                }
                            }
                        }
                    }
                }
                catch {
                    /* ignore */
                }
                return matches.length ? matches[matches.length - 1].ff : undefined;
            }
            function getSpecifiedFontFamily(element) {
                let el = element;
                while (el) {
                    const htmlEl = el;
                    const inline = htmlEl.style?.fontFamily;
                    if (inline)
                        return inline;
                    const fromSheet = getStylesheetFontFamily(el);
                    if (fromSheet)
                        return fromSheet;
                    el = el.parentElement;
                }
                try {
                    const computed = window.getComputedStyle(element).fontFamily;
                    if (computed)
                        return computed;
                }
                catch {
                    /* ignore */
                }
                return undefined;
            }
            /**
             * Get computed styles for an element
             */
            function getComputedStyles(element) {
                const style = window.getComputedStyle(element);
                const base = {
                    color: style.color,
                    fontSize: style.fontSize,
                    fontFamily: style.fontFamily,
                    fontFamilySpecified: getSpecifiedFontFamily(element),
                    fontWeight: style.fontWeight,
                    fontStyle: style.fontStyle,
                    textDecoration: style.textDecoration,
                    textAlign: style.textAlign,
                    writingMode: style.writingMode,
                    lineHeight: style.lineHeight,
                    letterSpacing: style.letterSpacing,
                    whiteSpace: style.whiteSpace,
                    backgroundColor: canonicalizeComputedBackgroundColor(style.backgroundColor),
                    backgroundImage: style.backgroundImage,
                    filter: style.filter,
                    backgroundClip: style.backgroundClip,
                    webkitBackgroundClip: style.webkitBackgroundClip,
                    webkitTextFillColor: style.webkitTextFillColor,
                    webkitTextStroke: style.getPropertyValue('-webkit-text-stroke'),
                    webkitTextStrokeWidth: style.getPropertyValue('-webkit-text-stroke-width'),
                    webkitTextStrokeColor: style.getPropertyValue('-webkit-text-stroke-color'),
                    opacity: parseFloat(style.opacity),
                    borderColor: style.borderColor,
                    borderWidth: style.borderWidth,
                    borderStyle: style.borderStyle,
                    borderRadius: style.borderRadius,
                    // Individual border sides
                    borderLeftWidth: style.borderLeftWidth,
                    borderRightWidth: style.borderRightWidth,
                    borderTopWidth: style.borderTopWidth,
                    borderBottomWidth: style.borderBottomWidth,
                    borderLeftColor: style.borderLeftColor,
                    borderRightColor: style.borderRightColor,
                    borderTopColor: style.borderTopColor,
                    borderBottomColor: style.borderBottomColor,
                    borderLeftStyle: style.borderLeftStyle,
                    borderRightStyle: style.borderRightStyle,
                    borderTopStyle: style.borderTopStyle,
                    borderBottomStyle: style.borderBottomStyle,
                    boxShadow: style.boxShadow,
                    textShadow: style.textShadow,
                    display: style.display,
                    visibility: style.visibility,
                    zIndex: style.zIndex,
                    transform: style.transform,
                    // Flexbox properties
                    flexDirection: style.flexDirection,
                    justifyContent: style.justifyContent,
                    alignItems: style.alignItems,
                    justifyItems: style.justifyItems,
                    placeItems: style.placeItems,
                    paddingTop: style.paddingTop,
                    paddingRight: style.paddingRight,
                    paddingBottom: style.paddingBottom,
                    paddingLeft: style.paddingLeft,
                    // Margins
                    marginTop: style.marginTop,
                    marginRight: style.marginRight,
                    marginBottom: style.marginBottom,
                    marginLeft: style.marginLeft,
                    listStyleType: style.listStyleType,
                    objectFit: style.objectFit,
                    backgroundSize: style.backgroundSize,
                    textTransform: style.textTransform,
                    lang: documentLanguage(element),
                };
                if (!isSvgNamespace(element))
                    return base;
                const tag = element.tagName.toLowerCase();
                if (tag === 'text' || tag === 'tspan') {
                    // SVG text paint comes from fill, not CSS color (which stays rgb(0,0,0) in Chromium).
                    const fill = style.fill;
                    if (fill &&
                        fill !== 'none' &&
                        fill !== 'transparent' &&
                        fill !== 'rgba(0, 0, 0, 0)' &&
                        fill !== 'rgba(0,0,0,0)') {
                        base.color = fill;
                    }
                    const fillOpacityRaw = style.getPropertyValue('fill-opacity');
                    if (fillOpacityRaw) {
                        const fillOpacity = parseFloat(fillOpacityRaw);
                        if (!Number.isNaN(fillOpacity) && fillOpacity < 1) {
                            base.opacity = (base.opacity ?? 1) * fillOpacity;
                        }
                    }
                    const anchor = style.getPropertyValue('text-anchor');
                    if (anchor === 'middle')
                        base.textAlign = 'center';
                    else if (anchor === 'end')
                        base.textAlign = 'right';
                    else if (anchor === 'start')
                        base.textAlign = base.textAlign || 'left';
                }
                const svgShapeTags = new Set([
                    'rect',
                    'circle',
                    'ellipse',
                    'path',
                    'polygon',
                    'polyline',
                    'line',
                    'use',
                    'image',
                ]);
                if (svgShapeTags.has(tag)) {
                    const fill = style.fill;
                    if (fill && fill !== 'none' && fill !== 'transparent') {
                        base.backgroundColor = fill;
                    }
                    const stroke = style.stroke;
                    const sw = style.getPropertyValue('stroke-width');
                    const swNum = parseFloat(sw) || 0;
                    if (stroke && stroke !== 'none' && swNum > 0) {
                        base.borderColor = stroke;
                        base.borderWidth = swNum;
                        base.borderTopWidth = sw;
                        base.borderRightWidth = sw;
                        base.borderBottomWidth = sw;
                        base.borderLeftWidth = sw;
                        base.borderTopColor = stroke;
                        base.borderRightColor = stroke;
                        base.borderBottomColor = stroke;
                        base.borderLeftColor = stroke;
                        base.borderTopStyle = 'solid';
                        base.borderRightStyle = 'solid';
                        base.borderBottomStyle = 'solid';
                        base.borderLeftStyle = 'solid';
                        const strokeOpacityRaw = style.getPropertyValue('stroke-opacity');
                        if (strokeOpacityRaw) {
                            const strokeOpacity = parseFloat(strokeOpacityRaw);
                            if (!Number.isNaN(strokeOpacity) && strokeOpacity < 1) {
                                base.opacity = (base.opacity ?? 1) * strokeOpacity;
                            }
                        }
                    }
                    const rxAttr = element.getAttribute('rx');
                    if (rxAttr) {
                        base.borderRadius = `${rxAttr}px`;
                    }
                    else {
                        const rxComputed = style.getPropertyValue('rx');
                        if (rxComputed)
                            base.borderRadius = rxComputed;
                    }
                    if (tag === 'circle') {
                        const r = parseFloat(element.getAttribute('r') || '0');
                        if (r > 0)
                            base.borderRadius = `${r}px`;
                    }
                    else if (tag === 'ellipse') {
                        const rx = parseFloat(element.getAttribute('rx') || '0');
                        const ry = parseFloat(element.getAttribute('ry') || String(rx) || '0');
                        if (rx > 0 || ry > 0)
                            base.borderRadius = `${Math.max(rx, ry)}px`;
                    }
                }
                return base;
            }
            /**
             * Check if element is a Font Awesome icon
             */
            function isFontAwesomeIcon(element) {
                const classList = element.classList;
                return (element.tagName.toLowerCase() === 'i' &&
                    (classList.contains('fa') ||
                        classList.contains('fas') ||
                        classList.contains('far') ||
                        classList.contains('fab') ||
                        classList.contains('fal') ||
                        classList.contains('fad') ||
                        classList.contains('fa-solid') ||
                        classList.contains('fa-regular') ||
                        classList.contains('fa-brands')));
            }
            /**
             * True when every visible element child participates in inline flow (no block/flex/grid layout).
             * Used for bordered wrappers like .sub-item that hold inline title + body divs.
             */
            function hasOnlyInlineFlowChildren(element) {
                let hasElementChild = false;
                for (const ch of Array.from(element.children)) {
                    if (!(ch instanceof Element) || !isVisible(ch))
                        continue;
                    hasElementChild = true;
                    const d = window.getComputedStyle(ch).display;
                    if (d === 'block' ||
                        d === 'flex' ||
                        d === 'inline-flex' ||
                        d === 'grid' ||
                        d === 'flow-root' ||
                        d === 'list-item' ||
                        d === 'table') {
                        return false;
                    }
                }
                return hasElementChild;
            }
            /**
             * Determine element type
             */
            function getElementType(element) {
                const tag = element.tagName.toLowerCase();
                // DH-P0-004: explicit element kind hint takes precedence over tag/style inference.
                // `ignore` is handled in processElement (skips the subtree); here we map the rest.
                if (element instanceof Element) {
                    const hint = element.getAttribute('data-pptx-kind');
                    if (hint) {
                        const kind = hint.trim().toLowerCase();
                        if (kind === 'text')
                            return 'text';
                        if (kind === 'image')
                            return 'image';
                        if (kind === 'shape')
                            return 'shape';
                        if (kind === 'table')
                            return 'table';
                        if (kind === 'group')
                            return 'container';
                        // 'ignore' is consumed before getElementType runs, but defend in depth.
                        if (kind === 'ignore')
                            return 'container';
                        // Unknown hint: fall through to inference (reported as ambiguous later).
                    }
                }
                if (tag === 'img')
                    return 'image';
                if (tag === 'video')
                    return 'video';
                if (tag === 'audio')
                    return 'audio';
                if (tag === 'canvas')
                    return 'canvas';
                if (tag === 'iframe')
                    return 'iframe';
                if (tag === 'math')
                    return 'math';
                if (tag === 'svg')
                    return 'svg';
                if (tag === 'table')
                    return 'table';
                // SVG child elements (decomposed standalone SVG or large HTML-embedded SVG)
                if (isSvgNamespace(element)) {
                    if (tag === 'text' || tag === 'tspan') {
                        if (element.textContent?.trim())
                            return 'text';
                        return 'container';
                    }
                    if (tag === 'use' ||
                        tag === 'rect' ||
                        tag === 'circle' ||
                        tag === 'ellipse' ||
                        tag === 'path' ||
                        tag === 'polygon' ||
                        tag === 'polyline' ||
                        tag === 'line' ||
                        tag === 'image') {
                        if (isSvgPaintVisible(window.getComputedStyle(element)))
                            return 'shape';
                        const r = element.getBoundingClientRect();
                        if (r.width > 0 && r.height > 0)
                            return 'shape';
                        return 'container';
                    }
                    if (tag === 'g' || tag === 'switch' || tag === 'a')
                        return 'container';
                    return 'container';
                }
                // KaTeX: only <math> inside .katex-mathml is converted; .katex-html is visual-only.
                if (element.closest('.katex')) {
                    if (element.closest('.katex-html'))
                        return 'container';
                    if (element instanceof HTMLElement &&
                        (element.classList.contains('katex') || element.classList.contains('katex-mathml'))) {
                        return 'container';
                    }
                    if (element.closest('.katex-mathml'))
                        return 'container';
                }
                // Check for Font Awesome icons
                if (isFontAwesomeIcon(element)) {
                    return 'icon';
                }
                // Heading elements (h1-h6) should always be treated as text,
                // even if they contain child elements (spans, icons, etc.)
                if (/^h[1-6]$/.test(tag)) {
                    const textContent = element.textContent?.trim();
                    if (textContent) {
                        return 'text';
                    }
                }
                // Strong, em, b, i (non-icon), u, etc. should be text if they have content
                const inlineTextTags = ['strong', 'em', 'b', 'u', 'span', 'a', 'label', 'p'];
                if (inlineTextTags.includes(tag)) {
                    const textContent = element.textContent?.trim();
                    if (textContent && !isFontAwesomeIcon(element)) {
                        return 'text';
                    }
                }
                // Check if element has direct text content (text nodes)
                const hasText = element.childNodes.length > 0 &&
                    Array.from(element.childNodes).some((node) => node.nodeType === Node.TEXT_NODE && node.textContent?.trim());
                // Check if it's a container with background/border
                const style = window.getComputedStyle(element);
                // Helper: check if color is visible (not transparent)
                const isColorVisible = (color) => {
                    return color !== 'rgba(0, 0, 0, 0)' &&
                        color !== 'transparent' &&
                        color !== 'none';
                };
                // Check for visible background
                const hasVisibleBackground = isColorVisible(style.backgroundColor) ||
                    style.backgroundImage !== 'none';
                // Check for visible border (must have both width AND non-transparent color)
                const hasVisibleBorder = (parseFloat(style.borderLeftWidth) > 0 && isColorVisible(style.borderLeftColor)) ||
                    (parseFloat(style.borderRightWidth) > 0 && isColorVisible(style.borderRightColor)) ||
                    (parseFloat(style.borderTopWidth) > 0 && isColorVisible(style.borderTopColor)) ||
                    (parseFloat(style.borderBottomWidth) > 0 && isColorVisible(style.borderBottomColor));
                // KaTeX wrappers (.formula etc.): editable math comes from .katex-mathml only.
                const hostsKatex = element instanceof HTMLElement && element.querySelector('.katex') !== null;
                if (hostsKatex && (hasVisibleBackground || hasVisibleBorder)) {
                    return 'shape';
                }
                // Determine type based on visual properties and content
                // If element has both background/border AND text, treat as text (with fill) to preserve content
                if ((hasVisibleBackground || hasVisibleBorder) && hasText) {
                    return 'text';
                }
                // Bordered wrapper with only inline-level text children (e.g. .sub-item > title + body divs)
                const hasDescendantText = !!(element.textContent?.trim());
                if (hasVisibleBorder &&
                    !hasText &&
                    hasDescendantText &&
                    hasOnlyInlineFlowChildren(element) &&
                    !hostsKatex) {
                    return 'text';
                }
                if (hasVisibleBackground || hasVisibleBorder) {
                    return 'shape';
                }
                // If element has direct text content, treat as text (even if it has child elements)
                if (hasText) {
                    return 'text';
                }
                return 'container';
            }
            /**
             * Get text content from element
             * Manually traverses text nodes and converts <br> to \n, avoiding pseudo-element content
             * (Since we extract ::before/::after separately, we must not include their content here)
             * @param excludeSubtrees - if provided, text inside these elements is omitted (used when those children are emitted as separate elements)
             */
            /** Render `text-transform` the way CSS does, in the element's own locale. */
            function applyCssTextTransform(value, style, el) {
                switch (style.textTransform) {
                    case 'uppercase':
                        return localeUpperCase(value, documentLanguage(el));
                    case 'lowercase':
                        return value.toLocaleLowerCase(documentLanguage(el) || undefined);
                    case 'capitalize':
                        return value.replace(/(^|[\s\u00A0])(\S)/gu, (_match, gap, first) => gap + localeUpperCase(first, documentLanguage(el)));
                    default:
                        return value;
                }
            }
            /** True when the element participates in inline flow (its text is adjacent to siblings'). */
            function isInlineFlowElement(el) {
                try {
                    const display = window.getComputedStyle(el).display;
                    return display === 'inline' || display === 'contents' || display === 'ruby';
                }
                catch {
                    return true;
                }
            }
            function getTextContent(element, excludeSubtrees) {
                const parts = [];
                function traverse(node) {
                    if (node.nodeType === Node.TEXT_NODE) {
                        const text = node.textContent || '';
                        if (text.trim()) {
                            parts.push(text);
                        }
                    }
                    else if (node.nodeType === Node.ELEMENT_NODE) {
                        const el = node;
                        if (excludeSubtrees && excludeSubtrees.has(el)) {
                            return; // Skip this subtree (child is emitted as separate element)
                        }
                        if (isKatexSubtreeForTextOmit(el))
                            return;
                        // <br> becomes line break
                        if (el.tagName.toLowerCase() === 'br') {
                            parts.push('\n');
                        }
                        else {
                            // A non-inline child starts its own box, so the glyphs either
                            // side of it are never adjacent on screen — but concatenating
                            // the text nodes made them adjacent in the export, which is how
                            // "INSERTION" + "DECISION" shipped as "INSERTIONDECISION" and
                            // "Interpretation:" + "candidate" as "Interpretation:candidate".
                            // A space is the safe separator in both arrangements: when the
                            // boxes sit on one line it is the gap the reader sees, and when
                            // they stack, the captured line boxes carry the real break and
                            // trim their own edges.
                            if (!isInlineFlowElement(el) && parts.length) {
                                const previous = parts[parts.length - 1];
                                if (previous && !/[\s\u00A0]$/.test(previous))
                                    parts.push(' ');
                            }
                            // Traverse children
                            node.childNodes.forEach(traverse);
                        }
                    }
                }
                traverse(element);
                let text = parts.join('').replace(/ +/g, ' ').trim();
                const style = window.getComputedStyle(element);
                if (style.textTransform === 'uppercase') {
                    text = localeUpperCase(text, documentLanguage(element));
                }
                return text;
            }
            /**
             * Extract rich text structure from element with styled children
             * Returns array of text runs with individual styles
             * @param excludeSubtrees - same as getTextContent: omit children emitted as separate ElementInfo (e.g. badge span)
             */
            function getTextHighlightBackdrop(element) {
                let el = element.parentElement;
                while (el) {
                    const bg = canonicalizeComputedBackgroundColor(window.getComputedStyle(el).backgroundColor);
                    if (bg &&
                        bg !== 'rgba(0, 0, 0, 0)' &&
                        bg !== 'rgba(0,0,0,0)' &&
                        bg !== 'transparent' &&
                        bg !== 'none') {
                        return bg;
                    }
                    el = el.parentElement;
                }
                return undefined;
            }
            /**
             * L1: Capture Chromium visual line boxes for a text host.
             * Groups Range.getClientRects() by top; maps each line to UTF-16 offsets
             * in the normalized host text (same normalization as richText join).
             */
            function captureLayoutLines(element, normalizedText, excludeSubtrees) {
                const lines = [];
                if (!normalizedText) {
                    return { lines, ambiguous: false, unsupportedReason: 'empty_text' };
                }
                const st = window.getComputedStyle(element);
                const wm = (st.writingMode || '').toLowerCase();
                if (wm.includes('vertical') || wm.includes('sideways')) {
                    return { lines, ambiguous: true, unsupportedReason: 'vertical_writing' };
                }
                const dir = (st.direction || 'ltr').toLowerCase();
                if (dir === 'rtl') {
                    return { lines, ambiguous: true, unsupportedReason: 'rtl_or_bidi' };
                }
                const tf = st.transform;
                if (tf && tf !== 'none') {
                    // Allow pure rotation / translation matrices; reject skew-like (b/c nonzero).
                    const m = tf.match(/matrix\(([^)]+)\)/);
                    if (m) {
                        const parts = m[1].split(',').map((x) => parseFloat(x.trim()));
                        if (parts.length >= 4) {
                            const b = parts[1];
                            const c = parts[2];
                            if (Math.abs(b) > 0.001 && Math.abs(c) > 0.001) {
                                return { lines, ambiguous: true, unsupportedReason: 'unsupported_transform' };
                            }
                        }
                    }
                    if (tf.includes('matrix3d') || tf.includes('skew')) {
                        return { lines, ambiguous: true, unsupportedReason: 'unsupported_transform' };
                    }
                }
                function isExcludedNode(node) {
                    if (!excludeSubtrees?.size)
                        return false;
                    let p = node.nodeType === Node.ELEMENT_NODE ? node : node.parentNode;
                    while (p && p !== element) {
                        if (p.nodeType === Node.ELEMENT_NODE && excludeSubtrees.has(p))
                            return true;
                        p = p.parentNode;
                    }
                    return false;
                }
                // Collect text nodes in order
                const textNodes = [];
                const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT, {
                    acceptNode: (node) => {
                        if (!node.textContent)
                            return NodeFilter.FILTER_REJECT;
                        if (isExcludedNode(node))
                            return NodeFilter.FILTER_REJECT;
                        return NodeFilter.FILTER_ACCEPT;
                    },
                });
                let tn;
                while ((tn = walker.nextNode()))
                    textNodes.push(tn);
                if (!textNodes.length) {
                    return { lines, ambiguous: true, unsupportedReason: 'empty_text' };
                }
                const pieces = [];
                let built = '';
                for (const node of textNodes) {
                    const raw = node.textContent || '';
                    // Skip pure formatting whitespace between blocks carefully: keep as in extractRichText
                    const collapsed = raw.replace(/[\s\u00A0]{2,}/g, ' ');
                    if (!collapsed)
                        continue;
                    const start = built.length;
                    built += collapsed;
                    pieces.push({ node, start, end: built.length, text: collapsed });
                }
                // Align with provided normalizedText when lengths match; else use built.
                const hostText = normalizedText.length ? normalizedText : built;
                if (!hostText.trim()) {
                    return { lines, ambiguous: false, unsupportedReason: 'empty_text' };
                }
                const frags = [];
                // Binary-search wrap points per text node using getClientRects — O(n log n) per node.
                for (const piece of pieces) {
                    const node = piece.node;
                    const len = (node.textContent || '').length;
                    if (len === 0)
                        continue;
                    // Map collapsed piece offsets back approximately by scanning the raw node text
                    // with the same collapse rules. For fidelity fixtures (no weird whitespace) this
                    // matches 1:1.
                    const raw = node.textContent || '';
                    let rawIdx = 0;
                    let coll = '';
                    const collToRaw = [];
                    while (rawIdx < raw.length) {
                        const ch = raw[rawIdx];
                        if (/[\s\u00A0]/.test(ch)) {
                            if (coll.length === 0 || coll[coll.length - 1] !== ' ') {
                                collToRaw.push(rawIdx);
                                coll += ' ';
                            }
                            rawIdx++;
                            while (rawIdx < raw.length && /[\s\u00A0]/.test(raw[rawIdx]))
                                rawIdx++;
                        }
                        else {
                            collToRaw.push(rawIdx);
                            coll += ch;
                            rawIdx++;
                        }
                    }
                    const range = document.createRange();
                    // Probe each character's mid-point y to detect line changes — but sample by
                    // binary splitting when many chars share a line.
                    let i = 0;
                    while (i < coll.length) {
                        let lo = i;
                        let hi = coll.length;
                        // Find end of current visual line starting at i
                        const yAt = (collOffset) => {
                            if (collOffset >= coll.length)
                                collOffset = coll.length - 1;
                            if (collOffset < 0)
                                return null;
                            const r0 = collToRaw[collOffset];
                            if (r0 == null)
                                return null;
                            try {
                                range.setStart(node, r0);
                                range.setEnd(node, Math.min(r0 + 1, raw.length));
                                const rects = range.getClientRects();
                                if (!rects.length)
                                    return null;
                                return rects[0].top;
                            }
                            catch {
                                return null;
                            }
                        };
                        const y0 = yAt(i);
                        if (y0 == null) {
                            i++;
                            continue;
                        }
                        // Grow while same line (tolerance 1px)
                        let end = i + 1;
                        while (end < coll.length) {
                            const y = yAt(end);
                            if (y == null || Math.abs(y - y0) > 1)
                                break;
                            end++;
                        }
                        // Refine end with binary search if we jumped due to early break
                        // (end already exclusive of next line)
                        const lineColl = coll.slice(i, end);
                        const rStart = collToRaw[i] ?? 0;
                        const rEnd = end > 0 ? (collToRaw[end - 1] ?? rStart) + 1 : rStart;
                        try {
                            range.setStart(node, rStart);
                            range.setEnd(node, Math.min(rEnd, raw.length));
                            const rects = Array.from(range.getClientRects()).filter((r) => r.width > 0 || r.height > 0);
                            let left = Infinity;
                            let top = Infinity;
                            let right = -Infinity;
                            let bottom = -Infinity;
                            for (const r of rects) {
                                left = Math.min(left, r.left);
                                top = Math.min(top, r.top);
                                right = Math.max(right, r.right);
                                bottom = Math.max(bottom, r.bottom);
                            }
                            if (!Number.isFinite(left)) {
                                i = end;
                                continue;
                            }
                            const absStart = piece.start + i;
                            frags.push({
                                top,
                                left,
                                width: right - left,
                                height: bottom - top,
                                text: lineColl,
                                absStart,
                            });
                        }
                        catch {
                            /* skip */
                        }
                        i = end;
                    }
                }
                if (!frags.length) {
                    return { lines, ambiguous: true, unsupportedReason: 'ambiguous_line_map' };
                }
                const sameVisualLine = (frag, line) => {
                    const center = frag.top + frag.height / 2;
                    if (center >= line.top && center <= line.bottom)
                        return true;
                    // A tall fragment can enclose the line rather than sit inside it.
                    const overlap = Math.min(frag.top + frag.height, line.bottom) - Math.max(frag.top, line.top);
                    const shortest = Math.min(frag.height, line.bottom - line.top);
                    return shortest > 0 && overlap >= shortest / 2;
                };
                const acc = [];
                for (const f of frags) {
                    const host = acc.find((line) => sameVisualLine(f, line));
                    if (host) {
                        host.text += f.text;
                        host.left = Math.min(host.left, f.left);
                        host.right = Math.max(host.right, f.left + f.width);
                        host.top = Math.min(host.top, f.top);
                        host.bottom = Math.max(host.bottom, f.top + f.height);
                        host.startOffset = Math.min(host.startOffset, f.absStart);
                    }
                    else {
                        acc.push({
                            top: f.top,
                            left: f.left,
                            right: f.left + f.width,
                            bottom: f.top + f.height,
                            text: f.text,
                            startOffset: f.absStart,
                        });
                    }
                }
                acc.sort((left, right) => left.top - right.top || left.startOffset - right.startOffset);
                const scrollX = window.scrollX || document.documentElement.scrollLeft || 0;
                const scrollY = window.scrollY || document.documentElement.scrollTop || 0;
                let offset = 0;
                for (const a of acc) {
                    // This walk reads text nodes, which hold the source case; the host
                    // text and the export carry the *rendered* case. Without applying
                    // the transform here, every `text-transform: uppercase` kicker
                    // compared unequal, was ruled an ambiguous line map, and had its
                    // line breaks handed back to the reader's renderer.
                    const text = applyCssTextTransform(a.text, st, element);
                    lines.push({
                        text,
                        x: a.left + scrollX,
                        y: a.top + scrollY,
                        width: Math.max(0, a.right - a.left),
                        height: Math.max(0, a.bottom - a.top),
                        startOffset: offset,
                        endOffset: offset + text.length,
                    });
                    offset += text.length;
                }
                const reconstructed = lines.map((l) => l.text).join('');
                // Ambiguous only if we lost or gained real content. Whitespace cannot be compared
                // here: `hostText` marks a <br> or a block boundary with "\n" while this walk sees
                // text nodes only, so `A<br>B` reconstructs as "AB" against a host "A\nB". Treating
                // that as ambiguity refused the frozen-line path on every hard-broken heading and
                // handed the line breaks back to PowerPoint, which re-wrapped them — the drift this
                // whole capture exists to prevent. Line breaks are exactly where whitespace appears
                // and disappears, so compare the glyphs.
                const norm = (value) => value.replace(/[\s\u00A0]+/g, '');
                const normalizedLines = norm(reconstructed);
                // Generated content is not a text node, so this walk structurally
                // cannot see it, while the host text carries it because it is exported
                // as a run. Discount it rather than call the block ambiguous: a
                // `.lede::before{content:"03 / FORMULATION"}` kicker was enough to
                // give an otherwise perfectly mapped paragraph back to the renderer.
                let normalizedHost = norm(hostText);
                for (const pseudo of ['::before', '::after']) {
                    let generated = '';
                    try {
                        generated = window.getComputedStyle(element, pseudo).content || '';
                    }
                    catch {
                        generated = '';
                    }
                    const literal = generated.match(/^"([\s\S]*)"$|^'([\s\S]*)'$/);
                    const text = norm(literal ? (literal[1] ?? literal[2] ?? '') : '');
                    if (!text)
                        continue;
                    if (normalizedHost.startsWith(text)) {
                        normalizedHost = normalizedHost.slice(text.length);
                    }
                    else if (normalizedHost.endsWith(text)) {
                        normalizedHost = normalizedHost.slice(0, -text.length);
                    }
                }
                const ambiguous = normalizedLines !== normalizedHost;
                return {
                    lines,
                    ambiguous,
                    unsupportedReason: ambiguous ? 'ambiguous_line_map' : undefined,
                    // Say what differed. Without it an ambiguity is only visible as a
                    // count, and the cost of each one is a text block whose line breaks
                    // the reader's renderer gets to choose.
                    ...(ambiguous
                        ? {
                            mismatch: {
                                lines: normalizedLines.slice(0, 120),
                                host: normalizedHost.slice(0, 120),
                            },
                        }
                        : {}),
                };
            }
            function extractRichText(element, excludeSubtrees) {
                const runs = [];
                let hasMultipleStyles = false;
                /** Next text run follows an HTML &lt;br&gt; — use OOXML soft break, not a new a:p */
                let softBreakBeforeNextRun = false;
                /**
                 * Block-level DOM children inside a flex row are often computed as display:block but still
                 * sit on one line with siblings (e.g. footer-horizontal). Those must not become separate
                 * a:p paragraphs in PPTX. Walk up past display:contents to the nearest non-contents ancestor
                 * before `root`; if we hit the root, use its flex state.
                 */
                function laysOutChildrenInHorizontalFlexRow(node, root) {
                    let p = node.parentElement;
                    while (p) {
                        if (p === root) {
                            const ps = window.getComputedStyle(p);
                            const d = ps.display;
                            if (d === 'contents')
                                return false;
                            const fd = ps.flexDirection || 'row';
                            return ((d === 'flex' || d === 'inline-flex') &&
                                (fd === 'row' || fd === 'row-reverse'));
                        }
                        const ps = window.getComputedStyle(p);
                        const d = ps.display;
                        if (d === 'contents') {
                            p = p.parentElement;
                            continue;
                        }
                        if (d === 'flex' || d === 'inline-flex') {
                            const fd = ps.flexDirection || 'row';
                            return fd === 'row' || fd === 'row-reverse';
                        }
                        return false;
                    }
                    return false;
                }
                function isExcludedElement(el) {
                    if (!excludeSubtrees?.size)
                        return false;
                    if (excludeSubtrees.has(el))
                        return true;
                    let p = el.parentNode;
                    while (p && p !== element) {
                        if (p.nodeType === Node.ELEMENT_NODE && excludeSubtrees.has(p))
                            return true;
                        p = p.parentNode;
                    }
                    return false;
                }
                /**
                 * OOXML run highlight is a text semantic, not a CSS paint shortcut.  Propagate only an
                 * explicitly selected glyph highlight to descendants (for example a <mark> containing a
                 * <sub>).  Container backgrounds are exported as shapes and must never leak into runs.
                 */
                function mergeAncestorHighlightForRichTextRuns(nodeStyles, parentInherited) {
                    if (nodeStyles?.glyphHighlightColor || !parentInherited?.glyphHighlightColor)
                        return nodeStyles;
                    return {
                        ...nodeStyles,
                        glyphHighlightColor: parentInherited.glyphHighlightColor,
                        ...(parentInherited.highlightBackdropColor != null
                            ? { highlightBackdropColor: parentInherited.highlightBackdropColor }
                            : {}),
                    };
                }
                function explicitGlyphHighlight(node, styles) {
                    const declared = node.getAttribute('data-pptx-highlight') ||
                        node.getAttribute('data-sunairum-highlight');
                    if (declared && declared !== 'false' && declared !== 'none') {
                        return declared === 'true' ? styles.backgroundColor : declared;
                    }
                    if (node.tagName.toLowerCase() === 'mark')
                        return styles.backgroundColor;
                    return undefined;
                }
                function processNode(node, inheritedStyles) {
                    if (node.nodeType === Node.TEXT_NODE) {
                        // Replace newlines with space: HTML source newlines display as space, but pptxgenjs
                        // interprets \n as paragraph break (would split one <p> into many). Only replace \n/\r,
                        // preserve other whitespace to minimize layout impact.
                        const raw = node.textContent || '';
                        let text = raw.replace(/[\r\n]+/g, ' ').replace(/ +/g, ' ');
                        if (inheritedStyles.textTransform === 'uppercase') {
                            text = localeUpperCase(text, inheritedStyles.lang);
                        } //.replace(/ +/g, ' ');
                        if (text) {
                            runs.push({
                                text: text,
                                styles: inheritedStyles,
                                ...(softBreakBeforeNextRun ? { softBreakBefore: true } : {}),
                            });
                            softBreakBeforeNextRun = false;
                        }
                    }
                    else if (node.nodeType === Node.ELEMENT_NODE && node instanceof HTMLElement) {
                        if (isExcludedElement(node))
                            return;
                        if (isKatexSubtreeForTextOmit(node))
                            return;
                        // <br> — soft line within one paragraph (pptxgen softBreakBefore), not \n → multiple a:p
                        if (node.tagName.toLowerCase() === 'br') {
                            if (softBreakBeforeNextRun) {
                                // <br><br>: blank line — carrier run must carry host font metrics (pptxgen otherwise
                                // uses default ~18pt for line height on <a:br/> lines → oversized paragraph gap).
                                runs.push({
                                    text: '\u200b',
                                    styles: elementStyles,
                                    softBreakBefore: true,
                                });
                            }
                            else {
                                softBreakBeforeNextRun = true;
                            }
                            return;
                        }
                        // Skip decorative elements with no text
                        if (!node.textContent?.trim())
                            return;
                        const childStyles = getComputedStyles(node);
                        const isBlock = childStyles.display === 'block';
                        if (node instanceof HTMLElement) {
                            const markerBg = markerHighlightAfterBackground(node);
                            if (markerBg) {
                                childStyles.backgroundColor = markerBg;
                            }
                            const glyphHighlight = explicitGlyphHighlight(node, childStyles);
                            if (glyphHighlight)
                                childStyles.glyphHighlightColor = glyphHighlight;
                        }
                        if (childStyles.backgroundColor &&
                            childStyles.backgroundColor !== 'rgba(0, 0, 0, 0)' &&
                            childStyles.backgroundColor !== 'transparent') {
                            const backdrop = getTextHighlightBackdrop(node);
                            if (backdrop)
                                childStyles.highlightBackdropColor = backdrop;
                        }
                        // Check if this child has different style than parent.
                        // Include font-size so smaller/larger inline spans are preserved as rich text runs.
                        if (inheritedStyles.color !== childStyles.color)
                            hasMultipleStyles = true;
                        if (inheritedStyles.opacity !== childStyles.opacity)
                            hasMultipleStyles = true;
                        if (inheritedStyles.fontWeight !== childStyles.fontWeight)
                            hasMultipleStyles = true;
                        if (inheritedStyles.fontStyle !== childStyles.fontStyle)
                            hasMultipleStyles = true;
                        if (inheritedStyles.fontSize !== childStyles.fontSize)
                            hasMultipleStyles = true;
                        if (inheritedStyles.textDecoration !== childStyles.textDecoration)
                            hasMultipleStyles = true;
                        if (inheritedStyles.backgroundColor !== childStyles.backgroundColor)
                            hasMultipleStyles = true;
                        const runCountBefore = runs.length;
                        const mergedForChildren = mergeAncestorHighlightForRichTextRuns(childStyles, inheritedStyles);
                        node.childNodes.forEach((child) => processNode(child, mergedForChildren));
                        // display:block elements = new paragraph (a:p), add breakLine after last run
                        if (isBlock &&
                            runs.length > runCountBefore &&
                            !laysOutChildrenInHorizontalFlexRow(node, element)) {
                            runs[runs.length - 1].breakLine = true;
                        }
                    }
                }
                const elementStyles = getComputedStyles(element);
                element.childNodes.forEach((child) => processNode(child, elementStyles));
                // Trim only at element boundaries; per-node trim() drops spaces between inline siblings.
                if (runs.length > 0) {
                    runs[0].text = runs[0].text.replace(/^\s+/, '');
                    runs[runs.length - 1].text = runs[runs.length - 1].text.replace(/\s+$/, '');
                }
                // Only return rich text if there are multiple styles
                return hasMultipleStyles && runs.length > 0 ? runs : null;
            }
            /**
             * Get only direct text nodes (used for specific cases)
             */
            function getDirectTextContent(element) {
                let text = '';
                element.childNodes.forEach((node) => {
                    if (node.nodeType === Node.TEXT_NODE) {
                        text += node.textContent || '';
                    }
                });
                return text.trim();
            }
            /**
             * Get Font Awesome icon content from ::before pseudo-element
             */
            function getFontAwesomeContent(element) {
                const beforeStyle = window.getComputedStyle(element, '::before');
                let content = beforeStyle.getPropertyValue('content');
                // Content might be empty string, 'none', or actual unicode
                if (!content || content === 'none' || content === '""' || content === "''") {
                    // Fallback: try to get text content directly
                    // Font Awesome 6 might render the icon as actual text content
                    const textContent = element.textContent || '';
                    if (textContent.trim()) {
                        return textContent.trim();
                    }
                    // If still empty, return a placeholder (FA icons use unicode in Private Use Area)
                    // We'll return a generic icon character
                    return '\uf111'; // fa-circle as fallback
                }
                // Remove quotes and convert escaped unicode to actual characters
                content = content.replace(/^["']|["']$/g, '');
                // Handle escaped unicode like "\f123"
                if (content.includes('\\')) {
                    content = content.replace(/\\([0-9a-fA-F]+)/g, (_, hex) => {
                        return String.fromCharCode(parseInt(hex, 16));
                    });
                }
                return content;
            }
            /**
             * Composited opaque background behind a cell (html → … → cell), for border-color blending.
             */
            function resolveEffectiveBackgroundColor(el) {
                const chain = [];
                let node = el;
                while (node) {
                    chain.unshift(node);
                    node = node.parentElement;
                }
                let r = null;
                let g = null;
                let b = null;
                for (const n of chain) {
                    const bg = window.getComputedStyle(n).backgroundColor;
                    const match = bg.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)/);
                    if (!match)
                        continue;
                    const pr = Number(match[1]);
                    const pg = Number(match[2]);
                    const pb = Number(match[3]);
                    const pa = match[4] !== undefined ? Number(match[4]) : 1;
                    if (pa <= 0)
                        continue;
                    if (r === null) {
                        r = pr;
                        g = pg;
                        b = pb;
                    }
                    else {
                        const inv = 1 - pa;
                        r = pr * pa + r * inv;
                        g = pg * pa + g * inv;
                        b = pb * pa + b * inv;
                    }
                }
                if (r === null || g === null || b === null) {
                    return 'rgb(255, 255, 255)';
                }
                return `rgb(${Math.round(r)}, ${Math.round(g)}, ${Math.round(b)})`;
            }
            /**
             * Extract table data including column widths and row heights from rendered layout
             */
            function extractTableData(table) {
                const rows = [];
                const trs = Array.from(table.querySelectorAll('tr'));
                // Compute column count from first row
                let colCount = 0;
                const firstRowCells = trs[0]?.querySelectorAll('td, th');
                if (firstRowCells?.length) {
                    firstRowCells.forEach((c) => {
                        colCount += c.colSpan || 1;
                    });
                }
                const colWidths = new Array(colCount).fill(0);
                const rowHeights = [];
                trs.forEach((tr) => {
                    const cells = [];
                    const trRect = tr.getBoundingClientRect();
                    // Prefer content-sized row height. Flex-stretched tables (flex:1 in a tall
                    // host) report huge getBoundingClientRect heights and PPT rows look empty.
                    let contentRowH = 0;
                    let colIdx = 0;
                    tr.querySelectorAll('td, th').forEach((cell) => {
                        if (cell instanceof HTMLElement) {
                            const style = window.getComputedStyle(cell);
                            const cSpan = cell.colSpan || 1;
                            const cellRect = cell.getBoundingClientRect();
                            const wPerCol = cSpan > 0 ? cellRect.width / cSpan : 0;
                            for (let k = 0; k < cSpan && colIdx + k < colCount; k++) {
                                colWidths[colIdx + k] = Math.max(colWidths[colIdx + k] || 0, wPerCol);
                            }
                            colIdx += cSpan;
                            // Content estimate only for detecting flex-inflated empty rows.
                            const fontPx = parseFloat(style.fontSize) || 14;
                            const padY = (parseFloat(style.paddingTop) || 0) + (parseFloat(style.paddingBottom) || 0);
                            const borderY = (parseFloat(style.borderTopWidth) || 0) +
                                (parseFloat(style.borderBottomWidth) || 0);
                            const naturalH = fontPx * 1.35 + padY + borderY + 2;
                            contentRowH = Math.max(contentRowH, naturalH);
                            // Freeze the cell's own wrap points. A cell body is exported
                            // with PowerPoint's default wrapping, so a cell that needs one
                            // more line there grows its row, the table grows past the height
                            // we declared, and it covers whatever sits below it. Capturing
                            // Chromium's lines lets the export state the breaks outright.
                            const cellText = cell.textContent?.trim() || '';
                            const cellCapture = captureLayoutLines(cell, cellText);
                            cells.push({
                                text: cellText,
                                ...(cellCapture.lines.length > 1 && !cellCapture.ambiguous
                                    ? { lines: cellCapture.lines }
                                    : {}),
                                colSpan: cSpan,
                                rowSpan: cell.rowSpan || 1,
                                styles: {
                                    color: style.color,
                                    fontSize: style.fontSize,
                                    fontFamily: style.fontFamily,
                                    fontWeight: style.fontWeight,
                                    backgroundColor: style.backgroundColor,
                                    textAlign: style.textAlign,
                                    verticalAlign: style.verticalAlign || 'middle',
                                    // Cell padding must survive into PPT (zero margins glue columns: "n"+"Brute").
                                    paddingTop: style.paddingTop,
                                    paddingRight: style.paddingRight,
                                    paddingBottom: style.paddingBottom,
                                    paddingLeft: style.paddingLeft,
                                    borderTopWidth: style.borderTopWidth,
                                    borderRightWidth: style.borderRightWidth,
                                    borderBottomWidth: style.borderBottomWidth,
                                    borderLeftWidth: style.borderLeftWidth,
                                    borderTopColor: style.borderTopColor,
                                    borderRightColor: style.borderRightColor,
                                    borderBottomColor: style.borderBottomColor,
                                    borderLeftColor: style.borderLeftColor,
                                    borderTopStyle: style.borderTopStyle,
                                    borderRightStyle: style.borderRightStyle,
                                    borderBottomStyle: style.borderBottomStyle,
                                    borderLeftStyle: style.borderLeftStyle,
                                    effectiveBackgroundColor: resolveEffectiveBackgroundColor(cell),
                                },
                            });
                        }
                    });
                    // Prefer measured row height (matches HTML layout). Collapse only when
                    // the row is clearly flex-inflated empty space (>> content estimate).
                    const measured = trRect.height || 0;
                    const useH = contentRowH > 0 && measured > contentRowH * 2.5
                        ? Math.max(contentRowH, measured > 0 ? Math.min(measured, contentRowH * 1.5) : contentRowH)
                        : measured > 0
                            ? measured
                            : Math.max(1, contentRowH);
                    rowHeights.push(useH);
                    if (cells.length > 0) {
                        rows.push({ cells });
                    }
                });
                const style = window.getComputedStyle(table);
                return {
                    rows,
                    colW: colCount > 0 ? colWidths : undefined,
                    rowH: rowHeights.length > 0 ? rowHeights : undefined,
                    borderColor: style.borderColor,
                    borderWidth: style.borderWidth,
                };
            }
            /**
             * Convert CSS color string to hex for SVG (handles rgb, rgba, hex; oklch/oklab via canvas)
             */
            function cssColorToHex(color) {
                if (!color || color === 'transparent' || color === 'none')
                    return null;
                const rgb = color.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*[\d.]+)?\)/);
                if (rgb) {
                    const r = parseInt(rgb[1]).toString(16).padStart(2, '0');
                    const g = parseInt(rgb[2]).toString(16).padStart(2, '0');
                    const b = parseInt(rgb[3]).toString(16).padStart(2, '0');
                    return (r + g + b).toUpperCase();
                }
                const hex8 = color.match(/^#([0-9A-Fa-f]{8})$/);
                if (hex8)
                    return hex8[1].slice(0, 6).toUpperCase();
                if (/^#[0-9A-Fa-f]{6}$/.test(color))
                    return color.slice(1).toUpperCase();
                if (color.startsWith('oklch') || color.startsWith('oklab')) {
                    const canvas = document.createElement('canvas');
                    canvas.width = 1;
                    canvas.height = 1;
                    const ctx = canvas.getContext('2d');
                    if (!ctx)
                        return null;
                    ctx.fillStyle = color;
                    ctx.fillRect(0, 0, 1, 1);
                    const [r, g, b] = ctx.getImageData(0, 0, 1, 1).data;
                    return [r, g, b].map((n) => n.toString(16).padStart(2, '0')).join('').toUpperCase();
                }
                return null;
            }
            /** Alpha (0–1) from rgba / #RRGGBBAA / oklch; opaque colors return 1 */
            function parseColorAlpha(color) {
                if (!color || color === 'transparent' || color === 'none')
                    return 1;
                const rgbaComma = color.match(/rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)/i);
                if (rgbaComma)
                    return parseFloat(rgbaComma[4]);
                const rgbSlash = color.match(/^rgba?\(\s*(\d+)\s+(\d+)\s+(\d+)(?:\s*\/\s*([\d.]+))?\s*\)$/i);
                if (rgbSlash)
                    return rgbSlash[4] !== undefined ? parseFloat(rgbSlash[4]) : 1;
                const hex8 = color.match(/^#([0-9A-Fa-f]{8})$/i);
                if (hex8)
                    return parseInt(hex8[1].slice(6, 8), 16) / 255;
                if (color.startsWith('oklch') || color.startsWith('oklab')) {
                    const canvas = document.createElement('canvas');
                    canvas.width = 1;
                    canvas.height = 1;
                    const ctx = canvas.getContext('2d');
                    if (!ctx)
                        return 1;
                    ctx.fillStyle = color;
                    ctx.fillRect(0, 0, 1, 1);
                    return ctx.getImageData(0, 0, 1, 1).data[3] / 255;
                }
                return 1;
            }
            /**
             * Resolve `var(--name)` using :root (variables live in page CSS, not in blob SVG).
             * Use this for SVG paint attrs — element getComputedStyle can be wrong during animation
             * (e.g. .dot pulse) or conflate stroke with fill.
             */
            function resolveCssVarFromRoot(attr) {
                const m = attr.match(/var\s*\(\s*([^)]+)\s*\)/);
                if (!m)
                    return null;
                const inner = m[1].trim();
                const parts = inner.split(',');
                const varName = parts[0].trim();
                const root = document.documentElement;
                let resolved = getComputedStyle(root).getPropertyValue(varName).trim();
                if (!resolved && parts.length > 1) {
                    resolved = parts.slice(1).join(',').trim();
                }
                return resolved || null;
            }
            /**
             * Apply computed styles to SVG clone (replace currentColor, set fill/stroke/opacity from computed styles)
             * When cloning, stylesheet is lost so elements with CSS styling need their computed styles baked in.
             * We must resolve currentColor and copy computed fill/stroke/opacity to attributes.
             * IMPORTANT: Respect fill="none" — stroke-only SVGs must remain hollow.
             */
            function applyStylesToSvgClone(clone, originalSvg, fallbackColorHex) {
                const colorVal = '#' + fallbackColorHex;
                // Set color attribute so 'currentColor' references resolve
                clone.setAttribute('color', colorVal);
                // Build a map from original elements to clone elements
                const originalToClone = new Map();
                const mapElements = (orig, cloned) => {
                    originalToClone.set(orig, cloned);
                    const origChildren = Array.from(orig.children);
                    const clonedChildren = Array.from(cloned.children);
                    for (let i = 0; i < origChildren.length; i++) {
                        if (i < clonedChildren.length) {
                            mapElements(origChildren[i], clonedChildren[i]);
                        }
                    }
                };
                mapElements(originalSvg, clone);
                const walk = (origEl, clonedEl) => {
                    const s = clonedEl.getAttribute('stroke');
                    const f = clonedEl.getAttribute('fill');
                    const c = clonedEl.getAttribute('color');
                    const o = clonedEl.getAttribute('opacity');
                    // Get computed styles from original element (before cloning, while CSS is still active)
                    const computedStyle = window.getComputedStyle(origEl);
                    // Blob SVG has no stylesheet — bake text-anchor so x/y anchor matches browser (e.g. middle-centered labels).
                    const svgTextTag = origEl.localName?.toLowerCase();
                    if (svgTextTag === 'text' || svgTextTag === 'tspan') {
                        const textAnchor = computedStyle.getPropertyValue('text-anchor');
                        if (textAnchor && textAnchor !== 'auto' && textAnchor !== 'inherit') {
                            clonedEl.setAttribute('text-anchor', textAnchor);
                        }
                    }
                    /**
                     * Blob-loaded SVG has no document styles — `stroke="var(--c1)"` / `fill="var(--c1)"` won't resolve.
                     * Bake getComputedStyle() results into attributes.
                     */
                    const resolvePaintAttr = (attrVal, computedPaint) => {
                        if (!attrVal || attrVal === 'none' || attrVal === 'transparent')
                            return null;
                        if (attrVal === 'currentColor')
                            return colorVal;
                        if (!attrVal.includes('var(')) {
                            const h = cssColorToHex(attrVal);
                            if (h)
                                return '#' + h;
                        }
                        else {
                            const fromRoot = resolveCssVarFromRoot(attrVal);
                            if (fromRoot) {
                                const h = cssColorToHex(fromRoot);
                                if (h)
                                    return '#' + h;
                            }
                        }
                        const fromComputed = cssColorToHex(computedPaint);
                        return fromComputed ? '#' + fromComputed : null;
                    };
                    if (s === 'currentColor') {
                        clonedEl.setAttribute('stroke', colorVal);
                    }
                    else if (s === 'none' || s === 'transparent') {
                        clonedEl.setAttribute('stroke', 'none');
                    }
                    else {
                        const resolvedStroke = resolvePaintAttr(s, computedStyle.stroke);
                        if (resolvedStroke) {
                            clonedEl.setAttribute('stroke', resolvedStroke);
                        }
                        else if (!s || s === 'inherit') {
                            const computedStroke = cssColorToHex(computedStyle.stroke);
                            if (computedStroke && computedStroke !== '000000') {
                                clonedEl.setAttribute('stroke', '#' + computedStroke);
                            }
                        }
                    }
                    // Bake stroke presentation attributes from CSS (clone loses stylesheet)
                    const strokeWidth = computedStyle.getPropertyValue('stroke-width') || computedStyle.strokeWidth;
                    if (strokeWidth && strokeWidth !== 'none')
                        clonedEl.setAttribute('stroke-width', strokeWidth);
                    const strokeOpacity = computedStyle.getPropertyValue('stroke-opacity') || computedStyle.strokeOpacity;
                    if (strokeOpacity)
                        clonedEl.setAttribute('stroke-opacity', strokeOpacity);
                    const strokeDasharray = computedStyle.getPropertyValue('stroke-dasharray') || computedStyle.strokeDasharray;
                    if (strokeDasharray && strokeDasharray !== 'none')
                        clonedEl.setAttribute('stroke-dasharray', strokeDasharray);
                    const strokeDashoffset = computedStyle.getPropertyValue('stroke-dashoffset') || computedStyle.strokeDashoffset;
                    if (strokeDashoffset)
                        clonedEl.setAttribute('stroke-dashoffset', strokeDashoffset);
                    const strokeLinecap = computedStyle.getPropertyValue('stroke-linecap') || computedStyle.strokeLinecap;
                    if (strokeLinecap && strokeLinecap !== 'butt' && strokeLinecap !== 'inherit') {
                        clonedEl.setAttribute('stroke-linecap', strokeLinecap);
                    }
                    const strokeLinejoin = computedStyle.getPropertyValue('stroke-linejoin') || computedStyle.strokeLinejoin;
                    if (strokeLinejoin && strokeLinejoin !== 'miter' && strokeLinejoin !== 'inherit') {
                        clonedEl.setAttribute('stroke-linejoin', strokeLinejoin);
                    }
                    // Handle fill carefully to preserve fill="none" (stroke-only paths like .curve)
                    const computedFillRaw = computedStyle.fill;
                    const isFillNone = !computedFillRaw || computedFillRaw === 'none' || computedFillRaw === 'transparent' || computedFillRaw === 'rgba(0, 0, 0, 0)';
                    const hasVarFill = !!(f && f.includes('var('));
                    // Do not clear fill when a presentation fill is present: e.g. <use fill="#FFFFFF"> often
                    // reports computed fill as transparent in Chromium; forcing "none" drops the paint and the
                    // referenced <polygon> falls back to baked #000000 / color — wrong vs on-screen SVG.
                    const noPresentationFill = !f || f === 'inherit';
                    if (f === 'none' || (isFillNone && !hasVarFill && noPresentationFill)) {
                        clonedEl.setAttribute('fill', 'none');
                    }
                    else if (hasVarFill) {
                        const resolvedFill = resolvePaintAttr(f, computedStyle.fill);
                        if (resolvedFill) {
                            clonedEl.setAttribute('fill', resolvedFill);
                        }
                    }
                    else if (f === 'currentColor') {
                        clonedEl.setAttribute('fill', colorVal);
                    }
                    else if (!f || f === 'inherit') {
                        const computedFill = cssColorToHex(computedStyle.fill);
                        if (computedFill && computedFill !== '000000') {
                            clonedEl.setAttribute('fill', '#' + computedFill);
                        }
                        else {
                            let ancestor = clonedEl.parentElement;
                            let inheritedNone = false;
                            while (ancestor) {
                                const af = ancestor.getAttribute('fill');
                                if (af === 'none') {
                                    inheritedNone = true;
                                    break;
                                }
                                if (af && af !== 'inherit')
                                    break;
                                ancestor = ancestor.parentElement;
                            }
                            if (!inheritedNone) {
                                // Geometry inside <defs> (e.g. <polygon id="hex">) is instanced via <use>.
                                // Baking fallback fill here sets a *definition* fill that wins over each
                                // <use fill="#FFFFFF"> in the shadow tree — all instances turn dark/black.
                                if (!origEl.closest('defs')) {
                                    clonedEl.setAttribute('fill', colorVal);
                                }
                            }
                        }
                    }
                    else {
                        const resolvedFill = resolvePaintAttr(f, computedStyle.fill);
                        if (resolvedFill) {
                            clonedEl.setAttribute('fill', resolvedFill);
                        }
                    }
                    // Bake fill-opacity: rgba alpha is stripped when fill is written as opaque #hex
                    if (!isFillNone && clonedEl.getAttribute('fill') !== 'none') {
                        let fillAlpha = parseColorAlpha(computedFillRaw);
                        const cssFillOpacity = computedStyle.getPropertyValue('fill-opacity') || computedStyle.fillOpacity;
                        if (cssFillOpacity && cssFillOpacity !== '1') {
                            const fo = parseFloat(cssFillOpacity);
                            if (!isNaN(fo))
                                fillAlpha *= fo;
                        }
                        if (fillAlpha < 1 - 1e-6) {
                            clonedEl.setAttribute('fill-opacity', String(fillAlpha));
                        }
                    }
                    // Preserve opacity if not already set
                    if (!o && computedStyle.opacity && computedStyle.opacity !== '1') {
                        clonedEl.setAttribute('opacity', computedStyle.opacity);
                    }
                    // Resolve currentColor for color attribute
                    if (c === 'currentColor')
                        clonedEl.setAttribute('color', colorVal);
                    // Recursively process children
                    const origChildren = Array.from(origEl.children);
                    const clonedChildren = Array.from(clonedEl.children);
                    for (let i = 0; i < origChildren.length; i++) {
                        if (i < clonedChildren.length) {
                            walk(origChildren[i], clonedChildren[i]);
                        }
                    }
                };
                walk(originalSvg, clone);
            }
            const MATHML_NS = 'http://www.w3.org/1998/Math/MathML';
            /**
             * Serialize <math> to MathML string, stripping MathJax preview annotations.
             */
            function serializeMathMl(mathEl) {
                const clone = mathEl.cloneNode(true);
                clone.querySelectorAll('annotation, annotation-xml').forEach((el) => el.remove());
                if (!clone.getAttribute('xmlns')) {
                    clone.setAttribute('xmlns', MATHML_NS);
                }
                return new XMLSerializer().serializeToString(clone);
            }
            /**
             * KaTeX/MathJax hide <math> (often ~1px wide); use the visible renderer box for layout.
             */
            function resolveMathLayoutHost(mathEl) {
                // Formula plates: use the full data-pptx=formula host so OMML fills the canvas
                // (raw <math> without CSS is often ~16px tall and looks tiny in PPT).
                const formulaHost = mathEl.closest('[data-pptx="formula"]');
                if (formulaHost instanceof HTMLElement) {
                    const r = formulaHost.getBoundingClientRect();
                    if (r.width > 4 && r.height > 4)
                        return formulaHost;
                }
                // MathJax v3 (tex-svg) renders visible output in <mjx-container> (SVG),
                // while the sibling/descendant <math> inside <mjx-assistive-mml> is visually hidden.
                // Screenshooting <math> leads to clipped/partial text (e.g. only '/n').
                const mjx = mathEl.closest('mjx-container');
                if (mjx) {
                    const r = mjx.getBoundingClientRect();
                    if (r.width > 4 && r.height > 4)
                        return mjx;
                }
                const katex = mathEl.closest('.katex');
                if (katex) {
                    const r = katex.getBoundingClientRect();
                    if (r.width > 4 && r.height > 4)
                        return katex;
                }
                const display = mathEl.closest('.katex-display, .MathJax_Display, .math-display');
                if (display) {
                    const r = display.getBoundingClientRect();
                    if (r.width > 4 && r.height > 4)
                        return display;
                }
                return mathEl;
            }
            function getMathLayoutRect(mathEl) {
                return resolveMathLayoutHost(mathEl).getBoundingClientRect();
            }
            function getMathDisplayMode(mathEl) {
                if (mathEl.closest('.katex-display, .MathJax_Display, .math-display'))
                    return 'block';
                if (mathEl.getAttribute('display') === 'block')
                    return 'block';
                const host = resolveMathLayoutHost(mathEl);
                const d = window.getComputedStyle(host).display;
                if (d === 'block' || d === 'flex' || d === 'grid' || d === 'table' || d === 'list-item') {
                    return 'block';
                }
                return 'inline';
            }
            /**
             * MathJax v3 CHTML (tex-mml-chtml): visible formula is in mjx-math (often via ::before
             * per glyph). Editable MathML lives in mjx-assistive-mml > math only.
             */
            function isMathJaxVisualSubtree(element) {
                if (!(element instanceof Element))
                    return false;
                const tag = element.tagName.toLowerCase();
                // closest() only walks ancestors — mjx-container is not inside its descendant assistive-mml.
                if (tag === 'mjx-container' || tag === 'mjx-assistive-mml')
                    return false;
                if (!element.closest('mjx-container'))
                    return false;
                return element.closest('mjx-assistive-mml') === null;
            }
            function isMathJaxStructuralWrapper(element) {
                return (element instanceof HTMLElement && element.tagName.toLowerCase() === 'mjx-container');
            }
            function isKatexSubtreeForTextOmit(element) {
                if (!(element instanceof HTMLElement))
                    return false;
                if (element.classList.contains('katex') ||
                    element.classList.contains('katex-mathml') ||
                    element.classList.contains('katex-html')) {
                    return true;
                }
                if (element.closest('.katex'))
                    return true;
                return isMathJaxVisualSubtree(element);
            }
            function isKatexHtmlSubtree(element) {
                return (element instanceof HTMLElement &&
                    (element.classList.contains('katex-html') || element.closest('.katex-html') !== null));
            }
            function isKatexStructuralWrapper(element) {
                return (element instanceof HTMLElement &&
                    (element.classList.contains('katex') || element.classList.contains('katex-mathml')));
            }
            /** Native <math>, MathJax assistive MathML, or KaTeX .katex-mathml only — not CHTML/visual layers. */
            function isEditableMathElement(element) {
                if (element.tagName.toLowerCase() !== 'math')
                    return false;
                if (element.closest('mjx-container')) {
                    return element.closest('mjx-assistive-mml') !== null;
                }
                if (!element.closest('.katex'))
                    return true;
                return element.closest('.katex-mathml') !== null;
            }
            function markMathHostMapped(mathEl) {
                markDomAsPptxMapped(mathEl);
                const formulaHost = mathEl.closest('[data-pptx="formula"]');
                if (formulaHost)
                    markDomAsPptxMapped(formulaHost);
                const mjx = mathEl.closest('mjx-container');
                if (mjx)
                    markDomAsPptxMapped(mjx);
                const katexMathml = mathEl.closest('.katex-mathml');
                if (katexMathml)
                    markDomAsPptxMapped(katexMathml);
                const katex = mathEl.closest('.katex');
                if (katex) {
                    markDomAsPptxMapped(katex);
                    const katexHtml = katex.querySelector('.katex-html');
                    if (katexHtml)
                        markDomAsPptxMapped(katexHtml);
                }
                const display = mathEl.closest('.katex-display, .MathJax_Display, .math-display');
                if (display)
                    markDomAsPptxMapped(display);
            }
            /**
             * Decorative SVGs are rasterized via Playwright element screenshot (see needsScreenshot
             * backfill in inspectElements). PNG avoids pptxgenjs corrupt dual-media SVG packaging.
             */
            /**
             * True when ::after is a thin absolute bar used as a custom underline (content:'' + bg/border).
             * Such hosts must not stay merged into a wide parent text box — PPT lays out runs inside the
             * parent width and the bar's x no longer lines up with the child text.
             */
            /** ::after bar behind inline text (e.g. .highlight { position:relative } + ::after marker). */
            function isMarkerHighlightAfterPseudo(anchor) {
                if (!(anchor instanceof HTMLElement))
                    return false;
                const pa = window.getComputedStyle(anchor, '::after');
                const raw = pa.content;
                if (!raw || raw === 'none' || raw === 'normal')
                    return false;
                const textContent = raw.replace(/^["']|["']$/g, '');
                if (textContent.length > 0)
                    return false;
                const hasBg = pa.backgroundColor !== 'rgba(0, 0, 0, 0)' &&
                    pa.backgroundColor !== 'rgba(0,0,0,0)' &&
                    pa.backgroundColor !== 'transparent';
                const hasBgImg = pa.backgroundImage !== 'none';
                if (!hasBg && !hasBgImg)
                    return false;
                if (pa.position !== 'absolute' && pa.position !== 'fixed')
                    return false;
                const ph = parseFloat(pa.height) || 0;
                if (ph <= 0 || ph > 16)
                    return false;
                const z = parseInt(pa.zIndex, 10);
                if (!isNaN(z) && z < 0)
                    return true;
                const bottom = parseFloat(pa.bottom);
                if (!isNaN(bottom) && bottom >= 0 && bottom <= 12)
                    return true;
                return false;
            }
            function markerHighlightAfterBackground(anchor) {
                if (!isMarkerHighlightAfterPseudo(anchor))
                    return undefined;
                const pa = window.getComputedStyle(anchor, '::after');
                let bg = canonicalizeComputedBackgroundColor(pa.backgroundColor);
                if (!bg || bg === 'transparent' || bg === 'rgba(0, 0, 0, 0)' || bg === 'rgba(0,0,0,0)') {
                    return undefined;
                }
                const pseudoAlpha = parseColorAlpha(bg);
                const paOpacity = parseFloat(pa.opacity) || 1;
                const a = Math.max(0, Math.min(1, pseudoAlpha * paOpacity));
                const hex = cssColorToHex(bg);
                if (hex && a < 1 - 1e-6) {
                    const r = parseInt(hex.slice(0, 2), 16);
                    const g = parseInt(hex.slice(2, 4), 16);
                    const b = parseInt(hex.slice(4, 6), 16);
                    return `rgba(${r}, ${g}, ${b}, ${a})`;
                }
                return bg;
            }
            function hasUnderlineBarAfter(anchor) {
                if (isMarkerHighlightAfterPseudo(anchor))
                    return false;
                if (!(anchor instanceof HTMLElement))
                    return false;
                const pa = window.getComputedStyle(anchor, '::after');
                const raw = pa.content;
                if (!raw || raw === 'none' || raw === 'normal')
                    return false;
                const hasBg = pa.backgroundColor !== 'rgba(0, 0, 0, 0)' &&
                    pa.backgroundColor !== 'rgba(0,0,0,0)' &&
                    pa.backgroundColor !== 'transparent';
                const hasBgImg = pa.backgroundImage !== 'none';
                const hasBdr = parseFloat(pa.borderTopWidth) > 0 ||
                    parseFloat(pa.borderRightWidth) > 0 ||
                    parseFloat(pa.borderBottomWidth) > 0 ||
                    parseFloat(pa.borderLeftWidth) > 0;
                if (!hasBg && !hasBgImg && !hasBdr)
                    return false;
                if (pa.position !== 'absolute' && pa.position !== 'fixed')
                    return false;
                const ph = parseFloat(pa.height) || 0;
                const bh = parseFloat(pa.borderBottomWidth) || 0;
                const barH = Math.max(ph, bh);
                if (barH <= 0 || barH > 12)
                    return false;
                return true;
            }
            /**
             * ::before/::after that only set typographic properties (color, font-size, …) — merge as rich-text
             * runs on the host instead of a separate text box (avoids rotation / contrast issues).
             */
            function isTypographyOnlyTextPseudo(pStyle) {
                const rawContent = pStyle.content;
                if (!rawContent || rawContent === 'none' || rawContent === 'normal')
                    return false;
                const textContent = rawContent.replace(/^["']|["']$/g, '');
                if (!textContent.length)
                    return false;
                const hasBg = pStyle.backgroundColor !== 'rgba(0, 0, 0, 0)' &&
                    pStyle.backgroundColor !== 'transparent';
                const hasBgImage = pStyle.backgroundImage !== 'none';
                const hasBorder = parseFloat(pStyle.borderTopWidth) > 0 ||
                    parseFloat(pStyle.borderRightWidth) > 0 ||
                    parseFloat(pStyle.borderBottomWidth) > 0 ||
                    parseFloat(pStyle.borderLeftWidth) > 0;
                if (hasBg || hasBgImage || hasBorder)
                    return false;
                const bs = pStyle.boxShadow;
                if (bs && bs !== 'none')
                    return false;
                const filter = pStyle.filter;
                if (filter && filter !== 'none')
                    return false;
                const bgClip = pStyle.webkitBackgroundClip || pStyle.backgroundClip;
                if (bgClip === 'text')
                    return false;
                const t = pStyle.transform;
                if (t && t !== 'none') {
                    const identity = /^matrix\s*\(\s*1\s*,\s*0\s*,\s*0\s*,\s*1\s*,/.test(t) ||
                        /^matrix3d\s*\(\s*1\s*,/.test(t);
                    if (!identity)
                        return false;
                }
                return true;
            }
            function shouldMergeTypographyPseudo(host, pseudo) {
                if (!(host instanceof HTMLElement))
                    return false;
                if (host.tagName.toLowerCase() === 'li')
                    return false;
                if (pseudo === '::before' && isFontAwesomeIcon(host))
                    return false;
                if (getElementType(host) !== 'text')
                    return false;
                return isTypographyOnlyTextPseudo(window.getComputedStyle(host, pseudo));
            }
            function buildTypographyPseudoRunStyles(host, pseudo) {
                const pStyle = window.getComputedStyle(host, pseudo);
                let effectiveOpacity = parseFloat(pStyle.opacity) || 1;
                let ancestor = host;
                while (ancestor && ancestor !== document.body) {
                    effectiveOpacity *= parseFloat(window.getComputedStyle(ancestor).opacity) || 1;
                    ancestor = ancestor.parentElement;
                }
                return {
                    color: pStyle.color,
                    fontSize: pStyle.fontSize,
                    fontFamily: pStyle.fontFamily,
                    fontWeight: pStyle.fontWeight,
                    fontStyle: pStyle.fontStyle,
                    textDecoration: pStyle.textDecoration,
                    letterSpacing: pStyle.letterSpacing,
                    opacity: effectiveOpacity,
                    display: 'inline',
                };
            }
            /** Box padding/border belong on the text frame (host getTextOptions), not per-run a:highlight padding. */
            function stripTextBoxChromeFromRunStyles(styles) {
                const s = { ...styles };
                s.paddingTop = '0px';
                s.paddingRight = '0px';
                s.paddingBottom = '0px';
                s.paddingLeft = '0px';
                s.marginTop = '0px';
                s.marginRight = '0px';
                s.marginBottom = '0px';
                s.marginLeft = '0px';
                s.borderWidth = '0px';
                s.borderStyle = 'none';
                s.borderColor = 'transparent';
                for (const side of ['Left', 'Right', 'Top', 'Bottom']) {
                    s['border' + side + 'Width'] = '0px';
                    s['border' + side + 'Color'] = 'transparent';
                    s['border' + side + 'Style'] = 'none';
                }
                delete s.glyphHighlightColor;
                delete s.highlightBackdropColor;
                return s;
            }
            function mergeTypographyPseudoRichText(host, runs, excludeSubtrees, pseudo) {
                if (!shouldMergeTypographyPseudo(host, pseudo))
                    return runs;
                const pStyle = window.getComputedStyle(host, pseudo);
                const pseudoText = pStyle.content.replace(/^["']|["']$/g, '');
                if (!pseudoText)
                    return runs;
                const pseudoRun = {
                    text: pseudoText,
                    styles: buildTypographyPseudoRunStyles(host, pseudo),
                };
                let merged = runs ? [...runs] : null;
                if (!merged || merged.length === 0) {
                    const hostText = getTextContent(host, excludeSubtrees);
                    merged = hostText
                        ? [{ text: hostText, styles: stripTextBoxChromeFromRunStyles(getComputedStyles(host)) }]
                        : [];
                }
                const hostStyle = window.getComputedStyle(host);
                const flexGap = parseFloat(hostStyle.gap) || parseFloat(hostStyle.columnGap) || 0;
                // One ASCII space between pseudo and sibling text (HTML whitespace collapse); do not
                // emulate flex gap with marginLeft → multiple spaces in PPTX.
                const gapSuffix = flexGap > 0.5 ? ' ' : '';
                if (pseudo === '::before') {
                    merged = [{ ...pseudoRun, text: pseudoRun.text + gapSuffix }, ...merged];
                }
                else {
                    const gapPrefix = flexGap > 0.5 ? ' ' : '';
                    merged = [...merged, { ...pseudoRun, text: gapPrefix + pseudoRun.text }];
                }
                return merged;
            }
            /**
             * Extract visual ::before / ::after pseudo-elements as separate ElementInfo entries.
             * Uses a temporary real element to measure the pseudo-element's position via the browser layout engine.
             */
            function extractPseudoElements(element) {
                if (isMathJaxVisualSubtree(element))
                    return [];
                const items = [];
                for (const pseudo of ['::before', '::after']) {
                    // Skip ::before for Font Awesome icons (already handled separately)
                    if (pseudo === '::before' && element instanceof HTMLElement && isFontAwesomeIcon(element))
                        continue;
                    if (shouldMergeTypographyPseudo(element, pseudo))
                        continue;
                    if (pseudo === '::after' && isMarkerHighlightAfterPseudo(element))
                        continue;
                    const pStyle = window.getComputedStyle(element, pseudo);
                    const rawContent = pStyle.content;
                    // Skip if pseudo-element doesn't exist
                    if (!rawContent || rawContent === 'none' || rawContent === 'normal')
                        continue;
                    // Do not require explicit width/height from computed style here.
                    // Many decorative pseudos rely on auto sizing or left/right anchors
                    // (e.g. gradient bars), where width can be reported as "auto".
                    // We validate actual rendered size later via tempRect.
                    // Check if visually meaningful
                    const hasBg = pStyle.backgroundColor !== 'rgba(0, 0, 0, 0)' &&
                        pStyle.backgroundColor !== 'transparent';
                    const hasBgImage = pStyle.backgroundImage !== 'none';
                    const hasBorder = parseFloat(pStyle.borderTopWidth) > 0 ||
                        parseFloat(pStyle.borderRightWidth) > 0 ||
                        parseFloat(pStyle.borderBottomWidth) > 0 ||
                        parseFloat(pStyle.borderLeftWidth) > 0;
                    // rawContent is e.g. '""' (empty string literal) or '"Hello"'
                    const textContent = rawContent.replace(/^["']|["']$/g, '');
                    const hasText = textContent.length > 0;
                    if (!hasBg && !hasBgImage && !hasBorder && !hasText)
                        continue;
                    // --- Measure position via temporary real element ---
                    const temp = document.createElement('span');
                    const posProps = [
                        'position', 'display', 'width', 'height',
                        'top', 'right', 'bottom', 'left',
                        'marginTop', 'marginRight', 'marginBottom', 'marginLeft',
                        'paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft',
                        'boxSizing', 'transform',
                        'fontSize', 'fontFamily', 'fontWeight', 'fontStyle',
                        'lineHeight', 'letterSpacing', 'whiteSpace', 'textTransform',
                        'borderTopWidth', 'borderRightWidth', 'borderBottomWidth', 'borderLeftWidth',
                        'borderTopStyle', 'borderRightStyle', 'borderBottomStyle', 'borderLeftStyle',
                    ];
                    for (const prop of posProps) {
                        temp.style[prop] = pStyle[prop];
                    }
                    temp.style.visibility = 'hidden';
                    temp.style.pointerEvents = 'none';
                    temp.textContent = textContent;
                    if (pseudo === '::after') {
                        element.appendChild(temp);
                    }
                    else {
                        element.insertBefore(temp, element.firstChild);
                    }
                    const tempRect = temp.getBoundingClientRect();
                    element.removeChild(temp);
                    if (tempRect.width <= 0 || tempRect.height <= 0)
                        continue;
                    // --- Compute effective opacity (pseudo × ancestor chain) ---
                    let effectiveOpacity = parseFloat(pStyle.opacity) || 1;
                    let ancestor = element;
                    while (ancestor && ancestor !== document.body) {
                        effectiveOpacity *= parseFloat(window.getComputedStyle(ancestor).opacity) || 1;
                        ancestor = ancestor.parentElement;
                    }
                    const elType = hasText ? 'text' : 'shape';
                    // Calculate x position based on pseudo-element positioning
                    const elRect = element.getBoundingClientRect();
                    const elStyle = window.getComputedStyle(element);
                    let pseudoX = tempRect.left;
                    const borderLeft = parseFloat(elStyle.borderLeftWidth) || 0;
                    const paddingLeft = parseFloat(elStyle.paddingLeft) || 0;
                    const borderRight = parseFloat(elStyle.borderRightWidth) || 0;
                    const paddingRight = parseFloat(elStyle.paddingRight) || 0;
                    const contentWidth = elRect.width - borderLeft - paddingLeft - borderRight - paddingRight;
                    if (pseudo === '::before') {
                        // For absolutely positioned ::before with left: 0
                        if (pStyle.position === 'absolute' || pStyle.position === 'fixed') {
                            const leftVal = parseFloat(pStyle.left);
                            if (!isNaN(leftVal) && leftVal === 0) {
                                // CSS spec: left: 0 is relative to padding box (border inner edge)
                                // But for visual decorative elements like border bars, we want them
                                // to align with the parent's visual edge (border box), not inside the border.
                                // So we use the parent's border box left edge directly.
                                pseudoX = elRect.left;
                            }
                            else {
                                // Use measured position from temp element
                                pseudoX = tempRect.left;
                            }
                        }
                        else {
                            // Normal flow: first line box starts after border+padding. Do not use tempRect.left
                            // here — inserting a temp sibling while ::before still exists skews flex layout.
                            pseudoX = elRect.left + borderLeft + paddingLeft;
                        }
                    }
                    else if (pseudo === '::after') {
                        // Symmetric to ::before: appending a temp sibling while the real ::after still exists
                        // can skew measured x in flex/grid (temp ends up after in-flow content).
                        if (pStyle.position === 'absolute' || pStyle.position === 'fixed') {
                            const leftVal = parseFloat(pStyle.left);
                            const rightVal = parseFloat(pStyle.right);
                            if (!isNaN(leftVal) && leftVal === 0) {
                                pseudoX = elRect.left;
                            }
                            else if ((pStyle.left === 'auto' || isNaN(leftVal)) &&
                                !isNaN(rightVal) &&
                                rightVal === 0) {
                                pseudoX = elRect.right - tempRect.width;
                            }
                            else if (String(pStyle.left).includes('%')) {
                                const pct = parseFloat(pStyle.left);
                                if (!isNaN(pct) && contentWidth > 0) {
                                    pseudoX = elRect.left + borderLeft + paddingLeft + (contentWidth * pct) / 100;
                                }
                            }
                            else {
                                pseudoX = tempRect.left;
                            }
                        }
                        else {
                            pseudoX = tempRect.left;
                        }
                    }
                    let pseudoWidth = tempRect.width;
                    if (pseudo === '::after' &&
                        (pStyle.position === 'absolute' || pStyle.position === 'fixed') &&
                        String(pStyle.width).includes('%') &&
                        contentWidth > 0) {
                        const widthPct = parseFloat(pStyle.width);
                        if (!isNaN(widthPct)) {
                            pseudoWidth = (contentWidth * widthPct) / 100;
                        }
                    }
                    const info = {
                        type: elType,
                        tag: pseudo === '::after' ? 'after' : 'before',
                        elementId: readFragmentIdentity(element, pseudo === '::after' ? 'pseudo-after' : 'pseudo-before'),
                        x: pseudoX,
                        y: tempRect.top,
                        width: pseudoWidth,
                        height: tempRect.height,
                        styles: {
                            color: pStyle.color,
                            fontSize: pStyle.fontSize,
                            fontFamily: pStyle.fontFamily,
                            fontWeight: pStyle.fontWeight,
                            fontStyle: pStyle.fontStyle,
                            lineHeight: pStyle.lineHeight,
                            letterSpacing: pStyle.letterSpacing,
                            whiteSpace: pStyle.whiteSpace,
                            textDecoration: pStyle.textDecoration,
                            textAlign: pStyle.textAlign,
                            backgroundColor: pStyle.backgroundColor,
                            backgroundImage: pStyle.backgroundImage,
                            opacity: effectiveOpacity,
                            borderColor: pStyle.borderColor,
                            borderWidth: pStyle.borderWidth,
                            borderStyle: pStyle.borderStyle,
                            borderRadius: pStyle.borderRadius,
                            borderLeftWidth: pStyle.borderLeftWidth,
                            borderRightWidth: pStyle.borderRightWidth,
                            borderTopWidth: pStyle.borderTopWidth,
                            borderBottomWidth: pStyle.borderBottomWidth,
                            borderLeftColor: pStyle.borderLeftColor,
                            borderRightColor: pStyle.borderRightColor,
                            borderTopColor: pStyle.borderTopColor,
                            borderBottomColor: pStyle.borderBottomColor,
                            borderLeftStyle: pStyle.borderLeftStyle,
                            borderRightStyle: pStyle.borderRightStyle,
                            borderTopStyle: pStyle.borderTopStyle,
                            borderBottomStyle: pStyle.borderBottomStyle,
                            boxShadow: pStyle.boxShadow,
                            display: pStyle.display,
                            visibility: pStyle.visibility,
                            zIndex: pStyle.zIndex,
                        },
                    };
                    if (hasText) {
                        info.content = textContent;
                        info.styles.whiteSpace = 'nowrap';
                        info.layoutLines = [{
                                text: textContent,
                                x: pseudoX,
                                y: tempRect.top,
                                width: pseudoWidth,
                                height: tempRect.height,
                                startOffset: 0,
                                endOffset: textContent.length,
                            }];
                    }
                    // Pseudo is measured as a full box (e.g. absolute inset on .slice); ancestor clip-path
                    // still clips it visually — apply same polygon ∩ box as real shapes so PPTX has no
                    // full-width ghost rectangles behind trapezoids.
                    if (elType === 'shape') {
                        const clip = computeClipPathIntersection(element, {
                            x: info.x,
                            y: info.y,
                            width: info.width,
                            height: info.height,
                        });
                        if (clip) {
                            if (!clip.preserveLayoutBox) {
                                info.x = clip.bbox.left;
                                info.y = clip.bbox.top;
                                info.width = clip.bbox.width;
                                info.height = clip.bbox.height;
                            }
                            info.clipPathPolygonPx = clip.pointsRelative;
                        }
                    }
                    items.push(info);
                }
                return items;
            }
            function parseElementZIndex(el) {
                const z = window.getComputedStyle(el).zIndex;
                const parsed = Number.parseInt(z, 10);
                return Number.isNaN(parsed) ? 0 : parsed;
            }
            function compareElementsDomOrder(a, b) {
                const pos = a.compareDocumentPosition(b);
                if (pos & Node.DOCUMENT_POSITION_FOLLOWING)
                    return -1;
                if (pos & Node.DOCUMENT_POSITION_PRECEDING)
                    return 1;
                return 0;
            }
            /** Sibling paint order: lower z-index first, DOM order for ties. */
            function getChildrenInPaintOrder(parent) {
                const children = Array.from(parent.children).filter((child) => child instanceof Element);
                return children
                    .map((child, index) => ({ child, index, zIndex: parseElementZIndex(child) }))
                    .sort((a, b) => a.zIndex - b.zIndex || a.index - b.index)
                    .map((x) => x.child);
            }
            /** DOM nodes that become separate PPTX objects — hidden during needsScreenshot capture. */
            const PPTX_MAPPED_ATTR = 'data-html2pptx-mapped';
            function markDomAsPptxMapped(el, skip = false) {
                if (skip)
                    return;
                if (el instanceof HTMLElement || el instanceof SVGElement) {
                    el.setAttribute(PPTX_MAPPED_ATTR, '');
                }
            }
            /**
             * Process element and its children
             */
            async function processElement(element, depth = 0) {
                if (!element || !element.tagName)
                    return;
                if (isSvgNonRenderElement(element))
                    return;
                if (element.hasAttribute('data-pptx-preview-only') ||
                    element.hasAttribute('data-sunairum-preview-only')) {
                    return;
                }
                // DH-P0-005: runtime / navigation exclusion.
                // Skip the element and its entire subtree when it matches excludeSelector
                // or carries data-pptx-kind="ignore". Record a sample for diagnostics.
                if (element instanceof Element) {
                    const explicitIgnore = element.getAttribute('data-pptx-kind') === 'ignore';
                    const selectorMatched = excludeSelector
                        ? element.closest(excludeSelector) !== null
                        : false;
                    if (explicitIgnore || selectorMatched) {
                        if (_excludedCount.value < 5) {
                            _excludedSamples.push((explicitIgnore ? '[data-pptx-kind=ignore]' : '[excludeSelector]') +
                                ' ' +
                                (element.id ? '#' + element.id : '<' + element.tagName.toLowerCase() + '>'));
                        }
                        _excludedCount.value++;
                        return;
                    }
                    // DH-P0-009: surface unknown data-pptx-kind hints as a structured
                    // diagnostic so callers can fix their decks.
                    const kindHint = element.getAttribute('data-pptx-kind');
                    if (kindHint) {
                        const known = new Set([
                            'text', 'image', 'shape', 'table', 'group', 'decoration', 'ignore',
                        ]);
                        const normalized = kindHint.trim().toLowerCase();
                        if (normalized && !known.has(normalized)) {
                            _kindDiagnostics.push({
                                rule_id: 'DECKHTML_KIND_AMBIGUOUS',
                                severity: 'warning',
                                element_id: readElementIdentity(element) ?? null,
                                message: `Unknown data-pptx-kind="${kindHint}" on <${element.tagName.toLowerCase()}>; falling back to tag inference.`,
                                recovery: 'Use one of: text, image, shape, table, group, decoration, ignore.',
                            });
                        }
                    }
                }
                // Stamp animation group id on a group root before any info is emitted
                // or children recursed, so descendants inherit it via closest().
                stampAnimationGroupId(element);
                // const elementSelector = getElementSelector(element);
                // if (elementSelector === 'BODY > DIV.slide-container > HEADER > DIV.tag') {
                //   _debugInfo.push(`[DEBUG] Processing target element: ${elementSelector}`);
                //   _debugInfo.push(`[DEBUG]   isVisible: ${isVisible(element)}`);
                //   _debugInfo.push(`[DEBUG]   getElementType: ${getElementType(element)}`);
                //   _debugInfo.push(`[DEBUG]   Computed Styles: ${JSON.stringify(getComputedStyles(element))}`);
                // }
                // display:contents has no box (0×0 rect) but children participate in ancestor layout
                if (element instanceof HTMLElement && window.getComputedStyle(element).display === 'contents') {
                    for (const child of Array.from(element.children)) {
                        if (child instanceof Element) {
                            await processElement(child, depth + 1);
                        }
                    }
                    return;
                }
                if (element instanceof HTMLElement && element.hasAttribute(PPTX_MAPPED_ATTR)) {
                    return;
                }
                if (element instanceof SVGElement && element.hasAttribute(PPTX_MAPPED_ATTR)) {
                    return;
                }
                // KaTeX visible HTML layer — OMML comes from sibling .katex-mathml <math>
                if (isKatexHtmlSubtree(element))
                    return;
                // MathJax CHTML visual layer (mjx-math, glyph ::before, etc.) — OMML from assistive <math>
                if (isMathJaxVisualSubtree(element))
                    return;
                // KaTeX wrappers: recurse to <math> only, never emit as text
                if (isKatexStructuralWrapper(element)) {
                    for (const child of getChildrenInPaintOrder(element)) {
                        await processElement(child, depth + 1);
                    }
                    return;
                }
                // MathJax wrapper: recurse to mjx-assistive-mml > <math>, never emit mjx-math as text
                if (isMathJaxStructuralWrapper(element)) {
                    for (const child of getChildrenInPaintOrder(element)) {
                        await processElement(child, depth + 1);
                    }
                    return;
                }
                // Skip if not visible
                if (!isVisible(element))
                    return;
                const rect = docBox(element.getBoundingClientRect());
                const type = getElementType(element);
                // Complex semantic hosts have exactly one owner. Preview furniture inside the
                // host is browser-only; export either the native representation or one isolated
                // primary drawable, never both the host's fallback text and its visual child.
                if (element instanceof HTMLElement) {
                    const semanticKind = (element.getAttribute('data-pptx') || '').toLowerCase();
                    if (semanticKind === 'figure' || semanticKind === 'formula' || semanticKind === 'chart') {
                        const hasStructuredChart = semanticKind === 'chart' && element.hasAttribute('data-chart-payload');
                        if (!hasStructuredChart) {
                            const primarySelector = semanticKind === 'formula'
                                ? 'math, mjx-container, .katex, img, svg, canvas'
                                : 'img, picture img, svg, canvas, video';
                            const primary = element.querySelector(primarySelector);
                            if (primary instanceof Element) {
                                await processElement(primary, depth + 1);
                                markDomAsPptxMapped(element);
                                return;
                            }
                        }
                    }
                }
                // Native chart export: structured payload on data-pptx="chart" hosts.
                if (element instanceof HTMLElement) {
                    const pptxAttr = (element.getAttribute('data-pptx') || '').toLowerCase();
                    const chartPayloadAttr = element.getAttribute('data-chart-payload');
                    if (pptxAttr === 'chart' && chartPayloadAttr) {
                        try {
                            const parsed = JSON.parse(chartPayloadAttr);
                            const styles = getComputedStyles(element);
                            result.push({
                                type: 'chart',
                                tag: (element.tagName || 'div').toLowerCase(),
                                elementId: readElementIdentity(element),
                                semanticOwner: readElementIdentity(element),
                                semanticKind: 'chart',
                                animationRaw: readAnimationRaw(element),
                                animationGroupId: readAnimationGroupId(element),
                                x: rect.left,
                                y: rect.top,
                                width: rect.width,
                                height: rect.height,
                                styles,
                                chartPayload: parsed,
                            });
                            markDomAsPptxMapped(element);
                            return;
                        }
                        catch (e) {
                            console.warn('Failed to parse data-chart-payload:', e);
                        }
                    }
                }
                // Table hosts: native editable <table> + full-host chrome card (radius/shadow
                // match HTML). Corner chips clip square PPT table cells to the rounded card.
                if (element instanceof HTMLElement && rect.width > 8 && rect.height > 8) {
                    const pptxKind = (element.getAttribute('data-pptx') || '').toLowerCase();
                    const hasTableChromeMarker = pptxKind === 'table' ||
                        element.hasAttribute('data-sunairum-table-chrome');
                    if (hasTableChromeMarker) {
                        if (element.hasAttribute('data-sunairum-force-table-raster')) {
                            const styles = getComputedStyles(element);
                            const info = {
                                type: 'image',
                                tag: (element.tagName || 'div').toLowerCase(),
                                elementId: readElementIdentity(element),
                                animationRaw: readAnimationRaw(element),
                                animationGroupId: readAnimationGroupId(element),
                                x: rect.left,
                                y: rect.top,
                                width: rect.width,
                                height: rect.height,
                                styles,
                            };
                            assignScreenshotFallback(element, info, 'table-chrome');
                            result.push(info);
                            return;
                        }
                        const chromeEl = element.querySelector('[data-sunairum-table-chrome]') ||
                            element;
                        const innerTable = element.querySelector('table');
                        const tableRectRaw = innerTable instanceof HTMLTableElement
                            ? innerTable.getBoundingClientRect()
                            : null;
                        const tableRect = tableRectRaw ? docBox(tableRectRaw) : null;
                        // Full host card (HTML overflow:hidden + border-radius), not content-shrunk.
                        const plateW = rect.width;
                        const plateH = rect.height;
                        const plateX = rect.left;
                        const plateY = rect.top;
                        const chromeStyles = getComputedStyles(chromeEl);
                        const hostStyles = getComputedStyles(element);
                        const minSide = Math.min(plateW, plateH);
                        const rawBr = Math.max(parseFloat(String(chromeStyles.borderRadius || '0')) || 0, parseFloat(String(hostStyles.borderRadius || '0')) || 0);
                        const cardBr = Math.max(0, Math.min(rawBr, minSide / 2));
                        chromeStyles.borderRadius = cardBr > 0 ? `${cardBr}px` : '0px';
                        if (!chromeStyles.boxShadow || chromeStyles.boxShadow === 'none') {
                            chromeStyles.boxShadow = hostStyles.boxShadow;
                        }
                        const chromeShape = {
                            type: 'shape',
                            tag: (chromeEl.tagName || 'div').toLowerCase(),
                            elementId: readFragmentIdentity(element, 'table-chrome'),
                            semanticOwner: readElementIdentity(element),
                            semanticKind: 'table',
                            animationRaw: readAnimationRaw(element),
                            animationGroupId: readAnimationGroupId(element),
                            x: plateX,
                            y: plateY,
                            width: plateW,
                            height: plateH,
                            styles: chromeStyles,
                            // roundRect card (not ellipse); radius comes from CSS above.
                            tableChrome: true,
                        };
                        result.push(chromeShape);
                        if (innerTable instanceof HTMLTableElement) {
                            // Stamp host clip so convertTableElement can scale rows to fit.
                            innerTable.__deckhtmlTableHostBounds = {
                                x: rect.left,
                                y: rect.top,
                                width: rect.width,
                                height: rect.height,
                            };
                            innerTable.__deckhtmlSemanticOwner = readElementIdentity(element);
                            innerTable.__deckhtmlSemanticKind = 'table';
                            await processElement(innerTable, depth + 1);
                        }
                        // Native tables are rectangular — cover square corners with slide-bg chips
                        // so the card reads as the HTML rounded (oval-corner) plate.
                        if (cardBr >= 2 && innerTable instanceof HTMLTableElement) {
                            const slideEl = element.closest('.slide') ||
                                document.querySelector('.slide') ||
                                document.body;
                            const slideBg = window.getComputedStyle(slideEl).backgroundColor || 'rgb(255, 255, 255)';
                            // Always mask all four card corners (no-op over empty white chrome).
                            const corners = [
                                { id: 'tl', x: plateX, y: plateY },
                                { id: 'tr', x: plateX + plateW - cardBr, y: plateY },
                                { id: 'bl', x: plateX, y: plateY + plateH - cardBr },
                                { id: 'br', x: plateX + plateW - cardBr, y: plateY + plateH - cardBr },
                            ];
                            for (const c of corners) {
                                const poly = sampleCornerChipPolygon(c.id, cardBr);
                                if (!poly || poly.length < 3)
                                    continue;
                                result.push({
                                    type: 'shape',
                                    tag: 'div',
                                    elementId: readFragmentIdentity(element, `table-corner-${c.id}`),
                                    x: c.x,
                                    y: c.y,
                                    width: cardBr,
                                    height: cardBr,
                                    styles: {
                                        backgroundColor: slideBg,
                                        borderWidth: '0px',
                                        borderStyle: 'none',
                                        borderColor: 'transparent',
                                        borderRadius: '0px',
                                        boxShadow: 'none',
                                        opacity: '1',
                                    },
                                    clipPathPolygonPx: poly,
                                });
                            }
                        }
                        markDomAsPptxMapped(element);
                        if (chromeEl !== element)
                            markDomAsPptxMapped(chromeEl);
                        return;
                    }
                }
                // CSS border triangles (width/height ~0 + three transparent borders).
                if (element instanceof HTMLElement && (type === 'shape' || type === 'container')) {
                    const triStyle = window.getComputedStyle(element);
                    if (isCssBorderTriangle(triStyle, rect) &&
                        rect.width >= 4 &&
                        rect.height >= 4 &&
                        !readElementIdentity(element)) {
                        const screenshotId = `screenshot-${Math.random().toString(36).slice(2, 10)}`;
                        element.setAttribute('data-screenshot', screenshotId);
                        result.push({
                            type: 'image',
                            tag: (element.tagName || 'div').toLowerCase(),
                            elementId: readElementIdentity(element),
                            animationRaw: readAnimationRaw(element),
                            animationGroupId: readAnimationGroupId(element),
                            x: rect.left,
                            y: rect.top,
                            width: Math.max(rect.width, 8),
                            height: Math.max(rect.height, 8),
                            styles: getComputedStyles(element),
                            needsScreenshot: true,
                            screenshotSelector: `[data-screenshot="${screenshotId}"]`,
                            screenshotBakesOpacity: true,
                            rasterMethod: 'screenshot',
                            rasterReason: 'flex-icon-badge',
                            forceObjectFitContain: true,
                        });
                        markDomAsPptxMapped(element);
                        return;
                    }
                }
                // Flex-centered glyph badges (circles, rounded squares, FA icons).
                // Native PPT ellipse text and Playwright sibling-isolation screenshots both
                // mis-place glyphs; bake a hi-DPI canvas with true center fillText instead.
                if (element instanceof HTMLElement &&
                    rect.width > 8 &&
                    rect.height > 8 &&
                    (type === 'shape' || type === 'text' || type === 'icon') &&
                    rect.width <= 64 &&
                    rect.height <= 64 &&
                    rect.width >= 12 &&
                    rect.height >= 12) {
                    const s = window.getComputedStyle(element);
                    const flexCenter = (s.display === 'flex' || s.display === 'inline-flex') &&
                        s.alignItems === 'center' &&
                        s.justifyContent === 'center';
                    const br = s.borderRadius || '';
                    const minSide = Math.min(rect.width, rect.height);
                    const brPx = parseFloat(br) || 0;
                    const isRound = br.includes('50%') ||
                        brPx >= minSide / 2 - 1;
                    const isSquareRounded = !isRound && brPx >= 4;
                    const isFaIcon = type === 'icon' || isFontAwesomeIcon(element);
                    let glyph = '';
                    if (isFaIcon) {
                        glyph = getFontAwesomeContent(element);
                    }
                    else {
                        glyph = (element.textContent || '').replace(/\s+/g, '').trim();
                    }
                    const glyphOk = glyph.length >= 1 && glyph.length <= 4;
                    if (flexCenter &&
                        (isRound || isSquareRounded) &&
                        glyphOk &&
                        !readElementIdentity(element)) {
                        try {
                            const dpr = 3;
                            const w = Math.max(1, Math.round(rect.width));
                            const h = Math.max(1, Math.round(rect.height));
                            const canvas = document.createElement('canvas');
                            canvas.width = w * dpr;
                            canvas.height = h * dpr;
                            const ctx = canvas.getContext('2d');
                            if (ctx) {
                                ctx.scale(dpr, dpr);
                                const cx = w / 2;
                                const cy = h / 2;
                                const bw = Math.max(parseFloat(s.borderTopWidth) || 0, parseFloat(s.borderLeftWidth) || 0);
                                const inset = bw / 2;
                                const drawW = w - bw;
                                const drawH = h - bw;
                                const bg = s.backgroundColor;
                                const fillBg = () => {
                                    if (!bg || bg === 'transparent' || bg === 'rgba(0, 0, 0, 0)')
                                        return;
                                    ctx.fillStyle = bg;
                                    if (isRound) {
                                        const r = Math.max(0.5, Math.min(cx, cy) - inset);
                                        ctx.beginPath();
                                        ctx.arc(cx, cy, r, 0, Math.PI * 2);
                                        ctx.fill();
                                    }
                                    else {
                                        const rx = Math.min(brPx, drawW / 2, drawH / 2);
                                        ctx.beginPath();
                                        if (typeof ctx.roundRect === 'function') {
                                            ctx.roundRect(inset, inset, drawW, drawH, rx);
                                        }
                                        else {
                                            ctx.rect(inset, inset, drawW, drawH);
                                        }
                                        ctx.fill();
                                    }
                                };
                                const strokeBorder = () => {
                                    if (bw <= 0)
                                        return;
                                    const bc = s.borderTopColor || s.borderColor || s.color;
                                    if (!bc || bc === 'transparent' || bc === 'rgba(0, 0, 0, 0)')
                                        return;
                                    ctx.strokeStyle = bc;
                                    ctx.lineWidth = bw;
                                    if (isRound) {
                                        const r = Math.max(0.5, Math.min(cx, cy) - inset);
                                        ctx.beginPath();
                                        ctx.arc(cx, cy, r, 0, Math.PI * 2);
                                        ctx.stroke();
                                    }
                                    else {
                                        const rx = Math.min(brPx, drawW / 2, drawH / 2);
                                        ctx.beginPath();
                                        if (typeof ctx.roundRect === 'function') {
                                            ctx.roundRect(inset, inset, drawW, drawH, rx);
                                        }
                                        else {
                                            ctx.rect(inset, inset, drawW, drawH);
                                        }
                                        ctx.stroke();
                                    }
                                };
                                fillBg();
                                strokeBorder();
                                const fontWeight = s.fontWeight || '700';
                                const fontSize = s.fontSize || '14px';
                                const fontFamily = s.fontFamily || 'Arial, sans-serif';
                                ctx.fillStyle = s.color || '#000000';
                                ctx.textAlign = 'center';
                                ctx.textBaseline = 'middle';
                                const beforeGlyph = ctx.getImageData(0, 0, canvas.width, canvas.height);
                                ctx.font = `${fontWeight} ${fontSize} "Apple Symbols","Segoe UI Symbol","Noto Sans Symbols",${fontFamily}`;
                                ctx.fillText(glyph, cx, cy + 0.5);
                                let ink = canvasInkDelta(ctx, beforeGlyph);
                                if (ink < 8) {
                                    ctx.font = `${fontWeight} ${fontSize} ${fontFamily}`;
                                    ctx.fillText(glyph, cx, cy + 0.5);
                                    ink = canvasInkDelta(ctx, beforeGlyph);
                                }
                                const styles = getComputedStyles(element);
                                styles.objectFit = 'contain';
                                styles.paddingTop = '0px';
                                styles.paddingRight = '0px';
                                styles.paddingBottom = '0px';
                                styles.paddingLeft = '0px';
                                if (ink >= 8) {
                                    const dataUrl = canvas.toDataURL('image/png');
                                    result.push({
                                        type: 'image',
                                        tag: (element.tagName || 'div').toLowerCase(),
                                        elementId: readElementIdentity(element),
                                        animationRaw: readAnimationRaw(element),
                                        animationGroupId: readAnimationGroupId(element),
                                        x: rect.left,
                                        y: rect.top,
                                        width: rect.width,
                                        height: rect.height,
                                        styles,
                                        src: dataUrl,
                                        dataUrl,
                                        forceObjectFitContain: true,
                                        rasterMethod: 'canvas-export',
                                        rasterReason: 'flex-icon-badge',
                                    });
                                    markDomAsPptxMapped(element);
                                    return;
                                }
                                const screenshotId = `screenshot-${Math.random().toString(36).slice(2, 10)}`;
                                element.setAttribute('data-screenshot', screenshotId);
                                result.push({
                                    type: 'image',
                                    tag: (element.tagName || 'div').toLowerCase(),
                                    elementId: readElementIdentity(element),
                                    animationRaw: readAnimationRaw(element),
                                    animationGroupId: readAnimationGroupId(element),
                                    x: rect.left,
                                    y: rect.top,
                                    width: rect.width,
                                    height: rect.height,
                                    styles,
                                    needsScreenshot: true,
                                    screenshotSelector: `[data-screenshot="${screenshotId}"]`,
                                    screenshotBakesOpacity: true,
                                    forceObjectFitContain: true,
                                    rasterMethod: 'screenshot',
                                    rasterReason: 'flex-icon-badge',
                                });
                                markDomAsPptxMapped(element);
                                return;
                            }
                        }
                        catch (e) {
                            console.warn('flex icon badge canvas bake failed:', e);
                        }
                    }
                }
                // Debug: background fill vs background image layering
                // (prints once per matched element; safe in production, low volume)
                if (element instanceof HTMLElement && element.classList.contains('bg-primary-pattern')) {
                    const style = window.getComputedStyle(element);
                    const elementSelector = getElementSelector(element);
                    _debugInfo.push(`[DEBUG_BG] element: ${elementSelector}`);
                    _debugInfo.push(`[DEBUG_BG]   type=${type} w=${rect.width} h=${rect.height} zIndex=${style.zIndex}`);
                    _debugInfo.push(`[DEBUG_BG]   backgroundColor(raw)=${style.backgroundColor}`);
                    _debugInfo.push(`[DEBUG_BG]   backgroundColor(canon)=${canonicalizeComputedBackgroundColor(style.backgroundColor)}`);
                    _debugInfo.push(`[DEBUG_BG]   backgroundImage=${style.backgroundImage}`);
                    _debugInfo.push(`[DEBUG_BG]   opacity=${style.opacity}`);
                }
                // Skip purely decorative shape elements that sit behind content (z-index < 0)
                // e.g. <div class="border-2 rounded-lg -z-10"> - border-only frame behind image
                if (type === 'shape') {
                    const style = window.getComputedStyle(element);
                    const zIndex = parseInt(style.zIndex, 10);
                    const hasBg = (style.backgroundColor !== 'rgba(0, 0, 0, 0)' && style.backgroundColor !== 'transparent') ||
                        style.backgroundImage !== 'none';
                    const hasBorder = parseFloat(style.borderWidth) > 0;
                    if (!isNaN(zIndex) && zIndex < 0 && hasBorder && !hasBg) {
                        return; // Skip decorative border-only background elements
                    }
                }
                // MathML → OMML in Node; screenshot fallback if conversion fails
                if (type === 'math') {
                    if (!isEditableMathElement(element))
                        return;
                    const layoutHost = resolveMathLayoutHost(element);
                    const layoutRect = getMathLayoutRect(element);
                    const mathml = serializeMathMl(element);
                    const screenshotId = `screenshot-math-${Math.random().toString(36).slice(2, 10)}`;
                    layoutHost.setAttribute('data-screenshot', screenshotId);
                    const styles = getComputedStyles(layoutHost);
                    let effectiveOpacity = parseFloat(window.getComputedStyle(layoutHost).opacity) || 1;
                    for (let parent = layoutHost.parentElement; parent && parent !== document.body; parent = parent.parentElement) {
                        effectiveOpacity *= parseFloat(window.getComputedStyle(parent).opacity) || 1;
                    }
                    styles.opacity = effectiveOpacity;
                    // Scale Office Math to the plate. Fractions paint ~2.7× font height —
                    // a flat 0.38×hostH overflowed the blue host (O24).
                    const hostH = layoutRect.height || 0;
                    const hostW = layoutRect.width || 0;
                    const computedFs = parseFloat(String(styles.fontSize || '')) || 16;
                    if (hostH >= 48) {
                        const padT = parseFloat(String(styles.paddingTop || '0')) || 0;
                        const padB = parseFloat(String(styles.paddingBottom || '0')) || 0;
                        const air = Math.max(14, hostH * 0.12);
                        const usable = Math.max(20, hostH - padT - padB - air);
                        const fracCount = (mathml.match(/<mfrac\b/gi) || []).length;
                        const heightMul = fracCount >= 2 ? 3.4 : fracCount === 1 ? 2.7 : 1.4;
                        let fitted = usable / heightMul;
                        if (hostW > 40)
                            fitted = Math.min(fitted, hostW / 17);
                        fitted = Math.min(64, Math.max(13, fitted));
                        if (computedFs > 12)
                            fitted = Math.min(computedFs, fitted);
                        styles.fontSize = `${Math.round(fitted)}px`;
                        styles.textAlign = styles.textAlign || 'center';
                    }
                    const mathFallbackText = (element.textContent ?? '')
                        .replace(/\s+/g, ' ')
                        .trim()
                        .slice(0, 500);
                    result.push({
                        type: 'math',
                        tag: 'math',
                        elementId: readFragmentIdentity(layoutHost, 'native-formula'),
                        semanticOwner: readElementIdentity(layoutHost),
                        semanticKind: 'formula',
                        x: layoutRect.left,
                        y: layoutRect.top,
                        width: layoutRect.width,
                        height: layoutRect.height,
                        styles,
                        mathml,
                        mathDisplayMode: getMathDisplayMode(element),
                        mathFallbackText: mathFallbackText || undefined,
                        screenshotSelector: `[data-screenshot="${screenshotId}"]`,
                        animationGroupId: readAnimationGroupId(element),
                    });
                    markMathHostMapped(element);
                    return;
                }
                // iframe: record a placeholder; Node side opens the document in a new page.
                if (type === 'iframe') {
                    const iframeEl = element;
                    const iframeId = `iframe-${Math.random().toString(36).slice(2, 10)}`;
                    iframeEl.setAttribute('data-deckhtml-iframe', iframeId);
                    const styles = getComputedStyles(iframeEl);
                    const contentW = Math.max(1, Math.round(iframeEl.offsetWidth || iframeEl.clientWidth || rect.width));
                    const contentH = Math.max(1, Math.round(iframeEl.offsetHeight || iframeEl.clientHeight || rect.height));
                    let scale = 1;
                    const transform = window.getComputedStyle(iframeEl).transform;
                    if (transform && transform !== 'none') {
                        const m2 = transform.match(/^matrix\(([^)]+)\)$/);
                        const m3 = transform.match(/^matrix3d\(([^)]+)\)$/);
                        if (m2) {
                            const p = m2[1].split(',').map((v) => parseFloat(v.trim()));
                            const a = p[0] ?? 1;
                            const b = p[1] ?? 0;
                            scale = Math.sqrt(a * a + b * b) || 1;
                        }
                        else if (m3) {
                            const p = m3[1].split(',').map((v) => parseFloat(v.trim()));
                            const a = p[0] ?? 1;
                            const b = p[1] ?? 0;
                            scale = Math.sqrt(a * a + b * b) || 1;
                        }
                        else {
                            const sm = transform.match(/scale\(\s*([-\d.]+)(?:\s*,\s*([-\d.]+))?\s*\)/);
                            if (sm)
                                scale = Math.abs(parseFloat(sm[1])) || 1;
                        }
                    }
                    // Prefer visual/content ratio when transform parsing is ambiguous.
                    if (contentW > 0 && rect.width > 0) {
                        const ratio = rect.width / contentW;
                        if (Math.abs(ratio - scale) > 0.02 && ratio > 0.05 && ratio < 20) {
                            scale = ratio;
                        }
                    }
                    const srcAttr = iframeEl.getAttribute('src') || '';
                    const srcdoc = iframeEl.getAttribute('srcdoc') || '';
                    result.push({
                        type: 'iframe',
                        tag: 'iframe',
                        elementId: readElementIdentity(element),
                        animationRaw: readAnimationRaw(element),
                        animationGroupId: readAnimationGroupId(element),
                        x: rect.left,
                        y: rect.top,
                        width: rect.width,
                        height: rect.height,
                        styles,
                        iframeSrc: iframeEl.src || srcAttr || undefined,
                        iframeSrcdoc: srcdoc || undefined,
                        iframeName: iframeEl.name || undefined,
                        iframeSelector: `[data-deckhtml-iframe="${iframeId}"]`,
                        iframeContentWidth: contentW,
                        iframeContentHeight: contentH,
                        iframeScale: scale,
                        iframeBaseUrl: document.baseURI || location.href,
                    });
                    markDomAsPptxMapped(iframeEl);
                    return;
                }
                // Editor-addressable SVGs must stay editable in PowerPoint. Decompose
                // their primitives into native shapes/text instead of exporting one
                // opaque SVG picture. Unidentified third-party SVG assets keep the
                // image path as an intentional visual asset fallback.
                if (type === 'svg') {
                    if (element.closest?.('mjx-container')) {
                        return;
                    }
                    const svgIdentity = readElementIdentity(element);
                    if (svgIdentity) {
                        const children = getChildrenInPaintOrder(element);
                        for (let index = 0; index < children.length; index++) {
                            const child = children[index];
                            if (isSvgNonRenderElement(child))
                                continue;
                            if (!child.getAttribute(_identityAttr)) {
                                child.setAttribute(_identityAttr, `${svgIdentity}__svg-${index + 1}`);
                            }
                            await processElement(child, depth + 1);
                        }
                        markDomAsPptxMapped(element);
                        return;
                    }
                    emitSvgAsImage(element, rect);
                    return;
                }
                // Skip containers unless they have visual properties.
                // But container pseudo-elements (::before/::after) can still be visual and
                // must be extracted before the early return (e.g. decorative gradient lines).
                if (type === 'container' && depth > 0) {
                    const pseudoItems = extractPseudoElements(element);
                    for (const pi of pseudoItems) {
                        result.push(pi);
                    }
                    // A layout-only container is not emitted itself, but any extracted
                    // pseudo-elements are. Mark the host so isolated screenshot capture
                    // suppresses those pseudos instead of baking a duplicate copy into
                    // the raster background.
                    if (pseudoItems.length > 0) {
                        markDomAsPptxMapped(element);
                    }
                    // L1: merge consecutive bare inline text children (label+body spans).
                    // Capture host after null-check — nested fns do not keep TS narrowing.
                    const containerHost = element;
                    async function processContainerChildrenGrouped() {
                        function isBareInlineTextChild(ch) {
                            if (!(ch instanceof HTMLElement))
                                return false;
                            if (getElementType(ch) !== 'text')
                                return false;
                            const cs = window.getComputedStyle(ch);
                            const d = cs.display || '';
                            if (d === 'block' ||
                                d === 'flex' ||
                                d === 'inline-flex' ||
                                d === 'grid' ||
                                d === 'list-item' ||
                                d === 'flow-root' ||
                                d === 'table') {
                                return false;
                            }
                            const hasBg = (cs.backgroundColor !== 'rgba(0, 0, 0, 0)' &&
                                cs.backgroundColor !== 'transparent') ||
                                cs.backgroundImage !== 'none';
                            const radius = parseFloat(cs.borderRadius) || 0;
                            if (hasBg && (d === 'inline-block' || radius >= 4))
                                return false;
                            return true;
                        }
                        const kids = getChildrenInPaintOrder(containerHost);
                        let ki = 0;
                        while (ki < kids.length) {
                            const child = kids[ki];
                            if (isBareInlineTextChild(child)) {
                                let kj = ki + 1;
                                while (kj < kids.length && isBareInlineTextChild(kids[kj]))
                                    kj++;
                                const group = kids.slice(ki, kj);
                                const head = group[0];
                                if (group.length === 1) {
                                    await processElement(head, depth + 1);
                                }
                                else {
                                    const parentEl = head.parentElement;
                                    if (!parentEl) {
                                        for (const g of group)
                                            await processElement(g, depth + 1);
                                    }
                                    else {
                                        const wrap = document.createElement('span');
                                        wrap.setAttribute('data-deckhtml-text-flow', '1');
                                        wrap.style.cssText = 'display:inline;';
                                        parentEl.insertBefore(wrap, head);
                                        for (const g of group)
                                            wrap.appendChild(g);
                                        try {
                                            await processElement(wrap, depth + 1);
                                        }
                                        finally {
                                            while (wrap.firstChild)
                                                parentEl.insertBefore(wrap.firstChild, wrap);
                                            wrap.remove();
                                        }
                                    }
                                }
                                ki = kj;
                            }
                            else {
                                await processElement(child, depth + 1);
                                ki++;
                            }
                        }
                    }
                    await processContainerChildrenGrouped();
                    return;
                }
                // For shape elements with children, extract both the container shape
                // and the text children separately
                const shouldExtractChildrenSeparately = type === 'shape' && element.children.length > 0;
                // For text elements with decorative children (e.g. legend: <span><span class="dot"></span> 文本</span>),
                // use text node position so text doesn't overlap with preceding shapes/icons
                // Only truly visual element types count as "decorative".
                // Structural tags like <br> ('container') must NOT trigger textRect shrinking.
                const decorativeTypes = new Set(['icon', 'image', 'shape', 'canvas', 'svg', 'math']);
                /**
                 * Text hosts (e.g. h1) do not recurse into merged inline children, and textExcludeSubtrees
                 * only lists direct children. A positioned underline <div> nested under
                 * <span><span>…</span></span> would never be visited by processElement otherwise.
                 * Skip subtrees rooted at direct excluded children — those get a full processElement pass.
                 */
                function collectNestedVisualDecorationsFromTextHost(host, excludedDirectChildren) {
                    const acc = [];
                    function walk(parent) {
                        for (const child of Array.from(parent.children)) {
                            if (!(child instanceof Element))
                                continue;
                            if (excludedDirectChildren?.has(child))
                                continue;
                            if (!isVisible(child))
                                continue;
                            const ct = getElementType(child);
                            if (decorativeTypes.has(ct)) {
                                acc.push(child);
                            }
                            walk(child);
                        }
                    }
                    walk(host);
                    return acc;
                }
                /**
                 * ::before / ::after on descendants merged into a text host (e.g. <p><span class="x">…</span></p>)
                 * are never seen: only the host gets extractPseudoElements. Collect pseudos from non-decorative
                 * descendants; skip decorative subtrees (they get their own processElement + extractPseudo).
                 */
                function collectMergedTextSubtreePseudoElements(host, excludedDirectChildren) {
                    const acc = [];
                    function walk(parent) {
                        for (const child of Array.from(parent.children)) {
                            if (!(child instanceof Element))
                                continue;
                            if (excludedDirectChildren?.has(child))
                                continue;
                            if (!isVisible(child))
                                continue;
                            const ct = getElementType(child);
                            if (decorativeTypes.has(ct)) {
                                continue;
                            }
                            acc.push(...extractPseudoElements(child));
                            walk(child);
                        }
                    }
                    walk(host);
                    return acc;
                }
                const hasDecorativeChildren = type === 'text' &&
                    element.children.length > 0 &&
                    Array.from(element.children).some(
                    // SVG lives under SVGElement, not HTMLElement — must still count as in-flow decoration
                    (child) => child instanceof Element && (decorativeTypes.has(getElementType(child))
                        // The authoring contract *mandates* data-pptx-kind="decoration"
                        // for ornament, and "decoration" is not one of the inferred
                        // types above — so the one marker authors are told to use was
                        // the one this test could not see. A flex row holding a bullet
                        // dot and its own copy therefore exported with the text starting
                        // under the dot instead of 17px clear of it.
                        || child.getAttribute('data-pptx-kind') === 'decoration'));
                // Check for in-flow ::before pseudo-element that occupies layout space
                // (e.g. .subtitle::before { content:''; width:40px; height:3px; background:#2d3436; }
                //  or .subtitle::before { content:'•'; color:… } in flex with gap)
                // When present, text content is pushed to the right in flex/block layout,
                // so we need to measure actual text position via Range.
                const hasInFlowPseudoBefore = type === 'text' && (() => {
                    if (element instanceof HTMLElement && shouldMergeTypographyPseudo(element, '::before')) {
                        return false;
                    }
                    const bs = window.getComputedStyle(element, '::before');
                    if (!bs.content || bs.content === 'none' || bs.content === 'normal')
                        return false;
                    if (bs.position === 'absolute' || bs.position === 'fixed')
                        return false;
                    const hasBg = bs.backgroundColor !== 'rgba(0, 0, 0, 0)' && bs.backgroundColor !== 'transparent';
                    const hasBgImg = bs.backgroundImage !== 'none';
                    const hasBdr = parseFloat(bs.borderTopWidth) > 0 || parseFloat(bs.borderRightWidth) > 0 ||
                        parseFloat(bs.borderBottomWidth) > 0 || parseFloat(bs.borderLeftWidth) > 0;
                    const pseudoText = bs.content.replace(/^["']|["']$/g, '');
                    const hasPseudoText = pseudoText.length > 0;
                    if (!hasBg && !hasBgImg && !hasBdr && !hasPseudoText)
                        return false;
                    const bw = parseFloat(bs.width), bh = parseFloat(bs.height);
                    if (!isNaN(bw) && bw > 0 && !isNaN(bh) && bh > 0)
                        return true;
                    // Text bullets (e.g. content:'•') may report auto size — measure like li bullets
                    if (hasPseudoText) {
                        const temp = document.createElement('span');
                        temp.style.visibility = 'hidden';
                        temp.style.pointerEvents = 'none';
                        temp.style.display = 'inline';
                        temp.style.fontSize = bs.fontSize;
                        temp.style.fontFamily = bs.fontFamily;
                        temp.style.fontWeight = bs.fontWeight;
                        temp.style.fontStyle = bs.fontStyle;
                        temp.style.letterSpacing = bs.letterSpacing;
                        temp.textContent = pseudoText;
                        element.insertBefore(temp, element.firstChild);
                        const tr = temp.getBoundingClientRect();
                        element.removeChild(temp);
                        return tr.width > 0 && tr.height > 0;
                    }
                    return false;
                })();
                // Children merged into the parent's text box only when they participate in the same inline
                // flow as preceding siblings. Non-inline-level (CSS block / flow-root / list-item) text
                // subtrees must be separate ElementInfo so they are not flattened into the parent shape.
                // Previously, "preceding text" skipped all later children — that incorrectly merged
                // display:block boxes (e.g. .quote-block) into the parent paragraph.
                // Exception: flex + justify-content space-* distributes items to opposite ends — preceding
                // text is intentional (e.g. .ill-header: label left, badge span right).
                let textExcludeSubtrees;
                if (type === 'text' && element.children.length > 0) {
                    function hasPrecedingText(parent, beforeChild) {
                        for (const node of Array.from(parent.childNodes)) {
                            if (node === beforeChild)
                                break;
                            if (node.nodeType === Node.TEXT_NODE && (node.textContent?.trim() ?? '').length > 0)
                                return true;
                            if (node.nodeType === Node.ELEMENT_NODE && (node.textContent?.trim() ?? '').length > 0)
                                return true;
                        }
                        return false;
                    }
                    const parentFlowStyle = window.getComputedStyle(element);
                    const flexDistributesSpace = (parentFlowStyle.display === 'flex' || parentFlowStyle.display === 'inline-flex') &&
                        /space-(between|around|evenly)/.test(parentFlowStyle.justifyContent || '');
                    textExcludeSubtrees = new Set();
                    if (element instanceof HTMLElement) {
                        element.querySelectorAll('.katex').forEach((katexEl) => {
                            textExcludeSubtrees.add(katexEl);
                        });
                        element.querySelectorAll('mjx-container').forEach((mjxEl) => {
                            textExcludeSubtrees.add(mjxEl);
                        });
                    }
                    const separateInlineChildTypes = new Set([
                        'icon',
                        'image',
                        'shape',
                        'canvas',
                        'svg',
                        'math',
                    ]);
                    for (const ch of Array.from(element.children)) {
                        if (!(ch instanceof Element))
                            continue;
                        const childStyle = window.getComputedStyle(ch);
                        const childDisplay = childStyle.display || '';
                        const childType = getElementType(ch);
                        const isFlowBreakingBlockTextChild = childDisplay === 'block' ||
                            childDisplay === 'flow-root' ||
                            childDisplay === 'list-item';
                        const isFlexColumnChild = (childDisplay === 'flex' || childDisplay === 'inline-flex') &&
                            (childStyle.flexDirection === 'column' || childStyle.flexDirection === 'column-reverse');
                        // Flex column / structural containers after intro text (e.g. .step-desc > .sub-list)
                        // are separate layout regions — must not merge into the parent text box.
                        // <br> is typed as container but must stay in the parent text flow for soft line breaks.
                        const isBrLineBreak = ch.tagName.toLowerCase() === 'br';
                        // A flex/grid row that owns text is a block-level box: it starts
                        // its own line, and whatever it lays out before that text — a
                        // bullet dot, an icon, a rule — sets a left inset for that line
                        // only. Merged into the parent's text box that inset is
                        // unexpressible: one `marL` cannot describe both the host's copy
                        // at zero and this row's copy at 17px, so the dot exported
                        // touching its own words. Kept separate, the row carries its own
                        // measured box and the gap survives.
                        const isTextRowWithLeadingObject = (() => {
                            if (childType !== 'text')
                                return false;
                            if (childDisplay !== 'flex' && childDisplay !== 'inline-flex'
                                && childDisplay !== 'grid' && childDisplay !== 'inline-grid') {
                                return false;
                            }
                            if (childStyle.flexDirection === 'column'
                                || childStyle.flexDirection === 'column-reverse') {
                                return false;
                            }
                            let firstText = null;
                            const walker = document.createTreeWalker(ch, NodeFilter.SHOW_TEXT);
                            let node;
                            while ((node = walker.nextNode())) {
                                if (String(node.textContent || '').trim()) {
                                    firstText = node;
                                    break;
                                }
                            }
                            if (!firstText)
                                return false;
                            try {
                                const range = document.createRange();
                                range.selectNodeContents(firstText);
                                const textRect = range.getBoundingClientRect();
                                const childRect = ch.getBoundingClientRect();
                                const inset = textRect.left - childRect.left
                                    - (parseFloat(childStyle.borderLeftWidth) || 0)
                                    - (parseFloat(childStyle.paddingLeft) || 0);
                                return inset > 0.5;
                            }
                            catch {
                                return false;
                            }
                        })();
                        if (hasPrecedingText(element, ch) && !flexDistributesSpace && !isFlowBreakingBlockTextChild) {
                            if (hasUnderlineBarAfter(ch) ||
                                isFlexColumnChild ||
                                isTextRowWithLeadingObject ||
                                (childType === 'container' && !isBrLineBreak) ||
                                separateInlineChildTypes.has(childType)) {
                                textExcludeSubtrees.add(ch);
                            }
                            continue;
                        }
                        if (isTextRowWithLeadingObject) {
                            textExcludeSubtrees.add(ch);
                            continue;
                        }
                        const childBg = (childStyle.backgroundColor !== 'rgba(0, 0, 0, 0)' &&
                            childStyle.backgroundColor !== 'transparent') ||
                            childStyle.backgroundImage !== 'none';
                        const childBorder = parseFloat(childStyle.borderLeftWidth) > 0 ||
                            parseFloat(childStyle.borderRightWidth) > 0 ||
                            parseFloat(childStyle.borderTopWidth) > 0 ||
                            parseFloat(childStyle.borderBottomWidth) > 0;
                        const textWithFill = childType === 'text' && (childBg || childBorder);
                        if (childType !== 'text' && !isBrLineBreak) {
                            textExcludeSubtrees.add(ch);
                        }
                        else if (textWithFill && childBg) {
                            // Only treat "text with fill" as separate when it has background (not just border/radius)
                            textExcludeSubtrees.add(ch);
                        }
                        else if (isFlowBreakingBlockTextChild) {
                            textExcludeSubtrees.add(ch);
                        }
                    }
                    if (textExcludeSubtrees.size === 0)
                        textExcludeSubtrees = undefined;
                }
                const hasExcludedTextSubtrees = type === 'text' && !!textExcludeSubtrees?.size;
                function isInsideExcluded(node, excludeSet, container) {
                    let p = node.parentNode;
                    while (p && p !== container) {
                        if (p.nodeType === Node.ELEMENT_NODE && excludeSet.has(p))
                            return true;
                        p = p.parentNode;
                    }
                    return false;
                }
                let textRect = rect;
                let textFlowExtraMarginLeftPx;
                /** Text+fill+border box with excluded SVG/img/etc.: emit full-rect shape for box, caption uses Range geometry */
                let emitSplitCaptionFrameShape = false;
                if ((hasDecorativeChildren || hasInFlowPseudoBefore || hasExcludedTextSubtrees) &&
                    type === 'text' &&
                    element.childNodes.length > 0) {
                    const range = document.createRange();
                    let firstTextNode = null;
                    let lastTextNode = null;
                    if (textExcludeSubtrees?.size) {
                        for (const node of Array.from(element.childNodes)) {
                            if (node.nodeType !== Node.TEXT_NODE || !node.textContent?.trim())
                                continue;
                            if (isInsideExcluded(node, textExcludeSubtrees, element))
                                continue;
                            if (!firstTextNode)
                                firstTextNode = node;
                            lastTextNode = node;
                        }
                        if (!firstTextNode) {
                            const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT, {
                                acceptNode: (node) => {
                                    if (!node.textContent?.trim())
                                        return NodeFilter.FILTER_SKIP;
                                    return isInsideExcluded(node, textExcludeSubtrees, element)
                                        ? NodeFilter.FILTER_SKIP
                                        : NodeFilter.FILTER_ACCEPT;
                                }
                            });
                            firstTextNode = walker.nextNode();
                            if (firstTextNode) {
                                lastTextNode = firstTextNode;
                                let next;
                                while ((next = walker.nextNode()))
                                    lastTextNode = next;
                            }
                        }
                    }
                    else {
                        for (const node of Array.from(element.childNodes)) {
                            if (node.nodeType === Node.TEXT_NODE && node.textContent?.trim()) {
                                if (!firstTextNode)
                                    firstTextNode = node;
                                lastTextNode = node;
                            }
                        }
                        if (!firstTextNode) {
                            const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT, {
                                acceptNode: (node) => node.textContent?.trim() ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_SKIP
                            });
                            firstTextNode = walker.nextNode();
                            if (firstTextNode) {
                                lastTextNode = firstTextNode;
                                let next;
                                while ((next = walker.nextNode()))
                                    lastTextNode = next;
                            }
                        }
                    }
                    if (firstTextNode && lastTextNode) {
                        const style = window.getComputedStyle(element);
                        const bgClipForFill = style.webkitBackgroundClip || style.backgroundClip;
                        const bgImageIsTextGradient = bgClipForFill === 'text' && style.backgroundImage !== 'none';
                        const hasFill = (style.backgroundColor && style.backgroundColor !== 'rgba(0, 0, 0, 0)' && style.backgroundColor !== 'transparent') ||
                            (style.backgroundImage !== 'none' && !bgImageIsTextGradient);
                        const hasBorder = (parseFloat(style.borderLeftWidth) > 0 && style.borderLeftColor !== 'transparent') ||
                            (parseFloat(style.borderRightWidth) > 0 && style.borderRightColor !== 'transparent') ||
                            (parseFloat(style.borderTopWidth) > 0 && style.borderTopColor !== 'transparent') ||
                            (parseFloat(style.borderBottomWidth) > 0 && style.borderBottomColor !== 'transparent');
                        // Shrink to text ink only when this element has no own "box" (background/border).
                        // If it has fill or border (e.g. flex pill: dot + text), keep full rect — otherwise Range
                        // excludes padding and sibling decorations, so PPT background size/position won't match
                        // the browser and separate shape children (e.g. .dot) appear misaligned.
                        const shouldShrinkToTextRange = (hasExcludedTextSubtrees || (!hasFill && !hasBorder)) && !hasFill && !hasBorder;
                        range.setStart(firstTextNode, 0);
                        range.setEnd(lastTextNode, lastTextNode.textContent?.length ?? 0);
                        const rangeRect = range.getBoundingClientRect();
                        // Client HTML often mixes in-flow SVG/img with trailing text in one bordered/filled box.
                        // PPT would center text in the full box; split: shape = border+fill (full rect), text = Range box.
                        const shouldSplitCaptionFrame = type === 'text' &&
                            hasExcludedTextSubtrees &&
                            (hasFill || hasBorder) &&
                            rangeRect.width > 0.5 &&
                            rangeRect.height > 0.5 &&
                            !hasTransformRotation(element);
                        if (shouldSplitCaptionFrame) {
                            textRect = docBox(rangeRect);
                            emitSplitCaptionFrameShape = true;
                        }
                        else if (shouldShrinkToTextRange) {
                            textRect = docBox(rangeRect);
                        }
                        else if (element instanceof HTMLElement &&
                            (hasExcludedTextSubtrees || hasDecorativeChildren || hasInFlowPseudoBefore)) {
                            // Full border-box kept for background/border; PPT margin only encodes padding+border,
                            // not in-flow icons/SVG/gap — shift text by measured first-line left edge.
                            //
                            // NOTE: a single `marL` cannot describe a host that merged two
                            // blocks with different insets — its own copy at zero and a
                            // nested bullet row at 17px. That needs a per-paragraph marL
                            // and is not handled here; the bullet exports touching its copy.
                            const tr = docBox(rangeRect);
                            const bl = parseFloat(style.borderLeftWidth) || 0;
                            const pl = parseFloat(style.paddingLeft) || 0;
                            const extraPx = tr.left - rect.left - bl - pl;
                            if (extraPx > 0.5) {
                                textFlowExtraMarginLeftPx = extraPx;
                            }
                        }
                    }
                }
                const baseTag = element.tagName.toLowerCase();
                const tagWithMeta = element instanceof HTMLElement
                    ? [
                        baseTag,
                        element.id ? `#${element.id}` : '',
                        element.classList?.length ? `.${Array.from(element.classList).join('.')}` : '',
                    ].join('')
                    : baseTag;
                const info = {
                    type,
                    tag: tagWithMeta,
                    elementId: readElementIdentity(element),
                    semanticOwner: element.__deckhtmlSemanticOwner ||
                        (() => {
                            const owner = element.closest('[data-pptx="table"], [data-pptx="figure"], [data-pptx="chart"], [data-pptx="formula"]');
                            return owner ? readElementIdentity(owner) : undefined;
                        })(),
                    semanticKind: element.__deckhtmlSemanticKind ||
                        (() => {
                            const owner = element.closest('[data-pptx="table"], [data-pptx="figure"], [data-pptx="chart"], [data-pptx="formula"]');
                            const kind = owner?.getAttribute('data-pptx')?.toLowerCase();
                            return kind === 'table' || kind === 'figure' || kind === 'chart' || kind === 'formula'
                                ? kind
                                : undefined;
                        })(),
                    animationRaw: readAnimationRaw(element),
                    animationGroupId: readAnimationGroupId(element),
                    x: textRect.left,
                    y: textRect.top,
                    width: textRect.width,
                    height: textRect.height,
                    styles: getComputedStyles(element),
                    circleGlyphBadge: element instanceof HTMLElement &&
                        element.getAttribute('data-html2pptx-circle-badge') === '1',
                    pageChrome: element instanceof HTMLElement &&
                        element.hasAttribute('data-sunairum-page-number'),
                };
                const overflowClip = nearestOverflowClipRect(element);
                if (overflowClip)
                    info.overflowClipRect = overflowClip;
                if (type === 'text' && isSvgNamespace(element)) {
                    info.svgText = true;
                }
                // Mermaid labels: HTML inside foreignObject (font metrics differ from native SVG text).
                if (type === 'text' && element instanceof HTMLElement) {
                    const fo = element.closest('foreignObject');
                    if (fo?.closest('svg')) {
                        info.svgText = true;
                        info.svgForeignObjectText = true;
                    }
                }
                // When element has CSS transform rotation, getBoundingClientRect() returns the AABB (larger).
                // PPTX expects unrotated size and position, then applies rotation — so use layout size/position.
                if (hasTransformRotation(element) && element instanceof HTMLElement && !emitSplitCaptionFrameShape) {
                    const ow = element.offsetWidth;
                    const oh = element.offsetHeight;
                    if (ow > 0 && oh > 0) {
                        const centerX = rect.left + rect.width / 2;
                        const centerY = rect.top + rect.height / 2;
                        info.x = centerX - ow / 2;
                        info.y = centerY - oh / 2;
                        info.width = ow;
                        info.height = oh;
                    }
                }
                // li: ::before bullet (in-flow) sits after padding; getTextOptions already applies padding+border as
                // PPT margin. beforePseudoWidthPx is only the extra horizontal space for the pseudo (ml + w + mr) in px,
                // added on top of margin-left in the converter — do not change x/w or the card fills the border box wrong.
                const tag = element.tagName.toLowerCase();
                if (tag === 'li') {
                    const bs = window.getComputedStyle(element, '::before');
                    const hasBefore = bs.content && bs.content !== 'none' && bs.content !== 'normal';
                    if (hasBefore && bs.position !== 'absolute' && bs.position !== 'fixed') {
                        const ml = parseFloat(bs.marginLeft) || 0;
                        const mr = parseFloat(bs.marginRight) || 0;
                        const w = parseFloat(bs.width);
                        let bulletAdvance = 0;
                        if (!isNaN(w) && w > 0) {
                            bulletAdvance = ml + w + mr;
                        }
                        else {
                            const textContent = bs.content.replace(/^["']|["']$/g, '');
                            if (textContent.length > 0) {
                                const temp = document.createElement('span');
                                temp.style.visibility = 'hidden';
                                temp.style.pointerEvents = 'none';
                                temp.style.display = 'inline';
                                temp.style.fontSize = bs.fontSize;
                                temp.style.fontFamily = bs.fontFamily;
                                temp.style.fontWeight = bs.fontWeight;
                                temp.style.fontStyle = bs.fontStyle;
                                temp.style.letterSpacing = bs.letterSpacing;
                                temp.textContent = textContent;
                                element.insertBefore(temp, element.firstChild);
                                const tempRect = temp.getBoundingClientRect();
                                element.removeChild(temp);
                                if (tempRect.width > 0)
                                    bulletAdvance = ml + tempRect.width + mr;
                            }
                        }
                        if (bulletAdvance > 0)
                            info.beforePseudoWidthPx = bulletAdvance;
                    }
                }
                // clip-path polygon (ancestor or self): visible region = clip polygon ∩ element box → custGeom in PPTX
                // Apply to all renderable element types to avoid unclipped rectangular fallbacks.
                if (type !== 'container') {
                    const clip = computeClipPathIntersection(element, {
                        x: info.x,
                        y: info.y,
                        width: info.width,
                        height: info.height,
                    });
                    if (clip) {
                        if (!clip.preserveLayoutBox) {
                            info.x = clip.bbox.left;
                            info.y = clip.bbox.top;
                            info.width = clip.bbox.width;
                            info.height = clip.bbox.height;
                        }
                        info.clipPathPolygonPx = clip.pointsRelative;
                    }
                }
                // Flex space-* row: bare text at an end should hug that end (e.g. .ill-header > span).
                // Skip chips/cards that paint their own border/fill — flex already placed the box;
                // stamping right/left align inside a shrink-wrapped pill overflows the outline in PPT.
                if (type === 'text' && element.parentElement && element instanceof HTMLElement) {
                    const selfStyle = window.getComputedStyle(element);
                    const selfHasFill = selfStyle.backgroundColor &&
                        selfStyle.backgroundColor !== 'rgba(0, 0, 0, 0)' &&
                        selfStyle.backgroundColor !== 'transparent';
                    const selfHasBorder = (parseFloat(selfStyle.borderLeftWidth) > 0 && selfStyle.borderLeftColor !== 'transparent') ||
                        (parseFloat(selfStyle.borderRightWidth) > 0 && selfStyle.borderRightColor !== 'transparent') ||
                        (parseFloat(selfStyle.borderTopWidth) > 0 && selfStyle.borderTopColor !== 'transparent') ||
                        (parseFloat(selfStyle.borderBottomWidth) > 0 && selfStyle.borderBottomColor !== 'transparent');
                    const skipFlexTextAlignStamp = !!(selfHasFill || selfHasBorder);
                    const flexParent = element.parentElement;
                    const ps = window.getComputedStyle(flexParent);
                    const flexDistributesSpace = (ps.display === 'flex' || ps.display === 'inline-flex') &&
                        /space-(between|around|evenly)/.test(ps.justifyContent || '');
                    const flexDir = ps.flexDirection || 'row';
                    if (!skipFlexTextAlignStamp &&
                        flexDistributesSpace &&
                        (flexDir === 'row' || flexDir === 'row-reverse')) {
                        const inFlowItems = Array.from(flexParent.childNodes).filter((n) => {
                            if (n.nodeType === Node.TEXT_NODE)
                                return (n.textContent?.trim() ?? '').length > 0;
                            if (n.nodeType === Node.ELEMENT_NODE)
                                return isVisible(n);
                            return false;
                        });
                        const lastItem = inFlowItems[inFlowItems.length - 1];
                        const firstItem = inFlowItems[0];
                        const isLast = lastItem === element;
                        const isFirst = firstItem === element;
                        if (flexDir === 'row-reverse') {
                            if (isFirst)
                                info.flexItemTextAlign = 'right';
                            else if (isLast)
                                info.flexItemTextAlign = 'left';
                        }
                        else {
                            if (isLast)
                                info.flexItemTextAlign = 'right';
                            else if (isFirst)
                                info.flexItemTextAlign = 'left';
                        }
                    }
                }
                // Add type-specific data
                if (type === 'text') {
                    info.content = getTextContent(element, textExcludeSubtrees);
                    let richText = extractRichText(element, textExcludeSubtrees);
                    richText = mergeTypographyPseudoRichText(element, richText, textExcludeSubtrees, '::before');
                    richText = mergeTypographyPseudoRichText(element, richText, textExcludeSubtrees, '::after');
                    if (richText && richText.length > 0) {
                        richText = richText.map((run, index) => ({
                            ...run,
                            fragmentId: readFragmentIdentity(element, `inline-run-${index + 1}`),
                        }));
                        info.richText = richText;
                        info.content = richText.map((r) => r.text).join('');
                    }
                    if (textFlowExtraMarginLeftPx != null && textFlowExtraMarginLeftPx > 0) {
                        info.textFlowExtraMarginLeftPx = textFlowExtraMarginLeftPx;
                    }
                    // L1 layout-faithful: capture Chromium line boxes + font closure probe
                    try {
                        const hostText = String(info.content || '');
                        const captured = captureLayoutLines(element, hostText, textExcludeSubtrees);
                        if (captured.lines.length)
                            info.layoutLines = captured.lines;
                        if (captured.ambiguous)
                            info.layoutFaithfulAmbiguous = true;
                        if (captured.unsupportedReason) {
                            info.layoutFaithfulUnsupportedReason = captured.unsupportedReason;
                        }
                        if (captured.mismatch) {
                            info.layoutFaithfulMismatch = captured.mismatch;
                        }
                        const face = (info.styles?.fontFamily || '').split(',')[0]?.replace(/["']/g, '').trim();
                        const weight = String(info.styles?.fontWeight || '400');
                        info.layoutFontFace = face;
                        info.layoutFontWeight = weight;
                        if (face && document.fonts?.check) {
                            try {
                                const sizePx = info.styles?.fontSize || 16;
                                info.layoutFontReady = document.fonts.check(`${weight} ${sizePx}px "${face}"`);
                            }
                            catch {
                                info.layoutFontReady = false;
                            }
                        }
                    }
                    catch {
                        info.layoutFaithfulAmbiguous = true;
                        info.layoutFaithfulUnsupportedReason = 'ambiguous_line_map';
                    }
                }
                else if (type === 'icon') {
                    // Extract Font Awesome icon content from ::before pseudo-element
                    info.content = getFontAwesomeContent(element);
                    // Mark as icon type for converter to handle specially
                    info.isIcon = true;
                    // Opacity is not inherited in computed style, but parent opacity affects the
                    // whole rendered subtree. Apply effective opacity so decorative icons inside
                    // low-opacity containers (e.g. opacity-5) keep the intended visual color.
                    let effectiveOpacity = parseFloat(window.getComputedStyle(element).opacity) || 1;
                    for (let parent = element.parentElement; parent && parent !== document.body; parent = parent.parentElement) {
                        effectiveOpacity *= parseFloat(window.getComputedStyle(parent).opacity) || 1;
                    }
                    info.styles.opacity = effectiveOpacity;
                }
                else if (type === 'image') {
                    const imgElement = element;
                    info.src = imgElement.src;
                    // Extract natural dimensions for object-fit calculations
                    info.imageNaturalWidth = imgElement.naturalWidth || 0;
                    info.imageNaturalHeight = imgElement.naturalHeight || 0;
                    if (info.src &&
                        !info.src.startsWith('data:') &&
                        imgElement.complete &&
                        info.imageNaturalWidth === 0) {
                        info.resourceUnavailable = true;
                    }
                    // Parent has border-radius + overflow-hidden and img is only child → parent clips img to rounded corners
                    const parent = element.parentElement;
                    if (parent && parent.children.length === 1) {
                        const parentStyle = window.getComputedStyle(parent);
                        const overflow = `${parentStyle.overflow} ${parentStyle.overflowX} ${parentStyle.overflowY}`;
                        const clips = overflow.includes('hidden') || overflow.includes('clip');
                        const br = parentStyle.borderRadius;
                        const radiusPx = br ? parseFloat(br) || 0 : 0;
                        if (clips && radiusPx > 0) {
                            info.parentBorderRadiusPx = radiusPx;
                        }
                    }
                    // Formula/figure PNG plates: always contain inside the padded content box.
                    const parentPptx = (parent?.getAttribute?.('data-pptx') || '').toLowerCase();
                    const imgComputed = window.getComputedStyle(imgElement);
                    let hasFigureAncestor = false;
                    for (let anc = element.parentElement; anc; anc = anc.parentElement) {
                        if ((anc.getAttribute('data-pptx') || '').toLowerCase() === 'figure') {
                            hasFigureAncestor = true;
                            break;
                        }
                    }
                    if (imgElement.hasAttribute('data-sunairum-formula') ||
                        imgElement.hasAttribute('data-sunairum-figure') ||
                        imgElement.hasAttribute('data-figure-id') ||
                        imgElement.hasAttribute('data-sunairum-figure-id') ||
                        parentPptx === 'formula' ||
                        parentPptx === 'figure' ||
                        hasFigureAncestor ||
                        imgComputed.objectFit === 'contain' ||
                        (imgElement.getAttribute('alt') || '').toLowerCase() === 'formula') {
                        info.forceObjectFitContain = true;
                    }
                }
                else if (type === 'video') {
                    const videoElement = element;
                    info.src = videoElement.currentSrc || videoElement.src || '';
                    info.poster = videoElement.poster || '';
                    if (videoElement.error ||
                        videoElement.networkState === HTMLMediaElement.NETWORK_NO_SOURCE ||
                        videoElement.readyState === 0) {
                        info.resourceUnavailable = true;
                    }
                }
                else if (type === 'audio') {
                    const audioElement = element;
                    info.src = audioElement.currentSrc || audioElement.src || '';
                    if (audioElement.error ||
                        audioElement.networkState === HTMLMediaElement.NETWORK_NO_SOURCE ||
                        audioElement.readyState === 0) {
                        info.resourceUnavailable = true;
                    }
                }
                else if (type === 'canvas') {
                    try {
                        info.dataUrl = element.toDataURL('image/png');
                        info.rasterMethod = 'canvas-export';
                        info.rasterReason = 'chart-canvas';
                    }
                    catch (e) {
                        console.warn('Failed to export canvas:', e);
                        info.resourceUnavailable = true;
                    }
                }
                else if (type === 'table') {
                    info.tableData = extractTableData(element);
                    const stamped = element.__deckhtmlTableHostBounds;
                    const hostEl = element.closest('[data-pptx="table"]');
                    if (stamped && stamped.width > 8 && stamped.height > 8) {
                        info.tableHostBounds = stamped;
                    }
                    else if (hostEl) {
                        const hr = hostEl.getBoundingClientRect();
                        if (hr.width > 8 && hr.height > 8) {
                            info.tableHostBounds = {
                                x: hr.left,
                                y: hr.top,
                                width: hr.width,
                                height: hr.height,
                            };
                        }
                    }
                    // Lay out native table in the host box (matches overflow:hidden clip).
                    if (info.tableHostBounds) {
                        info.x = info.tableHostBounds.x;
                        info.y = info.tableHostBounds.y;
                        info.width = info.tableHostBounds.width;
                        info.height = Math.min(info.height, info.tableHostBounds.height);
                    }
                }
                // Detect visual styles that PPT native shapes cannot faithfully reproduce.
                // Mark for isolated Playwright screenshot fallback.
                if (type === 'shape' && info.styles.backgroundImage && !readElementIdentity(element)) {
                    const bgImg = info.styles.backgroundImage;
                    const bgSize = window.getComputedStyle(element).backgroundSize;
                    const gradientCount = (bgImg.match(/linear-gradient/g) || []).length;
                    const isDefaultSize = !bgSize || bgSize === 'auto' || bgSize === 'auto auto' || bgSize === '100% 100%';
                    // Do not isolate-screenshot <body> backgrounds. The screenshot flow forces
                    // html/body background to transparent to capture overlay grids, which would
                    // erase page-level background fills when the target itself is <body>.
                    const isBody = element.tagName?.toLowerCase() === 'body';
                    if (!isBody && gradientCount >= 2 && !isDefaultSize) {
                        assignScreenshotFallback(element, info, 'gradient-layered');
                    }
                    else if (!isBody && hasTiledRadialGradientBackground(bgImg, bgSize)) {
                        assignScreenshotFallback(element, info, 'gradient-tiled-radial');
                    }
                    else if (!isBody &&
                        (gradientCount >= 1 || /radial-gradient\(|repeating-radial-gradient\(/i.test(bgImg)) &&
                        hasAdjacentDuplicatePercentHardStopInGradients(bgImg)) {
                        assignScreenshotFallback(element, info, 'gradient-hard-stop');
                    }
                    else if (!isBody && /url\s*\(/i.test(bgImg)) {
                        // background-image: url() — pptx shapes only support solid/gradient fills, not photos.
                        // Full-slide url+gradient overlays are handled in converter; skip screenshot there.
                        const hasGrad = gradientCount >= 1 ||
                            /radial-gradient\(|repeating-radial-gradient\(/i.test(bgImg);
                        const isNearFullSlide = info.width >= 1152 && info.height >= 648;
                        const elemOpacity = typeof info.styles?.opacity === 'number' && !Number.isNaN(info.styles.opacity)
                            ? info.styles.opacity
                            : 1;
                        // Subtle full-slide texture overlays (e.g. opacity:0.03 paper grain) are invisible in
                        // practice and screenshot isolation composites ancestor fills into the PNG.
                        if (isNearFullSlide && !hasGrad && elemOpacity <= 0.05) {
                            return;
                        }
                        if (!(isNearFullSlide && hasGrad)) {
                            assignScreenshotFallback(element, info, 'background-url');
                        }
                    }
                }
                // Border-radius polygon fallback:
                // For complex radii (non-uniform/elliptical/%), generate a custom polygon path
                // so converter can emit custGeom instead of unstable screenshot fallback.
                if (type === 'shape' && !info.clipPathPolygonPx && !info.svgTag) {
                    const radiusPoly = sampleRoundedRectPolygon(element, info.width, info.height);
                    if (radiusPoly && radiusPoly.length >= 3) {
                        info.clipPathPolygonPx = radiusPoly;
                    }
                }
                if (type === 'shape' && isSvgNamespace(element)) {
                    applySvgShapeMetadata(info, element);
                }
                // Bordered/filled flex (or block) box with excluded SVG/img/canvas/icon: frame shape + Range-sized caption text
                if (emitSplitCaptionFrameShape && element instanceof HTMLElement) {
                    const stripCaptionOnlyBoxStyles = (st) => {
                        const captionBgClip = st.webkitBackgroundClip ?? st.backgroundClip;
                        const captionTextGradient = captionBgClip === 'text' && st.backgroundImage && st.backgroundImage !== 'none';
                        st.backgroundColor = 'rgba(0, 0, 0, 0)';
                        if (!captionTextGradient) {
                            st.backgroundImage = 'none';
                        }
                        st.boxShadow = 'none';
                        st.borderWidth = '0px';
                        st.borderStyle = 'none';
                        st.borderColor = 'transparent';
                        st.borderRadius = '0px';
                        // Caption uses Range geometry (content ink box); padding/border live on frame shape only.
                        st.paddingTop = '0px';
                        st.paddingRight = '0px';
                        st.paddingBottom = '0px';
                        st.paddingLeft = '0px';
                        for (const side of ['Left', 'Right', 'Top', 'Bottom']) {
                            st['border' + side + 'Width'] = '0px';
                            st['border' + side + 'Color'] = 'transparent';
                            st['border' + side + 'Style'] = 'none';
                        }
                    };
                    stripCaptionOnlyBoxStyles(info.styles);
                    const frameShape = {
                        type: 'shape',
                        tag: (element.tagName || 'div').toLowerCase(),
                        elementId: readFragmentIdentity(element, 'frame'),
                        x: rect.left,
                        y: rect.top,
                        width: rect.width,
                        height: rect.height,
                        styles: getComputedStyles(element),
                        animationGroupId: readAnimationGroupId(element),
                    };
                    const clipFrame = computeClipPathIntersection(element, {
                        x: frameShape.x,
                        y: frameShape.y,
                        width: frameShape.width,
                        height: frameShape.height,
                    });
                    if (clipFrame) {
                        if (!clipFrame.preserveLayoutBox) {
                            frameShape.x = clipFrame.bbox.left;
                            frameShape.y = clipFrame.bbox.top;
                            frameShape.width = clipFrame.bbox.width;
                            frameShape.height = clipFrame.bbox.height;
                        }
                        frameShape.clipPathPolygonPx = clipFrame.pointsRelative;
                    }
                    if (!frameShape.clipPathPolygonPx) {
                        const radiusPoly = sampleRoundedRectPolygon(element, frameShape.width, frameShape.height);
                        if (radiusPoly && radiusPoly.length >= 3) {
                            frameShape.clipPathPolygonPx = radiusPoly;
                        }
                    }
                    result.push(frameShape);
                }
                // Text hosts: z-index < 0 decorations paint behind in-flow text (CSS stacking).
                let textDecorationsBehind = [];
                let textDecorationsFront = [];
                if (type === 'text') {
                    const nestedDecor = collectNestedVisualDecorationsFromTextHost(element, textExcludeSubtrees);
                    const excludedDirect = textExcludeSubtrees ? Array.from(textExcludeSubtrees) : [];
                    const seen = new Set();
                    const batch = [];
                    for (const el of [...nestedDecor, ...excludedDirect]) {
                        if (seen.has(el))
                            continue;
                        seen.add(el);
                        batch.push(el);
                    }
                    batch.sort((a, b) => parseElementZIndex(a) - parseElementZIndex(b) || compareElementsDomOrder(a, b));
                    for (const el of batch) {
                        if (parseElementZIndex(el) < 0)
                            textDecorationsBehind.push(el);
                        else
                            textDecorationsFront.push(el);
                    }
                }
                for (const ch of textDecorationsBehind) {
                    await processElement(ch, depth + 1);
                }
                // Skip transparent flex/grid wrappers whose only visible child is text.
                let skipEmptyFlexWrapper = false;
                if ((type === 'shape' || type === 'container') &&
                    element instanceof HTMLElement) {
                    const disp = info.styles?.display;
                    const isFlexGrid = disp === 'flex' ||
                        disp === 'inline-flex' ||
                        disp === 'grid' ||
                        disp === 'inline-grid';
                    if (isFlexGrid) {
                        const bg = info.styles?.backgroundColor;
                        const bgImg = info.styles?.backgroundImage;
                        const hasMeaningfulBg = (bg && bg !== 'transparent' && bg !== 'rgba(0, 0, 0, 0)') ||
                            (bgImg && bgImg !== 'none');
                        const hasMeaningfulBorder = (parseFloat(info.styles?.borderLeftWidth || '0') > 0) ||
                            (parseFloat(info.styles?.borderRightWidth || '0') > 0) ||
                            (parseFloat(info.styles?.borderTopWidth || '0') > 0) ||
                            (parseFloat(info.styles?.borderBottomWidth || '0') > 0);
                        if (!hasMeaningfulBg && !hasMeaningfulBorder) {
                            const visibleChildren = Array.from(element.children).filter((ch) => ch instanceof Element && isVisible(ch));
                            if (visibleChildren.length === 1 &&
                                getElementType(visibleChildren[0]) === 'text') {
                                skipEmptyFlexWrapper = true;
                            }
                        }
                    }
                }
                if (type === 'text' &&
                    element instanceof HTMLElement &&
                    (info.layoutFaithfulUnsupportedReason === 'vertical_writing' ||
                        info.layoutFaithfulUnsupportedReason === 'rtl_or_bidi' ||
                        info.layoutFaithfulUnsupportedReason === 'unsupported_transform')) {
                    assignScreenshotFallback(element, info, `unsupported-text-${info.layoutFaithfulUnsupportedReason || 'ambiguous-line-map'}`);
                }
                if (!skipEmptyFlexWrapper) {
                    result.push(info);
                    markDomAsPptxMapped(element, !!info.needsScreenshot);
                    // Extract visual ::before / ::after pseudo-elements as separate entries
                    const pseudoItems = extractPseudoElements(element);
                    for (const pi of pseudoItems) {
                        result.push(pi);
                    }
                    if (type === 'text') {
                        for (const pi of collectMergedTextSubtreePseudoElements(element, textExcludeSubtrees)) {
                            result.push(pi);
                        }
                    }
                }
                for (const ch of textDecorationsFront) {
                    await processElement(ch, depth + 1);
                }
                if (type === 'text' && textExcludeSubtrees?.size) {
                    return;
                }
                // For shape elements with children, always process children separately
                // For other non-leaf elements, process children normally
                if (shouldExtractChildrenSeparately ||
                    skipEmptyFlexWrapper ||
                    (type !== 'text' && type !== 'icon' && type !== 'image' && type !== 'canvas' && type !== 'svg' && type !== 'math' && type !== 'table')) {
                    /**
                     * L1: consecutive bare inline text children under a shape must stay one
                     * rich-text host. Separate emission causes shared-origin overlap when
                     * wrapped spans' AABB left edges align (slide 07 Candidate pool).
                     */
                    function isBareInlineTextChild(ch) {
                        if (!(ch instanceof HTMLElement))
                            return false;
                        if (getElementType(ch) !== 'text')
                            return false;
                        const cs = window.getComputedStyle(ch);
                        const d = cs.display || '';
                        if (d === 'block' ||
                            d === 'flex' ||
                            d === 'inline-flex' ||
                            d === 'grid' ||
                            d === 'list-item' ||
                            d === 'flow-root' ||
                            d === 'table') {
                            return false;
                        }
                        const hasBg = (cs.backgroundColor !== 'rgba(0, 0, 0, 0)' &&
                            cs.backgroundColor !== 'transparent') ||
                            cs.backgroundImage !== 'none';
                        const radius = parseFloat(cs.borderRadius) || 0;
                        // Filled/pill chips are separate shapes
                        if (hasBg && (d === 'inline-block' || radius >= 4))
                            return false;
                        return true;
                    }
                    async function processInlineTextGroup(group, childDepth) {
                        if (group.length === 1) {
                            await processElement(group[0], childDepth);
                            return;
                        }
                        const parentEl = group[0].parentElement;
                        if (!parentEl) {
                            for (const g of group)
                                await processElement(g, childDepth);
                            return;
                        }
                        const wrap = document.createElement('span');
                        wrap.setAttribute('data-deckhtml-text-flow', '1');
                        wrap.style.cssText = 'display:inline;';
                        const firstId = group[0] instanceof HTMLElement
                            ? group[0].getAttribute(_identityAttr)
                            : null;
                        if (firstId)
                            wrap.setAttribute(_identityAttr, `${firstId}__flow`);
                        parentEl.insertBefore(wrap, group[0]);
                        for (const g of group)
                            wrap.appendChild(g);
                        try {
                            await processElement(wrap, childDepth);
                        }
                        finally {
                            while (wrap.firstChild)
                                parentEl.insertBefore(wrap.firstChild, wrap);
                            wrap.remove();
                        }
                    }
                    const kids = getChildrenInPaintOrder(element);
                    let ki = 0;
                    while (ki < kids.length) {
                        const child = kids[ki];
                        if (isBareInlineTextChild(child)) {
                            let kj = ki + 1;
                            while (kj < kids.length && isBareInlineTextChild(kids[kj]))
                                kj++;
                            await processInlineTextGroup(kids.slice(ki, kj), depth + 1);
                            ki = kj;
                        }
                        else {
                            await processElement(child, depth + 1);
                            ki++;
                        }
                    }
                }
            }
            // Find root elements to process
            let rootElements;
            /**
             * Emit page background as a rasterized full-viewport image.
             * This avoids severe color drift when CSS uses layered gradients on <body>.
             * Returns true when a background entry was emitted.
             */
            function emitPageBackgroundRasterIfAny() {
                try {
                    if (!document.body)
                        return false;
                    const bs = window.getComputedStyle(document.body);
                    const hasBg = (bs.backgroundColor &&
                        bs.backgroundColor !== 'rgba(0, 0, 0, 0)' &&
                        bs.backgroundColor !== 'rgba(0,0,0,0)' &&
                        bs.backgroundColor !== 'transparent') ||
                        (bs.backgroundImage && bs.backgroundImage !== 'none');
                    if (!hasBg)
                        return false;
                    document.querySelectorAll('[data-html2pptx-page-bg]').forEach((node) => {
                        node.remove();
                    });
                    const bgId = '0';
                    const bgHost = document.createElement('div');
                    bgHost.setAttribute('data-html2pptx-page-bg', bgId);
                    bgHost.style.cssText = [
                        'position:fixed',
                        'left:0',
                        'top:0',
                        'width:100vw',
                        'height:100vh',
                        'pointer-events:none',
                        // Keep it behind normal content; isolated screenshot hides other elements anyway.
                        'z-index:-999999',
                        // Copy computed background from body (includes layered gradients, resolved vars)
                        `background-image:${bs.backgroundImage}`,
                        `background-color:${canonicalizeComputedBackgroundColor(bs.backgroundColor)}`,
                        `background-position:${bs.backgroundPosition}`,
                        `background-size:${bs.backgroundSize}`,
                        `background-repeat:${bs.backgroundRepeat}`,
                    ].join(';');
                    document.body.appendChild(bgHost);
                    result.push({
                        type: 'shape',
                        tag: 'body.page-bg',
                        elementId: readFragmentIdentity(document.body, 'page-background'),
                        x: 0,
                        y: 0,
                        width: window.innerWidth,
                        height: window.innerHeight,
                        styles: getComputedStyles(bgHost),
                    });
                    // Do not emit this helper node again during normal traversal.
                    markDomAsPptxMapped(bgHost);
                    return true;
                }
                catch {
                    return false;
                }
            }
            const emittedPageBg = emitPageBackgroundRasterIfAny();
            if (slideSelector) {
                // Use custom slide selector
                rootElements = Array.from(document.querySelectorAll(slideSelector));
            }
            else if (inputIsSvg) {
                const svgRoot = getStandaloneSvgRoot();
                rootElements = svgRoot
                    ? Array.from([svgRoot])
                    : document.body
                        ? [document.body]
                        : [document.documentElement];
            }
            else {
                // Default: process body
                // If we already emitted a raster page background, skip emitting <body> itself as a shape
                // (its fill approximation can wash out the raster). Traverse its children instead.
                rootElements = emittedPageBg
                    ? Array.from(document.body.children)
                    : [document.body];
            }
            // Process root elements (body background is extracted via processElement when body has background)
            for (const root of rootElements) {
                await processElement(root);
            }
            // Keep raw viewport coordinates. Do not normalize by inner slide/container size.
            result.push({ _debugInfo, _excludedCount: _excludedCount.value, _excludedSamples, _identityWarnings, _kindDiagnostics });
            return result;
        }, {
            slideSelector,
            slideHeight: (0, coordinate_1.getSlideHeightPx)(),
            inputIsSvg,
            excludeSelector: options?.excludeSelector,
            slideIdAttribute: options?.slideIdAttribute,
            identityAttribute: options?.identityAttribute,
        });
        // Check if the last element is our debug info
        const lastElement = elements[elements.length - 1];
        let _debugInfo = [];
        let excludedCount = 0;
        let excludedSamples = [];
        let identityWarnings = [];
        let kindDiagnostics = [];
        if (lastElement && lastElement._debugInfo) {
            _debugInfo = lastElement._debugInfo;
            excludedCount = lastElement._excludedCount ?? 0;
            excludedSamples = lastElement._excludedSamples ?? [];
            identityWarnings = lastElement._identityWarnings ?? [];
            kindDiagnostics = lastElement._kindDiagnostics ?? [];
            elements.pop(); // Remove the debug info object from the elements array
        }
        // Stamp emission order so generator can stably restore paint order after merges.
        for (let i = 0; i < elements.length; i++) {
            elements[i].paintOrder = i;
        }
        for (const msg of _debugInfo) {
            console.log(msg);
        }
        if (excludedCount > 0) {
            console.warn(`🚫 Excluded ${excludedCount} runtime/navigation element(s) via excludeSelector or data-pptx-kind=ignore: ` +
                excludedSamples.join(', '));
            if (options?.excludedCount)
                options.excludedCount.value += excludedCount;
        }
        for (const msg of identityWarnings) {
            console.warn(`⚠️  ${msg}`);
            // Also push a structured diagnostic so callers can branch on rule_id (DH-P0-001/009).
            if (options?.identityDiagnostics) {
                const dupMatch = msg.match(/Duplicate element identity "([^"]+)"/);
                if (dupMatch) {
                    options.identityDiagnostics.push({
                        rule_id: 'DECKHTML_IDENTITY_DUPLICATE',
                        severity: 'warning',
                        element_id: dupMatch[1],
                        message: msg,
                    });
                }
            }
        }
        // DH-P0-009: surface unknown data-pptx-kind hints as structured diagnostics.
        if (options?.identityDiagnostics) {
            for (const d of kindDiagnostics) {
                console.warn(`⚠️  ${d.message}`);
                options.identityDiagnostics.push(d);
            }
        }
        for (const el of elements) {
            if (el.type !== 'math' || !el.mathml)
                continue;
            const converted = await (0, mathml_to_omml_1.convertMathmlToOmml)(el.mathml);
            if (!converted.ok) {
                console.warn(`MathML→OMML failed, using screenshot fallback: ${converted.error}`);
                el.needsScreenshot = true;
                el.rasterMethod = 'screenshot';
                el.rasterReason = 'math-fallback';
                continue;
            }
            el.ommlXml = converted.omml;
        }
        // Resolve iframe placeholders into editable child elements (or screenshot/skip).
        await this.resolveIframes(elements, options);
        // Isolated screenshot backfill: remove every other box from layout (display:none)
        // so Playwright's element screenshot cannot composite separate PPTX layers (text,
        // icons, etc.) into the PNG. Keep the host and its ancestor chain visible.
        const PPTX_SHOT_HIDDEN_ATTR = 'data-html2pptx-shot-hidden';
        const PPTX_SHOT_ANCESTOR_BG_ATTR = 'data-html2pptx-shot-ancestor-bg';
        for (const el of elements) {
            if (el.needsScreenshot && el.screenshotSelector) {
                const selector = el.screenshotSelector;
                try {
                    await this.page.evaluate(({ sel, hiddenAttr, ancestorBgAttr, hideSvgText }) => {
                        const host = document.querySelector(sel);
                        if (!host)
                            return;
                        const hideTargets = document.body
                            ? Array.from(document.body.querySelectorAll('*'))
                            : Array.from(document.documentElement.querySelectorAll('*'));
                        hideTargets.forEach((node) => {
                            if (!(node instanceof HTMLElement || node instanceof SVGElement))
                                return;
                            if (node === host)
                                return;
                            if (host.contains(node)) {
                                const tag = node.localName?.toLowerCase();
                                const isSvgText = tag === 'text' || tag === 'tspan' || tag === 'foreignobject';
                                if (hideSvgText && isSvgText) {
                                    node.setAttribute(hiddenAttr, '1');
                                    node.style.setProperty('visibility', 'hidden', 'important');
                                    return;
                                }
                                if (node.hasAttribute('data-html2pptx-mapped')) {
                                    node.setAttribute(hiddenAttr, '1');
                                    if (isSvgText) {
                                        node.style.setProperty('visibility', 'hidden', 'important');
                                    }
                                    else {
                                        node.style.setProperty('display', 'none', 'important');
                                    }
                                }
                                return;
                            }
                            if (node.contains(host))
                                return;
                            node.setAttribute(hiddenAttr, '1');
                            node.style.setProperty('display', 'none', 'important');
                        });
                        // Low-opacity overlays must not composite ancestor fills (e.g. slide container bg)
                        // into the isolated screenshot — that produces an opaque full-slide wash in PPT.
                        let parent = host.parentElement;
                        while (parent) {
                            if (parent === document.body || parent === document.documentElement)
                                break;
                            if (parent instanceof HTMLElement) {
                                parent.setAttribute(ancestorBgAttr, '1');
                                parent.style.setProperty('background-color', 'transparent', 'important');
                                parent.style.setProperty('background-image', 'none', 'important');
                            }
                            parent = parent.parentElement;
                        }
                    }, {
                        sel: selector,
                        hiddenAttr: PPTX_SHOT_HIDDEN_ATTR,
                        ancestorBgAttr: PPTX_SHOT_ANCESTOR_BG_ATTR,
                        hideSvgText: !!el.svgHybridRaster,
                    });
                    const hybridTextCss = el.svgHybridRaster
                        ? `${selector} text, ${selector} tspan, ${selector} foreignObject { visibility: hidden !important; }`
                        : '';
                    // Pseudo-elements have no DOM node to hide during isolated screenshot
                    // capture. Their host is often an ancestor that must remain in layout,
                    // so a mapped ::before/::after would otherwise be baked into the PNG and
                    // emitted again as a native PPTX object. Suppress only pseudos whose hosts
                    // were already mapped; screenshot-only hosts are deliberately unmarked.
                    const mappedPseudoCss = '[data-html2pptx-mapped]::before, [data-html2pptx-mapped]::after {' +
                        ' content: none !important; background: none !important;' +
                        ' border: 0 !important; box-shadow: none !important; }';
                    const bgCss = el.screenshotPreserveBackground
                        ? 'html, body { background: transparent !important; }'
                        : 'html, body, svg { background: transparent !important; }';
                    await this.page.evaluate((css) => {
                        let s = document.querySelector('[data-html2pptx-shot-style]');
                        if (!s) {
                            s = document.createElement('style');
                            s.setAttribute('data-html2pptx-shot-style', '1');
                            (document.head || document.documentElement).appendChild(s);
                        }
                        s.textContent = css;
                    }, `${bgCss} ${hybridTextCss} ${mappedPseudoCss}`.trim());
                    await this.page.evaluate(() => new Promise((resolve) => {
                        requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
                    }));
                    await this.page.waitForTimeout(50);
                    const locator = this.page.locator(selector);
                    const count = await locator.count();
                    if (count > 0) {
                        const buffer = await locator.first().screenshot({
                            type: 'png',
                            omitBackground: !el.screenshotPreserveBackground,
                        });
                        el.dataUrl = `data:image/png;base64,${buffer.toString('base64')}`;
                        const preserveSvgType = el.type === 'svg';
                        if (!preserveSvgType) {
                            el.type = 'canvas';
                            el.screenshotBakesOpacity = true;
                        }
                        await locator.first().evaluate((node) => {
                            if (node instanceof HTMLElement || node instanceof SVGElement) {
                                node.setAttribute('data-html2pptx-mapped', '');
                            }
                        });
                    }
                }
                catch (e) {
                    console.warn(`Failed to screenshot element ${el.screenshotSelector}:`, e);
                }
                finally {
                    await this.page.evaluate(() => {
                        document.querySelector('[data-html2pptx-shot-style]')?.remove();
                    });
                    if (selector.includes('data-html2pptx-page-bg')) {
                        await this.page.evaluate((sel) => {
                            document.querySelector(sel)?.remove();
                        }, selector);
                    }
                    await this.page.evaluate(({ hiddenAttr, ancestorBgAttr }) => {
                        document.querySelectorAll(`[${hiddenAttr}]`).forEach((node) => {
                            if (!(node instanceof HTMLElement || node instanceof SVGElement))
                                return;
                            node.style.removeProperty('display');
                            node.style.removeProperty('visibility');
                            node.removeAttribute(hiddenAttr);
                        });
                        document.querySelectorAll(`[${ancestorBgAttr}]`).forEach((node) => {
                            if (!(node instanceof HTMLElement))
                                return;
                            node.style.removeProperty('background-color');
                            node.style.removeProperty('background-image');
                            node.removeAttribute(ancestorBgAttr);
                        });
                    }, {
                        hiddenAttr: PPTX_SHOT_HIDDEN_ATTR,
                        ancestorBgAttr: PPTX_SHOT_ANCESTOR_BG_ATTR,
                    });
                }
            }
        }
        return elements;
    }
    /**
     * Replace iframe placeholders with inspected child elements, screenshots, or remove them.
     */
    async resolveIframes(elements, options) {
        const mode = options?.iframes ?? 'inspect';
        if (mode === 'skip') {
            for (let i = elements.length - 1; i >= 0; i--) {
                if (elements[i]?.type === 'iframe')
                    elements.splice(i, 1);
            }
            return;
        }
        const depth = options?.iframeDepth ?? 0;
        const maxDepth = options?.iframeMaxDepth ?? DEFAULT_IFRAME_MAX_DEPTH;
        const timeoutMs = options?.iframeLoadTimeoutMs ?? DEFAULT_IFRAME_LOAD_TIMEOUT_MS;
        const diagnostics = options?.iframeDiagnostics;
        // Collect indices first — splice while iterating would skip entries.
        const iframeIndices = [];
        for (let i = 0; i < elements.length; i++) {
            if (elements[i]?.type === 'iframe')
                iframeIndices.push(i);
        }
        if (iframeIndices.length === 0)
            return;
        // Process from the end so splice offsets stay valid.
        for (let k = iframeIndices.length - 1; k >= 0; k--) {
            const index = iframeIndices[k];
            const placeholder = elements[index];
            const selector = placeholder.iframeSelector;
            if (depth >= maxDepth) {
                diagnostics?.push({
                    rule_id: diagnostics_1.RULE_IDS.IFRAME_NESTED_TOO_DEEP,
                    severity: 'warning',
                    element_id: placeholder.elementId ?? null,
                    message: `iframe nesting exceeded max depth ${maxDepth}; falling back to screenshot`,
                    recovery: 'Reduce nested iframes or raise iframeMaxDepth',
                });
                const shot = await this.screenshotIframePlaceholder(placeholder);
                if (shot) {
                    elements.splice(index, 1, shot);
                }
                else {
                    elements.splice(index, 1);
                }
                continue;
            }
            if (mode === 'screenshot') {
                const shot = await this.screenshotIframePlaceholder(placeholder);
                if (shot) {
                    elements.splice(index, 1, shot);
                }
                else {
                    elements.splice(index, 1);
                    diagnostics?.push({
                        rule_id: diagnostics_1.RULE_IDS.IFRAME_INSPECT_FAILED,
                        severity: 'warning',
                        element_id: placeholder.elementId ?? null,
                        message: `iframe screenshot failed (${selector ?? placeholder.iframeSrc ?? 'unknown'})`,
                    });
                }
                continue;
            }
            // mode === 'inspect'
            try {
                const childElements = await this.inspectIframeInNewPage(placeholder, {
                    ...options,
                    iframeDepth: depth + 1,
                    iframeLoadTimeoutMs: timeoutMs,
                });
                if (childElements.length === 0) {
                    throw new Error('iframe inspect returned no elements');
                }
                // The child page emits its <body> background as a full-viewport raster
                // (emitPageBackgroundRasterIfAny). That raster is a sharp rectangle which
                // would cover the iframe chrome's rounded corners. Extract the body
                // background and merge it into the chrome shape (a roundRect that already
                // carries the iframe's border-radius) so the visible fill respects the
                // rounded corners.
                const bodyBgIndex = childElements.findIndex((el) => el?.tag === 'body.page-bg');
                let bodyBg;
                if (bodyBgIndex >= 0) {
                    const bodyBgEl = childElements[bodyBgIndex];
                    bodyBg = bodyBgEl.styles;
                    childElements.splice(bodyBgIndex, 1);
                }
                const frameChrome = this.buildIframeChromeShape(placeholder, bodyBg);
                const replacement = frameChrome
                    ? [frameChrome, ...childElements]
                    : childElements;
                elements.splice(index, 1, ...replacement);
            }
            catch (err) {
                const reason = err instanceof Error ? err.message : String(err);
                console.warn(`⚠️  iframe inspect failed, using screenshot: ${reason}`);
                diagnostics?.push({
                    rule_id: diagnostics_1.RULE_IDS.IFRAME_INSPECT_FAILED,
                    severity: 'warning',
                    element_id: placeholder.elementId ?? null,
                    message: `iframe inspect failed (${selector ?? placeholder.iframeSrc ?? 'unknown'}): ${reason}`,
                    recovery: 'Check iframe src/srcdoc availability; conversion fell back to screenshot',
                });
                const shot = await this.screenshotIframePlaceholder(placeholder);
                if (shot) {
                    elements.splice(index, 1, shot);
                }
                else {
                    elements.splice(index, 1);
                }
            }
        }
    }
    /**
     * Open the iframe document in a new page sized to the iframe CSS box and inspect it.
     */
    async inspectIframeInNewPage(placeholder, options) {
        const contentW = Math.max(1, Math.round(placeholder.iframeContentWidth || placeholder.width || 1));
        const contentH = Math.max(1, Math.round(placeholder.iframeContentHeight || placeholder.height || 1));
        const scale = typeof placeholder.iframeScale === 'number' &&
            !Number.isNaN(placeholder.iframeScale) &&
            placeholder.iframeScale > 0
            ? placeholder.iframeScale
            : 1;
        const timeoutMs = options?.iframeLoadTimeoutMs ?? DEFAULT_IFRAME_LOAD_TIMEOUT_MS;
        const context = this.page.context();
        const childPage = await context.newPage();
        try {
            await childPage.setViewportSize({ width: contentW, height: contentH });
            await (0, anime_interceptor_1.installAnimeInterceptor)(childPage);
            const loadTarget = await this.resolveIframeLoadTarget(placeholder);
            if (!loadTarget) {
                throw new Error('iframe has no loadable src/srcdoc/blob content');
            }
            if (loadTarget.kind === 'url') {
                const inputForPolicy = loadTarget.url.startsWith('file:')
                    ? (() => {
                        try {
                            return (0, url_1.fileURLToPath)(loadTarget.url);
                        }
                        catch {
                            return loadTarget.url;
                        }
                    })()
                    : loadTarget.url;
                await (0, resource_policy_1.setupResourcePolicyOnPage)(childPage, inputForPolicy, {
                    allowLocalResources: options?.allowLocalResources,
                    policy: options?.resourcePolicy,
                });
                await (0, navigate_1.gotoAndSettle)(childPage, loadTarget.url, {
                    navigationTimeoutMs: timeoutMs,
                    networkIdleTimeoutMs: Math.min(timeoutMs, 10000),
                    settleMs: Math.min(2000, Math.max(500, Math.floor(timeoutMs / 4))),
                });
            }
            else {
                // srcdoc / inline HTML — optional <base> for relative assets.
                const baseHref = placeholder.iframeBaseUrl || this.page.url();
                const html = /<base\s/i.test(loadTarget.html)
                    ? loadTarget.html
                    : `<base href="${baseHref.replace(/"/g, '&quot;')}">` + loadTarget.html;
                // Best-effort resource policy keyed off parent document.
                try {
                    const parentUrl = this.page.url();
                    const policyInput = parentUrl.startsWith('file:')
                        ? (0, url_1.fileURLToPath)(parentUrl)
                        : parentUrl || 'about:blank';
                    await (0, resource_policy_1.setupResourcePolicyOnPage)(childPage, policyInput, {
                        allowLocalResources: options?.allowLocalResources,
                        policy: options?.resourcePolicy,
                    });
                }
                catch {
                    // ignore policy setup failures for srcdoc
                }
                await childPage.setContent(html, {
                    waitUntil: 'domcontentloaded',
                    timeout: timeoutMs,
                });
                await childPage
                    .waitForLoadState('networkidle', { timeout: Math.min(timeoutMs, 10000) })
                    .catch(() => { });
                await Promise.race([
                    childPage.evaluate(() => document.fonts.ready),
                    childPage.waitForTimeout(2000),
                ]);
                await childPage.waitForTimeout(500);
            }
            const childInspector = new ElementInspector(childPage);
            const childElements = await childInspector.inspectElements(undefined, {
                ...options,
                inputIsSvg: false,
                // Nested resolveIframes runs inside this call via iframeDepth.
            });
            this.offsetIframeElements(childElements, placeholder.x, placeholder.y, scale);
            return childElements;
        }
        finally {
            await childPage.close().catch(() => { });
        }
    }
    /**
     * Resolve what to load into the child page for an iframe placeholder.
     */
    async resolveIframeLoadTarget(placeholder) {
        if (placeholder.iframeSrcdoc && placeholder.iframeSrcdoc.trim()) {
            return { kind: 'html', html: placeholder.iframeSrcdoc };
        }
        const rawSrc = (placeholder.iframeSrc || '').trim();
        if (!rawSrc || rawSrc === 'about:blank') {
            // Last chance: read live srcdoc / blob from the parent DOM.
            if (placeholder.iframeSelector) {
                const live = await this.page
                    .evaluate(async (sel) => {
                    const el = document.querySelector(sel);
                    if (!el)
                        return null;
                    if (el.srcdoc && el.srcdoc.trim())
                        return { kind: 'html', html: el.srcdoc };
                    const src = el.src || el.getAttribute('src') || '';
                    if (src.startsWith('blob:')) {
                        try {
                            const res = await fetch(src);
                            const html = await res.text();
                            return { kind: 'html', html };
                        }
                        catch {
                            return null;
                        }
                    }
                    if (src && src !== 'about:blank')
                        return { kind: 'url', url: src };
                    return null;
                }, placeholder.iframeSelector)
                    .catch(() => null);
                if (live)
                    return live;
            }
            return null;
        }
        if (rawSrc.startsWith('blob:')) {
            if (placeholder.iframeSelector) {
                const html = await this.page
                    .evaluate(async (sel) => {
                    const el = document.querySelector(sel);
                    const src = el?.src || '';
                    if (!src.startsWith('blob:'))
                        return null;
                    try {
                        const res = await fetch(src);
                        return await res.text();
                    }
                    catch {
                        return null;
                    }
                }, placeholder.iframeSelector)
                    .catch(() => null);
                if (html)
                    return { kind: 'html', html };
            }
            return null;
        }
        if (rawSrc.startsWith('data:text/html')) {
            try {
                const comma = rawSrc.indexOf(',');
                if (comma < 0)
                    return null;
                const meta = rawSrc.slice(0, comma);
                const data = rawSrc.slice(comma + 1);
                const html = /;base64/i.test(meta)
                    ? Buffer.from(data, 'base64').toString('utf8')
                    : decodeURIComponent(data);
                return { kind: 'html', html };
            }
            catch {
                return null;
            }
        }
        try {
            const base = placeholder.iframeBaseUrl || this.page.url() || 'about:blank';
            const absolute = new URL(rawSrc, base).href;
            return { kind: 'url', url: absolute };
        }
        catch {
            return { kind: 'url', url: rawSrc };
        }
    }
    /**
     * Translate + scale child-page element coordinates into the parent slide space.
     */
    offsetIframeElements(elements, offsetX, offsetY, scale) {
        const s = scale > 0 ? scale : 1;
        const scaleCmd = (cmd) => {
            if (cmd.type === 'Z')
                return cmd;
            if (cmd.type === 'M' || cmd.type === 'L') {
                return { type: cmd.type, x: cmd.x * s, y: cmd.y * s };
            }
            if (cmd.type === 'C') {
                return {
                    type: 'C',
                    x1: cmd.x1 * s,
                    y1: cmd.y1 * s,
                    x2: cmd.x2 * s,
                    y2: cmd.y2 * s,
                    x: cmd.x * s,
                    y: cmd.y * s,
                };
            }
            if (cmd.type === 'A') {
                const arc = cmd;
                return {
                    type: 'A',
                    rx: arc.rx * s,
                    ry: arc.ry * s,
                    rot: arc.rot,
                    large: arc.large,
                    sweep: arc.sweep,
                    x: arc.x * s,
                    y: arc.y * s,
                };
            }
            return cmd;
        };
        for (const el of elements) {
            el.x = offsetX + el.x * s;
            el.y = offsetY + el.y * s;
            el.width = el.width * s;
            el.height = el.height * s;
            if (el.svgLineEndpoints) {
                el.svgLineEndpoints = {
                    x1: offsetX + el.svgLineEndpoints.x1 * s,
                    y1: offsetY + el.svgLineEndpoints.y1 * s,
                    x2: offsetX + el.svgLineEndpoints.x2 * s,
                    y2: offsetY + el.svgLineEndpoints.y2 * s,
                };
            }
            // Relative to element bbox — scale only.
            if (el.clipPathPolygonPx) {
                el.clipPathPolygonPx = el.clipPathPolygonPx.map((p) => ({
                    x: p.x * s,
                    y: p.y * s,
                }));
            }
            if (el.svgPathCommandsPx) {
                el.svgPathCommandsPx = el.svgPathCommandsPx.map(scaleCmd);
            }
            if (el.svgMarkerShapes) {
                for (const m of el.svgMarkerShapes) {
                    m.x = offsetX + m.x * s;
                    m.y = offsetY + m.y * s;
                    m.width *= s;
                    m.height *= s;
                    if (m.clipPathPolygonPx) {
                        m.clipPathPolygonPx = m.clipPathPolygonPx.map((p) => ({
                            x: p.x * s,
                            y: p.y * s,
                        }));
                    }
                }
            }
            if (typeof el.listMarkerOffset === 'number')
                el.listMarkerOffset *= s;
            if (typeof el.beforePseudoWidthPx === 'number')
                el.beforePseudoWidthPx *= s;
            if (typeof el.textFlowExtraMarginLeftPx === 'number') {
                el.textFlowExtraMarginLeftPx *= s;
            }
            if (typeof el.parentBorderRadiusPx === 'number')
                el.parentBorderRadiusPx *= s;
        }
    }
    /**
     * Emit the iframe element's own border/fill as a shape so the frame chrome
     * is preserved after the placeholder is replaced by child content.
     *
     * When `bodyBg` is provided (extracted from the child page's rasterized
     * `<body>` background), the chrome shape adopts it as its fill so the visible
     * background respects the iframe's border-radius. Without this, the body
     * background would be emitted as a separate sharp rectangle image that covers
     * the chrome shape's rounded corners.
     */
    buildIframeChromeShape(placeholder, bodyBg) {
        const styles = placeholder.styles || {};
        const bg = styles.backgroundColor;
        const hasBg = !!bg &&
            bg !== 'rgba(0, 0, 0, 0)' &&
            bg !== 'transparent' &&
            bg !== 'none';
        const borderWidth = typeof styles.borderWidth === 'number' ? styles.borderWidth : 0;
        const hasBorder = borderWidth > 0 ||
            [styles.borderLeftWidth, styles.borderRightWidth, styles.borderTopWidth, styles.borderBottomWidth]
                .some((w) => (typeof w === 'string' ? parseFloat(w) : 0) > 0);
        // The child page <body> background is what the user actually sees inside
        // the iframe (it sits on top of the iframe element's own background). When
        // we extracted it from the rasterized page-bg element, prefer it for the
        // chrome fill so the rounded shape shows the correct color/gradient.
        const mergedBg = bodyBg?.backgroundColor;
        const mergedBgImage = bodyBg?.backgroundImage;
        const hasMergedBg = !!mergedBg &&
            mergedBg !== 'rgba(0, 0, 0, 0)' &&
            mergedBg !== 'transparent' &&
            mergedBg !== 'none';
        const hasMergedBgImage = !!mergedBgImage && mergedBgImage !== 'none';
        // Emit a chrome shape when the iframe has its own bg/border OR when we
        // have a merged body background to render (so the body fill still gets
        // the rounded corners even if the iframe element itself is transparent).
        if (!hasBg && !hasBorder && !hasMergedBg && !hasMergedBgImage)
            return null;
        return {
            type: 'shape',
            tag: 'iframe-chrome',
            elementId: placeholder.elementId,
            animationGroupId: placeholder.animationGroupId,
            x: placeholder.x,
            y: placeholder.y,
            width: placeholder.width,
            height: placeholder.height,
            styles: {
                backgroundColor: hasMergedBg ? mergedBg : (hasBg ? bg : undefined),
                backgroundImage: hasMergedBgImage ? mergedBgImage : styles.backgroundImage,
                borderColor: styles.borderColor,
                borderWidth: styles.borderWidth,
                borderStyle: styles.borderStyle,
                borderRadius: styles.borderRadius,
                borderLeftWidth: styles.borderLeftWidth,
                borderRightWidth: styles.borderRightWidth,
                borderTopWidth: styles.borderTopWidth,
                borderBottomWidth: styles.borderBottomWidth,
                borderLeftColor: styles.borderLeftColor,
                borderRightColor: styles.borderRightColor,
                borderTopColor: styles.borderTopColor,
                borderBottomColor: styles.borderBottomColor,
                borderLeftStyle: styles.borderLeftStyle,
                borderRightStyle: styles.borderRightStyle,
                borderTopStyle: styles.borderTopStyle,
                borderBottomStyle: styles.borderBottomStyle,
                opacity: styles.opacity,
                zIndex: typeof styles.zIndex === 'number' ? styles.zIndex - 1 : undefined,
            },
        };
    }
    /**
     * Rasterize the iframe element as it appears on the parent page.
     */
    async screenshotIframePlaceholder(placeholder) {
        const selector = placeholder.iframeSelector;
        if (!selector)
            return null;
        try {
            const locator = this.page.locator(selector);
            if ((await locator.count()) === 0)
                return null;
            const buffer = await locator.first().screenshot({
                type: 'png',
                omitBackground: false,
            });
            return {
                type: 'image',
                tag: 'iframe',
                elementId: placeholder.elementId,
                animationRaw: placeholder.animationRaw,
                animationGroupId: placeholder.animationGroupId,
                x: placeholder.x,
                y: placeholder.y,
                width: placeholder.width,
                height: placeholder.height,
                styles: {
                    ...placeholder.styles,
                    // Screenshot already bakes opacity into pixels.
                    opacity: 1,
                },
                dataUrl: `data:image/png;base64,${buffer.toString('base64')}`,
                screenshotBakesOpacity: true,
            };
        }
        catch (e) {
            console.warn('Failed to screenshot iframe:', e);
            return null;
        }
    }
    /**
     * Detect slide boundaries based on selector or height
     */
    async detectSlides(elements, slideSelector, splitByHeight = false) {
        const slides = new Map();
        if (slideSelector) {
            // Group by slide selector elements
            const slideElements = elements.filter((el) => this.matchesSelector(el, slideSelector));
            slideElements.forEach((slideEl, index) => {
                const slideY = slideEl.y;
                const nextSlideY = index < slideElements.length - 1
                    ? slideElements[index + 1].y
                    : Infinity;
                const slideContent = elements.filter((el) => el.y >= slideY && el.y < nextSlideY);
                slides.set(index, slideContent);
            });
        }
        else if (splitByHeight) {
            // Split by fixed height (720px sections)
            elements.forEach((el) => {
                const slideIndex = Math.floor(el.y / (0, coordinate_1.getSlideHeightPx)());
                if (!slides.has(slideIndex)) {
                    slides.set(slideIndex, []);
                }
                slides.get(slideIndex).push(el);
            });
        }
        else {
            // Single slide
            slides.set(0, elements);
        }
        return slides;
    }
    /**
     * Simple selector matching helper
     */
    matchesSelector(element, selector) {
        // Simple class selector matching
        if (selector.startsWith('.')) {
            const className = selector.slice(1);
            return element.tag.includes(className);
        }
        return false;
    }
}
exports.ElementInspector = ElementInspector;
