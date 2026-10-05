# Aesthetic Weekly · Unlocking the Prologue to Trends - Design Spec

> This document is the human-readable design narrative — rationale, audience, style, color choices, content outline. It is read once by downstream roles for context.
>
> The machine-readable execution contract lives in `spec_lock.md` (short form of color / typography / icon / image decisions). Executor re-reads `spec_lock.md` before every SVG page to resist context-compression drift. Keep the two files in sync; if they diverge, `spec_lock.md` wins.

## I. Project Information

| Item | Value |
| ---- | ----- |
| **Project Name** | Aesthetic Weekly · Unlocking the Prelude to Trends |
| **Canvas Format** | PPT 16:9 (1280×720) |
| **Page Count** | 16 |
| **Design Style** | General Versatile — Magazine Editorial |
| **Target Audience** | Fashion industry professionals, luxury enthusiasts, and brand marketers |
| **Use Case** | Fashion news sharing, brand updates, and social media distribution |
| **Created Date** | 2026-04-26 |

---

## II. Canvas Specification

| Property | Value |
| -------- | ----- |
| **Format** | PPT 16:9 |
| **Dimensions** | 1280×720 |
| **viewBox** | `0 0 1280 720` |
| **Margins** | 50px left/right, 40px top/bottom |
| **Content Area** | 1180×640 |

---

## III. Visual Theme

### Theme Style

- **Style**: Magazine Editorial — high-end fashion magazine editorial style
- **Theme**: Dark theme — dark background highlighting the brand identity
- **Tone**: Luxurious, refined, modern, magazine-like

### Color Scheme

| Role | HEX | Purpose |
| ---- | --- | ------- |
| **Background** | `#0A0A0A` | Deep black background, luxury-magazine tone |
| **Secondary bg** | `#1A1A1A` | Card / section background |
| **Primary** | `#C9A96E` | Gold, a luxury-brand signature color for title decoration and icons |
| **Accent** | `#E8D5B5` | Light gold / ivory for subtitles and key information highlights |
| **Secondary accent** | `#8B7355` | Dark gold / bronze for gradient transitions and supporting decoration |
| **Body text** | `#F5F0EB` | Warm white body text |
| **Secondary text** | `#9E9690` | Gray-brown annotation text |
| **Border/divider** | `#2A2520` | Dark brown borders and dividers |

### Gradient Scheme

```xml
<!-- Title accent gradient -->
<linearGradient id="titleGradient" x1="0%" y1="0%" x2="100%" y2="0%">
  <stop offset="0%" stop-color="#C9A96E"/>
  <stop offset="100%" stop-color="#E8D5B5"/>
</linearGradient>

<!-- Decorative radial glow -->
<radialGradient id="bgDecor" cx="80%" cy="20%" r="50%">
  <stop offset="0%" stop-color="#C9A96E" stop-opacity="0.08"/>
  <stop offset="100%" stop-color="#C9A96E" stop-opacity="0"/>
</radialGradient>

<!-- Image overlay gradient (bottom fade) -->
<linearGradient id="imageOverlay" x1="0%" y1="0%" x2="0%" y2="100%">
  <stop offset="0%" stop-color="#0A0A0A" stop-opacity="0"/>
  <stop offset="60%" stop-color="#0A0A0A" stop-opacity="0.3"/>
  <stop offset="100%" stop-color="#0A0A0A" stop-opacity="0.85"/>
</linearGradient>
```

---

## IV. Typography System

### Font Plan

**Typography direction**: Editorial display — serif titles create a magazine feel, while sans-serif body text ensures readability

| Role | Chinese | English | Fallback tail |
| ---- | ------- | ------- | ------------- |
| **Title** | `SimSun` | `Georgia` | `serif` |
| **Body** | `"Microsoft YaHei", "PingFang SC"` | `Arial` | `sans-serif` |
| **Emphasis** | `SimSun` | `Georgia` | `serif` |
| **Code** | — | `Consolas, "Courier New"` | `monospace` |

**Per-role font stacks** (CSS `font-family` strings):

- Title: `Georgia, SimSun, serif`
- Body: `"Microsoft YaHei", "PingFang SC", Arial, sans-serif`
- Emphasis: `Georgia, SimSun, serif`
- Code: `Consolas, "Courier New", monospace`

> **Stack ordering rationale**: Title stack is Latin-led (`Georgia` first) because brand names dominate headline text — Georgia's elegant serifs display English brand names beautifully, while CJK characters fall through to SimSun. Body stack is CJK-led because the main content is in Chinese.

### Font Size Hierarchy

**Baseline**: Body font size = 18px (dense — accommodating 16 brand stories across 16 pages)

| Purpose | Ratio to body | Size | Weight |
| ------- | ------------- | ---- | ------ |
| Cover title | 3.3x | 60px | Bold |
| Brand name heading | 2x | 36px | Bold |
| Page title | 1.7x | 30px | Bold |
| Subtitle | 1.3x | 24px | SemiBold |
| **Body content** | **1x** | **18px** | Regular |
| Brand tag / label | 0.8x | 14px | SemiBold |
| Annotation / caption | 0.7x | 13px | Regular |
| Page number / footnote | 0.6x | 11px | Regular |

---

## V. Layout Principles

### Page Structure

- **Header area**: 40px — brand name/section identifier area, separated by a thin gold line
- **Content area**: 640px — main content area, flexibly allocated according to the number of brands
- **Footer area**: 40px — page number and source attribution

### Layout Pattern Library

This project centers on an editorial magazine style and uses varied layouts to avoid an AI-generated feel:

| Pattern | Usage |
| ------- | ----- |
| **Full-bleed + floating text** | Cover page; brand image fills the canvas, title floats over it |
| **Asymmetric split (3:7 / 4:6)** | Single-brand feature page; image-led with concise text |
| **Figure-text overlap** | Brand title overlaps the image edge for a magazine-layout feel |
| **Two-column magazine** | Two-brand spread; one brand on each side |
| **Negative-space-driven** | Breathing page; whitespace highlights a single brand visual |
| **Top-bottom split** | Wide brand image + copy below |

### Spacing Specification

**Universal**:

| Element | Value |
| ------- | ----- |
| Safe margin | 50px |
| Content block gap | 30px |
| Icon-text gap | 10px |

**Card-based layouts** (where applicable):

| Element | Value |
| ------- | ----- |
| Card gap | 24px |
| Card padding | 24px |
| Card border radius | 12px |

---

## VI. Icon Usage Specification

### Source

- **Built-in icon library**: `phosphor-duotone` — duotone style with rich layering, fashionable and modern
- **Brand icons**: `simple-icons` — brand logos (for displaying brand marks when needed)
- **Usage method**: SVG placeholder `<use data-icon="library/icon-name" .../>`

### Recommended Icon List

| Purpose | Icon Path | Page |
| ------- | --------- | ---- |
| Fashion/trends | `phosphor-duotone/dress` | Cover, multiple pages |
| Fine jewelry | `phosphor-duotone/diamond` | P07 |
| Watches | `phosphor-duotone/watch` | P04 |
| Home/design | `phosphor-duotone/house` | P02, P05 |
| Exhibition/art | `phosphor-duotone/palette` | P06, P08 |
| Fragrance/beauty | `phosphor-duotone/flower` | P11 |
| Handbags/accessories | `phosphor-duotone/handbag` | P10 |
| Events/celebrities | `phosphor-duotone/star` | P12 |
| Collaboration/partnership | `phosphor-duotone/handshake` | P13 |
| Scissors/tailoring | `phosphor-duotone/scissors` | P09 |
| Store/retail | `phosphor-duotone/storefront` | P07 |
| Camera/photography | `phosphor-duotone/camera` | P08 |
| Crown/luxury | `phosphor-duotone/crown` | Cover |
| Sparkle/highlight | `phosphor-duotone/sparkle` | Multiple pages |
| Tag/brand | `phosphor-duotone/tag` | Multiple pages |
| Global/international | `phosphor-duotone/globe` | P07 |

---

## VII. Visualization Reference List

```
Catalog read: 40+ templates / 8 categories
Runners-up considered: fewer than 3 viz pages — this is a magazine-style news digest, not a data-driven deck
```

This project is a compilation of fashion news and features, centered on brand narratives and image presentation, with no data visualization requirements. All pages use editorial layouts combining text and images, so no chart templates are needed.

---

## VIII. Image Resource List

| Filename | Dimensions | Ratio | Intent | Purpose | Type | Status |
| -------- | ---------- | ----- | ------ | ------- | ---- | ------ |
| cover_hermes.jpg | 1080x997 | 1.08 | Hero / full-bleed | Cover key visual | Photography | Existing |
| hermes_home.jpg | 1080x772 | 1.40 | Side-by-side | Hermès home world | Photography | Existing |
| chanel_coco.jpg | 1080x608 | 1.78 | Hero / full-bleed | CHANEL COCO BEACH | Photography | Existing |
| dior_fashion.jpg | 1080x1080 | 1.00 | Side-by-side | Dior fashion | Photography | Existing |
| dior_watch1.jpg | 1080x1080 | 1.00 | Side-by-side | Dior Chiffre Rouge watch | Photography | Existing |
| lv_objets.jpg | 1080x608 | 1.78 | Hero / full-bleed | LV Objets Nomades | Photography | Existing |
| gucci_memoria1.jpg | 1080x810 | 1.33 | Side-by-side | Gucci Memoria exhibition | Photography | Existing |
| gucci_memoria2.jpg | 1080x810 | 1.33 | Accent | Additional Gucci exhibition image | Photography | Existing |
| vhernier_jewelry.jpg | 1080x720 | 1.50 | Side-by-side | Vhernier jewelry | Photography | Existing |
| celine_summer.jpg | 1080x1350 | 0.80 | Side-by-side | CELINE summer | Photography | Existing |
| bv_arts.jpg | 1080x1350 | 0.80 | Side-by-side | BV art photography | Photography | Existing |
| mcqueen_exhibition.jpg | 1080x721 | 1.50 | Side-by-side | McQueen beneath the surface | Photography | Existing |
| maxmara_show.jpg | 1080x634 | 1.70 | Hero / full-bleed | Max Mara debut show | Photography | Existing |
| chloe_tomato.jpg | 1080x1440 | 0.75 | Side-by-side | Chloé Tomato chairs | Photography | Existing |
| tadfab_bag.jpg | 1080x1440 | 0.75 | Side-by-side | TAD FAB bags | Photography | Existing |
| apedemod_fold.jpg | 1080x1619 | 0.67 | Side-by-side | Apede Mod origami folds | Photography | Existing |
| boss_fragrance.jpg | 1080x1440 | 0.75 | Side-by-side | BOSS fragrance | Photography | Existing |
| fresh_event.jpg | 1080×721 | 1.50 | Side-by-side | fresh launch event | Photography | Existing |
| jorya_popup.jpg | 1080x810 | 1.33 | Side-by-side | JORYA pop-up | Photography | Existing |
| arket_gohar.jpg | 1080x720 | 1.50 | Side-by-side | ARKET collaboration | Photography | Existing |
| stevemadden_lexie.jpg | 1080x721 | 1.50 | Side-by-side | Steve Madden ambassador | Photography | Existing |
| crocs_molly.jpg | 1080x608 | 1.78 | Side-by-side | Crocs × MOLLY | Photography | Existing |

---

## IX. Content Outline

### Part 1: Introduction

#### Slide 01 — Cover

- **Layout**: Full-bleed + floating text — cover_hermes.jpg fills the canvas, with the title floating over a dark gradient layer
- **Title**: NEWS Café | Aesthetic Weekly
- **Subtitle**: Unlock the Prelude to Trends
- **Info**: This week's fashion highlights · April 2026

### Part 2: Top Luxury Brands

#### Slide 02 — The World of Hermès Home

- **Layout**: Asymmetric split (4:6) — text on the left, hermes_home.jpg on the right
- **Title**: The World of Hermès Home
- **Content**:
  - New home collection unveiled during Milan Design Week
  - Thirty rectangular columns form an immersive set
  - Hammered metal, leather inlay, and sculpted textiles create a dialogue between materials and an object-driven narrative
  - Continuing the brand’s craft traditions and timeless aesthetics

#### Slide 03 — CHANEL COCO BEACH

- **Layout**: Hero / full-bleed — chanel_coco.jpg as the background, with text floating over a bottom gradient layer
- **Title**: CHANEL COCO BEACH 2026
- **Content**:
  - A limited-time boutique opens in central Shanghai
  - A resort villa concept facing a garden
  - Inspired by pastoral landscapes and black-sand beaches
  - The first COCO BEACH collection created by Matthieu Blazy

#### Slide 04 — Dior: Fashion and Timepieces

- **Layout**: Two-column — dior_fashion.jpg on the left, dior_watch1.jpg + copy on the right
- **Title**: Dior’s dual-sided allure
- **Content**:
  - Left column: Sabrina Carpenter appeared at Coachella in a gown designed by Jonathan Anderson
  - Right column: The Chiffre Rouge watch collection refreshed with three limited-edition pieces
  - The red seconds hand pays tribute to the color of life in Monsieur Dior’s imagination
  - Monsieur Dior’s favorite number, “8,” becomes a talisman

#### Slide 05 — Louis Vuitton Objets Nomades

- **Layout**: Hero / full-bleed — lv_objets.jpg background + floating text block
- **Title**: Louis Vuitton Objets Nomades
- **Content**:
  - A new travel-home collection presented during Milan Design Week
  - A tribute to Art Deco and master designer Pierre Legrain
  - New works by contemporary designers from Studio Campana, Raw Edges, and Franck Genser
  - New pieces including the Collar lounge chair and Aqua dining table

#### Slide 06 — Gucci Memoria

- **Layout**: Asymmetric split (3:7) — gucci_memoria1.jpg dominates on the right + copy on the left, with gucci_memoria2.jpg as a small accent image
- **Title**: Gucci Memoria
- **Content**:
  - Immersive exhibition in the cloister of San Simpliciano, Milan
  - Curated by Demna, tracing the brand’s 105-year history
  - Twelve tapestries distill key milestones in the brand’s development
  - Flora-themed garden installation and exclusive presale

### Part 3: Fine Jewelry and Fashion

#### Slide 07 — Vhernier × CELINE

- **Layout**: Two-column magazine — Vhernier on the left (vhernier_jewelry.jpg), CELINE on the right (celine_summer.jpg)
- **Title**: A new realm of jewelry · French allure
- **Content**:
  - Left column: Vhernier officially enters mainland China, opening dual stores in Beijing and Shanghai, with pure Milanese design
  - Right column: Été CELINE campaign, inspired by seaside holidays, with the effortless allure of the French coast

#### Slide 08 — BV × McQueen: Two Expressions of Art

- **Layout**: Two-column magazine — BV on the left (bv_arts.jpg), McQueen on the right (mcqueen_exhibition.jpg)
- **Title**: Two expressions of art
- **Content**:
  - Left column: BV “for the Arts” photography book, Venice through Peter Fraser’s lens, woven aesthetics
  - Right column: McQueen “Beneath the Surface” immersive exhibition in Shanghai, Manta bag recreating a 2010 classic

### Part 4: Design and Lifestyle

#### Slide 09 — Max Mara × Chloé

- **Layout**: Two-column — Max Mara on the left (maxmara_show.jpg), Chloé on the right (chloe_tomato.jpg)
- **Title**: A new chapter in heritage
- **Content**:
  - Left column: Max Mara 2027 Resort collection debut in Shanghai, “THE MAX!” 75th-anniversary archive exhibition
  - Right column: Chloé × Poltronova limited reissue of the Tomato chair, an icon of Italy’s radical design movement of the 1970s

#### Slide 10 — TAD FAB × Apede Mod

- **Layout**: Two-column — TAD FAB on the left (tadfab_bag.jpg), Apede Mod on the right (apedemod_fold.jpg)
- **Title**: Reshaping structure
- **Content**:
  - Left column: TAD FAB’s new collection, defined by zippers, featuring a wraparound-zipper Hobo bag and relaxed sophistication
  - Right column: Apede Mod’s 10th-anniversary PF 2026 Origami collection, advancing folded-structure design

### Part 5: Beauty and Fragrance

#### Slide 11 — BOSS × fresh

- **Layout**: Two-column — BOSS on the left (boss_fragrance.jpg), fresh on the right (fresh_event.jpg)
- **Title**: A new sensory chapter
- **Content**:
  - Left column: BOSS The Scent fragrance, fresh woody leather notes, dual olfactory profiles, attended by Wang Tianchen and others
  - Right column: fresh’s “Ferment Your Way” launch, endorsed by all members of CORTIS, inspired by tea-drink culture

### Part 6: Collaborations and Crossovers

#### Slide 12 — JORYA × ARKET

- **Layout**: Two-column — JORYA on the left (jorya_popup.jpg), ARKET on the right (arket_gohar.jpg)
- **Title**: A new spirit of crossovers
- **Content**:
  - Left column: JORYA × YVMIN “Princess Diaries” Chengdu pop-up, featuring Zhao Lusi and a concept of layered, lightweight couture for heiresses
  - Right column: ARKET × Laila Gohar Milan installation, transforming an 18th-century carousel, with 27 collaborative pieces

### Part 7: Closing

#### Slide 16 — Ending

- **Layout**: Negative-space-driven — minimalist ending, brand/column mark centered
- **Title**: NEWS Café
- **Subtitle**: See You Next Week
- **Info**: A weekly aesthetic digest, unlocking the prelude to what's next<rect>` elements
3. Text wrapping uses `<tspan>` (`<foreignObject>` FORBIDDEN)
4. Transparency defaults to `fill-opacity` / `stroke-opacity`; `rgba()` remains converter-compatible
5. FORBIDDEN: `mask`, `<style>`, `class`, `foreignObject`
6. FORBIDDEN: `textPath`, `animate*`, `script`
7. Text characters: write typography & symbols as raw Unicode; HTML named entities FORBIDDEN. XML reserved chars use `&amp;` `&lt;` `&gt;` `&quot;` `&apos;`
8. `clipPath` conditionally allowed only on `<image>` elements
9. Prefer opacity on each child; `<g opacity>` remains converter-compatible with an approximate-fidelity warning
10. Dark theme: all text must use light colors (contrast ratio >= 4.5:1 against #0A0A0A)
