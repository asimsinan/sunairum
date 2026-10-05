# pritzker_2026_test_20260516 - Design Spec

## I. Project Information

| Item | Value |
| ---- | ----- |
| **Project Name** | pritzker_2026_test_20260516 |
| **Canvas Format** | PPT 16:9 (1280×720) |
| **Page Count** | 11 |
| **Design Style** | A) General Versatile + editorial design / magazine feel / architecture photography-led |
| **Target Audience** | Architecture/design enthusiasts, design professionals, and cultural media readers |
| **Use Case** | Industry sharing, design classes, long-form social media posts, and book-club talks |
| **Created Date** | 2026-05-16 |

---

## II. Canvas Specification

| Property | Value |
| -------- | ----- |
| **Format** | PPT 16:9 |
| **Dimensions** | 1280×720 |
| **viewBox** | `0 0 1280 720` |
| **Margins** | 60px left/right / 50px top/bottom |
| **Content Area** | 1160×620 |

---

## III. Visual Theme

### Theme Style

- **Style**: Editorial magazine feel + architecture photography-led
- **Theme**: Light theme
- **Tone**: Restrained, resilient, weighty — let the images speak, with text providing the point; concrete-textured off-white background + ink-black text + warm-gold accents

### Color Scheme

| Role | HEX | Purpose |
| ---- | --- | ------- |
| **Background** | `#F5F2EC` | Off-white xuan-paper background |
| **Secondary bg** | `#EDE8DE` | Cards / sidebars |
| **Primary** | `#1C1C1C` | Titles and body text |
| **Accent** | `#B8935A` | Numbers, dividers, and emphasis |
| **Body text** | `#1C1C1C` | Main body color |
| **Secondary text** | `#5C5852` | Secondary text and figure captions |
| **Tertiary text** | `#8B8680` | Concrete gray for footers and supporting information |
| **Border/divider** | `#D4CFC4` | Dividers |

---

## IV. Typography System

### Font Plan

**Typography direction**: Editorial CJK — Western serif × Chinese sans serif, evoking the feel of a magazine column

| Role | Chinese | English | Fallback tail |
| ---- | ------- | ------- | ------------- |
| **Title** | `"Microsoft YaHei", "PingFang SC"` | `Georgia` | `serif` |
| **Body** | `"Microsoft YaHei", "PingFang SC"` | `Arial` | `sans-serif` |
| **Emphasis** | `KaiTi` | `Georgia` | `serif` |
| **Code** | — | `Consolas, "Courier New"` | `monospace` |

**Per-role font stacks**:

- Title: `Georgia, "Microsoft YaHei", "PingFang SC", serif`
- Body: `"Microsoft YaHei", "PingFang SC", Arial, sans-serif`
- Emphasis: `KaiTi, Georgia, "Microsoft YaHei", serif`
- Code: `Consolas, "Courier New", monospace`

### Font Size Hierarchy

**Baseline**: Body = 22px (moderate density)

| Purpose | Ratio | Project value | Weight |
| ------- | ----- | ------------- | ------ |
| Cover title | 3.3x | 72px | Bold |
| Chapter / section opener | 2.2x | 48px | Bold |
| Page title | 1.6-1.8x | 36-40px | Bold |
| Project number (01-08 large number) | 4x | 88px | Light Italic (Georgia) |
| Subtitle | 1.3x | 28px | SemiBold |
| **Body** | **1x** | **22px** | Regular |
| Annotation / caption | 0.7x | 15px | Regular |
| Page number / footnote | 0.55x | 12px | Regular |

---

## V. Layout Principles

### Page Structure

- **Header area**: 50-100px (number + section anchor)
- **Content area**: ~520px (main visual and textual content)
- **Footer area**: 30-40px (page number, sources, brand anchor)

### Layout Pattern Library

Do not assume a dominant pattern. Choose the rhythm for each page based on its content and character (see the `Layout pattern` column in the §VIII table). Principles:
1. Do not repeat the pattern on adjacent pages
2. Use the same pattern no more than twice across the entire deck
3. Let image proportions drive orientation (landscape images favor hero/top-and-bottom bands, square images favor side-by-side layouts, portrait images favor left-and-right bands)
4. Combine multiple images on the same topic into one page (multi-image composition) rather than splitting them across pages

### Spacing Specification

**Universal**:

| Element | Range | Project |
| ------- | ----- | ------- |
| Safe margin | 40-60px | 60px |
| Content block gap | 24-40px | 32px |
| Icon-text gap | 8-16px | 12px |

**Non-card containers** (many breathing/hero pages):

- Line height: 1.5×
- Use `xMidYMid slice` for full-width hero images; hero text overlays use a 35–55% translucent black scrim
- Equal-width columns are not required; set text width for readability (24–32 Chinese characters per line)

---

## VI. Icon Usage Specification

### Source

- **Built-in icon library**: `tabler-outline` (1.5px stroke)
- Used only as accents for section numbers, geographic markers, and year badges; do not force them onto every page

### Recommended Icon List

| Purpose | Icon Path | Page |
| ------- | --------- | ---- |
| Location | `tabler-outline/map-pin` | P03-P10 (top right of each page) |
| Time/year | `tabler-outline/calendar` | P02 (overview) |
| Architect seal | `tabler-outline/blockquote` | P11 (closing) |
| Page-turn indicator | `tabler-outline/arrow-right` | P02 |

---

## VII. Visualization Reference List

No data visualization pages. This deck is driven entirely by image-and-text narratives, with no charts.

---

## VIII. Image Resource List

> All layout patterns are verbatim from `references/image-layout-patterns.md`. Cover at least 4 groups from Group A / C / D / E; rotate IDs within each group; do not repeat patterns on adjacent pages.

| Filename | Dimensions | Ratio | Purpose | Type | Layout pattern | Acquire Via | Status | Reference |
| -------- | --------- | ----- | ------- | ---- | -------------- | ----------- | ------ | --------- |
| ando_h_rooftop.png | 685×514 | 1.33 | P01 cover background (concrete water feature) | Photography | #1 full-bleed background with floating title | user | Existing | Tadao Ando H+ Art Museum rooftop water feature |
| ando_h_exterior.png | 1080×810 | 1.33 | P03 main image of an Ando landmark | Photography | #41 background image with native callout cards floating over | user | Existing | H+ Art Museum exterior along the river |
| ando_h_interior.png | 667×937 | 0.71 | P03 Ando secondary image (vertical) | Photography | (same multi-image composition) | user | Existing | H+ Art Museum interior space |
| chipperfield_milan_exterior.png | 1080×810 | 1.33 | P04 Chipperfield main image | Photography | #48 side-by-side comparison (ancient Rome vs. contemporary) | user | Existing | Milan ice hockey arena exterior |
| chipperfield_roman_amphitheater.png | 800×533 | 1.50 | P04 ancient Roman reference | Photography | (placed alongside the main image) | user | Existing | Ancient Roman amphitheater |
| chipperfield_milan_facade.png | 1024×1365 | 0.75 | P04 façade detail (vertical) | Photography | (secondary image strip) | user | Existing | Metal ring bands on the venue façade |
| zaha_tamkang_bridge.png | 960×640 | 1.50 | P05 Zaha bridge key visual | Photography | #15 multi-image montage with bold text spanning across | user | Existing | The Tamkang Bridge’s streamlined form |
| zaha_tamkang_structure.png | 960×640 | 1.50 | P05 Bridge structure | Photography | (montage member) | user | Existing | Single-tower cable-stayed bridge structure |
| zaha_tamkang_full.png | 831×554 | 1.50 | P05 Bridge wide view | Photography | (montage member) | user | Existing | Panoramic view of the bridge spanning the river |
| foster_shanghai_exterior.png | 1080×652 | 1.66 | P06 Foster feature image | Photography | #12 faded image as backdrop with oversized overlay text | user | Existing | Panoramic exterior of the Shanghai Ji Art Center |
| foster_shanghai_petal.png | 1080×1368 | 0.79 | P06 Petal detail | Photography | (small image frame beside floating layer) | user | Existing | Petal facade detail |
| oma_new_museum_before.png | 1080×809 | 1.33 | P07 OMA expansion before and after (before) | Photography | #50 before/after slider-style side-by-side | user | Existing | New Museum in New York before expansion |
| oma_new_museum_after.png | 1080×921 | 1.17 | P07 OMA expansion before and after (after) | Photography | (#50 paired) | user | Existing | New Museum in New York after expansion |
| oma_new_museum_massing.png | 1080×608 | 1.78 | P07 Massing model strip | Photography | (#50 lower sub-strip) | user | Existing | OMA massing model |
| oma_new_museum_interior.png | 1080×896 | 1.21 | P07 Interior (alternate) | Photography | (embedded secondary image frame) | user | Existing | Museum interior |
| zumthor_lacma_exterior.png | 1080×608 | 1.78 | P08 Zumthor feature image | Photography | #14 horizontal banner strip cutting through mid-section | user | Existing | LACMA David Geffen Galleries banner |
| zumthor_lacma_underside.png | 1080×720 | 1.50 | P08 Lower public space | Photography | (secondary image below mid-section strip) | user | Existing | Suspended, elevated ground-level public space |
| zumthor_lacma_interior.png | 1080×608 | 1.78 | P08 Interior (alternate) | Photography | (small upper-right scene) | user | Existing | LACMA interior |
| gehry_abu_dhabi_render1.png | 1080×608 | 1.78 | P09 Gehry render feature image | Photography | #19 image floating in whitespace with thin frame and caption | user | Existing | Main render of the Guggenheim Abu Dhabi |
| gehry_abu_dhabi_render2.png | 1080×607 | 1.78 | P09 Secondary render | Photography | (#19 second floating layer) | user | Existing | Render from a second angle |
| gehry_abu_dhabi_render3.png | 1000×1000 | 1.00 | P09 Square secondary image | Photography | (#19 third floating layer) | user | Existing | Aerial render |
| kere_senegal_exterior.png | 818×546 | 1.50 | P10 Kéré feature image (rammed-earth exterior) | Photography | #38 background image + annotation cards | user | Existing | Exterior of the Goethe-Institut in Senegal |
| kere_senegal_courtyard.png | 630×944 | 0.67 | P10 Courtyard (portrait) | Photography | (small image embedded in annotation) | user | Existing | Baobab-centered courtyard |
| kere_senegal_interior.png | 980×654 | 1.50 | P10 Interior | Photography | (small image embedded in annotation) | user | Existing | Institute interior space |

**Layout pattern coverage audit**:
- Group A (containers): #1 cover, #12 faded backdrop, #14 mid-section banner, #15 montage with text → 4 patterns
- Group C (overlay): #19 floating frame → 1 pattern
- Group D (image-as-canvas): #38 background + cards, #41 background + callouts → **2 patterns, satisfying Group D's hard coverage constraint**
- Group E (multi-image): #48 side-by-side, #50 before/after → 2 patterns
- 9 different patterns across 4 groups; no pattern used more than twice; no repetition on adjacent pages

---

## IX. Content Outline

### Part 1: Introduction

#### Slide 01 - Cover

- **Layout**: #1 Full-bleed background + floating title (concrete water feature as the visual anchor)
- **Title**: 2026 Pritzker Prize: A Season of Masters
- **Subtitle**: 8 new works, 8 distinct commitments
- **Info**: From the Suzhou Creek waterfront to the heart of the desert · Understanding the ideas and convictions of the world’s leading architects / Source: WeChat account Sun Wantong / 2026

#### Slide 02 - Overview of 8 Masters

- **Layout**: Negative-space-driven + accent image
- **Title**: Eight Masters, Eight Commitments
- **Content**:
  - 01 Tadao Ando · Suzhou H+ Museum · Suzhou, China
  - 02 David Chipperfield · Milano Santa Giulia Ice Palace · Milan, Italy
  - 03 Zaha Hadid（posthumous）· Tamsui Bridge · Taipei, China
  - 04 Norman Foster · Jiayu Art Museum Shanghai · Shanghai, China
  - 05 OMA + SANAA · New Museum Expansion · New York, USA
  - 06 Peter Zumthor · LACMA David Geffen Galleries · Los Angeles, USA
  - 07 Frank Gehry（posthumous）· Guggenheim Abu Dhabi · Abu Dhabi, UAE
  - 08 Diébédo Francis Kéré · Goethe-Institut Senegal · Dakar, Senegal

### Part 2: A Deep Dive into 8 New Works

#### Slide 03 - 01 Tadao Ando · Suzhou H+ Art Museum

- **Layout**: #41 image-as-canvas + floating annotation cards (horizontal image as the base, with a card floating on the left to carry text and a vertical image as a small inset at the upper right)
- **Title**: Writing a Concrete Poem in a Jiangnan Garden
- **Subtitle**: Tadao Ando · 1995 Pritzker Prize · Opens 2026.1
- **Content**:
  - Design concept: a three-dimensional garden with a wandering route, drawing the essence of gardens from Suzhou’s landscape memory
  - Material language: fair-faced concrete texture, no ornament, geometric lines × blank space shaped by light and shadow
  - Spatial narrative: the roof takes water as its theme, leading through a circuitous journey to spaces oriented toward sky and water
  - Core idea: "Return architecture to nature, and let art heal the human heart"

#### Slide 04 - 02 David Chipperfield · Milan Santa Giulia Ice Hockey Arena

- **Layout**: #48 side-by-side comparison (main contemporary venue on the left, ancient Roman theater reference on the right, with a horizontal façade strip below)
- **Title**: A Modern Echo of the Millennium-Old Roman Arena
- **Subtitle**: David Chipperfield · 2023 Pritzker Prize · 2026 Winter Olympics venue
- **Content**:
  - Capacity: 16,000 spectators; the only newly built permanent venue for these Winter Olympics
  - Formal lineage: echoes the elliptical form of Milan’s ancient Roman amphitheater
  - Façade: three metal rings + glass belt line + LED light strips
  - Design ethos: utmost restraint and precision; public architecture in service of people

#### Slide 05 - 03 Zaha Hadid (Posthumous Project) · Danjiang Bridge

- **Layout**: #15 multi-image montage + translucent dark banner at the top carrying the main title (three images arranged as a horizontal montage)
- **Title**: A Fluid Gesture Spanning the River
- **Subtitle**: Zaha Hadid · 2004 Pritzker Prize · Opens to traffic 2026.5.12
- **Content**:
  - 920 meters long, the world’s longest single-tower asymmetric cable-stayed bridge of its kind
  - A 100% realization of Zaha’s idealized design
  - A perfect fusion of engineering mechanics × avant-garde aesthetics
  - "Never set limits" — the master is gone, but the ideas endure

#### Slide 06 - 04 Norman Foster · Shanghai Ji Art Center

- **Layout**: #12 faded image as backdrop + oversized overlay text (darkened horizontal image as texture, oversized "04" and short title overlaid, with a slender vertical image as a small frame on the right)
- **Title**: Steel Petals Blossoming Along the Suzhou Creek
- **Subtitle**: Norman Foster · 1999 Pritzker Prize · Opens 2026.4
- **Content**:
  - Not a white box, but a life-form slowly growing within the city
  - A flower-like growth trajectory, rooted in the ground and reaching toward the sky
  - Three experiences: exhibitions, views, and the city
  - Beneath the high-tech shell, classical humanist spirit is reborn through modern materials

#### Slide 07 - 05 OMA + SANAA · New Museum Expansion, New York

- **Layout**: #50 before/after side-by-side (expansion before/after images placed side by side above, with a massing-model strip below)
- **Title**: Two Powerhouses, One Living Continuum of Old and New Art
- **Subtitle**: OMA (Rem Koolhaas, 2000) × SANAA (Kazuyo Sejima + Ryue Nishizawa, 2010) · Opens 2026.3.21
- **Content**:
  - $82 million investment, adding 5,574 ㎡
  - A collision between OMA’s avant-garde deconstruction and SANAA’s lightness and transparency
  - Transparent façades + staggered spaces + open planning allow city streetscapes and art spaces to flow into one another
  - "Iterative renewal, embracing diversity" — a century-old museum gains new vitality

#### Slide 08 - 06 Peter Zumthor · LACMA David Geffen Gallery

- **Layout**: #14 horizontal banner strip running through the middle (title space at the top, large horizontal image in the middle, narrative text at the bottom)
- **Title**: A Poetic Art Ark 20 Years in the Making
- **Subtitle**: Peter Zumthor · 2009 Pritzker Prize · Opens 2026.5.4
- **Content**:
  - $724 million investment, 32,293 ㎡, built over 20 years
  - Seven minimalist concrete pavilions spanning Wilshire Boulevard
  - Rejecting a hierarchy among artworks, the classical and contemporary coexist as equals
  - "Architecture is a poetic vessel for place"

#### Slide 09 - 07 Frank Gehry (Posthumous Work) · Abu Dhabi Guggenheim Museum

- **Layout**: #19 image floating in whitespace + multiple floating fine-line frames (three renderings staggered over an off-white background, with fine frames + small captions; text carried by negative space)
- **Title**: A "Deconstructivist Swan Song" in the Desert
- **Subtitle**: Frank Gehry (1929-2025) · 1989 Pritzker Prize · Opens 2026
- **Content**:
  - Two decades of work from the master’s final years; the metal façade shifts in texture with the sunlight
  - Irregular curves + dynamic folds + radically striking geometry
  - Advanced shading and insulation systems designed for the desert’s extreme climate
  - "Architecture has no boundaries, and creativity has no limits" — the deconstructivist master’s final chapter

#### Slide 10 - 08 Diébédo Francis Kéré · Goethe-Institut Senegal

- **Layout**: #38 background image + annotation cards (horizontal image as the base, with 2-3 translucent information cards floating above; vertical and interior images embedded within the cards)
- **Title**: Rammed-Earth Brick "Screens": Warm Architecture Rooted in the Local Soil
- **Subtitle**: Diébédo Francis Kéré · 2022 Pritzker Prize · Opens 2026.4
- **Content**:
  - A baobab tree (symbol of life) placed in the central courtyard
  - Locally compressed earth bricks + natural ventilation system, reducing reliance on air conditioning
  - "Adapt to nature rather than fight it"
  - In an era of global architectural homogenization, Kéré proves again that great architecture is rooted in the land and warms the heart

### Part 3: Wrap-Up

#### Slide 11 - Closing: All Enduring Legacies Begin with Deep Cultivation

- **Layout**: Negative-space-driven single element + warm-gold accent quote（no large image, text-led, generous whitespace）
- **Title**: Every Classic That Stands the Test of Time Comes from Day After Day of Commitment
- **Content**:
  - Some spend twenty years refining a venue — Zumthor
  - Some stay rooted in local culture, allowing architecture to take root in the land — Kéré
  - Some break boundaries and overturn conventions — Zaha, Gehry
  - Closing statement: An ultimate reverence for and deep reflection on space, nature, and humanity
- **Footer**: Sources: WeChat Official Account "Sun Wantong" / A Tribute to Eight Masters / 2026

---

## X. Speaker Notes Requirements

- **Filename**: Match the SVG name (`01_cover.svg` → `notes/01_cover.md`)
- **Total duration**: Approximately 12 minutes
- **Notes style**: Cultural essay style, prioritizing narrative warmth over technical parameters
- **Purpose**: inform + inspire

---

## XI. Technical Constraints Reminder

1. viewBox: `0 0 1280 720`
2. `<rect>` background, `<tspan>` text wrapping
3. Transparency defaults to `fill-opacity` / `stroke-opacity`; `rgba()` remains converter-compatible
4. Forbidden: `mask`, `<style>`, `class`, `foreignObject`, `textPath`, `<animate*>`, `<script>`
   - `<g opacity>` can be converted but produces an approximate-fidelity warning; use child-element opacity by default
5. Characters such as `—`, `·`, and `→` use raw Unicode; HTML named entities are forbidden
6. Use `preserveAspectRatio="xMidYMid slice"` for full-bleed images; use `<rect fill-opacity>` for translucent scrims
