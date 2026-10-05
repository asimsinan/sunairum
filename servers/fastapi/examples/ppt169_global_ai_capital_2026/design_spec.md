# global_ai_capital_2026 - Design Spec

## I. Project Information

| Item | Value |
| ---- | ----- |
| **Project Name** | global_ai_capital_2026 |
| **Canvas Format** | PPT 16:9 (1280×720) |
| **Page Count** | 18 |
| **Design Style** | B) General Consulting + Bloomberg/Economist news infographic style |
| **Target Audience** | Technology/finance industry researchers, AI practitioners, venture capital professionals, and media editors |
| **Use Case** | Industry insights / investment briefings / media analysis columns |
| **Created Date** | 2026-05-16 |

---

## II. Canvas Specification

| Property | Value |
| -------- | ----- |
| **Format** | PPT 16:9 |
| **Dimensions** | 1280×720 |
| **viewBox** | `0 0 1280 720` |
| **Margins** | 60px left/right / 50px top/bottom |
| **Content Area** | 1160×620 (header 80 + body 560 + footer 30) |

---

## III. Visual Theme

### Theme Style

- **Style**: B) General Consulting + Bloomberg/Economist news-infographic style
- **Theme**: Dark theme
- **Tone**: Calm, restrained, publication-grade, data-driven; not the impact of a keynote, but the contemplative feeling of reading a long-form financial article at night

### Color Scheme

| Role | HEX | Purpose |
| ---- | --- | ------- |
| **Background** | `#0E1116` | Deep graphite black, not pure black |
| **Secondary bg** | `#1A1F26` | Card / section background |
| **Primary** | `#E8E6E1` | Newspaper warm white — main text and titles |
| **Accent** | `#E63946` | Financial red — risks, warnings, key figures |
| **Secondary accent** | `#F4A261` | Amber gold — secondary emphasis (China / tier-two companies) |
| **Body** | `#C9C5BE` | Warm gray-white — body text |
| **Secondary text** | `#8A857E` | Annotations / footers |
| **Tertiary text** | `#5C5852` | Very light information / source lines |
| **Border** | `#2A2F36` | Hairline dividers |
| **Success** | `#52B788` | Positive trend (green up) |
| **Warning** | `#E63946` | Reuses accent |

### AI Image Strategy

- **Image Rendering**: editorial
- **Image Palette**: dark-cinematic

### Gradient Scheme

```xml
<linearGradient id="scrim_v" x1="0%" y1="0%" x2="0%" y2="100%">
  <stop offset="0%" stop-color="#0E1116" stop-opacity="0.3"/>
  <stop offset="100%" stop-color="#0E1116" stop-opacity="0.92"/>
</linearGradient>

<linearGradient id="accentLine" x1="0%" y1="0%" x2="100%" y2="0%">
  <stop offset="0%" stop-color="#E63946" stop-opacity="1"/>
  <stop offset="100%" stop-color="#E63946" stop-opacity="0"/>
</linearGradient>
```

---

## IV. Typography System

**Typography direction**: Newspaper editorial — Western serif Cambria handles headlines and large hero numbers, Chinese uses Microsoft YaHei, and Latin body text uses Arial for numerical precision

| Role | Chinese | English | Fallback tail |
| ---- | ------- | ------- | ------------- |
| **Title** | `"Microsoft YaHei"` | `Cambria` | `serif` |
| **Body** | `"Microsoft YaHei", "PingFang SC"` | `Arial` | `sans-serif` |
| **Emphasis** | `"Microsoft YaHei"` | `Georgia` | `serif` |
| **Code** | — | `Consolas, "Courier New"` | `monospace` |

**Per-role font stacks**:

- Title: `Cambria, "Microsoft YaHei", serif`
- Body: `"Microsoft YaHei", "PingFang SC", Arial, sans-serif`
- Emphasis: `Georgia, "Microsoft YaHei", serif`
- Code: `Consolas, "Courier New", monospace`

### Font Size Hierarchy

**Baseline**: Body font size = **16px** (chart-heavy, high density)

| Purpose | Ratio to body | Px @ 16 | Weight |
| ------- | ------------- | ------- | ------ |
| Cover title (hero headline) | 4-5x | 64-80px | Bold |
| Chapter / section opener | 2.5-3x | 40-48px | Bold |
| Page title | 1.5-2x | 24-32px | Bold |
| Hero number (large number) | 4-6x | 64-96px | Bold (Cambria) |
| Subtitle | 1.2-1.5x | 19-24px | SemiBold |
| **Body content** | **1x** | **16px** | Regular |
| Annotation / caption | 0.7-0.85x | 11-14px | Regular |
| Page number / footnote | 0.6-0.7x | 10-11px | Regular |

---

## V. Layout Principles

### Page Structure

- **Header area**: Top 50px — chapter number + chapter name (left-aligned, 11px tertiary) + ultra-thin divider
- **Content area**: Middle 560px — primary visualization / hero number / chart
- **Footer area**: Bottom 30px — page number + Sources footnote + ultra-thin top divider

### Layout Pattern Library

> Dominant layouts in this deck: **Asymmetric split (3:7 chart vs. annotation) / Single column centered (cover / section openers) / Three-column (KPI cards) / Top-bottom split (chart with hero band + footnote) / Full-bleed + floating text (3 atmospheric section pages)**. Z-pattern and Matrix grid appear on the quadrant_text_bullets page.

### Spacing Specification

**Universal**:

| Element | Range | This Deck |
| ------- | ----- | --------- |
| Safe margin | 40-60px | 60px |
| Content block gap | 24-40px | 28px |
| Icon-text gap | 8-16px | 10px |

**Card-based**:

| Element | Range | This Deck |
| ------- | ----- | --------- |
| Card gap | 20-32px | 24px |
| Card padding | 20-32px | 22px |
| Card border radius | 8-16px | 6px (restrained, not overly rounded) |

**Non-card** (breathing pages / atmospheric background images):
- Line-height: 1.5× body
- Use a `scrim_v` gradient behind full-bleed text for legibility
- Do not force column alignment; use flexible insets like newspaper standfirsts

---

## VI. Icon Usage Specification

### Source

- **Library**: `tabler-outline` (stroke 1.5)
- **Brand-logo library**: `simple-icons` (for logo marks including OpenAI / Anthropic / xAI / Nvidia / Google / Microsoft / Amazon / Meta / Oracle / SoftBank)
- **Usage**: `<use data-icon="library/icon-name" .../>`

### Recommended Icon List

| Purpose | Icon Path | Page |
| ------- | --------- | ---- |
| Trending up (capital inflow) | `tabler-outline/trending-up` | P04, P05, P11 |
| Currency dollar (valuation) | `tabler-outline/currency-dollar` | P04, P06, P09 |
| Building (company) | `tabler-outline/building` | P06, P09 |
| Chart bar (data) | `tabler-outline/chart-bar` | P05, P15 |
| Server (infrastructure) | `tabler-outline/server` | P14, P15 |
| Bolt (electricity) | `tabler-outline/bolt` | P05, P14 |
| Alert triangle (risk) | `tabler-outline/alert-triangle` | P15, P16, P17 |
| Globe (global) | `tabler-outline/globe` | P04, P09 |
| Cpu (chip) | `tabler-outline/cpu` | P12, P13 |
| Trending down (decay) | `tabler-outline/trending-down` | P15, P16 |
| Arrow right (flow direction) | `tabler-outline/arrow-right` | P12, P14 |
| Bookmark (chapter marker) | `tabler-outline/bookmark` | Chapter pages |
| OpenAI brand | `simple-icons/openai` | P06, P08, P14 |
| Anthropic | `simple-icons/anthropic` | P06 |
| Nvidia | `simple-icons/nvidia` | P12, P13 |
| Google | `simple-icons/google` | P05, P06 |
| Microsoft | `simple-icons/microsoft` | P05 |
| Amazon | `simple-icons/amazon` | P05 |
| Meta | `simple-icons/meta` | P05 |
| Oracle | `simple-icons/oracle` | P14 |
| SoftBank | `simple-icons/softbank` | P14 |

---

## VII. Visualization Reference List

Catalog read: 71 templates

| Page | Template | Path | Summary-quote (verbatim) | Usage |
| ---- | -------- | ---- | ------------------------ | ----- |
| P04 | kpi_cards | `templates/charts/kpi_cards.svg` | "Pick for 4-8 standalone numeric metrics shown as overview cards (2x2 or 1x4) — exec summary opener, " | Four Q1 venture capital KPIs (total VC / AI share / three major deals / concentration) |
| P05 | bar_chart | `templates/charts/bar_chart.svg` | "Pick for single-series category value comparison, 3-8 categories. Skip for >12 long-label items (use" | Capex comparison across Amazon / Microsoft / Google / Meta |
| P07 | dumbbell_chart | `templates/charts/dumbbell_chart.svg` | "Pick for before-vs-after or two-state difference across 5-10 items. Skip for single snapshot (use ba" | OpenAI/Anthropic/xAI valuation comparison (start of year vs Q2) |
| P08 | bubble_chart | `templates/charts/bubble_chart.svg` | "Pick for 3-axis data (x position, y position, size). Skip for plain x-y correlation (use scatter_cha" | Valuation × ARR × number of investors for the three giants |
| P09 | donut_chart | `templates/charts/donut_chart.svg` | "Pick for 3-6 part proportions where a center KPI/total deserves emphasis. Skip if no center value to" | OpenAI's $122B investor composition (Amazon/Nvidia/SoftBank/MSFT/other) |
| P10 | horizontal_bar_chart | `templates/charts/horizontal_bar_chart.svg` | "Pick for ranking 5-12 items, especially with long labels. Skip if <=8 short-label items (use bar_cha" | Valuation ranking of 5 Chinese companies (DeepSeek/Zhipu/MiniMax/Moonshot/StepFun) |
| P11 | comparison_table | `templates/charts/comparison_table.svg` | "Pick for 2-4 plans/products compared across many feature rows (dense matrix). Skip for pricing-tier " | Two-track comparison of Chinese and U.S. AI capital paths (private funding / IPO / government / peak valuation / exit method) |
| P12 | sankey_chart | `templates/charts/sankey_chart.svg` | "Pick for 3-stage flow with magnitude (sources -> nodes -> sinks). Skip for simple linear conversion " | Nvidia loop: equity investment → AI companies → recycled chip purchases |
| P13 | pareto_chart | `templates/charts/pareto_chart.svg` | "Pick for 80/20 contribution: descending bars + cumulative line. Skip if cumulative line is not t" | 85% of Nvidia's customers come from 6 companies |
| P14 | hub_spoke | `templates/charts/hub_spoke.svg` | "Pick for 1 core capability + 4-8 surrounding capabilities (platform/ecosystem); each spoke = title o" | Stargate project hub + 7 data center sites |
| P16 | dual_axis_line_chart | `templates/charts/dual_axis_line_chart.svg` | "Pick when 2 metrics with different units/scales must be compared over time. Skip if both metrics sha" | 2020-2026 Capex (left axis $B) vs Enterprise AI Revenue (right axis $B) scissors gap |
| P17 | quadrant_text_bullets | `templates/charts/quadrant_text_bullets.svg` | "Pick for any 2×2 framework where each quadrant holds a titled bullet list — SWOT (Strengths/Weakness" | Four risk quadrants: capital gap / enterprise ROI / customer concentration / financing structure |

**Runners-up considered**:

- `donut_chart` | rejected for P04: KPI cards are better for displaying four independent metrics side by side; a donut emphasizes proportional segmentation rather than standalone readings
- `stacked_bar_chart` | rejected for P05: A single metric (capex amount) is being compared, with no internal grouping structure
- `grouped_bar_chart` | rejected for P07: A dumbbell better supports a “difference between two states” narrative; grouped bars are better for multi-category YoY comparisons
- `treemap_chart` | rejected for P09: OpenAI has only 5–6 independent investors/shares; a donut can show the total of $122B in the center, while a treemap emphasizes hierarchy
- `radar_chart` | rejected for P10: Five companies are being ranked on a single metric (valuation); radar charts are better for multidimensional capabilities
- `hub_inward_arrows` | rejected for P12: Only a sankey can express “monetary flows”; hub_inward shows direction without magnitude
- `bar_chart` | rejected for P13: A pareto chart shows both individual contribution and cumulative share, while a bar chart shows only the former
- `process_flow` | rejected for P14: `hub_spoke` expresses the Stargate topology of “one central hub + multiple peripheral sites”; `process_flow` implies linearity

---

## VIII. Image Resource List

| Filename | Dimensions | Ratio | Purpose | Layout pattern | Acquire Via | Status | Reference | text_policy | page_role |
| -------- | --------- | ----- | ------- | -------------- | ----------- | ------ | --------- | ----------- | --------- |
| cover_atmosphere.png | 1280×720 | 1.78 | Cover atmosphere background | #1 full-bleed background with floating title + #29 two-stop scrim | ai | Pending | Abstract nighttime aerial of a vast data-center campus, faint server-rack lights forming a constellation pattern; quiet wide-angle composition with reserved dark sky for title overlay; sense of capital flowing through silent infrastructure | none | hero_page |
| nvidia_circular.png | 1280×720 | 1.78 | Part V Nvidia closed-loop chapter anchor | Background | #1 full-bleed background with floating title + #29 two-stop scrim | ai | Pending | Abstract macro shot of a circular wafer-like geometry with subtle red glow at the rim suggesting circulation; central dark void reserved for chapter title; metallic finish but no recognizable logos | none | hero_page |
| bubble_tension.png | 1280×720 | 1.78 | Part VI bubble theory chapter anchor | Background | #1 full-bleed background with floating title + #29 two-stop scrim | ai | Pending | Abstract atmospheric image of a single iridescent soap bubble suspended in deep dark space, surface tension catching a faint warning-red highlight; quiet composition with negative space; sense of fragile inflation | none | hero_page |

---

## IX. Content Outline

### Part 0: Opening (Cover + Introduction + Table of Contents)

#### Slide 01 - Cover

- **Layout**: Full-bleed atmospheric background + bottom scrim + oversized title at bottom left
- **Title**: The Global AI Capital Landscape, 2026
- **Subtitle**: Capital, Compute, and the Closed Loop
- **Info**: May 2026 · Industry Insights · Data as of 2026-05-15

#### Slide 02 - Editor's Introduction

- **Layout**: Single centered column + oversized quotation marks + three-line core narrative
- **Title**: Editorial Introduction | Editor's Note
- **Content**:
  - $297 billion in VC in a single quarter; AI took 81%
  - Four deals totaling $188 billion; 65% flowed to four companies
  - The gap between capital and commercial ROI has surpassed that of the 2001 telecom bubble

#### Slide 03 - Contents

- **Layout**: Roman-numeral sections on the left + page numbers and one-line titles for each section on the right
- **Title**: Contents | Contents
- **Content**:
  - I. Panorama — P04-P05
  - II. The Big Three — P06-P09
  - III. China’s Camp — P10-P11
  - IV. The Second Tier — P12
  - V. Infrastructure & the Closed Loop — P13-P15
  - VI. Bubble & Judgment — P16-P18

### Part I: Panorama

#### Slide 04 - Q1 Venture Capital Landscape

- **Layout**: Four-quadrant KPI cards + small chapter marker at top
- **Title**: Global Venture Capital, Q1 2026: A Record $297B, with AI Taking 81%
- **Visualization**: `kpi_cards`
- **Content**:
  - $297B — Total VC for the quarter (Crunchbase)
  - 81% — AI share (approximately $242B)
  - $188B — Combined value of the top 4 deals (OpenAI + Anthropic + xAI + Waymo)
  - 65% — Concentration (top 4 deals as a share of quarterly VC)

#### Slide 05 - Hyperscaler Capex

- **Layout**: Bar chart left 7, right 3 + three key annotations on the right
- **Title**: Four Hyperscalers' 2026 Capex: $725B, Up 77% YoY
- **Visualization**: bar_chart
- **Content**:
  - Amazon $200B / Microsoft $190B / Alphabet $190B / Meta $145B+
  - 60%+ flows to power / cooling / civil works, not chips
  - Resource constraints have shifted from "compute" to "power"

### Part II: The Big Three

#### Slide 06 - Before-and-After Valuation Comparison

- **Layout**: Dumbbell chart + chapter marker at the top
- **Title**: The Big Three's 2026 Valuation Leap: Doubling from the Start of the Year to Q2
- **Visualization**: dumbbell_chart
- **Content**:
  - OpenAI: $300B → $852B (Mar 2026)
  - Anthropic: $61.5B → $380B (Series G) → $900B (in talks)
  - xAI: $50B → $230B (Jan 2026) → $1.25T merger with SpaceX

#### Slide 07 - Valuation × Revenue × Investors

- **Layout**: Full-screen bubble chart + data sources in the corner
- **Title**: Valuation Realisation: The Higher the Revenue, the More Grounded the Valuation
- **Visualization**: bubble_chart
- **Content**:
  - X-axis: ARR ($B), Y-axis: valuation ($B), bubble size: number of investors
  - OpenAI: ARR $24B / Val $852B / 7 major investors
  - Anthropic: ARR $30B+ / Val $380B (in talks at $900B) / 5 major investors
  - xAI: ARR $5B (est) / Val $230B / 8+ investors

#### Slide 08 - OpenAI Investor Structure

- **Layout**: Donut chart on the left + investor list on the right
- **Title**: Where OpenAI's $122B Comes From
- **Visualization**: donut_chart
- **Content**:
  - Amazon $50B (41%)
  - Nvidia $30B (25%)
  - SoftBank $30B (25%)
  - Microsoft + others $12B (10%)
  - Centre: $122B / $852B valuation

#### Slide 09 - Comprehensive Comparison of the Big Three

- **Layout**: Three-column comparison + small top label + one-line summary at bottom
- **Title**: OpenAI vs Anthropic vs xAI: Three growth curves
- **Content**:
  - OpenAI: Consumer-driven + strong IPO expectations
  - Anthropic: Enterprise-driven + valuation surpassing OpenAI ($900B vs $852B)
  - xAI: Merger narrative + SpaceX synergies

### Part III: Chinese Players

#### Slide 10 - China's Five Powerhouses

- **Layout**: Horizontal bar chart + one-line summary at top
- **Title**: China's Big Five in AI: DeepSeek Leads, with a Clear Valuation Ladder
- **Visualization**: horizontal_bar_chart
- **Content**:
  - DeepSeek $50B（led by the national major fund）
  - Zhipu AI（Hong Kong-listed market cap）$56B
  - MiniMax（Hong Kong-listed market cap）$37B
  - Moonshot (Kimi) $20B
  - StepFun ~$8B

#### Slide 11 - China–US Dual Track

- **Layout**: Comparison table (5 rows × 2 columns) + small label at the top
- **Title**: China–US AI Capital: Two Paths, Two Rhythms
- **Visualization**: comparison_table
- **Content**:
  - Private funding scale: US $30–122B per round vs China $2–4B per round
  - IPO pace: US delayed vs China already landed in Q1
  - Government role: US market-driven vs China led by state-backed mega-funds
  - Valuation peak: US $852B vs China $56B (market cap)
  - Exit strategy: private IPOs deferred vs secondary markets prioritised

### Part IV: The Second Tier

#### Slide 12 - Second-Tier $10-50B Cohort

- **Layout**: Four-column cards (each: company logo + valuation hero number + one-line highlight) + small label at top
- **Title**: The Second Tier: The $10–50B Elite
- **Content**:
  - SSI $32B (Sutskever, 6× jump)
  - Perplexity $21B (45 million MAU)
  - Mistral $13.7B (13,800 GPUs at its Paris data center)
  - Cohere + Aleph Alpha merger at $20B (transatlantic sovereign AI)

### Part V: Infrastructure and Closed Loop

#### Slide 13 - Nvidia Closed Loop (Chapter Anchor Slide)

- **Layout**: Full-bleed atmospheric background（nvidia_circular.png）+ oversized chapter marker + bottom scrim + three introductory statements
- **Title**: V. The Closed Loop
- **Subtitle**: When the chipmaker is also a major shareholder
- **Content**:
  - Nvidia has made $40B+ in equity investments since the start of 2026
  - OpenAI $30B + xAI + Anthropic + Mistral—all fully funded
  - 85% of revenue comes from six customers

#### Slide 14 - Nvidia Capital Flow Chart

- **Layout**: Full-width Sankey chart + section label at top + source at bottom
- **Title**: How the money flows: Nvidia’s circular investment
- **Visualization**: sankey_chart
- **Content**:
  - Left: Nvidia’s $40B investment
  - Center: OpenAI / xAI / Anthropic / Mistral / CoreWeave
  - Right: Nvidia chip sales flowing back in (tens of billions of dollars in computing commitments)

#### Slide 15 - NVIDIA Customer Concentration

- **Layout**: Pareto chart + bottom-right risk annotation
- **Title**: Concentration risk: 85% of Nvidia’s revenue comes from 6 customers
- **Visualization**: pareto_chart
- **Content**:
  - Top 4 customers account for nearly 60% (MSFT / Meta / Google / Amazon)
  - 6 customers account for 85% cumulatively
  - Any one customer cutting capex would trigger a cascading shock across the entire chain

#### Slide 16 - Stargate

- **Layout**: Hub-spoke chart（Stargate logo at center + seven radiating sites）+ chapter marker at top
- **Title**: Stargate: $500B / 10GW / 7 Sites
- **Visualization**: hub_spoke
- **Content**:
  - Center: Stargate（OpenAI + Oracle + SoftBank）
  - Seven sites: Abilene TX（operational）/ Shackelford TX / Doña Ana NM / Midwest / Lordstown OH / Milam TX / Saline MI
  - Nearly 7GW planned, with $400B to be invested over the next three years

### Part VI: Bubbles and Judgment

#### Slide 17 - Bubble Thesis Chapter Anchor

- **Layout**: Full-bleed atmospheric background（bubble_tension.png）+ oversized chapter title + bottom scrim + three core arguments
- **Title**: VI. The Bubble
- **Subtitle**: The widening gap between capitalism and commercial reality
- **Content**:
  - Capex growth is 46 percentage points faster than AI revenue growth
  - The gap was 32% during the 2001 telecom bubble
  - **The current gap has surpassed the 2001 telecom bubble**

#### Slide 18 - Capex vs. Revenue Scissors Gap

- **Layout**: Dual-axis line chart + chapter label at the top + source at the bottom
- **Title**: The Capital–Revenue Gap: $400B Invested vs $100B in Revenue
- **Visualization**: dual_axis_line_chart
- **Content**:
  - Left axis: Hyperscaler Capex ($B), 2020–2026
  - Right axis: Enterprise AI Revenue ($B), 2020–2026
  - Shading: ROI Gap between the two lines

#### Slide 19 - Four Major Risks

- **Layout**: 2×2 quadrant + title for each quadrant + 2-3 lines of bullets
- **Title**: Four Risks, Amplifying One Another
- **Visualization**: quadrant_text_bullets
- **Content**:
  - Top left Capex/Revenue gap: gap exceeds that of the 2001 telecom bubble
  - Top right Corporate ROI: 95% of MIT pilots generated no business value
  - Bottom left Customer concentration: 85% of Nvidia’s revenue comes from 6 customers
  - Bottom right Financing structure: operating cash flow → debt financing

#### Slide 20 - Six Key Judgments and Closing

- **Layout**: Single-column numbered list of 6 lines + Sources acknowledgment at the bottom
- **Title**: Six Key Judgments | Closing
- **Content**:
  - ① Capital concentration is the defining theme of 2026
  - ② Compute is the real hard currency
  - ③ Power > Chips
  - ④ A dual-track US–China structure
  - ⑤ Real ROI lags, but the giants have not stopped bleeding
  - ⑥ Anthropic's valuation surpasses OpenAI's

> Note: Actual page count = 20 (1 cover + 1 introduction + 1 contents page + 16 content pages + 1 conclusion). The Strategist reported 18 pages in the eight-point confirmation; this was refined to 20 pages after editorial introduction adjustments to maintain a one-argument-per-page density.

---

## X. Speaker Notes Requirements

- File naming matches the SVG (`01_cover.svg` → `notes/01_cover.md`)
- 100–150 Chinese characters per page, in an editorial-introduction voice—not sales-oriented or instructional
- Target total deck duration: 15–20 minutes

---

## XI. Technical Constraints Reminder

### SVG Generation Must Follow:

1. viewBox: `0 0 1280 720`
2. Background uses `<rect>`
3. Text wrapping uses `<tspan>`
4. Use `fill-opacity` / `stroke-opacity` for transparency
5. FORBIDDEN: `mask`, `<style>`, `class`, `foreignObject`, `textPath`, `animate*`, `script`, custom `<symbol>` + `<use>`
   - Transparency defaults to explicit alpha attributes; `rgba()` and `<g opacity>` remain converter-compatible, with group opacity carrying an approximate-fidelity warning.
6. HTML named entities are forbidden; write raw Unicode
7. `marker-start` / `marker-end` may only use `<marker>` in `<defs>` with `orient="auto"`
8. `clipPath` applies only to `<image>`, with a single shape child

### PPT Compatibility:

- Inline styles only
- Set opacity individually for each element
- End each font stack with a preinstalled font
