# swiss_grid_systems — Design Spec

> Human-readable design narrative for a Swiss International Typographic Style lecture deck. Machine-readable contract: `spec_lock.md`.

## I. Project Information

| Item | Value |
| ---- | ----- |
| **Project Name** | swiss_grid_systems |
| **Canvas Format** | PPT 16:9 (1280×720) |
| **Page Count** | 14 |
| **Design Style** | A) General Versatile + Swiss International Typographic Style / minimalist grid / Müller-Brockmann homage |
| **Target Audience** | Designers / design students / cultural institution event audiences |
| **Use Case** | Approximately 25-minute design history lecture |
| **Created Date** | 2026-05-17 |

---

## II. Canvas Specification

| Property | Value |
| -------- | ----- |
| **Format** | PPT 16:9 |
| **Dimensions** | 1280×720 |
| **viewBox** | `0 0 1280 720` |
| **Margins** | left/right 64px, top/bottom 56px (4×16 modular scale) |
| **Content Area** | 1152×608 (strict 4-column grid: 264px column width, 32px column gap) |

---

## III. Visual Theme

### Theme Style

- **Style**: Swiss International Typographic Style, pure white paper + black type + vermilion accents
- **Theme**: Light theme
- **Tone**: Restrained, rational, readable, visually impactful; the grid is the skeleton, and whitespace is the language

### Color Scheme

| Role | HEX | Purpose |
| ---- | --- | ------- |
| **Background** | `#FFFFFF` | Paper-white background, dominated by negative space |
| **Secondary bg** | `#F4F4F4` | Very light gray, used only for pattern-differentiation blocks on P10/P11 |
| **Primary** | `#1A1A1A` | Text, primary geometry, poster black |
| **Accent** | `#D9251D` | Swiss vermilion (focal points / red circles / rulers) |
| **Secondary accent** | `#1A4FA0` | Print Klein blue (backup, for chapter differentiation only) |
| **Body text** | `#1A1A1A` | Main body text |
| **Secondary text** | `#666666` | Notes, subtitles, years |
| **Tertiary text** | `#999999` | Page numbers, footer |
| **Border/divider** | `#E8E8E8` | Very light grid lines / dividers |
| **Success** | `#1A4FA0` | (Backup; this deck does not need status colors, blue is used instead to avoid color contamination) |
| **Warning** | `#D9251D` | (Backup, shared with Accent) |

> Strictly enforce 60-30-10: white (≥60%) + black (~30%) + red (≤10%). Blue is reserved for chapter/category distinctions, appearing no more than 1–2 times in the entire deck.

### AI Image Strategy

- **Image Rendering**: `minimalist-swiss`
- **Image Palette**: `mono-ink`

> Lock once, and all three AI images inherit: paper white 60–70% + near-black 25–30% + vermilion <10%.

### Gradient Scheme

Do not use gradients. One of the core principles of Swiss minimalism is rejecting gradients and shadows; all colors are solid blocks.

---

## IV. Typography System

**Typography direction**: A single family (the Arial family, the Windows equivalent of Helvetica), with hierarchy created internally through weight + size. The core typographic grammar of Swiss International Style.

| Role | Chinese | English | Fallback tail |
| ---- | ------- | ------- | ------------- |
| **Title** | `"Microsoft YaHei"` | `"Arial Black"` | `sans-serif` |
| **Body** | `"Microsoft YaHei"` | `Arial` | `sans-serif` |
| **Emphasis** | `"Microsoft YaHei"` | `Arial`（weight 700） | `sans-serif` |
| **Code** | — | `Consolas, "Courier New"` | `monospace` |

**Per-role font stacks**:

- Title: `"Arial Black", "Microsoft YaHei", sans-serif`
- Body: `Arial, "Microsoft YaHei", sans-serif`
- Emphasis: `Arial, "Microsoft YaHei", sans-serif`（with `font-weight="700"`）
- Code: `Consolas, "Courier New", monospace`

### Font Size Hierarchy

**Baseline**: Body = **18px** (moderately high lecture information density, compact yet clear in the Swiss manner)

| Purpose | Ratio to body | Example @ body=18 | Weight |
| ------- | ------------- | ----------------- | ------ |
| Cover title (hero headline) | 2.5-5x | 60-90px | Bold/Heavy |
| Chapter / section opener | 2-2.5x | 36-45px | Bold |
| Page title | 1.5-2x | 27-36px | Bold |
| Hero number | 1.5-2x | 27-36px | Bold |
| Subtitle | 1.2-1.5x | 22-27px | SemiBold |
| **Body** | **1x** | **18px** | Regular |
| Annotation / caption | 0.7-0.85x | 13-15px | Regular |
| Page number / footnote | 0.5-0.65x | 9-12px | Regular |

---

## V. Layout Principles

### Page Structure

- **Header area**: No title within the top 56px (Swiss style often places the page number/chapter number at the top left, with the title set along the top edge of the content area)
- **Content area**: Freely arranged within 64px margins; multi-page layouts use a 4-column 264×608 grid
- **Footer area**: 32px high; left side shows "page number / 14" right-aligned, with the center/right left blank

### Layout Pattern Library

This deck primarily uses the following formats:

| Pattern | Used in pages |
| ------- | ------------- |
| **Single column centered** | P14 conclusion |
| **Asymmetric split (2:8 / 3:7)** | P02 introduction / P09 modular diagram |
| **Three/four column cards** | P05 figures / P07 typefaces / P11 applications |
| **Matrix grid (2×2)** | P08 four grid categories |
| **Top-bottom split** | P03 origins / P06 biography / P12 digital era |
| **Negative-space-driven** | P10 whitespace as structure |
| **Full-bleed + floating text** | P01 cover / P14 conclusion |
| **Vertical list** | P04 eight principles |
| **Icon-grid** | P13 contemporary brands |

### Spacing Specification

**Universal**:

| Element | Range | This deck |
| ------- | ----- | --------- |
| Safe margin | 40-60px | **64px** (4×16 modular scale) |
| Content block gap | 24-40px | **32px** |
| Icon-text gap | 8-16px | **12px** |

**Cards** (P05 / P07 / P11 / P13):

| Element | Range | This deck |
| ------- | ----- | --------- |
| Card gap | 20-32px | **32px** |
| Card padding | 20-32px | **24px** |
| Card border radius | 8-16px | **0** (strict Swiss minimalism, no rounded corners) |
| Three-column card width | 360-380px | **361px** (three columns merged within a 4-column grid) |

**Non-card containers** (P02 / P09 / P10 / P14):
- Line-height = 1.5 × body
- Full-bleed whitespace drives the layout, with text blocks separated by generous blank space rather than divider lines

---

## VI. Icon Usage Specification

### Source

- **Generic library**: `tabler-outline` (stroke-width **1.5**) — used only as an accent in very few places
- **Brand library**: `simple-icons` (used only for the contemporary brand wall on P13)

> Swiss minimalism is fundamentally about removing decoration. The body of this deck does not rely on icons to convey information; icons serve as brand-identification symbols only on P13. Other pages are built with typography + geometry + whitespace.

### Recommended Icon List

| Purpose | Icon Path | Page |
| ------- | --------- | ---- |
| Quotation mark (optional) | `tabler-outline/blockquote` | P02 |
| Grid diagram | `tabler-outline/grid-3x3` | P08 (small marker) |
| Apple logo | `simple-icons/apple` | P13 |
| Google logo | `simple-icons/google` | P13 |
| Spotify logo | `simple-icons/spotify` | P13 |
| Airbnb logo | `simple-icons/airbnb` | P13 |
| IBM logo | `simple-icons/ibm` | P13 |
| Lufthansa logo | `simple-icons/lufthansa` | P13 |

---

## VII. Visualization Reference List

Catalog read: 71 templates

| Page | Template | Path | Summary-quote (verbatim) | Usage |
| ---- | -------- | ---- | ------------------------- | ----- |
| P03 | timeline | `templates/charts/timeline.svg` | "Pick for 3-8 milestone events on a horizontal time axis (no duration). Skip for tasks with start/end ranges (use gantt_chart) or vertical layout (use roadmap_vertical)." | Swiss Style's dual origins and milestone dates (1896 Akzidenz / 1908 Basel / 1918 Keller / 1936 JMB / 1957 Helvetica) |
| P04 | vertical_list | `templates/charts/vertical_list.svg` | "Pick for 3-6 numbered key points each with a short description — design principles, core tenets, action items, key takeaways, recommendations, executive summary points. Skip for icon-style cards (use icon_grid) or sequential steps (use numbered_steps)." | Eight core principles (8 numbered items + ultra-short descriptions) |
| P05 | team_roster | `templates/charts/team_roster.svg` | "Pick for 3-12 leadership/team profile cards (photo + name + title + short bio). Skip for reporting hierarchy (use top_down_tree)." | Key figures (8 representative designer cards; without photos, use names + life dates + one-line contributions) |
| P06 | timeline | `templates/charts/timeline.svg` | "Pick for 3-8 milestone events on a horizontal time axis (no duration). Skip for tasks with start/end ranges (use gantt_chart) or vertical layout (use roadmap_vertical)." | Müller-Brockmann life milestones (1914 / 1936 / 1950 / 1957 / 1958 / 1981 / 1996) |
| P07 | comparison_columns | `templates/charts/comparison_columns.svg` | "Pick for 2-4 pricing/service tier cards in side-by-side columns (marketing layout). Skip for dense feature comparison (use comparison_table)." | Card-based comparison of three typefaces (Akzidenz-Grotesk / Helvetica / Univers) |
| P08 | quadrant_text_bullets | `templates/charts/quadrant_text_bullets.svg` | "Pick for any 2×2 framework where each quadrant holds a titled bullet list — SWOT (Strengths/Weaknesses/Opportunities/Threats, internal-external × helpful-harmful), Ansoff (Existing/New Markets × Existing/New Products), or any named two-axis matrix with text content. Skip for items plotted as points (use matrix_2x2) or bubble-sized portfolios (use quadrant_bubble_scatter)." | 2×2 grid of four types (manuscript / columnar / modular / hierarchical) |
| P11 | icon_grid | `templates/charts/icon_grid.svg` | "Pick for 4-9 parallel features/capabilities/services as icon cards — feature grid, service lineup, benefits matrix, brand values, product highlights. Skip for sequential ordering (use numbered_steps) or hierarchical layers (use pyramid_chart)." | Output to the four quadrants: corporate VI / airport signage / publishing / education (text rather than colored icons here) |
| P12 | numbered_steps | `templates/charts/numbered_steps.svg` | "Pick for 3-6 horizontal sequential steps with numeric emphasis — how-it-works section, getting-started guide, methodology overview, implementation phases. Skip if steps need connector arrows (use process_flow) or named output artifacts (use pipeline_with_stages)." | Continuation in the digital era (four stages: 960 Grid → Bootstrap 12 → CSS Grid → Design Systems) |
| P13 | icon_grid | `templates/charts/icon_grid.svg` | (same as P11) | Contemporary brand presence (six-brand logo grid) |

**Runners-up considered**:

- `numbered_steps` | rejected for P04: The eight principles are not sequential steps; `vertical_list`’s “number + description card” format is a better fit and avoids implying order dependence
- `concentric_circles` | rejected for P10: Making “whitespace as structure” concrete through concentric circles would undermine the meaning of negative-space-driven design; P10 uses free-form whitespace with no template
- `comparison_table` | rejected for P07: The three typefaces only need three simple cards; the density of a feature-row matrix is too high and crosses the boundary of “clear” in “dense yet clear”

---

## VIII. Image Resource List

| Filename | Dimensions | Ratio | Purpose | Type | Layout pattern | Acquire Via | Status | Reference | text_policy | page_role |
| -------- | --------- | ----- | ------- | ---- | -------------- | ----------- | ------ | --------- | ----------- | --------- |
| cover_bg.png | 1280×720 | 1.78 | Cover hero background | Background | #38 image-as-canvas with text-block inset + #1 full-bleed background with floating title | ai | Pending | Swiss-grid geometric abstraction: horizontal and vertical black fine-line grids form a 4×3 matrix on a pure white background; a red circle hovers at the grid intersection in the second row of the third column; large white area in the lower left reserved for title overlay; strictly symmetrical off-center composition, geometry absolutely dominant | none | hero_page |
| negative_space.png | 1280×720 | 1.78 | P10 Negative space as structure hero | Background | #46 image-as-canvas with caption-stripe overlay + #39 image-as-canvas with mega-headline | ai | Pending | Pure white canvas with a solid red circle 80px in diameter positioned slightly left of center at one-third height; a 1px black horizontal baseline in the lower right spanning only 12% of the frame; remaining 90% pure white; latent tension between the red circle and black line, making the entire image an argument for "negative space" itself | none | hero_page |
| closing_grid.png | 1280×720 | 1.78 | P14 closing statement hero | Background | #38 image-as-canvas with text-block inset + #29 two-stop scrim | ai | Pending | Dense black grid lines spaced 16px across the entire frame, with selected intersections highlighted as red dots to form a sparse star chart; strictly geometric composition; lower-left third reserved for an 8% opaque white overlay for floating text | none | hero_page |

> All three images use `minimalist-swiss × mono-ink`; rendering + palette are provided by §III AI Image Strategy; the Reference field should not repeat style terms or HEX values.

---

## IX. Content Outline

### Part 1: Setting the Scene

#### Slide 01 - Cover

- **Layout**: Full-bleed + floating text (cover hero)
- **Title**: The Grid System
- **Subtitle**: The Grid as a Way of Seeing
- **Info**: A Lecture on Swiss International Typographic Style · 2026

#### Slide 02 - Introduction

- **Layout**: Asymmetric split 3:7 (large quotation mark on the left + quotation on the right)
- **Title**: (No title; the quotation is the hero)
- **Content**:
  - "The grid system is an aid, not a guarantee. It permits a number of possible uses and each designer can look for a solution appropriate to his personal style. But one must learn how to use the grid; it is an art that requires practice."
  - — Josef Müller-Brockmann, *Grid Systems in Graphic Design*, 1981

### Part 2: History & Principles

#### Slide 03 - Dual Origins

- **Layout**: Top-bottom split (timeline above, brief narrative below)
- **Title**: Two origins · 1896 → 1957
- **Visualization**: timeline
- **Content**:
  - 1896 Akzidenz-Grotesk released by the Berthold type foundry
  - 1908 Reform of the Basel School of Design
  - 1918 Ernst Keller joined the Zurich School of Arts and Crafts
  - 1936 Müller-Brockmann opened his studio
  - 1957 Helvetica + Univers launched in the same year
  - Conclusion: Rationalism did not emerge from nowhere; it grew from half a century of typefaces + schools + teaching

#### Slide 04 - Eight Core Principles

- **Layout**: Vertical list (number + one-line principle + annotation)
- **Title**: Eight core principles
- **Visualization**: vertical_list
- **Content**:
  1. Objectivity over expression · Objectivity over expression
  2. Mathematical grid as the framework · Mathematical grid
  3. Asymmetric composition · Asymmetric layout
  4. Sans-serif typefaces · Sans-serif typography
  5. Flush left, ragged right · Flush-left ragged-right
  6. Objective photography · Objective photography
  7. Negative space as structure · Negative space as structure
  8. Reproducible and scalable · Reproducible at scale

#### Slide 05 - Key Figures

- **Layout**: Four-column cards × 2 rows (8 people)
- **Title**: Eight Shapers
- **Visualization**: team_roster
- **Content**:
  - Ernst Keller (1891–1968) · Founder of the Zurich School
  - Théo Ballmer (1902–1965) · Early experimenter with grids
  - Max Bill (1908–1994) · Bauhaus → Ulm
  - Emil Ruder (1914–1970) · Basel typography
  - Armin Hofmann (1920–2020) · Basel posters
  - Josef Müller-Brockmann (1914–1996) · Zurich Grid Systems
  - Max Miedinger (1910–1980) · Designed Helvetica in 1957
  - Adrian Frutiger (1928–2015) · Designed Univers in 1957

#### Slide 06 - Müller-Brockmann

- **Layout**: Top-bottom split (timeline above, key-event text below)
- **Title**: Josef Müller-Brockmann · 1914–1996
- **Visualization**: timeline
- **Content**:
  - 1914 Born in Rapperswil, Switzerland
  - 1936 Independent studio in Zurich
  - 1950 Began the Tonhalle Musica Viva poster series
  - 1957 Professor at the Zurich School of Arts and Crafts
  - 1958 Founded the journal *Neue Grafik*
  - 1981 Published *Grid Systems in Graphic Design*
  - 1996 Died in Unterengstringen

### Part 3: Typography & Grids

#### Slide 07 - Three Defining Typefaces

- **Layout**: Three-column cards
- **Title**: Three definitive typefaces
- **Visualization**: comparison_columns
- **Content**:
  - **Akzidenz-Grotesk · 1896** · Berthold · The first commercially modern sans serif · An early favorite of the Swiss School
  - **Helvetica · 1957** · Miedinger + Hoffmann · Named after the Latin word for “Swiss” · Exceptionally neutral, objective, and readable
  - **Univers · 1957** · Frutiger · The first typeface to systematize 21 weights with a numerical coordinate system · The beginning of type family engineering

#### Slide 08 - Four Types of Grids

- **Layout**: Matrix grid 2×2
- **Title**: Four Types of Grids
- **Visualization**: quadrant_text_bullets
- **Content**:
  - **Manuscript Grid** · Single column · Traditional · The only option for long-form text
  - **Column Grid** · Multiple columns side by side · The grammar of journals and newspapers
  - **Modular Grid** · A matrix of horizontal bands × vertical columns · Ideal for posters and catalogs
  - **Hierarchical Grid** · Irregular but internally logical · For complex layouts

#### Slide 09 - Modular Grid Diagram

- **Layout**: Asymmetric split 2:8 (numerical specifications on the left, SVG geometric drawing of an 8×6 modular grid on the right)
- **Title**: Everything Is Calculable
- **Content**:
  - Column width = 264px · column gap = 32px · line height = body × 1.5
  - Safe margin = 64px = 4 × 16px base modules
  - Draw a 4×6 modular grid on the right, each cell 264×96, with red lines marking an image area spanning 3 columns

#### Slide 10 - Negative Space as Structure

- **Layout**: Negative-space-driven（90% pure white + a red circle + one short sentence）
- **Title**: Whitespace Is Structure
- **Content**:
  - One line: Whitespace is not what's left over; it carries the information
  - One line: The space between is the message
  - Hero image as the subject of the entire page（red dot + ultra-thin horizontal line）

### Part 4: Impact and Legacy

#### Slide 11 - Output to the Modern World

- **Layout**: Four cards
- **Title**: Output into the Modern World · 1960s →
- **Visualization**: icon_grid
- **Content**:
  - **Corporate VI** · IBM, Knoll, Lufthansa · Turning Swiss rationalism into the "identity systems" industry
  - **Airport / Metro Signage** · New York's Unimark, Frutiger typeface at Paris airports
  - **Publishing** · The layout grammar of *Du* magazine, *Eye*, and *Domus*
  - **Design Education** · Students from the Basel and Zurich schools spreading across the globe

#### Slide 12 - Continuation in the Digital Age

- **Layout**: Top-bottom split (four stages above, one-line thesis below)
- **Title**: Continuity in the digital age
- **Visualization**: numbered_steps
- **Content**:
  - 01. 960 Grid System · 2008 · The first to bring grid grammar to the Web
  - 02. Bootstrap 12-column grid · 2011 · Democratizing the modular grid
  - 03. CSS Grid · 2017 · Native browser grid
  - 04. Design Systems · 2020s · The continuation of large-enterprise visual identities on screen

#### Slide 13 - The Swiss Heritage of Contemporary Brands

- **Layout**: Six icon cards 3×2
- **Title**: The Swiss lineage of contemporary brands
- **Visualization**: icon_grid
- **Content**:
  - Apple · Minimalist, rational product language
  - Google · Material grid + geometric typeface
  - Spotify · Magazine-inspired layout grammar
  - Airbnb · Modular grid + minimalist identity
  - IBM · Swiss lineage since 1967 (JMB as consultant)
  - Lufthansa · Otl Aicher’s 1962 VI to the present

#### Slide 14 - Closing Remarks

- **Layout**: Full-bleed + floating text (cover echo)
- **Title**: The Grid Is Not a Limitation
- **Subtitle**: It Is a Grammar of Freedom
- **Info**: The grid is not a constraint. It is a grammar of freedom.

---

## X. Speaker Notes Requirements

- **Filename**: Correspond to the SVG filename (`01_cover.svg` → `notes/01_cover.md`)
- **Tone**: Semi-formal lecture style + occasional live examples (referencing visual elements on the screen)
- **Length per page**: 80-180 Chinese characters (approximately 30-60 seconds at speaking pace)
- **Total presentation duration**: 25 minutes (14 pages averaging ~107 seconds/page)
- **Purpose**: Teach + inspire, helping designers rethink "the grid as a system rather than decoration"

---

## XI. Technical Constraints Reminder

### SVG Generation Must Follow

1. viewBox: `0 0 1280 720`
2. Background uses `<rect>`
3. Text wrapping uses `<tspan>` (`<foreignObject>` forbidden)
4. Transparency defaults to `fill-opacity` / `stroke-opacity`; `rgba()` remains converter-compatible
5. Forbidden: `mask` / `<style>` / `class` / `foreignObject`
6. Forbidden: `textPath` / `animate*` / `script`
7. Use Unicode characters (`—`, `–`, `©`, `®`, `→`, etc.); HTML entities are forbidden
8. `marker-start` / `marker-end` are allowed only for triangles / diamonds / circles inside `<defs>` with `orient="auto"`
9. `clipPath` is only for `<image>`, with a single shape child

### Project-specific

- Strictly no rounded corners (rx = 0) — a core principle of Swiss minimalism; the sole exception is brand logos from the built-in simple-icons library
- Strictly no gradients — `linearGradient` / `radialGradient` must not appear anywhere in the deck
- Strictly no shadows — `filter` must not appear anywhere in the deck
- Four colors only — white / black / vermilion / light gray (border); whenever blue appears, verify why it cannot be replaced with red
