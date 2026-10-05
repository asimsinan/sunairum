# glassmorphism_demo - Design Spec

> Human-readable design narrative — rationale, audience, style, color choices, content outline. Read once by downstream roles for context.
>
> Machine-readable execution contract: `spec_lock.md`. Executor re-reads `spec_lock.md` before every SVG page.

## I. Project Information

| Item | Value |
| ---- | ----- |
| **Project Name** | glassmorphism_demo |
| **Canvas Format** | PPT 16:9 (1280×720) |
| **Page Count** | 12 |
| **Design Style** | B) General Consulting + Glassmorphism SaaS |
| **Target Audience** | AI product managers / engineering leads / technical decision-makers |
| **Use Case** | Technical sharing / internal training / product launch |
| **Created Date** | 2026-05-17 |

---

## II. Canvas Specification

| Property | Value |
| -------- | ----- |
| **Format** | PPT 16:9 |
| **Dimensions** | 1280×720 |
| **viewBox** | `0 0 1280 720` |
| **Margins** | 60px left/right / 50px top/bottom |
| **Content Area** | 1160×620 (excluding margins) |

---

## III. Visual Theme

### Theme Style

- **Style**: B) General Consulting + Glassmorphism SaaS
- **Theme**: Dark theme (dark glass + flowing luminous neon)
- **Tone**: Futuristic, technological, light and floating, professional

### Color Scheme

| Role | HEX | Purpose |
| ---- | --- | ------- |
| **Background** | `#0A0E27` | Deep space-blue background |
| **Secondary bg** | `#1A2150` | Base for transparent glass-panel overlays (actual fill-opacity 0.4-0.6) |
| **Primary** | `#5B8DEF` | Luminous blue — title decoration / main icons / primary charts |
| **Accent** | `#A26BFA` | Luminous purple — key data / gradient endpoint |
| **Secondary accent** | `#3DDDFC` | Neon cyan — highlights and glowing connector lines |
| **Body text** | `#E8ECFF` | Pale blue-white body text |
| **Secondary text** | `#A8B0D0` | Soft gray-blue annotations |
| **Tertiary text** | `#6B7299` | Footers and supporting information |
| **Border/divider** | `#2E3672` | Glass outline (actual stroke-opacity 0.4-0.6) |
| **Success** | `#4ADE80` | Mint green |
| **Warning** | `#FB7185` | Neon pink-red |

> 60-30-10: 60% deep-space background / 30% glass + text / 10% neon accents.

### AI Image Strategy

- **Image Rendering**: glassmorphism
- **Image Palette**: tech-neon

### Gradient Scheme

```xml
<!-- Main title gradient (blue → purple → cyan) -->
<linearGradient id="titleGradient" x1="0%" y1="0%" x2="100%" y2="0%">
  <stop offset="0%" stop-color="#5B8DEF"/>
  <stop offset="50%" stop-color="#A26BFA"/>
  <stop offset="100%" stop-color="#3DDDFC"/>
</linearGradient>

<!-- Glass panel gradient -->
<linearGradient id="glassPanel" x1="0%" y1="0%" x2="100%" y2="100%">
  <stop offset="0%" stop-color="#5B8DEF" stop-opacity="0.18"/>
  <stop offset="100%" stop-color="#A26BFA" stop-opacity="0.08"/>
</linearGradient>

<!-- Background flowing glow radial -->
<radialGradient id="bgGlow" cx="80%" cy="20%" r="60%">
  <stop offset="0%" stop-color="#5B8DEF" stop-opacity="0.25"/>
  <stop offset="100%" stop-color="#5B8DEF" stop-opacity="0"/>
</radialGradient>

<radialGradient id="bgGlow2" cx="20%" cy="80%" r="55%">
  <stop offset="0%" stop-color="#A26BFA" stop-opacity="0.2"/>
  <stop offset="100%" stop-color="#A26BFA" stop-opacity="0"/>
</radialGradient>

<!-- Glass panel highlight line -->
<linearGradient id="glassEdge" x1="0%" y1="0%" x2="100%" y2="0%">
  <stop offset="0%" stop-color="#FFFFFF" stop-opacity="0"/>
  <stop offset="50%" stop-color="#FFFFFF" stop-opacity="0.35"/>
  <stop offset="100%" stop-color="#FFFFFF" stop-opacity="0"/>
</linearGradient>
```

---

## IV. Typography System

**Typography direction**: modern CJK sans, same family weight contrast (heavy title / regular body)

| Role | Chinese | English | Fallback tail |
| ---- | ------- | ------- | ------------- |
| **Title** | `"Microsoft YaHei", "PingFang SC"` | — | `sans-serif` |
| **Body** | `"Microsoft YaHei", "PingFang SC"` | `Arial` | `sans-serif` |
| **Emphasis** | `"Microsoft YaHei", "PingFang SC"` | — | `sans-serif` |
| **Code** | — | `Consolas, "Courier New"` | `monospace` |

**Per-role font stacks**:

- Title: `"Microsoft YaHei", "PingFang SC", sans-serif`（font-weight: 900）
- Body: `"Microsoft YaHei", "PingFang SC", Arial, sans-serif`（font-weight: 400）
- Emphasis: same as Body（font-weight: 600）
- Code: `Consolas, "Courier New", monospace`

### Font Size Hierarchy

**Baseline**: Body font size = **20px** (moderate-density SaaS deck)

| Purpose | Ratio to body | Example @ body=20 | Weight |
| ------- | ------------- | ------------------ | ------ |
| Cover title (hero headline) | 2.5-5x | 60-100px | 900 |
| Chapter / section opener | 2-2.5x | 40-50px | 900 |
| Page title | 1.5-2x | 30-40px | 900 |
| Hero number (KPI) | 1.5-2x | 30-40px | 900 |
| Subtitle | 1.2-1.5x | 24-30px | 600 |
| **Body content** | **1x** | **20px** | 400 |
| Annotation / caption | 0.7-0.85x | 14-17px | 400 |
| Page number / footnote | 0.5-0.65x | 10-13px | 400 |

---

## V. Layout Principles

### Page Structure

- **Header area**: 60px top margin + page title 50px = approximately 110px at the top
- **Content area**: approximately 500px in the middle (including glass panels / chart / visuals)
- **Footer area**: 40px at the bottom (page number + project identifier)

### Layout Pattern Library

| Pattern | Suitable Scenarios |
| ------- | ----------------- |
| **Single column centered** | Cover, closing (P01/P12) |
| **Symmetric split (5:5)** | Pattern comparison (P05) |
| **Three/four column cards** | Three-part current dilemma / KPI dashboard (P03/P08) |
| **Matrix grid (2×2)** | Failure modes (P10) |
| **Top-bottom split** | Hero transition (P02) |
| **Center-radiating** | Context engineering hub_spoke (P07) |
| **Layered horizontal** | Agent architecture layered (P04) |
| **Z-pattern / waterfall** | Tool orchestration numbered_steps (P06) |
| **Negative-space-driven** | Breathing page (P02/P12) |
| **Image-as-canvas + native overlay** | All pages with AI-generated images (P01/P02/P04/P06/P07/P08/P10/P12) |

### Spacing Specification

**Universal**：

| Element | Value |
| ------- | ----- |
| Safe margin from canvas edge | 50-60px |
| Content block gap | 28px |
| Icon-text gap | 12px |

**Card-based (glass panels)**：

| Element | Value |
| ------- | ----- |
| Card gap | 24px |
| Card padding | 24-28px |
| Card border radius | 16px |
| Card stroke | `#FFFFFF` stroke-width 1, stroke-opacity 0.18 |
| Card fill | `url(#glassPanel)` or `#1A2150` with fill-opacity 0.5 |

**Non-card / breathing**：

- Line-height 1.5x body
- Full-bleed text inset 80px+; use a two-stop scrim with #29 to ensure legibility

---

## VI. Icon Usage Specification

### Source

- **Library**: `phosphor-duotone` (its two-layer backplate resonates with the layered language of glassmorphism)
- **Usage**: `<use data-icon="phosphor-duotone/<name>" .../>`

### Recommended Icon List

| Purpose | Icon Path | Page |
| ------- | --------- | ---- |
| Performance/latency pain point | `phosphor-duotone/gauge` | P03, P08 |
| Cost pain point | `phosphor-duotone/coin` | P03, P08, P10 |
| Quality/error pain point | `phosphor-duotone/bug` | P03, P10 |
| Perception layer | `phosphor-duotone/eye` | P04 |
| Inference layer | `phosphor-duotone/brain` | P04 |
| Action layer | `phosphor-duotone/lightning` | P04 |
| Memory layer | `phosphor-duotone/database` | P04, P07 |
| Workflow mode | `phosphor-duotone/flow-arrow` | P05 |
| Agent mode | `phosphor-duotone/robot` | P05 |
| Multi-Agent mode | `phosphor-duotone/users-three` | P05 |
| Parsing task | `phosphor-duotone/magnifying-glass` | P06, P07 |
| Tool selection | `phosphor-duotone/target` | P06 |
| Invocation | `phosphor-duotone/plug` | P06 |
| Verification | `phosphor-duotone/check-circle` | P06, P08 |
| Retry/loop | `phosphor-duotone/arrows-clockwise` | P06, P10 |
| Aggregation | `phosphor-duotone/stack` | P06 |
| Context core | `phosphor-duotone/cube` | P07 |
| Reranking/filtering | `phosphor-duotone/funnel` | P07 |
| Truncation/balancing | `phosphor-duotone/scales` | P07 |
| Tool description | `phosphor-duotone/gear` | P07 |
| System prompt | `phosphor-duotone/code-block` | P07 |
| Reliability | `phosphor-duotone/shield-check` | P08 |
| Hallucination | `phosphor-duotone/sparkle` | P10 |
| Prototype stage | `phosphor-duotone/crosshair` | P11 |
| Engineering phase | `phosphor-duotone/gear-six` | P11 |
| Scaling phase | `phosphor-duotone/chart-line-up` | P11 |
| Production phase | `phosphor-duotone/rocket` | P11, P12 |
| Call for collaboration | `phosphor-duotone/handshake` | P12 |

---

## VII. Visualization Reference List

Catalog read: 71 templates

| Page | Template | Path | Summary-quote (verbatim from `charts_index.json`) | Usage |
| ---- | -------- | ---- | ------------------------------------------------- | ----- |
| P03 | vertical_pillars | `templates/charts/vertical_pillars.svg` | "Pick for 1×3 / 1×4 / 1×5 vertical column layout where each pillar = one independent category with title + bullets — PEST (Political/Economic/Social/Technological), four-pillar strategy overview, side-by-side independent categories. Skip for 2×2 quadrant (use quadrant_text_bullets), pricing tiers (use comparison_columns), or 2×2 parallel aspects (use labeled_card)." | Three major pain points shown side by side |
| P04 | layered_architecture | `templates/charts/layered_architecture.svg` | "Pick for 3-4 horizontal architecture layers (presentation/service/data), 2-4 module cards per layer, each card = title + 1-line description (description required, even if source brief). Skip if no per-module descriptions (use icon_grid) or no horizontal layering (use module_composition)." | Four-layer Agent architecture (Perception/Reasoning/Action/Memory) |
| P05 | comparison_columns | `templates/charts/comparison_columns.svg` | "Pick for 2-4 pricing/service tier cards in side-by-side columns (marketing layout). Skip for dense feature comparison (use comparison_table)." | Three-mode comparison: Workflow vs Agent vs Multi-Agent |
| P06 | numbered_steps | `templates/charts/numbered_steps.svg` | "Pick for 3-6 horizontal sequential steps with numeric emphasis — how-it-works section, getting-started guide, methodology overview, implementation phases. Skip if steps need connector arrows (use process_flow) or named output artifacts (use pipeline_with_stages)." | Six-step tool orchestration method |
| P07 | hub_spoke | `templates/charts/hub_spoke.svg` | "Pick for 1 core capability + 4-8 surrounding capabilities (platform/ecosystem); each spoke = title or title + 1-2 line description. Skip if center is a system containing parts with their own descriptions (use module_composition), or surroundings exert inward pressure on the center (use hub_inward_arrows)." | Context engineering — 1 core + 6 capabilities |
| P08 | kpi_cards | `templates/charts/kpi_cards.svg` | "Pick for 4-8 standalone numeric metrics shown as overview cards (2x2 or 1x4) — exec summary opener, dashboard headline, quarterly recap, results-at-a-glance. Skip if metrics have target baselines (use bullet_chart) or single hero number (use gauge_chart)." | 4 KPI cards (Accuracy/Latency/Cost/Reliability) |
| P09 | line_chart | `templates/charts/line_chart.svg` | "Pick for 1-3 time-series on a continuous axis showing direction. Skip if cumulative volume matters (use area_chart) or different units (use dual_axis_line_chart)." | 12-week post-launch dual-line trend for accuracy + cost |
| P10 | quadrant_text_bullets | `templates/charts/quadrant_text_bullets.svg` | "Pick for any 2×2 framework where each quadrant holds a titled bullet list — SWOT (Strengths/Weaknesses/Opportunities/Threats, internal-external × helpful-harmful), Ansoff (Existing/New Markets × Existing/New Products), or any named two-axis matrix with text content. Skip for items plotted as points (use matrix_2x2) or bubble-sized portfolios (use quadrant_bubble_scatter)." | Four quadrants of failure modes (tool errors / infinite loops / hallucinations / runaway costs) |
| P11 | roadmap_vertical | `templates/charts/roadmap_vertical.svg` | "Pick for 4-8 milestones on a vertical timeline with status indicators. Skip for horizontal time emphasis (use timeline) or tasks with durations (use gantt_chart)." | Four-stage implementation roadmap |

**Runners-up considered** (3 entries minimum):

- `pyramid_chart` | rejected for P04: The Agent architecture requires multiple horizontal layers × multiple module cards per layer; a pyramid is a vertically layered structure with one element per level and cannot accommodate descriptions for 2–3 modules per layer
- `icon_grid` | rejected for P03: Each of the three pain points requires a title + 2–3 lines of bullet descriptions; `icon_grid` only supports a title + short subtitle, which lacks sufficient depth
- `mind_map` | rejected for P07: Context engineering has a focused structure of 1 core + 6 fixed capabilities; `hub_spoke` is more symmetrical and grounded than `mind_map` (`mind_map` tends toward brainstorming / asymmetrical fan shapes)

---

## VIII. Image Resource List

| Filename | Dimensions | Ratio | Purpose | Layout pattern | Acquire Via | Status | Reference | text_policy | page_role |
| -------- | --------- | ----- | ------- | -------------- | ----------- | ------ | --------- | ----------- | --------- |
| 01_cover_aurora.png | 1280×720 | 1.78 | Cover luminous-flow main background | #1 full-bleed background with floating title + #29 two-stop scrim + #28 radial gradient vignette | ai | Pending | Deep space backdrop, drifting frosted glass shards in soft orbit, neon blue-purple-cyan light beams streaming horizontally, calm center band reserved for title overlay, no figures or text | none | hero_page |
| 02_hero_transition.png | 1280×720 | 1.78 | "Demo → Production" transition atmosphere | #12 faded image as backdrop with oversized overlay text + #28 radial vignette + #30 flat semi-transparent overlay | ai | Pending | Wide cinematic horizon: a glowing data city rising from violet mist, distant translucent towers and floating glass platforms, sense of crossing from small workshop to large infrastructure, low-contrast central area for hero title | none | hero_page |
| 04_agent_topology.png | 1280×720 | 1.78 | Agent topology neural network background | Background | #44 background image + native network/architecture diagram + #28 radial vignette + #30 flat overlay | ai | Pending | Abstract agent topology background: glowing neural mesh with constellation nodes connected by thin luminous filaments, soft depth-of-field, frosted glass tiles floating quietly, dark deep-space field with low-contrast working zone, no labels or text | none | local |
| 06_pipeline_flow.png | 1280×720 | 1.78 | Tool-call luminous flow pipeline | Background | #39 background image + flow nodes drawn over the scene + #30 flat overlay + #21 rounded rectangle crop | ai | Pending | Translucent data pipelines flowing horizontally behind frosted glass, glowing liquid light traveling through tubes, scattered floating cubes catching reflections, low-detail center band, dark cosmic backdrop | none | local |
| 07_context_sphere.png | 1280×720 | 1.78 | Context knowledge sphere / RAG metaphor | Background | #42 background image + glassmorphism UI panels + #28 radial vignette + #30 overlay | ai | Pending | Large luminous sphere of light filaments suspended in deep space, fine threads of information radiating outward, smaller glass shards in orbit, slight chromatic aberration, calm dark surrounding for overlay panels | none | local |
| 08_dashboard_bokeh.png | 1280×720 | 1.78 | Dashboard out-of-focus bokeh | Background | #40 background image + floating KPI metric cards + #34 gaussian blur backdrop baked-in + #30 overlay | ai | Pending | Out-of-focus dashboard scene: rows of soft neon bokeh circles in blue, purple, cyan against deep-space dark, hint of translucent interface panels in the distance, no readable text or numbers | none | local |
| 10_failure_glow.png | 1280×720 | 1.78 | Failure-mode warning atmosphere | Background | #12 faded image as backdrop with oversized overlay text + #31 color-tinted overlay + #28 radial vignette | ai | Pending | Dark moody field washed with neon pink and violet, fractured glass shards scattered with subtle distortion, faint warning halos, deep-space backdrop, calm working zone in the center | none | local |
| 12_cta_horizon.png | 1280×720 | 1.78 | CTA closing distant horizon | Background | #1 full-bleed background with floating title + #66 image fading into solid background + #29 two-stop scrim | ai | Pending | Distant glowing horizon at dawn of the data era, floating glass platforms drifting toward the light, soft particulate atmosphere, deep navy field grading into warm blue-purple toward horizon, no figures or text | none | hero_page |

---

## IX. Content Outline

### Part 1: Opening

#### Slide 01 - Cover

- **Layout**: Full-bleed AI background + centered floating glass title panel（Single column centered + #1 + #29）
- **Title**: AI Agent Engineering and Deployment
- **Subtitle**: From Demo to Production, It Takes More Than a Foundation Model
- **Info**: 2026 · Technology Talk Series

#### Slide 02 - Hero / Section opener "From Demo to Production"

- **Layout**: Full-bleed AI background + oversized floating text（breathing — #1 + #12 + #28）
- **Title**: 90% of Agent Projects Stop at the Demo
- **Body**: Reaching production requires clearing four engineering hurdles —
- **Sub-text**: Architecture · Context · Evaluation · Observability
- **Visualization**: None（breathing page, text only + AI atmosphere background）

### Part 2: Current State & Foundation

#### Slide 03 - Three Major Pain Points: Why Agents Can't Reach Production

- **Layout**: 1×3 vertical_pillars (V. three columns)
- **Title**: Three Real-World Barriers Blocking Agent Adoption
- **Visualization**: vertical_pillars
- **Content**:
  - Unstable performance (gauge): errors compound across multi-step reasoning, making P95 latency uncontrollable
  - Unpredictable costs (coin): tokens per task fluctuate by 5-50×
  - Quality lacks a closed loop (bug): failure causes are ambiguous and regression testing is missing

#### Slide 04 - Agent Architecture Fundamentals: The Four-Layer Model

- **Layout**: layered_architecture (4 horizontal layers) + #44 AI background overlay
- **Title**: The four-layer skeleton of an Agent
- **Visualization**: layered_architecture
- **Content**:
  - **Perception** (eye) — Input parsing / multimodality / context-window management
  - **Reasoning** (brain) — Plan / ReAct / Tree-of-Thought / Reflection
  - **Action** (lightning) — Tool calling / function execution / API orchestration
  - **Memory** (database) — Short-term context / long-term vector store / task-level cache

#### Slide 05 - Comparison of Three Working Modes

- **Layout**: Symmetric 3-column (comparison_columns)
- **Title**: Workflow / Agent / Multi-Agent — which one to choose?
- **Visualization**: comparison_columns
- **Content**:
  - **Workflow** (flow-arrow): Fixed path / predictable / easy to debug / suited to deterministic tasks
  - **Agent** (robot): Dynamic path / LLM decision-making / tool use / suited to semi-structured exploration
  - **Multi-Agent** (users-three): Multi-role collaboration / task delegation / shared context / suited to complex, long-horizon tasks

### Part 3: Four Core Engineering Capabilities

#### Slide 06 - Tool Calling and Orchestration: A Six-Step Method

- **Layout**: numbered_steps (6 steps horizontally) + #39 AI pipeline background
- **Title**: Take tool calling from “it runs” to “it runs reliably”
- **Visualization**: numbered_steps
- **Content**:
  - 01 Parse the task (magnifying-glass) — Break down user intent
  - 02 Select tools (target) — Schema matching + description retrieval
  - 03 Execute the call (plug) — Parameter filling + timeout control
  - 04 Validate the response (check-circle) — JSON schema / business rules
  - 05 Retry and fall back (arrows-clockwise) — Exponential backoff / fallback path
  - 06 Aggregate results (stack) — Multi-turn aggregation → final answer

#### Slide 07 - Context Engineering: 1 Core + 6 Capabilities

- **Layout**: hub_spoke (center + 6 surrounding nodes) + #42 AI sphere background
- **Title**: Context is the Agent’s true “weight”
- **Visualization**: hub_spoke
- **Content**:
  - **Core** (cube): Context Engineering
  - **Retrieval** (magnifying-glass): RAG / vector retrieval / BM25 hybrid ranking
  - **Reranking** (funnel): Reranker / Top-K filtering
  - **Truncation** (scales): Token budget allocation / prioritize key information
  - **Memory** (database): Short- and long-term memory / session state
  - **Tool instructions** (gear): Tool schema / example descriptions
  - **System prompt** (code-block): Persona / output format / safety rules

#### Slide 08 - KPI Dashboard: Track Four Numbers

- **Layout**: kpi_cards 2×2 + #40 AI bokeh background
- **Title**: Install these four dashboards before going to production
- **Visualization**: kpi_cards
- **Content**:
  - **Task success rate** (check-circle): 92.4% ↑ 3.2pp / week
  - **P95 latency** (gauge): 4.8s ↓ 18% / week
  - **Cost per run** (coin): ¥0.42 ↓ 22% / week
  - **Reliability** (shield-check): 99.7% SLO / 30 days

#### Slide 09 - Metric Trends: 12 Weeks After Launch

- **Layout**: Full-width line_chart (dual lines — accuracy + cost)
- **Title**: The True Curve of Continuous Optimization: Accuracy ↑ Cost ↓
- **Visualization**: line_chart
- **Content**:
  - Series A: task success rate (left axis %, from 71% → 92.4%)
  - Series B: average cost per run (right axis ¥, from 1.20 → 0.42)
  - 12-week timeline W1–W12, with key milestones: reranker introduced at W4 / fallback introduced at W8 / caching introduced at W11

#### Slide 10 - Failure Mode Quadrant

- **Layout**: quadrant_text_bullets 2×2 + #12 AI failure background
- **Title**: Of these four failure modes, which will you encounter first?
- **Visualization**: quadrant_text_bullets
- **Content**:
  - **Tool errors** (bug): Schema mismatch / hallucinated parameters / no fallback on timeout
  - **Infinite loops** (arrows-clockwise): Unbounded reflection loops / repeated Plan revisions
  - **Hallucinations** (sparkle): Invented tools / fabricated results / pretending to succeed
  - **Runaway costs** (coin): Token drift / repeated retrieval / overly long chains

### Part 4: Implementation and Wrap-Up

#### Slide 11 - Implementation Roadmap: Four Phases

- **Layout**: roadmap_vertical (4 milestones vertically)
- **Title**: From prototype to production — Four phases over 12 weeks
- **Visualization**: roadmap_vertical
- **Content**:
  - **W1-W3 Prototype** (crosshair): Get a single task working + draft the tool schema
  - **W4-W7 Engineering** (gear-six): Evaluation set + automated testing + fallback mechanisms
  - **W8-W10 Scaling** (chart-line-up): Caching + rate limiting + multi-tenant isolation
  - **W11-W12 Production** (rocket): Staged rollout + SLO monitoring + continuous optimization

#### Slide 12 - CTA / Closing

- **Layout**: breathing — Full-bleed AI wide shot + centered CTA glass panel (#1 + #66 + #29)
- **Title**: Your next Agent starts with engineering
- **Body**: It’s not “adding an LLM”; it’s truly integrating an LLM into the system
- **CTA**: Start engineering your Agent now (rocket / handshake)

---

## X. Speaker Notes Requirements

One file per page, saved to `notes/`:

- **Filename**: match SVG name (e.g., `01_cover.md`)
- **Total duration**: 12-15 minutes
- **Style**: conversational + technical presentation
- **Purpose**: inform + persuade (convince decision-makers to prioritize engineering Agents)

---

## XI. Technical Constraints Reminder

### SVG Generation Must Follow:

1. viewBox: `0 0 1280 720`
2. Background uses `<rect>` elements
3. Text wrapping uses `<tspan>` (`<foreignObject>` FORBIDDEN)
4. Transparency defaults to `fill-opacity` / `stroke-opacity`; `rgba()` remains converter-compatible
5. FORBIDDEN: `mask`, `<style>`, `class`, `foreignObject`, `textPath`, `animate*`, `script`
6. Text characters: raw Unicode (`—`, `→`, `©`, NBSP); HTML named entities FORBIDDEN; XML reserved characters must be escaped as `&amp; &lt; &gt; &quot; &apos;`
7. `clipPath` may only be used on `<image>` (rounded crop, etc.)
8. Prefer opacity on each child; `<g opacity>` remains converter-compatible with an approximate-fidelity warning

### Glassmorphism Implementation Focus

- Glass panel: `<rect fill="url(#glassPanel)" stroke="#FFFFFF" stroke-opacity="0.18" stroke-width="1" rx="16"/>`
- Glass edge highlight: `<rect ... fill="url(#glassEdge)" height="1"/>` placed along the top edge of the panel
- Do not use `<feGaussianBlur>` for frosted-glass blur effects (PPT export is unstable) — let AI-generated imagery provide the atmosphere
- Simulate flowing neon effects with a translucent overlay: `<rect fill="primary" fill-opacity="0.15-0.25"/>`
- If shadows are needed, use `<feDropShadow>` only on decorative elements, not the main structure

### PPT Compatibility Rules

- Prefer descendant opacity; `<g opacity="...">` remains converter-compatible with an approximate-fidelity warning
- Use an overlay mask layer for image transparency
- Inline styles only; no external CSS / `@font-face`
