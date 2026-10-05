# LoRA: Low-Rank Adaptation of Large Language Models - Design Spec

> Academic paper interpretation presentation · Source document: Hu et al., 2021, Microsoft (arXiv:2106.09685v2). The design narrative is in this document; the machine-readable execution contract is in `spec_lock.md` (in case of conflict, spec_lock takes precedence).

## I. Project Information

| Item | Value |
| ---- | ----- |
| **Project Name** | lora_hu_2021 |
| **Canvas Format** | PPT 16:9 (1280×720) |
| **Page Count** | 15 |
| **Design Style** | B) General Consulting (data clarity first) + academic technical minimalism |
| **Target Audience** | Machine learning researchers / engineers; paper presentations, group meetings, and technical defenses |
| **Use Case** | Chinese-language presentation of an English paper (with terminology retained in English) |
| **Created Date** | 2026-05-23 |

---

## II. Canvas Specification

| Property | Value |
| -------- | ----- |
| **Format** | PPT 16:9 |
| **Dimensions** | 1280×720 |
| **viewBox** | `0 0 1280 720` |
| **Margins** | 64px left/right, 56px top/bottom |
| **Content Area** | 1152×608 (safe area) |

---

## III. Visual Theme

### Theme Style

- **Style**: Academic technical minimalism — blueprint-like structure, restrained whitespace, data and formulas doing the talking
- **Theme**: Light theme (white background)
- **Tone**: Rigorous, credible, engineering-oriented, analytical

### Color Scheme

| Role | HEX | Purpose |
| ---- | --- | ------- |
| **Background** | `#FFFFFF` | Page background |
| **Secondary bg** | `#F4F7FA` | Card / section background |
| **Primary** | `#1B3A5C` | Deep academic blue — titles, structural lines, chart axes, icons |
| **Accent** | `#E8743B` | Warm orange — key figures (10000×, zero latency), highlights, LoRA branch |
| **Secondary accent** | `#3E7CB1` | Medium blue — secondary data series and supporting structure |
| **Body text** | `#1D2733` | Main body text |
| **Secondary text** | `#5B6776` | Notes and subtitles |
| **Tertiary text** | `#8A94A1` | Footnotes and page numbers |
| **Border/divider** | `#D8DEE6` | Card borders and dividers |
| **Success** | `#2E7D32` | Better-than-baseline indicator (LoRA wins) |
| **Warning** | `#C62828` | Cost / disadvantage indicator (full fine-tuning overhead, increased latency) |

**Color rules**: 60-30-10 (60% white background / 30% dark blue / ≤10% warm orange); body-text contrast ≥ 4.5:1; ≤ 4 colors per page.

### AI Image Strategy

- **Image Rendering**: blueprint
- **Image Palette**: cool-corporate

> The blueprint × cool-corporate compatibility matrix is ✓✓. All AI images across the deck share this rendering and color scheme; `text_policy: embedded`, with text allowed inside images (English for terminology, Chinese for explanations); validate the output after generation. HEX values are authoritative; the palette only defines the 60-30-10 usage.

### Gradient Scheme

```xml
<linearGradient id="titleGradient" x1="0%" y1="0%" x2="100%" y2="0%">
  <stop offset="0%" stop-color="#1B3A5C"/>
  <stop offset="100%" stop-color="#3E7CB1"/>
</linearGradient>
<radialGradient id="bgDecor" cx="85%" cy="15%" r="55%">
  <stop offset="0%" stop-color="#1B3A5C" stop-opacity="0.06"/>
  <stop offset="100%" stop-color="#1B3A5C" stop-opacity="0"/>
</radialGradient>
```

---

## IV. Typography System

### Font Plan

**Typography direction**: Unified sans-serif (the convention for technical-paper slides); use monospace for code / dimensional symbols.

| Role | Chinese | English | Fallback tail |
| ---- | ------- | ------- | ------------- |
| **Title** | `"Microsoft YaHei"` | `Arial` | `sans-serif` |
| **Body** | `"Microsoft YaHei"` | `Arial` | `sans-serif` |
| **Emphasis** | `"Microsoft YaHei"` | `Arial` | `sans-serif` (weight contrast, not a font change) |
| **Code** | — | `Consolas, "Courier New"` | `monospace` |

**Per-role font stacks**:

- Title: `"Microsoft YaHei", Arial, sans-serif`
- Body: `"Microsoft YaHei", Arial, sans-serif`
- Emphasis: same as Body (create contrast with font-weight 700/900)
- Code: `Consolas, "Courier New", monospace`

### Font Size Hierarchy

**Baseline**: Body = 18px (dense — data tables + formulas + multiple content points).

| Purpose | Ratio | px | Weight |
| ------- | ----- | -- | ------ |
| Cover title | 3.3x | 60 | Heavy |
| Hero number (e.g., 10000×) | 3.1x | 56 | Heavy |
| Page title | 1.8x | 32 | Bold |
| Subtitle | 1.3x | 24 | SemiBold |
| **Body** | **1x** | **18** | Regular |
| Annotation / caption | 0.78x | 14 | Regular |
| Chart annotation | 0.72x | 13 | Regular |
| Page number / footnote | 0.61x | 11 | Regular |

---

## V. Layout Principles

### Page Structure

- **Header area**: ~96px high — header title + thin color bar + sequence number
- **Content area**: ~520px high — main body (charts / images / formulas / cards)
- **Footer area**: ~40px high — source note (LoRA, Hu et al. 2021) + page number

### Layout Pattern Library (combined by information hierarchy)

Choose by page: centered single column (cover/conclusion), asymmetrical columns (image vs. key points), three-/four-column cards (advantages/KPIs), image-as-canvas + native overlays (method diagrams), negative-space led (breathing-concept pages). Do not turn every page into the same card grid.

### Spacing Specification

**Universal**: 64px safe margins; 28px spacing between content blocks; 10px icon-text gap.
**Card-based**: 24px spacing between cards; 24px internal card padding; 12px corner radius; four card columns approximately 264px wide.
**Non-card (breathing)**: 1.5× line height; use whitespace and divider lines to create sections.

---

## VI. Icon Usage Specification

### Source

- Library: `tabler-outline` (linear, lightweight, suitable for technical screens), `stroke_width: 2`; do not mix in other libraries within the deck.
- Usage: `<use data-icon="tabler-outline/<name>" stroke-width="2" .../>`

### Recommended Icon List

| Purpose | Icon Path | Page |
| ------- | --------- | ---- |
| Frozen weights | `tabler-outline/snowflake` / `tabler-outline/lock` | P03/P06 |
| Deployment cost | `tabler-outline/building-bank` / `tabler-outline/server-2` | P03 |
| Limitation warning | `tabler-outline/alert-triangle` | P04 |
| Low-rank insight | `tabler-outline/bulb` / `tabler-outline/layers-subtract` | P05 |
| Method / formula | `tabler-outline/math-function` / `tabler-outline/transform` | P06/P07 |
| Branch A/B | `tabler-outline/arrows-split` | P06 |
| Transformer architecture | `tabler-outline/sitemap` / `tabler-outline/topology-star` | P08 |
| Shareable | `tabler-outline/share-2` / `tabler-outline/git-branch` | P09 |
| Efficient training | `tabler-outline/bolt` | P09 |
| Zero inference latency | `tabler-outline/gauge` | P09/P10 |
| Orthogonally composable | `tabler-outline/puzzle` | P09 |
| Experiment | `tabler-outline/flask` / `tabler-outline/database` | P11 |
| Results | `tabler-outline/chart-bar` | P10/P12 |
| Meets target / outperforms | `tabler-outline/circle-check` | P12/P13 |
| Conclusion | `tabler-outline/target` | P15 |

---

## VII. Visualization Reference List

Catalog read: 71 templates

| Page | Template | Path | Summary-quote (verbatim from `charts_index.json`) | Usage |
| ---- | -------- | ---- | ------------------------------------------------- | ----- |
| P02 | agenda_list | `templates/charts/agenda_list.svg` | "Pick for table of contents, meeting agendas, or presentation roadmap — numbered items + brief description + duration / owner per row." | Presentation roadmap (6 sections) |
| P04 | vertical_list | `templates/charts/vertical_list.svg` | "Pick for 3-6 numbered key points each with a short description — design principles, core tenets, action items, key takeaways, recommendations, executive summary points." | Three limitations of existing methods |
| P09 | icon_grid | `templates/charts/icon_grid.svg` | "Pick for 4-9 parallel features/capabilities/services as icon cards — feature grid, service lineup, benefits matrix, brand values, product highlights." | Four key advantages of LoRA |
| P10 | grouped_bar_chart | `templates/charts/grouped_bar_chart.svg` | "Pick for 2-4 series side-by-side across the same categories (e.g. YoY/QoQ)." | Comparison of inference latency increases across methods |
| P11 | basic_table | `templates/charts/basic_table.svg` | "Pick for plain tabular text/number grid, 3-8 columns." | Model × benchmark × task experiment matrix |
| P12 | consulting_table | `templates/charts/consulting_table.svg` | "Pick for high-density tables with embedded micro bar visuals (consulting/financial reports)." | GLUE results (parameter count + Avg micro bars) |
| P13 | kpi_cards | `templates/charts/kpi_cards.svg` | "Pick for 4-8 standalone numeric metrics shown as overview cards (2x2 or 1x4) — exec summary opener, dashboard headline, quarterly recap, results-at-a-glance." | Four key GPT-3 175B metrics |
| P14 | basic_table | `templates/charts/basic_table.svg` | "Pick for plain tabular text/number grid, 3-8 columns." | Adapter weights (Table 5) + optimal rank (Table 6) |
| P15 | vertical_list | `templates/charts/vertical_list.svg` | "Pick for 3-6 numbered key points each with a short description — design principles, core tenets, action items, key takeaways, recommendations, executive summary points." | Key takeaways |

**Runners-up considered**:

- `numbered_steps` | rejected for P02: The presentation agenda consists of parallel sections rather than sequential steps; `agenda_list`’s built-in duration/section columns are a better fit.
- `pros_cons_chart` | rejected for P04: The limitations of the existing approach form a “one-sided list of drawbacks (latency / sequence length / quality–efficiency trade-off)”, not a symmetrical pros-versus-cons comparison.
- `bar_chart` | rejected for P10: Latency needs to compare two variants, AdapterL × AdapterH, across sequence scenarios; this is a multi-series comparison, for which `grouped_bar` is more accurate.
- `comparison_table` | rejected for P12: GLUE uses tiny Avg bars to reinforce the visual message of “fewer parameters, higher scores”; the embedded micro-bars in `consulting_table` outperform a text-only comparison table.
- `gauge_chart` | rejected for P13: GPT-3 involves multiple metrics (parameter ratio / VRAM / throughput / accuracy), not a single hero metric; `kpi_cards` is more suitable.

---

## VIII. Image Resource List

| Filename | Dimensions | Ratio | Purpose | Type | Layout pattern | Acquire Via | Status | Reference | text_policy | page_role |
| -------- | --------- | ----- | ------- | ---- | -------------- | ----------- | ------ | --------- | ----------- | --------- |
| cover_hero.png | 1280x720 | 1.78 | Cover key visual (Slide 01) | Illustration | #1 full-bleed background with floating title + #29 two-stop scrim | ai | Pending | A frozen array of large pretrained weights is locked in place; a trainable side branch composed of two slender low-rank matrices (down-projection A and up-projection B) is injected alongside it, with the connections converging at the output; blueprint-style diagram, leaving a quiet lower band for the SVG title | embedded | hero_page |
| cost_explosion.png | 860x720 | 1.19 | Cost of full fine-tuning deployment (Slide 03) | Diagram | #4 right image bleeding off the canvas edge + #32 multi-stop scrim with hue shift | ai | Pending | The same 175B giant model copied in full into multiple heavy server racks for each downstream task, emphasizing the high storage and deployment cost of "one full-parameter copy per task" | embedded | local |
| lowrank_insight.png | 1280x720 | 1.78 | Insight into the intrinsic low-rank dimension (Slide 05) | Illustration | #19 image floating in whitespace with thin frame and caption + #21 rounded rectangle crop | ai | Pending | A cloud of high-dimensional weight updates collapsing onto a thin low-dimensional subspace, with a few principal directions carrying most of the information; conceptual diagram with extensive negative space | embedded | local |
| reparam_diagram_cropped.png | 1280x531 | 2.41 | LoRA reparameterization architecture diagram (Slide 06) | Diagram | #44 background image + native network/architecture diagram + #41 measurement lines and module tags (engineering overlay) | ai | Pending | Input x simultaneously enters frozen pretrained weights W and a parallel low-rank bypass: first through down-projection matrix A to a rank-r bottleneck, then through up-projection matrix B; the two outputs are added to produce h; clear arrows, bottleneck dimension r labeled | embedded | local |
| attention_apply.png | 530x580 | 0.91 | Applied to Transformer attention (Slide 08) | Diagram | #2 left-third image + right text body + #21 rounded rectangle crop | ai | Pending | A Transformer self-attention module with four projection matrices Wq/Wk/Wv/Wo; Wq and Wv each connected to a highlighted low-rank LoRA bypass, with the MLP module labeled frozen; blueprint structure | embedded | local |
| subspace_heatmap.png | 1024x1024 | 1.0 | Subspace similarity heatmap (Slide 14) | Diagram | #3 right-third image + left text body + #21 rounded rectangle crop | ai | Pending | Square heatmap: normalized subspace similarity at row i, column j; high intensity at the upper left (top singular directions), rapidly darkening elsewhere; clear grid cells, blue-to-orange intensity scale | embedded | local |
| formula_001.png | 688x44 | 15.64 | Forward propagation formula (Slide 06) | Latex Formula | formula-block | formula | Rendered | `h = W_0 x + \Delta W x = W_0 x + B A x` — forward propagation after LoRA modification | | |
| formula_002.png | 1280x55 | 23.27 | Low-rank decomposition and constraints (Slide 06) | Latex Formula | formula-block | formula | Rendered | `W_0 + \Delta W = W_0 + BA, B∈R^{d×r}, A∈R^{r×k}, r≪min(d,k)` — low-rank decomposition | | |
| formula_003.png | 220x91 | 2.42 | Scaling factor (Slide 07) | Latex Formula | formula-block | formula | Rendered | `\Delta W x · α/r` — scaling of ΔWx | | |
| formula_004.png | 604x60 | 10.07 | Number of trainable parameters (Slide 08) | Latex Formula | formula-block | formula | Rendered | `|Θ| = 2 × L_LoRA × d_model × r` — number of trainable LoRA parameters | | |

> Determine whether text inside an image needs to remain editable (“frozen raster → validate after generation”); P06 uses image-as-canvas (#44) to satisfy the image-as-canvas coverage requirement—precise formulas and editable labels are added as SVG overlays, while the image itself carries the structural atmosphere. All AI images use blueprint × cool-corporate; HEX values should not be written literally inside the images.

---

## IX. Content Outline

### Part 1: Introduction & the Problem

#### Slide 01 - Cover
- **Layout**: Full-screen hero visual + floating title (breathing→anchor)
- **Title**: LoRA: Low-Rank Adaptation of Large Language Models
- **Subtitle**: Low-Rank Adaptation of Large Language Models
- **Info**: Hu et al., 2021 · Microsoft · arXiv:2106.09685 · Paper Walkthrough

#### Slide 02 - Presentation Roadmap
- **Layout**: agenda_list(anchor)
- **Title**: What We’ll Cover
- **Visualization**: agenda_list
- **Content**: ① The problem: Why is fine-tuning becoming increasingly expensive? ② Limitations of existing methods ③ Core insight: the low-rank assumption ④ The LoRA method and implementation ⑤ Experimental results ⑥ Understanding low rank and conclusions

#### Slide 03 - Problem: The Cost of Full Fine-Tuning
- **Layout**: Left hero number + right overflow image (breathing)
- **Title**: The larger the model, the less feasible full fine-tuning becomes
- **Content**:
  - GPT-3 175B: a full-parameter copy (175B) must be stored for every downstream task
  - Deploying N tasks = N × 175B, with extremely high storage and switching costs
  - Hero: **175B** trainable parameters / task

### Part 2: Existing Methods & Insights

#### Slide 04 - Limitations of Existing Methods
- **Layout**: vertical_list, three items (dense)
- **Title**: Why Existing Efficient Adaptation Methods Aren't Good Enough
- **Visualization**: vertical_list
- **Content**:
  - Adapter layers: increase model depth → introduce inference latency (especially for short online sequences)
  - Prefix / Prompt tuning: consume input length → reduce the available sequence length
  - Generally: often fail to match the full fine-tuning baseline → a trade-off between efficiency and quality

#### Slide 05 - Core Insight: Low "Intrinsic Rank"
- **Layout**: Concept diagram + short text (breathing)
- **Title**: Weight updates are actually "low-rank"
- **Content**:
  - Overparameterized models actually occupy a low intrinsic dimension (Aghajanyan et al. 2020)
  - Hypothesis: weight changes ΔW during adaptation also have a low "intrinsic rank"
  - Even when d reaches 12,288, an extremely low r (1–2) is sufficient

### Part 3: Method

#### Slide 06 - The LoRA Method
- **Layout**: Image-as-canvas structural diagram + overlaid formulas (breathing)
- **Title**: Freeze W₀, Inject Low-Rank BA
- **Visualization**: (AI structural diagram reparam_diagram_cropped + formula_001/002)
- **Content**:
  - Constrain updates through low-rank decomposition: W₀ + ΔW = W₀ + BA
  - Forward pass: h = W₀x + BAx; W₀ is frozen during training, and only A and B are trained
  - A is initialized with Gaussian noise and B is set to zero → initial ΔW = 0

#### Slide 07 - Implementation Details: Initialization and Scaling
- **Layout**: Formula + key points (dense)
- **Title**: One constant α, one deployment merge
- **Visualization**: (formula_003)
- **Content**:
  - Scale ΔWx by α/r; set α to the first r tried and never tune it again
  - Explicitly merge W = W₀ + BA at deployment → same architecture as the original model
  - To switch tasks: subtract BA and add B′A′, with negligible overhead

#### Slide 08 - Applied to the Transformer
- **Layout**: Structural diagram on the left + key points on the right + parameter-count formula (dense)
- **Title**: Adapt Only the Attention Weights
- **Visualization**: (AI structure diagram attention_apply + formula_004)
- **Content**:
  - Self-attention includes Wq/Wk/Wv/Wo; the experiment adapts only Wq and Wv, while freezing the MLP
  - Trainable parameter count: |Θ| = 2 × L_LoRA × d_model × r
  - GPT-3 175B: VRAM 1.2TB → 350GB; checkpoint 350GB → 35MB

#### Slide 09 - Four Key Advantages
- **Layout**: icon_grid, four dense cards
- **Title**: Four Key Advantages of LoRA
- **Visualization**: icon_grid
- **Content**:
  - Shareable: one base model + multiple small LoRA modules; switch tasks by swapping only BA
  - Efficient training: no need to store gradients or optimizer states for frozen parameters; hardware requirements reduced 3×
  - Zero inference latency: after merging weights, architecturally identical to a fully fine-tuned model
  - Orthogonally composable: can be combined with methods such as prefix-tuning

### Part 4: Experimental Results

#### Slide 10 - Zero Inference Latency
- **Layout**: grouped_bar_chart(dense)
- **Title**: Adapters Add Latency; LoRA Does Not
- **Visualization**: grouped_bar_chart
- **Content**:
  - GPT-2 medium single forward-pass latency (average over 100 runs, RTX 8000)
  - AdapterL: up to +20.7%; AdapterH: up to +30.3% (short sequences/small batches)
  - LoRA / FT baseline: **0% additional latency**

#### Slide 11 - Experimental Setup
- **Layout**: basic_table model×benchmark(dense)
- **Title**: Four model types spanning NLU to NLG
- **Visualization**: basic_table
- **Content**:
  - RoBERTa base/large(125M/355M), DeBERTa XXL(1.5B)→ GLUE
  - GPT-2 medium → E2E NLG;GPT-3 175B → WikiSQL / MNLI / SAMSum
  - Baselines:FT, BitFit, PreEmbed/PreLayer, Adapter H/L/P/D

#### Slide 12 - GLUE Results
- **Layout**: consulting_table(dense)
- **Title**: Fewer parameters, equal or better performance
- **Visualization**: consulting_table
- **Content**:
  - RoBERTa-base:FT 86.4(125M)→ LoRA **87.2**(0.3M)
  - RoBERTa-large:FT 88.9(355M)→ LoRA **89.0**(0.8M)
  - DeBERTa-XXL:FT 91.1(1500M)→ LoRA **91.3**(4.7M)

#### Slide 13 - GPT-3 175B Results
- **Layout**: kpi_cards four metrics(dense)
- **Title**: Still Holds at the 175B Scale
- **Visualization**: kpi_cards
- **Content**:
  - **10,000×** reduction in trainable parameters(checkpoint 350GB → 35MB)
  - VRAM 1.2TB → **350GB**(approximately 1/3)
  - Training throughput **+25%**(no need to calculate gradients for most parameters)
  - WikiSQL/MNLI/SAMSum all **match or exceed** full fine-tuning

### Part 5: Understanding and Conclusions

#### Slide 14 - Understanding Low Rank: Weights and Rank
- **Layout**: Two tables on the left + heatmap (dense) on the right
- **Title**: Which weights should be adapted? How large should the rank be?
- **Visualization**: basic_table + (AI heatmap subspace_heatmap)
- **Content**:
  - With the same parameter budget: adapting {Wq, Wv} performs best (WikiSQL 73.7)
  - Rank r=1 is already sufficient for adapting {Wq, Wv} (r=64 offers almost no additional gain)
  - Subspace similarity: top singular directions overlap heavily → ΔW has intrinsically very low rank

#### Slide 15 - Conclusions and Implications
- **Layout**: vertical_list takeaways(anchor)
- **Title**: Conclusions and Implications
- **Visualization**: vertical_list
- **Content**:
  - Low-rank adaptation = parameter-efficient + zero additional inference latency + equal or better quality
  - Engineering significance: host multiple tasks on one base model and hot-swap LoRA modules on demand
  - Open-sourced (microsoft/LoRA), it has become one of the de facto standards for large-model fine-tuning

---

## X. Speaker Notes Requirements

- One piece per page, stored in `notes/total.md` (the master document uses `#` heading lines; filenames match the SVG)
- Total duration: approximately 18–22 minutes; style: conversational-professional; purpose: inform + instruct
- Explanation in Chinese, with technical terms retained in English

---

## XI. Technical Constraints Reminder

### SVG Generation Must Follow:
1. Use viewBox `0 0 1280 720`; use `<rect>` for the background
2. Use `<tspan>` for text wrapping; `<foreignObject>` is prohibited
3. Use `fill-opacity` / `stroke-opacity` by default for transparency; retain `rgba()` for conversion compatibility
4. Prohibited: `mask`, `<style>`, `class`, `foreignObject`, `textPath`, `animate*`, `script`
5. Write characters as raw Unicode (`—`, `→`, `×`, `≪`); HTML entities are prohibited; escape `& < >` as `&amp; &lt; &gt;`
6. Use `clipPath` only for `<image>` (rounded-corner clipping, etc.)

### PPT Compatibility Rules:
- Set opacity on each child element by default; `<g opacity>` can be converted but may produce an approximate-fidelity warning
- Use an overlay mask for semi-transparent images
- Inline styles only; external CSS / `@font-face` prohibited
