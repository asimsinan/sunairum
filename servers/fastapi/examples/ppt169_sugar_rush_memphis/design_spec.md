# sugar_rush_memphis - Design Spec

> Human-readable design narrative. Machine-readable execution contract: `spec_lock.md`. Executor re-reads `spec_lock.md` before every SVG page. On divergence, `spec_lock.md` wins.

## I. Project Information

| Item | Value |
| ---- | ----- |
| **Project Name** | sugar_rush_memphis |
| **Canvas Format** | PPT 16:9 (1280×720) |
| **Page Count** | 14 |
| **Design Style** | A) General Versatile + Memphis / Pop |
| **Target Audience** | Music festival audiences (18–35) + brand sponsors + media |
| **Use Case** | Annual guide to a fictional music festival (browsing + media distribution) |
| **Created Date** | 2026-05-17 |

---

## II. Canvas Specification

| Property | Value |
| -------- | ----- |
| **Format** | PPT 16:9 |
| **Dimensions** | 1280×720 |
| **viewBox** | `0 0 1280 720` |
| **Margins** | 60px left/right / 50px top/bottom |
| **Content Area** | 1160×620 (safe area) |

---

## III. Visual Theme

### Theme Style

- **Style**: A) General Versatile + Memphis / Pop
- **Theme**: Light theme (cream background)
- **Tone**: Bold, candy-colored, 80s revival, clash-of-colors exuberance

### Color Scheme

| Role | HEX | Purpose |
| ---- | --- | ------- |
| **Background** | `#FFF8EE` | Cream-white page background (55%) |
| **Secondary bg** | `#FFE9C7` | Light cream card fill (specific cards) |
| **Primary** | `#FF3DA5` | Bubblegum pink — titles / accent color blocks |
| **Accent** | `#00B8D9` | Electric blue — secondary emphasis / links |
| **Secondary accent** | `#FFD93D` | Bright yellow — highlights / numbers |
| **Tertiary accent** | `#00C896` | Mint green — chapter color coding |
| **Quaternary accent** | `#FF6B4A` | Coral red — decorative fragments |
| **Body text** | `#1A1A2E` | Ink black — body text |
| **Secondary text** | `#5C5C7A` | Gray-purple — annotations |
| **Border/divider** | `#1A1A2E` | Thick ink-black outlines (2-4px) |
| **Success** | `#00C896` | Reuses mint green |
| **Warning** | `#FF6B4A` | Reuses coral red |

> The combined proportion of contrasting colors must be ≤ 40%; use only 2–3 contrasting colors prominently on each page rather than stacking them all. Text contrast #1A1A2E on #FFF8EE = 15.5:1 (well above 4.5:1).

### AI Image Strategy

- **Image Rendering**: `flat`
- **Image Palette**: `vivid-launch`

> Lock the entire deck — every AI image shares flat rendering + vivid-launch color behavior. Automatically injected by Image_Generator.

### Gradient Scheme

```xml
<!-- Chapter opening page scrim gradient -->
<linearGradient id="heroScrim" x1="0%" y1="100%" x2="0%" y2="0%">
  <stop offset="0%" stop-color="#1A1A2E" stop-opacity="0.55"/>
  <stop offset="60%" stop-color="#1A1A2E" stop-opacity="0"/>
</linearGradient>

<!-- Fade into background on closing page -->
<linearGradient id="fadeToBg" x1="0%" y1="0%" x2="0%" y2="100%">
  <stop offset="0%" stop-color="#FFF8EE" stop-opacity="0"/>
  <stop offset="100%" stop-color="#FFF8EE" stop-opacity="0.95"/>
</linearGradient>
```

---

## IV. Typography System

### Font Plan

**Typography direction**: Strong Display × Neutral contrast — Impact creates poster-like tension in titles, while Arial / Microsoft YaHei ensures readable body text.

| Role | Chinese | English | Fallback tail |
| ---- | ------- | ------- | ------------- |
| **Title** | `"Microsoft YaHei"` | `Impact, "Arial Black"` | `sans-serif` |
| **Body** | `"Microsoft YaHei", "PingFang SC"` | `Arial` | `sans-serif` |
| **Emphasis** | `"Microsoft YaHei"` | `Impact` | `sans-serif` |
| **Code** | — | `Consolas, "Courier New"` | `monospace` |

**Per-role font stacks**:

- Title: `Impact, "Arial Black", "Microsoft YaHei", sans-serif`
- Body: `Arial, "Microsoft YaHei", "PingFang SC", sans-serif`
- Emphasis: `Impact, "Microsoft YaHei", sans-serif`
- Code: `Consolas, "Courier New", monospace`

> Title/Emphasis is Latin-led (Impact preferred) → English carries the poster-like impact; CJK falls back to Microsoft YaHei. Body text is switched to Arial-led to ensure a modern feel for Latin characters, while Chinese body copy still uses YaHei.

### Font Size Hierarchy

**Baseline**: Body font size = **20px** (moderate density, poster-like feel)

| Purpose | Ratio to body | Px | Weight |
| ------- | ------------- | ---- | ------ |
| Cover hero headline | 4-5x | 80-100px | Black |
| Chapter opener | 2.8-3.6x | 56-72px | Black |
| Page title | 1.8-2.2x | 36-44px | Black |
| Hero number | 4-6x | 80-120px | Black |
| Subtitle | 1.4-1.6x | 28-32px | Bold |
| **Body content** | **1x** | **20px** | Regular |
| Annotation / caption | 0.7-0.85x | 14-17px | Regular |
| Page number / footnote | 0.55-0.65x | 11-13px | Regular |

---

## V. Layout Principles

### Page Structure

- **Header area**: Top 50-80px — chapter identifier / page number / decorative fragments
- **Content area**: Middle 540-600px — main content
- **Footer area**: Bottom 30-50px — footer / Logo / page number

### Layout Pattern Library

| Pattern | Suitable Scenarios |
| ------- | ----------------- |
| **Single column centered** | Cover, chapter openers, closing |
| **Asymmetric split (3:7 / 2:8)** | Main content page (title on left + image card on right) |
| **Top-bottom split** | Ticketing page (comparison above + sponsorship below) |
| **Three/four column cards** | KPI / style camps / ticket tiers |
| **Matrix grid (2×2)** | Four-way style classification |
| **Center-radiating** | Five-stage hub_spoke |
| **Full-bleed + floating text** | Six chapter openers and the cover |
| **Figure-text overlap** | Headliner artist page (bold outlined blocks layered over portraits) |
| **Z-pattern / waterfall** | Timeline schedule (serpentine layout) |

### Memphis Decorative Fragments (1–3 can be overlaid per page)

- Dot clusters (3–5 #FF3DA5 dots arranged irregularly)
- Wavy lines (3–5 undulating #00B8D9 waves)
- Z-shaped lightning (#FFD93D / #FF6B4A geometric Z shapes)
- Triangle blocks (solid triangles rotated 45°)
- Checkerboard stripes (corner bands made of small black-and-white squares)
- Thick black outlines (2–4px ink-black borders added to every block)

### Spacing Specification

**Universal**:

| Element | Range | Project Value |
| ------- | ----- | ------------- |
| Safe margin from canvas edge | 40-60px | 60px |
| Content block gap | 24-40px | 32px |
| Icon-text gap | 8-16px | 12px |

**Card-based**:

| Element | Range | Project Value |
| ------- | ----- | ------------- |
| Card gap | 20-32px | 24px |
| Card padding | 20-32px | 24px |
| Card border radius | 8-16px | 12px |
| Card border (essential for Memphis) | 2-4px | 3px solid #1A1A2E |

**Non-card / breathing pages**:

- Line-height: 1.4–1.5× body font size
- Full-bleed text placement: preserve the focal area and add a scrim behind the text

---

## VI. Icon Usage Specification

### Source

- **Library**: `chunk-filled` (bold, solid, geometric, and well suited to Memphis’s hard-edged character)
- **Usage**: SVG `<use data-icon="chunk-filled/<name>" .../>` placeholder

### Recommended Icon List

| Purpose | Icon | Page |
| ------- | ---- | ---- |
| Number of days | `chunk-filled/calendar` | P03 |
| Stage / music | `chunk-filled/music` | P03, P09 |
| Artists | `chunk-filled/microphone` | P03, P05 |
| Audience | `chunk-filled/users` | P03 |
| Time | `chunk-filled/clock` | P10 |
| Lightning / energy | `chunk-filled/bolt` | P04, P07 |
| Heart / love | `chunk-filled/heart` | P04, P14 |
| Star / headliner | `chunk-filled/star` | P06 |
| Venue / location | `chunk-filled/map-pin` | P09 |
| Sun / summer | `chunk-filled/sun` | P02, P14 |
| Sparkle decoration | `chunk-filled/sparkles` | Deck-wide decoration |
| Headphones / electronic | `chunk-filled/headphones` | P07 |
| Merchandise market | `chunk-filled/shopping-bag` | P12 |
| Games / interaction | `chunk-filled/game-controller` | P12 |
| Ticketing | `chunk-filled/ticket` | P13 |
| Sponsorship / gifts | `chunk-filled/gift` | P13 |
| Process arrow | `chunk-filled/arrow-right` | P10 |

---

## VII. Visualization Reference List

Catalog read: 71 templates

| Page | Template | Path | Summary-quote (verbatim) | Usage |
| ---- | -------- | ---- | ------------------------ | ----- |
| P03 | kpi_cards | `templates/charts/kpi_cards.svg` | "Pick for 4-8 standalone numeric metrics shown as overview cards (2x2 or 1x4) — exec summary opener, dashboard headline, quarterly recap, res..." | Four key numbers: 7 days / 5 stages / 80 artist groups / 50,000 attendees |
| P04 | vertical_pillars | `templates/charts/vertical_pillars.svg` | "Pick for 1×3 / 1×4 / 1×5 vertical column layout where each pillar = one independent category with title + bullets — PEST (Political/Economic..." | Three core ideas: FREE / FUN / FOREVER YOUNG |
| P06 | icon_grid | `templates/charts/icon_grid.svg` | "Pick for 4-9 parallel features/capabilities/services as icon cards — feature grid, service lineup, benefits matrix, brand values, product hi..." | Four headliner artist cards |
| P07 | quadrant_text_bullets | `templates/charts/quadrant_text_bullets.svg` | "Pick for any 2×2 framework where each quadrant holds a titled bullet list — SWOT (Strengths/Weaknesses/Opportunities/Threats, internal-exter..." | Four style camps: rock / electronic / folk / hip-hop |
| P09 | hub_spoke | `templates/charts/hub_spoke.svg` | "Pick for 1 core capability + 4-8 surrounding capabilities (platform/ecosystem); each spoke = title or title + 1-2 line description. Skip if..." | Central main stage + 4 satellite stages radiating outward |
| P10 | timeline | `templates/charts/timeline.svg` | "Pick for 3-8 milestone events on a horizontal time axis (no duration). Skip for tasks with start/end ranges (use gantt_chart) or vertical la..." | 7-day music festival schedule |
| P12 | comparison_columns | `templates/charts/comparison_columns.svg` | "Pick for 2-4 pricing/service tier cards in side-by-side columns (marketing layout). Skip for dense feature comparison (use comparison_table)..." | Merch market vs interactive installations (two-column comparison) |
| P13 | comparison_columns | `templates/charts/comparison_columns.svg` | "Pick for 2-4 pricing/service tier cards in side-by-side columns (marketing layout). Skip for dense feature comparison (use comparison_table)..." | Three ticket tiers: EARLY / REGULAR / VIP |

**Runners-up considered**:

- `team_roster` | rejected for P06: The project uses illustrated avatars rather than photos of real employees, and needs to include non-identity fields such as “representative albums”; `icon_grid` offers more flexibility
- `numbered_steps` | rejected for P10: The seven-day schedule consists of fixed-date milestones rather than “how-to” steps; `timeline` better matches the semantics of a time axis
- `comparison_table` | rejected for P13: Ticket tiers contain only 4–5 rows of attributes; column-based marketing cards are more Memphis-pop, while the density of a table would overwhelm the visual design

---

## VIII. Image Resource List

| Filename | Dimensions | Ratio | Purpose | Type | Layout pattern | Acquire Via | Status | Reference | text_policy | page_role |
| -------- | --------- | ----- | ------- | ---- | -------------- | ----------- | ------ | --------- | ----------- | --------- |
| cover_bg.png | 1280×720 | 1.78 | Cover key visual | Illustration | #1 full-bleed background with floating title + #29 two-stop scrim | ai | Pending | Summer festival key visual: candy-colored neon sign "SUGAR RUSH" floating horizontally centered in a tropical jungle night sky; dotted cluster decoration fragments in the lower left and wavy lightning accents in the upper right; large cool dark area on the left for subtitle overlay; bird’s-eye silhouettes of the crowd forming an arc along the bottom | embedded | hero_page |
| ch1_what.png | 1280×720 | 1.78 | P02 Chapter 1 WHAT divider page | Illustration | #12 faded image as backdrop with oversized overlay text + #27 linear gradient mask | ai | Pending | Overhead panoramic view of a summer beach party: high-contrast umbrellas and graffiti-style crowd silhouettes; 50% negative space retained at center for title overlay; checkerboard corner decoration in the lower right | none | hero_page |
| ch2_who.png | 1280×720 | 1.78 | P05 Chapter 2 WHO divider page | Illustration | #1 full-bleed background with floating title + #38 background image + annotation cards with bezier leader lines | ai | Pending | Five stylized musician silhouettes standing side by side on a stage under neon spotlights, holding microphones, guitars, and synthesizers; pink, blue, and yellow contrasting beams in the background; airy, uncrowded composition | none | hero_page |
| headliners.png | 1200×500 | 2.40 | P06 Headliner Artist Quartet | Illustration | #26 triptych baked into a single wide image + #21 rounded rectangle crop | ai | Pending | Four-panel horizontal banner illustration: four stylized fictional musicians shown in front-facing half-length portraits side by side, left to right: female electric-guitar vocalist (pink hair) / male electronic synth DJ (gold sunglasses) / female folk guitarist (mint-green shirt) / male hip-hop rapper (bright yellow hoodie); each figure stands before a contrasting color-block background matching their musical style, with unified bold black outlines | none | local |
| ch3_where.png | 1280×720 | 1.78 | P08 Chapter 3 WHERE & WHEN title page | Illustration | #41 background image + measurement lines and module tags (engineering overlay) + #29 two-stop scrim | ai | Pending | Bird’s-eye panoramic view of a fictional music festival site: palm groves surrounding a central main stage and four satellite stages arranged radially, colorful tents and neon streetlights scattered throughout, crowds suggested by soft pink vectors, with the top third left open for the title | none | hero_page |
| ch4_vibes.png | 1280×720 | 1.78 | P11 Chapter 4 VIBES title page | Illustration | #1 full-bleed background with floating title + #28 radial gradient vignette | ai | Pending | Panoramic nighttime atmosphere: fluorescent wristbands and colored smoke rising above the crowd, distant stage LED screen displaying a giant abstract wave pattern, a jumping figure silhouette as the visual focal point in the foreground, dark space retained in the upper left for the title | none | hero_page |
| market.png | 600×400 | 1.50 | P12 Merchandise market scene | Illustration | #19 image floating in whitespace with thin frame and caption + #21 rounded rectangle crop | ai | Pending | Outdoor merchandise market stall: T-shirts, canvas bags, stickers, and neon light swords printed with SUGAR RUSH displayed beneath contrasting-color awnings, the vendor handing an item to a customer; vivid pop-poster energy | none | local |
| installation.png | 600×400 | 1.50 | P12 Interactive installation scene | Illustration | #19 image floating in whitespace with thin frame and caption + #21 rounded rectangle crop | ai | Pending | Immersive interactive art installation: giant inflatable geometric sculptures (pink sphere + blue triangle + yellow wave) standing on a lawn, two or three visitors weaving between them, taking selfies, and jumping, with blue sky and white clouds in the background | none | local |
| closing.png | 1280×720 | 1.78 | P14 Closing page | Illustration | #1 full-bleed background with floating title + #66 image fading into the solid background | ai | Pending | Empty backstage area at sunset: scattered colored confetti, balloons lifted by the wind, purple-pink glow along the distant horizon, the bottom third fading into a cream-colored background; an overall lingering, nostalgic mood | none | hero_page |

> All 9 AI images across the deck share `flat × vivid-launch` (h.5 locked). These include 6 hero_page images (P01/P02/P05/P08/P11/P14) + 3 local images (P06 / P12 ×2). #38 image-as-canvas + native overlay is used on P05; #41 is used for P08, satisfying the hard requirement that among the “≥4 image-bearing pages,” at least one uses #38–#46.

---

## IX. Content Outline

### Part 1: WHAT — What It Is

#### Slide 01 - Cover

- **Layout**: Full-bleed + floating title (hero_page)
- **Title**: `SUGAR RUSH`
- **Subtitle**: 2026 Summer Music Festival · Annual Handbook
- **Info**: 7.18 – 7.24 · Coconut Island Prairie · Let the sugar-blasted summer begin

#### Slide 02 - Chapter 1: WHAT IS SUGAR RUSH

- **Layout**: Chapter opener — Faded image backdrop + oversized title
- **Title**: `WHAT.`
- **Subtitle**: As the whole world grows hotter, we decided to make it sweeter.

#### Slide 03 - Key Numbers

- **Layout**: Four-column cards (2×2 or 1×4)
- **Title**: BY THE NUMBERS
- **Visualization**: kpi_cards
- **Content**:
  - `7` DAYS · 7 days of non-stop celebration (icon: calendar)
  - `5` STAGES · 5 themed stages (icon: music)
  - `80` ARTISTS · 80 acts in the lineup (icon: microphone)
  - `50K` FANS · Expected audience of 50,000 (icon: users)

#### Slide 04 - Three Core Ideas

- **Layout**: Three-column vertical pillars
- **Title**: WHAT WE STAND FOR
- **Visualization**: vertical_pillars
- **Content**:
  - **FREE** (icon: bolt) — No hierarchy of taste; every style is a good style
  - **FUN** (icon: sparkles) — Take it to the extreme and make the sweetest memories
  - **FOREVER YOUNG** (icon: heart) — Whether 18 or 80, there is no age on the dance floor

### Part 2: WHO — Who Will Play

#### Slide 05 - Chapter 2: WHO

- **Layout**: Full-bleed + title over musician silhouettes + annotation cards
- **Title**: `WHO.`
- **Subtitle**: 80 acts, 5 style camps, 1 unforgettable face.

#### Slide 06 - Headliners

- **Layout**: 2×2 grid, 4 portraits + names + styles + signature works
- **Title**: THE HEADLINERS
- **Visualization**: icon_grid (each cell = portrait + text)
- **Content**:
  - **CHERRY BOMB** (pink-haired female lead singer · rock · signature work "Pink Static")
  - **NEON CLOUD** (DJ in gold sunglasses · electronic · signature work "3AM Mirror")
  - **MINT FOLK** (mint-green shirt · folk · signature work "Slow Lemon")
  - **YELLOW HUSTLE** (bright yellow hoodie · hip-hop · signature work "Sugar High")

#### Slide 07 - Four Major Style Camps

- **Layout**: 2×2 quadrant matrix
- **Title**: FOUR FLAVORS, ONE FESTIVAL
- **Visualization**: quadrant_text_bullets
- **Content**:
  - Rock (icon: bolt) — noise, fire, release · 25 acts
  - Electronic (icon: headphones) — groove, late nights, psychedelia · 30 acts
  - Folk (icon: heart) — stories, slowness, warmth · 15 acts
  - Hip-hop (icon: music) — streets, beats, attitude · 10 acts

### Part 3: WHERE & WHEN — Where and When

#### Slide 08 - Chapter 3: WHERE & WHEN

- **Layout**: Full-bleed aerial view + module label + scrim
- **Title**: `WHERE.`
- **Subtitle**: Coconut Island Grassland · A city made for summer.

#### Slide 09 - 5 Themed Stages

- **Layout**: Hub-spoke center-radiating
- **Title**: 5 STAGES, ONE WORLD
- **Visualization**: hub_spoke
- **Content**:
  - **Center · SUGAR DOME**（main stage, maximum capacity 30,000）
  - **Pink · CHERRY STAGE**（rock, 5,000）
  - **Blue · NEON GRID**（electronic, 5,000）
  - **Green · MINT GROVE**（folk, 3,000）
  - **Yellow · YELLOW BLOCK**（hip-hop, 7,000）

#### Slide 10 - 7-Day Schedule

- **Layout**: Horizontal timeline
- **Title**: SEVEN DAYS OF SUGAR
- **Visualization**: timeline
- **Content**:
  - Day 1 (7.18) · OPENING · Opening Night
  - Day 2 (7.19) · ROCK DAY
  - Day 3 (7.20) · ELECTRO NIGHT
  - Day 4 (7.21) · FOLK AFTERNOON
  - Day 5 (7.22) · HIPHOP MIDNIGHT
  - Day 6 (7.23) · CROSSOVER · Crossover Night
  - Day 7 (7.24) · CLOSING · Grand Closing Celebration

### Part 4: VIBES — What to Play

#### Slide 11 - Chapter 4: VIBES

- **Layout**: Full-bleed + radial vignette
- **Title**: `VIBES.`
- **Subtitle**: Beyond music, there are ten sweet ways to enjoy yourself.

#### Slide 12 - Surrounding Market + Interactive Installations

- **Layout**: Two-column comparison
- **Title**: BEYOND THE MUSIC
- **Visualization**: comparison_columns (left: MARKET / right: ART INSTALL)
- **Content**:
  - **Left · MARKET** (icon: shopping-bag) — 50+ stalls, limited-edition merchandise, craft market, local snacks
  - **Right · ART INSTALL** (icon: game-controller) — 10 oversized installations, AR interaction, painting workshops, glow-in-the-dark graffiti wall

#### Slide 13 - Ticketing + Sponsorship

- **Layout**: Three ticket columns at top + sponsor strip at bottom
- **Title**: GET YOUR TICKET
- **Visualization**: comparison_columns
- **Content**:
  - **EARLY BIRD** · ¥499 (limited to 5,000 tickets · mark as sold out)
  - **REGULAR** · ¥799 (includes 1 designated beverage)
  - **VIP 7-DAY PASS** · ¥1999 (includes full-event access + VIP area + networking opportunities)
  - Bottom sponsor row: 5–7 fictional sponsor logos (placeholder text + decorative icons)

#### Slide 14 - Closing

- **Layout**: Full-bleed + fade to background
- **Title**: `SEE YOU IN SUMMER.`
- **Subtitle**: SUGAR RUSH 2026 · 7.18 – 7.24
- **Info**: Get tickets at sugarrush.fest

---

## X. Speaker Notes Requirements

- **Total duration**: ~15 minutes (demonstration-style reading · 1 minute/slide)
- **Notes style**: Conversational + slightly promotional — like a host introducing a music festival
- **Presentation purpose**: Spark interest + convey the brand tone + guide ticket purchases
- **File naming**: Align with SVG `01_cover.svg → notes/01_cover.md`

---

## XI. Technical Constraints Reminder

### SVG Generation Must Follow:

1. viewBox: `0 0 1280 720`
2. Background uses `<rect>` elements (`#FFF8EE` cream base)
3. Text wrapping uses `<tspan>` (`<foreignObject>` FORBIDDEN)
4. Transparency defaults to `fill-opacity` / `stroke-opacity`; `rgba()` remains converter-compatible
5. FORBIDDEN: `mask`, `<style>`, `class`, `foreignObject`, `textPath`, `animate*`, `script`
6. Write text characters directly as Unicode (`—`, `→`, `·`, etc.); HTML named entities FORBIDDEN; `&` in text must be written as `&amp;`
7. `clipPath` is only for `<image>` (circle / rounded rectangle / polygon), not for shapes / groups / text
8. Memphis heavy outlines: add `stroke="#1A1A2E" stroke-width="2-4"` to all geometric blocks

### PPT Compatibility Rules:

- Prefer opacity on each child; `<g opacity="...">` remains converter-compatible with an approximate-fidelity warning
- Use an overlay mask for image transparency
- Inline styles only; `@font-face` FORBIDDEN
- Build Memphis decorative fragments with basic SVG primitives (circle / rect / path / polygon), not `<pattern>` + `<use>`
