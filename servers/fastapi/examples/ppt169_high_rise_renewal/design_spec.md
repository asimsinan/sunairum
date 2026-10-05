# High-Rise Housing “Active Regeneration” - Design Spec

> Presentation design specifications based on the WeChat article “After the Hong Kong Fire, I’ll Never Dare Buy a High-Rise Again: Can ‘Active Regeneration’ Solve the Problems of High-Rise Housing?”

## I. Project Information

| Item | Value |
| ---- | ----- |
| **Project Name** | High-Rise Housing “Active Regeneration” — From the Sydney Model to China's Dilemma |
| **Canvas Format** | PPT 16:9 (1280×720) |
| **Page Count** | 15 |
| **Design Style** | A) General Versatile + Editorial Magazine |
| **Target Audience** | Urban renewal/architecture/real estate professionals, policy researchers, and urban residents concerned about housing safety |
| **Use Case** | Topic sharing / industry salons / internal circulation |
| **Created Date** | 2026-05-16 |

---

## II. Canvas Specification

| Property | Value |
| -------- | ----- |
| **Format** | PPT 16:9 |
| **Dimensions** | 1280×720 |
| **viewBox** | `0 0 1280 720` |
| **Margins** | 60px left/right, 50px top/bottom |
| **Content Area** | 1160×620 (safe area) |

---

## III. Visual Theme

### Theme Style

- **Style**: Editorial magazine style — long-form excerpts + case-study images + distilled viewpoints
- **Theme**: Light theme (warm off-white paper feel)
- **Tone**: Steady, intellectually charged, highly readable; like a feature in *Sanlian Life Week* or *Kanli Xiang*

### Color Scheme

| Role | HEX | Purpose |
| ---- | --- | ------- |
| **Background** | `#F5F2EC` | Off-white, paper-textured page background |
| **Secondary bg** | `#EBE6DC` | Secondary background for cards / columns |
| **Primary** | `#2B3A4A` | Deep slate blue-gray — title and main body color |
| **Secondary accent** | `#5A6B7A` | Secondary text and dividers |
| **Accent (warning)** | `#C2410C` | Warning orange-red — fire and risk topics |
| **Accent (regen)** | `#6B7A4F` | Moss green — regeneration and sustainability topics |
| **Accent (heritage)** | `#8B7355` | Brick brown — architecture and history topics |
| **Body text** | `#2B3A4A` | Body text |
| **Secondary text** | `#5A6B7A` | Notes and sources |
| **Tertiary text** | `#8A8275` | Page numbers and footers |
| **Border/divider** | `#D6CFC0` | Dividers |

> 60-30-10: 60% warm ivory background / 30% deep blue-gray / 10% orange-red + moss green + brick brown combined. Select the theme color on each page according to its content (orange-red for the fire page, moss green for the regeneration page, brick brown for the architectural case-study page).

---

## IV. Typography System

### Font Plan

**Typography direction**: Cool serif (academic editorial) + Chinese Kai-style type for quotations

| Role | Chinese | English | Fallback tail |
| ---- | ------- | ------- | ------------- |
| **Title** | `KaiTi` | `Georgia` | `serif` |
| **Body** | `"Microsoft YaHei", "PingFang SC"` | `Arial` | `sans-serif` |
| **Emphasis** | `KaiTi` | `Georgia` | `serif` |
| **Code** | — | `Consolas, "Courier New"` | `monospace` |

**Per-role font stacks**:

- Title: `Georgia, KaiTi, serif` (Latin first, for a magazine feel)
- Body: `"Microsoft YaHei", "PingFang SC", Arial, sans-serif`
- Emphasis: `KaiTi, Georgia, serif` (KaiTi for quotations/case names)
- Code: `Consolas, "Courier New", monospace`

### Font Size Hierarchy

**Baseline**: Body = 20px (moderate density, suitable for long-form educational content)

| Purpose | Ratio | Px | Weight |
| ------- | ----- | -- | ------ |
| Cover title | 3-4x | 60-80 | Bold |
| Chapter opener | 2.2-2.5x | 44-50 | Bold |
| Page title | 1.6-1.8x | 32-36 | Bold |
| Subtitle | 1.2-1.4x | 24-28 | SemiBold |
| **Body** | **1x** | **20** | Regular |
| Annotation | 0.7-0.8x | 14-16 | Regular |
| Page number | 0.6x | 12 | Regular |

---

## V. Layout Principles

### Page Structure

- **Header area**: 80px — section number (Roman numerals) + page number + thin divider
- **Content area**: 540px — freely arranged, mixing multiple image-layout-patterns
- **Footer area**: 40px — footer source/page number

### Layout Pattern Library

Choose by content: single-column centered (cover/conclusion), asymmetrical columns (case comparisons), full-screen image + floating text (chapter openers/hero pages), image-text overlays, side-by-side comparisons (before and after), multi-image collages (global case tour), negative-space driven (quote pages).

### Spacing Specification

**Universal**:
- Safe margin: approximately 60px left and right / 50px top and bottom
- Content block gap: 28–36px
- Icon-text gap: 12px

**Non-card containers** (editorial magazine style, centered on divider lines and whitespace, with limited use of cards):
- Line-height: 1.5× body
- Full-bleed text: add a 0.4–0.6 opacity overlay when text is placed over images

---

## VI. Icon Usage Specification

### Source

- **Library**: `tabler-outline` (stroke=2 lines, preferred for editorial styles)
- **Usage**: SVG placeholder `<use data-icon="tabler-outline/icon-name" .../>`

### Recommended Icon List

| Purpose | Icon Path | Page |
| ------- | --------- | ---- |
| Fire/warning | `tabler-outline/flame` | P03 |
| Time/building age | `tabler-outline/clock` | P03 |
| Building/skyscraper | `tabler-outline/building-skyscraper` | P04, P12 |
| Maintenance/tools | `tabler-outline/tool` | P04 |
| Regeneration/cycle | `tabler-outline/refresh` | P06, P07 |
| Leaf/sustainability | `tabler-outline/leaf` | P07 |
| Demolition/blasting | `tabler-outline/bomb` | P05 |
| Map/location | `tabler-outline/map-pin` | P09, P10, P11 |
| Funding/money bag | `tabler-outline/coin` | P12 |
| Users/residents | `tabler-outline/users` | P13 |
| Inspection/health check | `tabler-outline/clipboard-check` | P13 |
| Quotation/key quote | `tabler-outline/quote` | P14 |

> If the Executor identifies a need for additional icons during generation, use `ls | grep` within `tabler-outline/` to find the nearest match; do not mix icon libraries.

---

## VII. Visualization Reference List

Catalog read: 71 templates

| Page | Template | Path | Summary-quote (verbatim) | Usage |
| ---- | -------- | ---- | ------------------------ | ----- |
| P02 | agenda_list | `templates/charts/agenda_list.svg` | "Pick for table of contents, meeting agendas, or presentation roadmap — numbered items + brief description + duration / owner per row." | Full-deck agenda overview (4 sections) |
| P13 | numbered_steps | `templates/charts/numbered_steps.svg` | "Pick for 3-6 horizontal sequential steps with numeric emphasis — how-it-works section, getting-started guide, methodology overview, implementation phases." | Four-step governance process: "assess first, then update" |

**Runners-up considered**:

- `vertical_list` | rejected for P02: An agenda page typically needs section numbers + brief descriptions; `agenda_list` is more specialized, while `vertical_list` is too generic
- `process_flow` | rejected for P13: The content consists of parallel stages of governance concepts rather than an arrow-connected workflow; `numbered_steps` is a better fit
- `pros_cons_chart` | rejected for P12: The dilemma of high-rise residential renovation is a complex one-sided argument, not a clear pros-and-cons comparison, so a freeform design is used

> Other pages are primarily narrative + image, using freeform design (editorial magazine collage / split columns / hero) rather than forcing a chart template.

---

## VIII. Image Resource List

> The user provided 25 original article images, all placed in `images/`. Layouts use diverse image-layout patterns rather than relying exclusively on left-right / top-bottom splits.

| Filename | Dimensions | Ratio | Purpose | Type | Layout pattern | Acquire Via | Status | Reference |
| -------- | --------- | ----- | ------- | ---- | -------------- | ----------- | ------ | --------- |
| 640.png | 606x991 | 0.61 | Hong Kong high-rise nightscape (cover background) | Background | #1 full-bleed background with floating title | user | Existing | City nightscape, densely lit supertall buildings |
| 640_1.png | 1080x917 | 1.18 | Still from the film *BURNING* | Photography | #38 background image + annotation cards | user | Existing | High-rise fire film scene, ominous atmosphere |
| 640_2.png | 1080x648 | 1.67 | Pruitt-Igoe housing complex | Photography | #48 side-by-side comparison (paired with 640_3) | user | Existing | Original appearance of the failed US housing complex |
| 640_3.png | 660x521 | 1.27 | Pruitt-Igoe demolition | Photography | #48 side-by-side comparison (paired with 640_2) | user | Existing | Moment of explosive demolition in 1972 |
| 640_4.png | 801x1200 | 0.67 | AMP Centre before renovation | Photography | #44 before-after split-screen (paired with 640_5) | user | Existing | Original appearance of the aging office tower |
| 640_5.png | 1080x2172 | 0.50 | Quay Quarter Tower after renovation | Photography | #44 before-after split-screen (paired with 640_4) | user | Existing | Full-height frontal view of the new skyscraper |
| 640_6.png | 750x1000 | 0.75 | Quay Quarter Tower detail 1 | Photography | #2 left-third image / right-side text | user | Existing | Curved top echoing the harbor |
| 640_7.png | 1080x440 | 2.45 | Quay Quarter Tower detail 2 | Photography | #5 top-bottom band (ultra-wide) | user | Existing | Ultra-wide distant view of a skyscraper |
| 640_8.png | 1080x1166 | 0.93 | Quay Quarter Tower detail 3 | Photography | #41 image-as-canvas + KPI overlay | user | Existing | Close-up architecture with sustainability data overlay |
| 640_9.png | 640x345 | 1.86 | Shenzhen Women and Children's Building before renovation | Photography | #44 before-after split-screen (placed alongside 640_10) | user | Existing | Original appearance of the old building |
| 640_10.png | 1080x1620 | 0.67 | Shenzhen Women and Children's Building after renovation | Photography | #44 before-after split-screen (placed alongside 640_9) | user | Existing | New colorful grid facade |
| 640_11.png | 600x781 | 0.77 | East China Electric Power Building before renovation | Photography | #44 before-after split-screen (placed alongside 640_12) | user | Existing | Original appearance in 1988 |
| 640_12.png | 1080x720 | 1.50 | The Edison Hotel after renovation | Photography | #44 before-after split-screen (placed alongside 640_11) | user | Existing | Facade after energy-efficient renovation |
| 640_13.png | 1080x718 | 1.50 | One Wall Street, New York, after renovation | Photography | #2 left-third image / right-side text | user | Existing | Art Deco skyscraper |
| 640_14.png | 1080x608 | 1.78 | One Wall Street apartment interior | Photography | #20 polaroid stack | user | Existing | Interior space details |
| 640_15.png | 469x581 | 0.81 | Urban architecture atmosphere | Atmosphere | #6 atmospheric backdrop with overlay | user | Existing | Looking up at a glass curtain wall |
| 640_16.png | 1080x1439 | 0.75 | Beijing “Office Ring” project | Photography | #3 right-third image / left-side text | user | Existing | High-rise residential building converted into offices |
| 640_17.png | 640x400 | 1.60 | MUJI renovation of an old apartment | Photography | #20 polaroid stack (collaged with 640_16) | user | Existing | Japanese-style renovated room |
| 640_18.png | 1080x1440 | 0.75 | High-rise residential exterior atmosphere | Atmosphere | #6 atmospheric backdrop with overlay | user | Existing | Looking up at a cluster of high-rise buildings |
| 640_19.png | 1080x810 | 1.33 | Zhejiang University of Technology New Village before renovation | Photography | #44 before-after split-screen (placed alongside 640_20) | user | Existing | Run-down residential compound from the 1980s |
| 640_20.png | 1080x619 | 1.74 | Rendered result of Zhejiang University of Technology New Village | Photography | #44 before-after split-screen (placed alongside 640_19) | user | Existing | Rendered result showing demolition and reconstruction in place |
| 640_21.png | 870x580 | 1.50 | Atmosphere of resident discussions | Atmosphere | #38 background image + annotation cards | user | Existing | Community co-building and shared governance atmosphere |
| 640_22.png | 1074x806 | 1.33 | Urban renewal / health-check atmosphere | Photography | #2 left-third image / right-side text | user | Existing | Aerial view of the city, evoking a health check |
| 640_23.png | 1080x723 | 1.49 | City skyline (conclusion) | Background | #1 full-bleed background with floating title | user | Existing | Large hero image for the conclusion |
| 640_24.png | 640x640 | 1.00 | Circular architectural decorative element | Decorative | #21 circular crop accent | user | Existing | Decorative circular image, chapter-opening accent |

> Layout diversity check: includes #1 (hero), #2/#3 (asymmetric split), #5 (extra-wide band), #6 (atmospheric background), #20 (Polaroid collage), #21 (circular cropped corner), #38 (background + cards), #41 (image-as-canvas + overlaid data), #44 (before-after comparison), and #48 (side-by-side comparison)—10 pattern types in total. Group D coverage: P08 (#41 image-as-canvas + overlaid KPI layer).

---

## IX. Content Outline

### Part 1: Prologue — It Began with a Fire

#### Slide 01 - Cover

- **Layout**: Full-screen hero background + floating text title (Pattern #1)
- **Title**: Proactive Renewal
- **Subtitle**: After the Hong Kong Fire, What Lies Ahead for Aging High-Rises?
- **Info**: Based on the original article by the WeChat public account "Sun Wantong" · 2026.05
- **Image**: 640.png (high-rise night view)

#### Slide 02 - Agenda

- **Layout**: Single-column agenda (agenda_list)
- **Title**: Today's Agenda
- **Visualization**: agenda_list (4 items)
- **Content**:
  - I. Warning Bell: Aging High-Rises and the Fire-Safety Dilemma
  - II. Model: The "Renewal Revolution" of a Sydney Skyscraper
  - III. Survey: Global Cases of Functional Transformation
  - IV. Hard Knot: Aging High-Rise Housing in China

### Part 2: Wake-Up Call — Aging in High-Rises & the Fire-Safety Dilemma

#### Slide 03 - The Hong Kong Fire Sounds an Alarm

- **Layout**: Background image + annotation card (Pattern #38)
- **Title**: One Fire Exposed More Than Just Fire-Safety Risks
- **Content**:
  - 2025.11.26 Hong Fook Court, Tai Po, Hong Kong: 7 buildings over 30 stories, nearly 100 meters tall, 42 years old
  - In the first 8 months of 2025, **36,000 high-rise building fires** occurred nationwide, exceeding the full-year total for 2023
  - Ground-based firefighting typically reaches 50–80 meters; above 100 meters, buildings mainly depend on self-rescue
- **Image**: 640_1.png (background still from *Burning City*)

#### Slide 04 - High-Rises Are Aging

- **Layout**: Asymmetrical split #2 (image left, text right)
- **Title**: Once a Symbol of Prosperity, It Is Becoming a Heavy Maintenance Burden
- **Content**:
  - Within little more than a decade of completion, structural, fire-safety, elevator, and exterior-wall risks emerged in clusters
  - Maintenance costs rise sharply with building age; fewer people are willing to live in high-rises
  - "High-rise housing is the slum of the future" — there are precedents in the West
- **Image**: 640_18.png (low-angle view of high-rise buildings)

#### Slide 05 - A Cautionary Tale: Pruitt-Igoe

- **Layout**: Juxtaposed comparison (Pattern #48)
- **Title**: Is Demolition the Only Fate for Aging High-Rises?
- **Content**:
  - Pruitt–Igoe, United States: 33 high-rise buildings, long-neglected public spaces → all demolished in 1972
  - Wealthier residents moved out → lower-income residents concentrated there → facilities deteriorated → crime rates rose → demolition
- **Images**: 640_2.png (original appearance) + 640_3.png (the moment of demolition)

### Part 3: Case Study — Sydney’s “Adaptive Reuse Revolution”

#### Slide 06 - Chapter Opener II

- **Layout**: Full-screen background + floating text + circular decoration (Pattern #1 + #21)
- **Title**: II
- **Subtitle**: The Sydney Model — A Skyscraper's "Renewal" Revolution
- **Image**: 640_24.png (circular decoration)

#### Slide 07 - Quay Quarter Tower: From Demolition to Transformation

- **Layout**: Before-after comparison (Pattern #44)
- **Title**: The World's First "Fully Upgraded" Skyscraper
- **Content**:
  - Former AMP Centre: 1976, 206 metres, 49 floors
  - Design: 3XN — "maximum retention, high-quality upgrading"
  - Retained 65% of the primary structure + 95% of the core, transforming it into a multifunctional complex
- **Images**: 640_4.png (before renovation) + 640_5.png (after renovation)

#### Slide 08 - Environmental Data: The True Weight of Recycling

- **Layout**: Image-as-canvas + KPI overlay（Pattern #41）
- **Title**: The Key to Reaching the Finals of the "Striving for the Earth Award"
- **Visualization**: Three large numbers（hero numbers）overlaid on the building image
- **Content**:
  - **−80%** construction waste（structural reuse）
  - **−40%** carbon emissions（compared with demolition and reconstruction）
  - **−30%** energy consumption（smart ventilation + photovoltaic facade + rainwater recycling）
- **Image**: 640_8.png（close-up architectural image as the background）

### Part 4: Tour — Global Adaptive Reuse Cases

#### Slide 09 - Shenzhen Women's and Children's Building (MVRDV)

- **Layout**: Before-after comparison (Pattern #44)
- **Title**: Dressing an Old Building in a "Colourful Grid Skin"
- **Content**:
  - Completed in 1994, with renovation led by MVRDV
  - Colourful grid façade adds 1 metre of depth → shading + natural ventilation
  - Introduces a range of uses, including a hotel, children's discovery centre, and picture-book museum
- **Images**: 640_9.png (before renovation) + 640_10.png (after renovation)

#### Slide 10 - The Shanghai EDITION (East China Electric Power Building)

- **Layout**: Before-after comparison (Pattern #44)
- **Title**: The Nation's First **Carbon-Neutral Hotel in the Urban Renewal Sector**
- **Content**:
  - Former 1988 East China Electric Power Building, 126 metres, the first high-rise on East Nanjing Road
  - Expanded and renovated into an EDITION hotel in 2018; energy-efficiency upgrades completed in 2023
  - High-performance windows + air-source heat pumps + energy-efficient elevators + water-saving fixtures
- **Images**: 640_11.png (before renovation) + 640_12.png (after renovation)

#### Slide 11 - New York One Wall Street: Office-to-Residential Conversion

- **Layout**: Asymmetrical split #2 (image left, text right) + polaroid collage #20
- **Title**: A 1931 Art Deco Skyscraper Becomes 566 Apartments
- **Content**:
  - 50-story office tower → apartments ranging from studios to four-bedroom units
  - Converting offices and commercial buildings into housing is a global trend: strong structural integrity and high flexibility
- **Images**: 640_13.png (exterior) + 640_14.png (polaroid apartment interior)

### Part 5: The Challenge — The Toughest Cases in China’s Aging High-Rise Housing

#### Slide 12 - Chapter Opener IV

- **Layout**: Atmospheric background + floating text (Pattern #6)
- **Title**: IV
- **Subtitle**: What should we do with high-rise housing that has grown old and deteriorated?
- **Image**: 640_15.png (upward view of a glass curtain wall)

#### Slide 13 - Pilot Cases: Beijing "Office Huancheng" + Zhejiang University of Technology New Village

- **Layout**: Two-column collage (#3 image right, text left + #44 comparison)
- **Title**: Existing Attempts: From Functional Transformation to Demolition and Reconstruction
- **Content**:
  - **Office Huanchen** (Tiantongyuan, Beijing): high-rise housing → office building, easing the "job-housing separation" problem
  - **Zhejiang Gongxin Village** (Hangzhou): the first aging residential community to undergo demolition and reconstruction
    - 13 buildings demolished, 7 new 11-story buildings constructed; total investment of ¥530 million, with residents raising ¥470 million themselves
    - Each household contributed ¥100,000–1 million
- **Images**: 640_16.png (Office Huanchen) + 640_19.png + 640_20.png (Zhejiang Gongxin Village comparison)

#### Slide 14 - The Real Challenge: Getting Everyone to Pay

- **Layout**: Negative-space driven — oversized statement + annotation (Pattern #11)
- **Title**: “Demolish and Rebuild in Place” Is Bound to Be Extremely Complex for High-Rise Projects
- **Content**:
  - **Key statement**: "High-rise residential complexes have more households, making it difficult for all owners to reach consensus."
  - Where the funding comes from and who pays → still being explored
  - A possible path forward lies in a “co-construction, co-governance, and shared-benefit” model — establishing a “housing pension” and bringing in residents’ committees for self-management
- **Image**: 640_21.png (background evoking a community discussion)

#### Slide 15 - Closing: Diagnose First, Update Later

- **Layout**: Full-screen hero + 4 numbered steps
- **Title**: From Pursuing Height to Building Depth
- **Visualization**: numbered_steps (4 steps)
- **Content**:
  - **1. Health check** — As of 2025.11, 297 prefecture-level cities + 150+ county-level cities nationwide have launched urban health checks
  - **2. Design** — Professional institutions provide safe and reliable plans
  - **3. Coordination** — Government platforms + grassroots community organizations
  - **4. Renewal** — Collective efforts breathe new life into aging supertall buildings
- **Image**: 640_23.png (city skyline hero background)

---

## X. Speaker Notes Requirements

- 100–180 Chinese characters per page, with filenames matching the SVG (`01_cover.md` ↔ `01_cover.svg`)
- Style: explanatory, in the voice of a magazine host; distill insights rather than pile up data
- The `notes/total.md` master document uses `#` section headings; paginated files must not use `#`

---

## XI. Technical Constraints Reminder

### SVG Generation Must Follow:

1. viewBox: `0 0 1280 720`
2. Background uses `<rect>` elements
3. Text wrapping uses `<tspan>` (`<foreignObject>` forbidden)
4. Transparency defaults to `fill-opacity` / `stroke-opacity`; `rgba()` remains converter-compatible
5. Forbidden: `mask`, `<style>`, `class`, `foreignObject`, `textPath`, `animate*`, `script`
6. Use raw Unicode characters (`—`, `–`, `©`, `®`, `→`, NBSP); HTML named entities are forbidden; `&`, `<`, `>`, `"`, and `'` must be escaped
7. `clipPath` may only be used on `<image>` elements

### PPT Compatibility Rules:

- Set opacity on each child element by default; `<g opacity="...">` can be converted but may produce an approximate-fidelity warning
- Use an overlaid `<rect>` mask for image transparency
- Inline styles only; external CSS and `@font-face` are disabled
