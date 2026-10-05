# ppt169_ai_industry_2026 — Design Spec

> Brutalist editorial newspaper · capability-showcase demo for PPT Master roadmap §P0-2
> Source: `sources/ai_industry_2026.md` (compiled May 2026 from Counterpoint / Stanford HAI / OneTrust / Deluair / IEEE Spectrum)

## I. Project Information

| Item | Value |
| ---- | ----- |
| **Project Name** | ppt169_ai_industry_2026 |
| **Canvas Format** | PPT 16:9 (1280×720) |
| **Page Count** | 10 |
| **Design Style** | B) General Consulting + Brutalist editorial newspaper |
| **Target Audience** | AI industry professionals / investors / researchers / technology readers interested in AI turning points |
| **Use Case** | Annual-report-style industry review — forum / brown-bag / investor quarterly report opener |
| **Created Date** | 2026-05-21 |

---

## II. Canvas Specification

| Property | Value |
| -------- | ----- |
| **Format** | PPT 16:9 |
| **Dimensions** | 1280×720 |
| **viewBox** | `0 0 1280 720` |
| **Margins** | Left/Right 48px, Top/Bottom 40px (newspaper-style narrow margins) |
| **Content Area** | 1184×640 |

---

## III. Visual Theme

### Theme Style

- **Style**: Brutalist editorial newspaper — full-bleed small type + irregular column widths + native shape rules and borders + black-and-white halftone imagery + single-point red emphasis
- **Theme**: Light theme (newsprint-white background)
- **Tone**: Serious, restrained, exceptionally information-dense, reportorial

### Color Scheme

| Role | HEX | Purpose |
| ---- | --- | ------- |
| **Background** | `#FFFFFF` | Main background (paper white) |
| **Secondary bg** | `#F4F1EA` | Sidebar / pull quote / pale paper-yellow sidebar |
| **Primary** | `#111111` | Main shapes / rule lines / main text |
| **Accent** | `#C8102E` | Red emphasis — one red masthead line, key data points, and the `The Number` anchor (under 5% throughout) |
| **Secondary accent** | `#3A3A3A` | Secondary text / annotations / footer |
| **Body text** | `#111111` | Main text |
| **Secondary text** | `#3A3A3A` | Secondary text / captions |
| **Tertiary text** | `#6B6B6B` | Footnotes / page numbers |
| **Border/divider** | `#000000` | Newspaper rules, column dividers, cell borders |
| **Success** | `#1A6E3A` | Positive data points (used sparingly) |
| **Warning** | `#A02014` | Negative data points (used sparingly) |

### AI Image Strategy

- **Image Rendering**: editorial
- **Image Palette**: mono-ink

> Newspaper documentary style: halftone grain, paper texture, clean partitioning, flat black-ink fills, with a single appearance of spot red `#C8102E` outside the ink-black core (such as a red seal / red circle annotation / red underline).

---

## IV. Typography System

### Font Plan

**Typography direction**: Brutalist newspaper — display sans Black headlines × small-type serif body text × monospace data, with strong contrast across the three families

| Role | Chinese | English | Fallback tail |
| ---- | ------- | ------- | ------------- |
| **Title (masthead / headline)** | `SimHei` | `Impact, "Arial Black"` | `sans-serif` |
| **Subtitle / Section label** | `SimHei` | `"Arial Black"` | `sans-serif` |
| **Body (newspaper column)** | `SimSun` | `"Times New Roman"` | `serif` |
| **Emphasis** | `SimSun` | `Georgia` | `serif` |
| **Code / Data** | — | `Consolas, "Courier New"` | `monospace` |

**Per-role font stacks**:

- Title: `Impact, "Arial Black", SimHei, sans-serif`
- Subtitle: `"Arial Black", SimHei, sans-serif`
- Body: `"Times New Roman", SimSun, serif`
- Emphasis: `Georgia, "Times New Roman", SimSun, serif`
- Code: `Consolas, "Courier New", monospace`

### Font Size Hierarchy

**Baseline**: Body font size = **14px** (full-page small-text density, denser than the conventional 18px dense setting; a typical reading rhythm for Brutalist broadsheets)

| Purpose | Ratio to body | Px @ body=14 | Weight |
| ------- | ------------- | ------------ | ------ |
| Cover masthead (THE AI INDUSTRY 2026) | 5-6x | 72-90 | Black |
| Section opener / headline | 3-4x | 42-56 | Black |
| Page title | 2-2.5x | 28-36 | Bold |
| Hero number (newspaper-style large number) | 3.5-5x | 50-72 | Black |
| Subtitle / Section label | 1.4-1.6x | 20-22 | SemiBold |
| **Body content** | **1x** | **14** | Regular |
| Annotation / caption | 0.75-0.85x | 11-12 | Regular |
| Page number / footnote / imprint | 0.6-0.75x | 9-10 | Regular |

---

## V. Layout Principles

### Page Structure

- **Header area**: Masthead/page-header 64px (4px top red line + 60px newspaper title bar)
- **Content area**: 568px (newspaper body; irregular multi-column widths)
- **Footer area**: 28px (imprint / page number / date)

### Layout Pattern Library

Brutalist newspaper layouts mainly use:
- **Asymmetric multi-column** (2/3/4 uneven-width columns) — irregular column widths are the defining feature
- **Top-band + multi-column** — a large image across the top + multiple columns below
- **Sidebar column** (image or pull-quote) — a fixed sidebar on the left or right of the page
- **Hero number + body** — a single oversized number + an explanatory column
- **Rule-line grid** — use thick and thin rule lines as dividers instead of box cards
- **Center-radiating** — used for the P06 KPI overlay

### Spacing Specification

**Universal**:

| Element | Range | Current |
| ------- | ----- | ------- |
| Safe margin from canvas edge | 40-60px | **48px L/R, 40px T/B** |
| Content block gap | 16-24px | **20px** |
| Column gap (rule line gutter) | 14-20px | **16px** |

**Non-card containers** (Brutalist broadsheets generally avoid cards, relying on rule lines for separation):

- Line-height: 1.35–1.45× body font size (compact newspaper rhythm)
- Body column width: 220–340px (typically 3–4 columns)
- Rule line stroke: 0.5px hairline / 1px standard / 2–3px section divider / 4px masthead red bar

---

## VI. Icon Usage Specification

**No icon library**. Brutalist newspapers speak through typography + rule lines + halftone illustrations; icons would only dilute the impact.

---

## VII. Visualization Reference List

Catalog read: 71 templates

| Page | Template | Path | Summary-quote (verbatim) | Usage |
| ---- | -------- | ---- | ------------------------ | ----- |
| P02 | kpi_cards | `templates/charts/kpi_cards.svg` | "Pick for 4-8 standalone numeric metrics shown as overview cards (2x2 or 1x4) — exec summary opener, dashboard headline," | Four headline KPIs: $2.02T spending / 3.8B users / $20.7B Q1 revenue / 1000+ policies |
| P03 | horizontal_bar_chart | `templates/charts/horizontal_bar_chart.svg` | "Pick for ranking 5-12 items, especially with long labels. Skip if <=8 short-label items (use bar_chart)." | LLM revenue share ranking, Q1 2026 — Anthropic / OpenAI / Google / MSFT / Tencent / Baidu / Alibaba / Meta / Grok / Perplexity |
| P04 | dumbbell_chart | `templates/charts/dumbbell_chart.svg` | "Pick for before-vs-after or two-state difference across 5-10 items. Skip for single snapshot (use bar_chart) or 3+ states" | ARPU gap comparison: MAU vs monthly ARPU for 5 major labs, two states |
| P05 | line_chart | `templates/charts/line_chart.svg` | "Pick for 1-3 time-series on a continuous axis showing direction. Skip if cumulative volume matters (use area_chart) or d" | Training cost trajectory: GPT-4 → Llama 3.1 → Gemini Ultra → 2026 frontier → 2027 projected |
| P06 | bar_chart | `templates/charts/bar_chart.svg` | "Pick for single-series category value comparison, 3-8 categories. Skip for >12 long-label items (use horizontal_bar_char" | Inference power comparison, W/query: Claude 4 Opus / GPT-4 / Gemini 2.5 / DeepSeek V3 / Llama 3.1 |
| P07 | dumbbell_chart | `templates/charts/dumbbell_chart.svg` | "Pick for before-vs-after or two-state difference across 5-10 items. Skip for single snapshot (use bar_chart) or 3+ states" | Benchmark saturation: 2024 → 2025 shifts across SWE-bench / HLE / PhD-QA / Math |
| P08 | comparison_table | `templates/charts/comparison_table.svg` | "Pick for 2-4 plans/products compared across many feature rows (dense matrix). Skip for pricing-tier marketing layout (us" | Three-way regulatory comparison: differences among the EU / US / China in effective dates / penalties / scope / focus |
| P09 | timeline | `templates/charts/timeline.svg` | "Pick for 3-8 milestone events on a horizontal time axis (no duration). Skip for tasks with start/end ranges (use gantt_c" | 6 milestone events from 2025-01 → 2026-04 |

**Runners-up considered**:

- `grouped_bar_chart` | rejected for P04: The two-state MAU/ARPU differences are enormous (four orders of magnitude); a dumbbell separates the scales more readably, while grouped bars become unbalanced when the gap is so large.
- `vertical_pillars` | rejected for P08: The regulatory comparison is a structured “many-row, many-column” format; pillars are better suited to 1×N side-by-side units. `comparison_table` more precisely matches the density of “many feature rows”.
- `process_flow` | rejected for P09: The 2025–2026 events are discrete, nonlinear milestones rather than a process; `timeline` directly matches “milestone events on a horizontal time axis”.
- `bullet_chart` | rejected for P02: A bullet chart requires target + actual values; the four KPIs on this page are standalone figures with no targets.
- `area_chart` | rejected for P05: Training cost is not cumulative volume but a model-by-model trajectory; `line_chart` is more accurate.

---

## VIII. Image Resource List

| Filename | Dimensions | Ratio | Purpose | Layout pattern | Acquire Via | Status | Reference | text_policy | page_role |
| -------- | --------- | ----- | ------- | -------------- | ----------- | ------ | --------- | ----------- | --------- |
| p01_cover_hero.png | 1280×720 | 1.78 | Cover hero key image | #1 full-bleed background with floating title + #29 two-stop scrim | ai | Pending | An abstract editorial newspaper photograph: vast information surge depicted as parallel cascading data ribbons descending from the upper darkness into bright reflective floor; silhouette of a lone figure standing at the foot looking up; high-contrast halftone, paper grain, slight motion blur on the ribbons; calm right-side area reserved for masthead title overlay | none | hero_page |
| p03_revenue_leader.png | 480×720 | 0.67 | Revenue ranking image — side image | #18 image as full-height sidebar column + #70 thin colored matte frame | ai | Pending | A vertical editorial photograph: an empty stage podium with the front sign blank and a smaller secondary podium behind partially in shadow; bright ceiling spotlight only on the front podium; halftone grain; suggests a changing of the guard, no people | none | local |
| p05_training_cost.png | 1280×320 | 4.00 | Training cost banner — mid-section horizontal banner | #14 horizontal banner strip cutting through mid-section + #70 thin colored matte frame | ai | Pending | An editorial wide photograph of a vast GPU server hall stretching to vanishing point; long aisle between two walls of black server racks with small status lights; cold overhead lighting; halftone, paper grain; reads as scale and power infrastructure | none | local |
| p06_inference_thermal.png | 1280×720 | 1.78 | Inference power hero — floating KPI card background | #40 background image + floating KPI metric cards + #30 flat semi-transparent rectangle overlay | ai | Pending | An editorial photograph: extreme close-up of a single matte-black processor die with intricate etched circuitry visible; ambient heat shimmer above the die surface; one tiny bright red anomaly point at the corner; halftone grain; calm uniform areas reserved for KPI card overlays | none | local |
| p08_regulation_table.png | 1280×280 | 4.57 | Regulatory comparison illustration — top banner | #5 top-band image + bottom multi-column text + #70 thin colored matte frame | ai | Pending | An editorial wide photograph: three closed leather-bound official folders side by side on a wooden table under raking light, each folder slightly different in age and patina; a single bold rubber stamp impression visible on the center folder; halftone, paper grain; suggests three regulatory traditions | none | local |

---

## IX. Content Outline

### Part 1: Masthead

#### Slide 01 - Cover (Masthead)

- **Layout**: Full-bleed hero image + 4px red line at top + oversized masthead overlay in the calm region at bottom right
- **Title**: `THE AI INDUSTRY 2026`
- **Subtitle**: `Annual Report — Volume 1, Edition 1`
- **Info**: `Compiled May 2026 · Sources: Stanford HAI · Counterpoint · OneTrust · Deluair · IEEE Spectrum`
- **Tagline (red accent)**: `THE YEAR THE LEAGUE TABLE CHANGED.`

### Part 2: Front Page

#### Slide 02 - Issue at a Glance

- **Layout**: Top page-header red rule + reused large masthead + 4 KPI cards (1×4 horizontal row) + three short columns below, “Three Observations”
- **Title**: `ISSUE AT A GLANCE`
- **Visualization**: kpi_cards (see VII)
- **KPIs**:
  - `$2.02T` — Worldwide AI spending 2026E (+36% YoY) · Gartner
  - `3.8B` — Monthly LLM users worldwide · Counterpoint
  - `$20.7B` — Quarterly LLM revenue Q1 2026 · Counterpoint
  - `1,000+` — Active national AI policy initiatives across 72 countries · OneTrust
- **Three observations (3-column short body)**:
  1. Revenue concentration is breaking away from user-count rankings.
  2. Frontier training costs have cleared the $200M floor and are heading toward $1–3B by late 2027.
  3. Inference cost is falling by ~10× per year for the same capability.

### Part 3: Lead Story

#### Slide 03 - Story I: Revenue League Q1 2026

- **Layout**: Full-height machine sidebar image on the left (podium) + horizontal bar chart in the upper right 2/3 + small red pull-quote commentary below
- **Title**: `STORY I — REVENUE LEAGUE TABLE`
- **Subtitle**: `Anthropic 31.4 %  vs  OpenAI 29.0 %`
- **Visualization**: horizontal_bar_chart (see VII)
- **Data points**:
  - Anthropic 31.4%, OpenAI 29.0%, Google 12.1%, Microsoft 7.2%, Tencent 4.8%, Baidu 3.6%, Alibaba 2.9%, Meta 1.4%, Grok 1.4%, Perplexity 1.0%, DeepSeek 0.2%, Zhipu 0.1%
- **Pull-quote (red)**: `"FIRST NON-OPENAI LAB IN #1 SINCE THE MODERN LLM ERA BEGAN."`
- **Source line**: `Counterpoint Research · Global LLM Adoption and Revenue Snapshot, Q1 2026`

### Part 4: Sidebar Data

#### Slide 04 - The ARPU Divide

- **Layout**: Full-width dumbbell_chart occupying the upper two-thirds, with a four-column short caption below; no image
- **Title**: `THE ARPU DIVIDE — SCALE ≠ MONETISATION`
- **Visualization**: dumbbell_chart (see VII)
- **Data points (MAU left dot · ARPU right dot)**:
  - Meta: ~1,000M MAU · $0.10
  - OpenAI: 900M · $2.20
  - Google: — · $1.10
  - Anthropic: 134M · $16.20
  - Microsoft: — · $5.00
- **Caption body**: Anthropic's per-user revenue is 7.4× OpenAI's, 14.7× Google's, and 162× Meta's. Enterprise API and coding workloads compound faster than consumer free-tier scale.

#### Slide 05 - Frontier Training Cost

- **Layout**: Midsection 1280×320 wide banner photo (GPU corridor) + page title above + line_chart below + annotation column on the right
- **Title**: `FRONTIER TRAINING COST — PAST THE HALF-BILLION LINE`
- **Visualization**: line_chart (see VII)
- **Data points**: GPT-4 $78M → Llama 3.1 $170M → Gemini Ultra $191M → 2026 frontier $200-500M → late-2027 projected $1-3B
- **Annotation**: `1e26 – 1e27 FLOPs` (2026 frontier compute range). Power and grid interconnect, not chip supply, are the binding constraint for the late-2027 cohort.

### Part 5: Inside Pages

#### Slide 06 - Inference — Watts per Query

- **Layout**: full-bleed processor die image as canvas + 4 floating KPI cards + translucent overlay for legibility
- **Title**: `INFERENCE — A 4.6× SPREAD INSIDE THE FRONTIER CLASS`
- **Visualization**: bar_chart (see VII)
- **KPI cards (floating)**:
  - `5 W` Claude 4 Opus per medium prompt
  - `23 W` DeepSeek V3 per medium prompt
  - `10×` Carbon emissions spread (most-vs-least efficient)
  - `~10×/yr` Inference cost decline at constant capability
- **Source**: Stanford HAI AI Index 2026

#### Slide 07 - Capability — Benchmarks Saturated

- **Layout**: Full-width dumbbell_chart showing the 2024→2025 leap + short body below; no image
- **Title**: `CAPABILITY — BENCHMARKS SATURATED FASTER THAN BUILT`
- **Visualization**: dumbbell_chart (see VII)
- **Data points (2024 → 2025)**:
  - SWE-bench Verified (coding): ~60% → ~100% of human baseline
  - Humanity's Last Exam: baseline → +30 pp
  - PhD-level science QA: below baseline → meet/exceed
  - Multimodal reasoning: below baseline → meet/exceed
  - Competition mathematics: below baseline → meet baseline
- **Editorial line**: `THE BENCH-DESIGN COMMUNITY IS NOW PERMANENTLY BEHIND THE MODEL-RELEASE CYCLE.`

### Part 6: Regulation

#### Slide 08 - Three Rulebooks, One Race

- **Layout**: Top 1280×280 banner photo (three folders) + comparison_table below, 3 columns × N rows
- **Title**: `THREE RULEBOOKS, ONE RACE`
- **Visualization**: comparison_table (see VII)
- **Columns**: EU · United States · China
- **Rows**:
  - Posture — Class-of-model regulation · Sector + state regulation · Output-tagging regulation
  - Core instrument — AI Act · EO 14179 + state laws · Gen-AI Services Mgmt Measures
  - Full force — August 2025 · No federal statute · Watermark rules effective 2025-09-01
  - Max penalty — €35M or 7 % turnover · Varies by state · Administrative + license revocation
  - Frontier focus — General-purpose AI w/ systemic risk · Innovation-first reframing · Domestic data + party-aligned standards
- **Closing line**: `Convergence on principle, divergence on implementation.`

### Part 7: Timeline

#### Slide 09 - 2025-2026 Timeline

- **Layout**: Full-width horizontal timeline + page title above + six milestone annotation columns below
- **Title**: `2025 – 2026 — SIX MILESTONES`
- **Visualization**: timeline (see VII)
- **Milestones**:
  - 2025-01 · US EO 14179 signed — Federal posture reversed
  - 2025-08 · EU AI Act takes full effect — First binding horizontal AI statute in a major economy
  - 2025-09 · China synthetic-content rules effective — First state-mandated watermark regime at frontier scale
  - 2025-Q4 · DeepSeek-R1 released — Open-weights reasoning at frontier-adjacent capability
  - 2026-Q1 · Anthropic overtakes OpenAI on LLM revenue — First non-OpenAI lab at #1
  - 2026-04 · Stanford HAI AI Index 2026 published — First year SWE-bench Verified saturated

### Part 8: Closing

#### Slide 10 - What Changed, What Didn't

- **Layout**: Two-column text-only (breathing) — left column: "CHANGED" in red as the section header + 4 lines; right column: "DID NOT CHANGE" in black as the section header + 4 lines; imprint footer at the bottom
- **Title**: `WHAT CHANGED · WHAT DIDN'T`
- **Visualization**: none
- **Changed (left column, red header)**:
  - Revenue leader no longer the user-count leader.
  - Frontier training cost crossed the half-billion line per run.
  - Inference power-per-query became a 4.6× discriminator inside the frontier class.
  - Benchmark half-life dropped from years to months.
- **Did not change (right column, black header)**:
  - Frontier cohort still ~5 labs. No Tier-1 added or removed since 2024.
  - China frontier labs still have $0 of EU-market revenue.
  - Open-weights distribution still does not translate to direct revenue capture.
  - Power and grid interconnect remain the single hardest input to source.
- **Imprint footer**: `THE AI INDUSTRY 2026 · Annual Report · Volume 1, Edition 1 · Compiled May 2026 · PPT Master ☐ AI Newspaper Demo`

---

## X. Speaker Notes Requirements

- **File naming**: match SVG names (e.g., `01_cover.svg` → `notes/01_cover.md`)
- **Total presentation duration**: ~12-15 minutes
- **Notes style**: formal, reportorial — match Brutalist newspaper tone
- **Purpose**: inform (annual-report-style industry briefing)

---

## XI. Technical Constraints Reminder

### SVG Generation Must Follow

1. viewBox: `0 0 1280 720`
2. Background uses `<rect>` (`#FFFFFF` paper white)
3. Text wrapping uses `<tspan>` (`<foreignObject>` FORBIDDEN)
4. Transparency defaults to `fill-opacity` / `stroke-opacity`; `rgba()` remains converter-compatible
5. FORBIDDEN: `mask`, `<style>`, `class`, `foreignObject`, `textPath`, `animate*`, `script`
6. Text chars: raw Unicode for typographic marks (em dash `—`, en dash `–`, `→`, NBSP, `©`); HTML named entities FORBIDDEN
7. `marker-start` / `marker-end` conditionally allowed (triangle / diamond / circle in `<defs>` with `orient="auto"`)
8. `clipPath` only on `<image>` (used here on hero / sidebar / banner photos)

### PPT Compatibility Rules

- Prefer opacity per child; `<g opacity="...">` remains converter-compatible with an approximate-fidelity warning
- Image transparency via overlay `<rect fill="bg" opacity="0.x"/>`
- Inline styles only; external CSS / `@font-face` FORBIDDEN
- Stick to PPT-safe fonts in `typography` stacks; converter writes first Latin + first CJK only
