# ppt169_indie_bookstore_zine_guide_20260517 - Design Spec

> Human-readable design narrative — rationale, audience, style, color choices, content outline. Read once by downstream roles for context.
>
> Machine-readable execution contract: `spec_lock.md` (color / typography / icon / image short form). Executor re-reads `spec_lock.md` before every SVG page to resist context-compression drift. Keep both in sync; on divergence, `spec_lock.md` wins.

## I. Project Information

| Item | Value |
| ---- | ----- |
| **Project Name** | ppt169_indie_bookstore_zine_guide_20260517 |
| **Canvas Format** | PPT 16:9 (1280×720) |
| **Page Count** | 18 |
| **Design Style** | A) General Versatile + Risograph zine printing / DIY poster aesthetics |
| **Target Audience** | Beginners interested in independent publishing / zines / art books; also suitable for independent bookstore promotion, design teaching, and urban culture sharing events |
| **Use Case** | In-person sharing events / café screenings / design school onboarding / derivative content for cultural media |
| **Created Date** | 2026-05-17 |

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

- **Style**: Risograph zine — misregistered spot colors + halftone dots + limited palette + handmade, rough-edged zine character
- **Theme**: Light theme (warm beige paper background)
- **Tone**: Print-process feel, poster-like, DIY energy, vintage independent-publishing character

### Color Scheme

| Role | HEX | Purpose |
| ---- | --- | ------- |
| **Background (paper)** | `#F5EFE0` | Warm beige, evoking kraft paper / recycled paper |
| **Secondary bg** | `#EAE2CC` | Subtle background variation for cards / sections |
| **Primary (Riso Federal Blue)** | `#1E4DBC` | Primary color blocks, title outlines, key graphics |
| **Accent (Riso Fluorescent Pink)** | `#FF5C8A` | High-contrast color, second layer of misregistered overprinting, decoration |
| **Secondary accent (Mustard)** | `#E8A02E` | Third color, <5%, for focal emphasis |
| **Body text** | `#1A1A1A` | Near-black, echoing the impure black of Riso ink |
| **Secondary text** | `#5A5A5A` | Annotations, page numbers, captions |
| **Tertiary text** | `#8C8275` | Very faint background text |
| **Border/divider** | `#1A1A1A` | Main dividers always near-black for a zine-print feel |

> **Riso aesthetic hard constraints**: 1–3px misregistration between color passes, halftone dot textures, and the illusion of a third color created by overlapping identical color blocks. On SVG, simulate these with multiple offset color blocks + opacity + dotted `<pattern>`.

### AI Image Strategy

- **Image Rendering**: `screen-print`
- **Image Palette**: `duotone`

> Pre-locked by the user (bypassing the three-candidate presentation). Screen-print × duotone is a ✓✓ recommended combination in the matrix. All AI images use the same rendering + palette, with HEX values injected from the solid colors in the table above (Federal Blue + Fluorescent Pink + occasional Mustard).

### Gradient Scheme

> Risograph zines generally avoid gradients (as they conflict with the logic of flat spot-color printing); use stop-opacity sparingly to simulate paper-texture bleeding.

```xml
<!-- Subtle paper halftone wash (light, 0.05–0.12 opacity) -->
<radialGradient id="paperHalftone" cx="50%" cy="50%" r="60%">
  <stop offset="0%" stop-color="#F5EFE0" stop-opacity="0"/>
  <stop offset="100%" stop-color="#5A5A5A" stop-opacity="0.08"/>
</radialGradient>
```

---

## IV. Typography System

### Font Plan

**Typography direction**: Contrast approach — zine punk DIY tension, with Impact poster lettering for titles, YaHei for body text, and monospaced Consolas annotations to create a “typewriter/photocopier” feel

| Role | Chinese | English | Fallback tail |
| ---- | ------- | ------- | ------------- |
| **Title** | `"Microsoft YaHei"` | `Impact, "Arial Black"` | `sans-serif` |
| **Body** | `"Microsoft YaHei", "PingFang SC"` | `Arial` | `sans-serif` |
| **Emphasis** | `SimHei` | `Impact, "Arial Black"` | `sans-serif` |
| **Code (annotation)** | — | `Consolas, "Courier New"` | `monospace` |

**Per-role font stacks**:

- Title: `Impact, "Arial Black", "Microsoft YaHei", sans-serif`
- Body: `"Microsoft YaHei", "PingFang SC", Arial, sans-serif`
- Emphasis: `Impact, "Arial Black", SimHei, "Microsoft YaHei", sans-serif`
- Code: `Consolas, "Courier New", monospace`

### Font Size Hierarchy

**Baseline**: Body font size = **20px** (moderate zine information density, between dense 18px and relaxed 24px)

| Purpose | Ratio to body | Example @ body=20 | Weight |
| ------- | ------------- | ----------------- | ------ |
| Cover title (Impact large type) | 4-5x | 80-100px | Heavy |
| Chapter / section opener | 2.5-3x | 50-60px | Bold |
| Page title | 1.6-2x | 32-40px | Bold |
| Hero number / large-type emphasis | 2.5-4x | 50-80px | Heavy |
| Subtitle | 1.2-1.4x | 24-28px | SemiBold |
| **Body content** | **1x** | **20px** | Regular |
| Annotation / caption | 0.7-0.85x | 14-17px | Regular |
| Page number / footnote | 0.55-0.65x | 11-13px | Regular |

---

## V. Layout Principles

### Page Structure

- **Header area**: 60px high (page number + section identifier + decorative bar)
- **Content area**: 600px high (main information area)
- **Footer area**: 40px high (page number + footer decorative bar)

### Layout Pattern Library

> **Principle — proportions follow information hierarchy, not a fixed grid.** Zine aesthetics encourage breaking uniform grids, intentionally "messy" layouts, and preserving the counterpoint between whitespace and high density.

| Pattern | Suitable Scenarios |
| ------- | ----------------- |
| **Single column centered** | Cover / back cover / large-type outro |
| **Asymmetric split (3:7 / 2:8)** | Chapter image + large title / single hero + sidebar |
| **Top-bottom split** | Banner image + multi-column content |
| **Three/four column cards** | Four waves / cities side by side / tool listings |
| **Full-bleed + floating text** | hero_page cover / Jimbocho / Berlin |
| **Figure-text overlap** | Large type overlapping the image edge (a classic zine technique) |
| **Negative-space-driven** | Breathing page — single element + generous whitespace |
| **Z-pattern waterfall** | Step-based pages (eight-page fold / Risograph process) |

### Spacing Specification

**Universal**:

| Element | Recommended Range | Current Project |
| ------- | ---------------- | --------------- |
| Safe margin from canvas edge | 40-60px | **Approximately 60px left and right / 50px top and bottom** |
| Content block gap | 24-40px | **32px** |
| Icon-text gap | 8-16px | **12px** |

**Card-based layouts** (used on P12 table / P08 content-type grid / P10 three-city comparison / P13 dual-book exhibition cards / P14–P15 vertical_list):

| Element | Recommended Range | Current Project |
| ------- | ---------------- | --------------- |
| Card gap | 20-32px | **24px** |
| Card padding | 20-32px | **24px** |
| Card border radius | 8-16px | **0px** (Risograph aesthetic = hard edges, no rounded corners) |
| Three-column card width | 360-380px each | **360px** |

**Non-card containers** (breathing pages / hero pages):

- Line-height: 1.5x body (= 30px @ body 20)
- Full-bleed text placement: oversized headlines commonly overlap the image edges
- Typeset information by hierarchy; do not recalculate “column widths”

---

## VI. Icon Usage Specification

### Source

- **Built-in icon library**: `templates/icons/chunk-filled/` (bold, solid geometry that best complements the Riso color-block aesthetic)
- **Library lock**: **chunk-filled** (single library throughout the deck; mixing is forbidden)
- **Usage method**: SVG placeholder `<use data-icon="chunk-filled/icon-name" .../>`

### Recommended Icon List

| Purpose | Icon Path | Page |
| ------- | --------- | ---- |
| Zine / magazine / book | `chunk-filled/book` | P03, P14 |
| Open book | `chunk-filled/book-open` | P02 (TOC) |
| Multiple books / bookshelf | `chunk-filled/books` | P09, P10, P11 |
| Newspaper | `chunk-filled/newspaper` | P04 |
| Sticky note / short article | `chunk-filled/sticky-note` | P08 |
| Printer | `chunk-filled/printer` | P05, P06 |
| Copy / photocopy | `chunk-filled/copy` | P06 |
| Ink / brush | `chunk-filled/brush` | P05 |
| Scissors (zine-folding tool) | `chunk-filled/scissors` | P07 |
| Pencil / content creation | `chunk-filled/pencil` | P08 |
| Pen nib / writing | `chunk-filled/pen-nib` | P08 |
| Toolbox | `chunk-filled/toolbox` | P07 |
| Map | `chunk-filled/map` | P12 |
| Map pin / location | `chunk-filled/map-pin` | P09, P10, P11, P12 |
| Globe / global | `chunk-filled/globe` | P09 |
| Calendar / book fair | `chunk-filled/calendar` | P13 |
| Clock | `chunk-filled/clock` | P13 |
| Heart / favorites | `chunk-filled/heart` | P15 |
| Star / recommendation | `chunk-filled/star` | P12 |
| Flag / action | `chunk-filled/flag` | P16 |
| Arrow right | `chunk-filled/arrow-right` | Multiple pages |
| Circular arrow | `chunk-filled/circle-arrow-right` | P02, P16 |
| Building / bookstore | `chunk-filled/building` | P12 |
| Shopping bag / shopping | `chunk-filled/shopping-bag` | P14 |
| Folders / favorites | `chunk-filled/folders` | P15 |
| Grid / library | `chunk-filled/grid` | P02 |
| Hand / DIY | `chunk-filled/hand` | P07, P16 |
| Users / community | `chunk-filled/users` | P04 (Riot grrrl) |

---

## VII. Visualization Reference List

> Catalog read: 71 templates

| Page | Template | Path | Summary-quote (verbatim from `charts_index.json`) | Usage |
| ---- | -------- | ---- | ------------------------------------------------- | ----- |
| P02 | agenda_list | `templates/charts/agenda_list.svg` | "Pick for table of contents, meeting agendas, or presentation roadmap — numbered items + brief description + duration / owner per row. Skip for substantive content lists (use vertical_list) or single-page section dividers (use a cover layout)." | Contents for an 18-page deck (5 sections + brief descriptions + page ranges) |
| P04 | timeline | `templates/charts/timeline.svg` | "Pick for 3-8 milestone events on a horizontal time axis (no duration). Skip for tasks with start/end ranges (use gantt_chart) or vertical layout (use roadmap_vertical)." | Four waves in zine history (amateur publishing 1920s / science fiction 1930s / punk 1976 / Riot grrrl 1991 / contemporary 2010s) = 5 milestones |
| P05 | vertical_list | `templates/charts/vertical_list.svg` | "Pick for 3-6 numbered key points each with a short description — design principles, core tenets, action items, key takeaways, recommendations, executive summary points. Skip for icon-style cards (use icon_grid) or sequential steps (use numbered_steps)." | Four defining visual features of Risograph: limited palette / misregistration / halftone texture / ink smell |
| P06 | numbered_steps | `templates/charts/numbered_steps.svg` | "Pick for 3-6 horizontal sequential steps with numeric emphasis — how-it-works section, getting-started guide, methodology overview, implementation phases. Skip if steps need connector arrows (use process_flow) or named output artifacts (use pipeline_with_stages)." | 5-step Risograph workflow: digital image → master burning → ink drum wrapping → ink rolling → multiple passes through the press |
| P07 | numbered_steps | `templates/charts/numbered_steps.svg` | "Pick for 3-6 horizontal sequential steps with numeric emphasis — how-it-works section, getting-started guide, methodology overview, implementation phases. Skip if steps need connector arrows (use process_flow) or named output artifacts (use pipeline_with_stages)." | Four-step eight-page folding method: fold → key cuts → assemble → fill in content |
| P08 | icon_grid | `templates/charts/icon_grid.svg` | "Pick for 4-9 parallel features/capabilities/services as icon cards — feature grid, service lineup, benefits matrix, brand values, product highlights. Skip for sequential ordering (use numbered_steps) or hierarchical layers (use pyramid_chart)." | 6 major zine content types: sketches / poetry + manifestos / illustrated recipes / personal writing / collage / comics |
| P10 | vertical_pillars | `templates/charts/vertical_pillars.svg` | "Pick for 1×3 / 1×4 / 1×5 vertical column layout where each pillar = one independent category with title + bullets — PEST (Political/Economic/Social/Technological), four-pillar strategy overview, side-by-side independent categories. Skip for 2×2 quadrant (use quadrant_text_bullets), pricing tiers (use comparison_columns), or 2×2 parallel aspects (use labeled_card)." | Three cities, three stores side by side: Shakespeare and Company (Paris) / Daunt + Word on the Water (London) / Strand + Yu and Me (New York) |
| P12 | basic_table | `templates/charts/basic_table.svg` | "Pick for plain tabular text/number grid, 3-8 columns. Skip if cells need visual bars (use consulting_table) or qualitative scores (use harvey_balls_table)." | Map of 15 zine-oriented independent bookstores in mainland China (bookstore / city / characteristics / zine orientation; 4 columns) |
| P13 | labeled_card | `templates/charts/labeled_card.svg` | "Pick for 3-4 parallel aspects of one subject with per-aspect titles + short body (self-introduction, four-pillar overview, capability quadrant). Skip for plain feature lists (use icon_grid), sequential steps (use numbered_steps), or strategic quadrants (use quadrant_text_bullets / matrix_2x2)." | Side-by-side cards for the two book fairs: abC (founded in 2015, Beijing and Shanghai) + UNFOLD (high booth fees, large crowds) |
| P14 | vertical_list | `templates/charts/vertical_list.svg` | "Pick for 3-6 numbered key points each with a short description — design principles, core tenets, action items, key takeaways, recommendations, executive summary points. Skip for icon-style cards (use icon_grid) or sequential steps (use numbered_steps)." | How to browse independent bookstores — 4 points: check the selection / allow 1 hour / bring cash / ask before taking photos |
| P15 | vertical_list | `templates/charts/vertical_list.svg` | "Pick for 3-6 numbered key points each with a short description — design principles, core tenets, action items, key takeaways, recommendations, executive summary points. Skip for icon-style cards (use icon_grid) or sequential steps (use numbered_steps)." | How to collect zines — 4 points: start with your interests / protect them with plastic sleeves / follow artists on IG / attend zine fairs |
| P16 | numbered_steps | `templates/charts/numbered_steps.svg` | "Pick for 3-6 horizontal sequential steps with numeric emphasis — how-it-works section, getting-started guide, methodology overview, implementation phases. Skip if steps need connector arrows (use process_flow) or named output artifacts (use pipeline_with_stages)." | Four-step action checklist for making your first zine: choose a topic / fold one A4 sheet / fill 8 pages / print 10 copies and give them away |

**Runners-up considered**:

- `roadmap_vertical` | rejected for P04: The timeline data is a horizontal chronological axis of “event milestones” (without duration); `roadmap_vertical` is suited to “project milestones + status,” while this page is a cultural-history timeline and better fits `timeline`
- `agenda_list` | rejected as the P02 alternative to `vertical_list`: `agenda_list` includes duration/owner columns, matching the semantics of “table of contents + page ranges”; `vertical_list` is a “principles/key points” list and is semantically mismatched
- `process_flow` | rejected for P06: `process_flow` uses connecting arrows and suits approval flows; the Riso workflow consists of “production steps” with no branching or approval semantics, so `numbered_steps` is lighter
- `icon_grid` | rejected for P08 because the content type itself is `icon_grid` (used as the selected option); rejected for P14/P15 because P14/P15 present “principles/key points,” not “capabilities/features”
- `consulting_table` | rejected for P12: The table contains only text + qualitative labels (★), with no micro-bar data to visualize; `basic_table` is the correct choice

---

## VIII. Image Resource List

> All `#<id>` entries in the Layout pattern column are quoted verbatim from `references/image-layout-patterns.md` (Part 1 Primary + Part 2 Modifiers). Image-as-canvas coverage (#38–#46) is handled by P07 + P09.

| Filename | Dimensions | Ratio | Purpose | Type | Layout pattern | Acquire Via | Status | Reference | text_policy | page_role |
| -------- | --------- | ----- | ------- | ---- | -------------- | ----------- | ------ | --------- | ----------- | --------- |
| cover_hero.png | 1280×720 | 1.78 | P01 cover hero | Background | `#1 Full-bleed background with floating title + #27 Linear gradient mask for text legibility + #29 Two-stop scrim — opaque on text side, transparent on focal side` | ai | Pending | "A risograph print studio scene: a hand-pulled silkscreen 'pull' of a two-color zine sheet rising from a paper stack; ink rollers and color drums visible in the lower edge; left side reserved as calm flat color block for large title overlay; bold silhouette composition" | none | hero_page |
| zine_history_collage.png | 760×420 | 1.81 | P03 Decorative image: What is a zine? | Illustration | `#13 Narrow vertical image strip + giant horizontal title + #21 Rounded rectangle crop` | ai | Pending | "Collage silhouette of stacked zines across eras: a sci-fi pulp magazine corner, a punk fanzine front, a riot grrrl xeroxed page, a modern art-book spine — overlapping at slight angles like a desk pile; the stack is the only motif, off-white paper background visible behind" | none | local |
| risograph_machine.png | 720×900 | 0.80 | P05 Risograph process sidebar | Illustration | `#18 Image as full-height sidebar column + #21 Rounded rectangle crop` | ai | Pending | "Front-three-quarter view of a vintage Risograph duplicator (Riso EZ200 era), boxy industrial silhouette, two color drums visible through a side panel slot, paper tray protruding from front; clean stencil-cut machine outline, no operator, isolated against off-white paper field" | none | local |
| risograph_process_banner.png | 1280×280 | 4.57 | P06 Process banner | Diagram | `#14 Horizontal banner strip cutting through mid-section + #29 Two-stop scrim` | ai | Pending | "Horizontal silkscreen frieze depicting Risograph workflow: from left to right — a digital file glyph, a stencil master sheet, a wrapped color drum, an inked roller pressing paper, a paper output stack; five stages connected by subtle ink-trail lines; bold stencil silhouettes, no text labels on the image" | none | local |
| zine_folding_hands.png | 1080×720 | 1.50 | P07 Eight-page folding diagram hero | Illustration | `#38 Background image + annotation cards with bezier leader lines + #21 Rounded rectangle crop` | ai | Pending | "Overhead view of two hands folding a single A4 sheet into an 8-page zine; the sheet partially folded mid-crease, scissors and pencil nearby; composition leaves four open negative-space pockets in corners for native SVG annotation cards to overlay; soft top-down vantage" | none | local |
| jimbocho_hero.png | 1280×720 | 1.78 | P09 Jimbocho hero | Background | `#1 Full-bleed background with floating title + #29 Two-stop scrim + #27 Linear gradient mask for text legibility` | ai | Pending | "Tokyo Jimbocho bookstore street at evening: rows of paper-lantern shop signs glowing, stacked secondhand books spilling onto sidewalk shelves, narrow alley vanishing into perspective; bold silhouette of pedestrian browsing in foreground; cinematic poster framing" | none | hero_page |
| three_cities_triptych.png | 1160×400 | 2.90 | P10 Three Cities, Three Bookshops Triptych | Illustration | `#56 Image triptych + #21 Rounded rectangle crop + #70 Image with thin colored matte frame` | ai | Pending | "Three-panel triptych baked in one image, panels equal width separated by 4px gutters. Left panel: Paris's Shakespeare and Company exterior — narrow green-fronted shop with cobbled foreground. Middle panel: London Word-on-the-Water bookbarge on canal at dusk. Right panel: New York Strand Bookstore corner with the red awning visible. All three panels in matching screen-print silhouette style, unified color treatment for visual continuity" | none | local |
| berlin_bucherbogen.png | 1280×720 | 1.78 | P11 Berlin hero | Background | `#1 Full-bleed background with floating title + #12 Faded image as backdrop with oversized overlay text` | ai | Pending | "Berlin Bücherbogen under S-Bahn arches: arched brick vault interior, light spilling from book-lined walls under the curved ceiling, a single train rumble silhouette implied above; central calm zone reserved for huge overlay title; atmospheric depth via halftone gradation" | none | hero_page |
| zine_fair_scene.png | 720×720 | 1.00 | P13 book-fair scene atmosphere | Illustration | `#2 Left-third image + right text body + #21 Rounded rectangle crop + #70 Image with thin colored matte frame` | ai | Pending | "Art-book-fair booth aisle scene: rows of low tables stacked with zines and small-press books, a few visitor silhouettes browsing, hand-lettered booth signs visible but unreadable, ceiling string-lights overhead; bold flat composition, no readable text in scene" | none | local |
| zine_action_outro.png | 1280×720 | 1.78 | P18 Back cover outro hero | Background | `#1 Full-bleed background with floating title + #12 Faded image as backdrop with oversized overlay text + #29 Two-stop scrim` | ai | Pending | "Single open hand from above holding up a small folded zine toward the viewer; the zine cover slightly halftoned; rest of canvas is open paper field; composition designed to host enormous closing-line typography overlay in upper region" | none | hero_page |

> **User-provided photos** (in `sources/`, available as visual references for Image_Generator prompts — not embedded directly): `riso_ez200_printer.jpg`, `risograph_two_color_print.jpg`, `shakespeare_and_company_paris.jpg`, `jimbocho_yaguchi_koga.jpg`, `jimbocho_used_books.jpg`, `sanseido_bookstore.jpg`. The Strategist does not include them as §VIII resource rows (to avoid conflict with the AI-row hero); Image_Generator may refer to their composition and atmosphere when writing prompts.

---

## IX. Content Outline

### Part 1: Introduction

#### Slide 01 - Cover

- **Layout**: Full-bleed hero image + floating Impact headline（zine poster aesthetic）
- **Title**: "Zine Culture Guide / INDIE BOOKSTORE × ZINE"
- **Subtitle**: An independent publishing map from a single sheet of paper to an entire bookstore
- **Info**: PPT Master Risograph-Style Presentation · 2026

#### Slide 02 - Table of Contents

- **Layout**: agenda_list (5 sections + brief descriptions + page ranges)
- **Title**: Contents / TABLE OF CONTENTS
- **Visualization**: agenda_list
- **Content**:
  - 01 What is a zine? + four waves in its brief history (P03–P04)
  - 02 Risograph: The soul medium of zine production (P05–P06)
  - 03 How to make your own zine (P07–P08)
  - 04 Map of independent bookstores worldwide + in China (P09–P13)
  - 05 How to browse / collect / action checklist (P14–P18)

### Part 2: What Is a Zine?

#### Slide 03 - What Is a Zine?

- **Layout**: Large-text definition + narrow vertical image strip on the left + three feature lists
- **Title**: ZINE = MAGAZINE − Commercial Logic
- **Content**:
  - Self-produced, noncommercial, extremely limited print runs (usually under 1,000 copies, often fewer than 100)
  - Simple binding / mixed content / complete authorial control
  - The boundary between magazine / book: print run + commercial intent + editorial process

#### Slide 04 - The Four Waves in Zine History

- **Layout**: horizontal timeline by era
- **Title**: Four waves of zines over a century
- **Visualization**: timeline
- **Content**:
  - 1920s Amateur publishing + Harlem’s *Fire!!*
  - 1930s Science-fiction fanzines *The Comet* / the term “fanzine” coined by Russ Chauvenet in 1940
  - 1976 Punk *Sniffin' Glue* and the spread of photocopiers
  - 1991 Riot Grrrl *Bikini Kill* + Riot Grrrl Press
  - 2010s Contemporary revival + explosion of zine fairs

### Part 3: Risograph

#### Slide 05 - Risograph Origins + Visual Characteristics

- **Layout**: Full-height machine side-panel image on the left + four visual features in a vertical list on the right
- **Title**: Risograph: The Soul-Bearing Medium of Zine Production
- **Visualization**: vertical_list
- **Content**:
  - Origin: Riso Kagaku 1946 / Risograph 007 1986
  - Visual feature 1: Limited palette (one color per ink drum)
  - Visual feature 2: 1–3px color misregistration
  - Visual feature 3: Halftone dots + the smell of ink
  - Visual feature 4: Overlaid color blocks create a third color

#### Slide 06 - Risograph Workflow

- **Layout**: Midsection banner image (process diagram) + five numbered steps below
- **Title**: The Process: 5 Steps from Digital Image to Printed Sheet
- **Visualization**: numbered_steps
- **Content**:
  - ① Receive the digital image
  - ② Ablate the pixelated master
  - ③ Wrap the master around the colored ink cylinder
  - ④ Roll ink from the cylinder onto the paper
  - ⑤ Run the paper through multiple times to complete the multicolor print

### Part 4: How to Make Your Own Zine

#### Slide 07 - The Eight-Page Folding Method

- **Layout**: Central hero image (folded hands) + four corner annotation cards (image-as-canvas + Bezier connector lines #38)
- **Title**: One Sheet of Paper → One Zine
- **Visualization**: numbered_steps (overlaid on image-as-canvas)
- **Content**:
  - ① Fold: fold the long edge in half → fold the short edge in half → fold along the center line, creating 8 rectangles
  - ② Key cut: cut from the folded edge to the center point
  - ③ Assemble: push both ends toward the center with both hands
  - ④ Add content: no rules

#### Slide 08 - Content Types

- **Layout**: icon_grid 2×3 or 3×2
- **Title**: Things you can fill
- **Visualization**: icon_grid
- **Content**:
  - Sketches / doodles / mini comics (pencil)
  - Poems / manifestos / short essays (pen-nib)
  - Illustrated recipes (sticky-note)
  - Family photos + personal writing (book)
  - Collage + mixed media (scissors)
  - Experimental visuals (brush)

### Part 5: Independent Bookstores Around the World

#### Slide 09 - Jimbōchō, Tokyo

- **Layout**: Full-bleed hero + oversized type + three fact bars at bottom left
- **Title**: Jimbōchō / JIMBŌCHŌ
- **Content**:
  - One of the world's largest used-book districts: 130–180 bookstores
  - 1875 Takayama Honten / 1902 Kitazawa English Books / 2015 Morioka Shoten（one book a week）
  - Time Out's "Coolest Neighborhoods in the World" in 2025

#### Slide 10 - Paris / London / New York

- **Layout**: vertical_pillars 1×3
- **Title**: Three cities, three attitudes
- **Visualization**: vertical_pillars
- **Content**:
  - **Shakespeare and Company, Paris**: Current location established by George Whitman in 1951; has hosted thousands of “tumbleweeds,” or traveling writers
  - **Daunt + Word on the Water, London**: Daunt organizes books by country; Word on the Water is a 1920s Dutch canal barge
  - **Strand + Yu and Me, New York**: Strand, founded in 1927, has 18 miles of bookshelves; Yu and Me, founded in 2021, is an Asian American women’s bookstore in Chinatown

#### Slide 11 - Berlin Bücherbogen

- **Layout**: Full-bleed hero + oversized type + floating definition text
- **Title**: BÜCHERBOGEN
- **Content**:
  - Located beneath an S-Bahn viaduct, with brick vaulted ceilings
  - Specializing in art, design, photography, film, and architecture

#### Slide 12 - Map of Bookstores in Mainland China

- **Layout**: basic_table (4 columns × 15 rows)
- **Title**: Map of independent bookstores in China (zine-oriented)
- **Visualization**: basic_table
- **Content**: Table of 15 bookstores — Bookstore / City / Distinctive features / Zine orientation (★/★★/★★★)

#### Slide 13 - China Art Book Fair

- **Layout**: labeled_card, two cards side by side (abC + UNFOLD)
- **Title**: China’s twin stars of the art book fair scene
- **Visualization**: labeled_card
- **Content**:
  - **abC Art Book Fair**: Founded in 2015, held in Beijing and Shanghai; 6th Shanghai edition: 145 Chinese + 41 international exhibitors + 10,000 visitors
  - **UNFOLD Shanghai Art Book Fair**: Held one week after abC, with higher booth fees + larger crowds

### Part 6: How to Browse / How to Collect / Take Action

#### Slide 14 - How to Browse Independent Bookstores

- **Layout**: vertical_list, 4 items
- **Title**: 4 things to do before entering the store
- **Visualization**: vertical_list
- **Content**:
  - ① Look at the selection = look at the owner — An independent bookstore is essentially a “spiritual bookshelf”
  - ② Allow at least 1 hour — Browsing itself is part of the experience
  - ③ Bring cash — Some small shops do not accept electronic payments
  - ④ Ask before taking photos — Most independent bookstores are sensitive about photography

#### Slide 15 - How to Collect Zines

- **Layout**: vertical_list, 4 items
- **Title**: 4 rules for collecting zines
- **Visualization**: vertical_list
- **Content**:
  - ① Start with one — Find a topic you care about most
  - ② Protect it with a plastic sleeve — Second printings are rare
  - ③ Follow the author / publisher on Instagram
  - ④ Attend abC / UNFOLD — New releases debut on-site

#### Slide 16 - Action Checklist: Your First Zine

- **Layout**: numbered_steps, 4 steps
- **Title**: Your first zine: 4 steps to get started
- **Visualization**: numbered_steps
- **Content**:
  - ① Choose a topic you genuinely care about (it doesn’t have to be grand)
  - ② Fold an A4 sheet — using the method from P07 of this deck
  - ③ Fill 8 pages — handwriting / collage / photocopied old photos
  - ④ Print 10 copies — give 5 to friends and mail 5 to independent bookstores

#### Slide 17 - Sources & Acknowledgments

- **Layout**: Two-column list of sources + small acknowledgment text
- **Title**: Sources / References
- **Content**: List of source links (Wikipedia / My Modern Met / AFAR / The Creative Independent / Digitaling / Sixth Tone, etc.)

#### Slide 18 - Back Cover Outro

- **Layout**: Full-bleed hero（holding a zine）+ oversized outro
- **Title**: "Print one. Give one. Trade one."
- **Subtitle**: A zine is the world's smallest publishing house. It can also be yours.

---

## X. Speaker Notes Requirements

- **Filename**: Correspond one-to-one with SVG names (`01_cover.svg` → `notes/01_cover.md`)
- **Style**: conversational (suited to café / sharing-session settings, not formal)
- **Total duration**: ~12-15 minutes (40-50 seconds per page)
- **Purpose**: inspire (make people want to create a zine, rather than merely know about zines)

---

## XI. Technical Constraints Reminder

### SVG Generation Must Follow

1. viewBox: `0 0 1280 720`
2. Background uses `<rect>` elements with `#F5EFE0` paper color
3. Text wrapping uses `<tspan>` (`<foreignObject>` FORBIDDEN)
4. Transparency defaults to `fill-opacity` / `stroke-opacity`; `rgba()` remains converter-compatible
5. FORBIDDEN: `mask`, `<style>`, `class`, `foreignObject`, `textPath`, `animate*`, `script`
6. Text characters: raw Unicode (`—`, `→`, `©`, NBSP); HTML named entities (`&nbsp;`, `&mdash;`) FORBIDDEN. XML reserved characters must be escaped as `&amp; &lt; &gt; &quot; &apos;`
7. **Risograph aesthetics:**
   - Simulate color-registration misalignment by layering offset color blocks (e.g., offset 1–3px copies of the same shape in Federal Blue and Fluorescent Pink)
   - Simulate halftone dots with `<pattern>` + small circles (control dot density)
   - Cards have no rounded corners (border-radius: 0), consistent with the Riso printing process
8. `clipPath` may only be applied to `<image>` elements; describe cards / blocks with native `<rect>` elements
9. Icons must strictly use only the 27 icons in the `chunk-filled/` library; for missing icons, find the closest substitute within the library—do not mix libraries

### PPT Compatibility Rules

- Set opacity on each child element individually by default; `<g opacity="...">` can be converted but may produce an approximate-fidelity warning
- Image transparency uses an overlay (`<rect fill="bg-color" opacity="0.x"/>`)
- Inline styles only; external CSS and `@font-face` are FORBIDDEN
- Impact is a built-in PPT display font and is safe to use; Microsoft YaHei / Consolas are also preinstalled on Windows

---

## ✅ Design spec complete.

Next step:
- Images include AI generation → Invoke Image_Generator
