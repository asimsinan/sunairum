# Lin Huiyin: Reconsidering the Architect, Not the Legend - Design Spec

> This document is the human-readable design narrative — rationale, audience, style, color choices, content outline. It is read once by downstream roles for context.
>
> The machine-readable execution contract lives in `spec_lock.md` (short form of color / typography / icon / image decisions). Executor re-reads `spec_lock.md` before every SVG page to resist context-compression drift. Keep the two files in sync; if they diverge, `spec_lock.md` wins.

## I. Project Information

| Item | Value |
| ---- | ----- |
| **Project Name** | Lin Huiyin: Reconsidering the Architect, Not the Legend |
| **Canvas Format** | PPT 16:9 (1280×720) |
| **Page Count** | 9 |
| **Design Style** | General Versatile (A) |
| **Target Audience** | Audiences interested in architecture and the humanities, cultural communications professionals, and lecture attendees |
| **Use Case** | Short commemorative talks, exhibition-style content presentations, and extended sharing for WeChat Official Account content |
| **Created Date** | 2026-04-22 |

---

## II. Canvas Specification

| Property | Value |
| -------- | ----- |
| **Format** | PPT 16:9 |
| **Dimensions** | 1280×720 |
| **viewBox** | `0 0 1280 720` |
| **Margins** | 64px left/right, 48px top/bottom |
| **Content Area** | 1152×624 (64,48 → 1216,672) |

---

## III. Visual Theme

### Theme Style

- **Style**: General Versatile — museum exhibition feel, architectural reference-book aesthetic, editorial layout
- **Theme**: Light theme (light exhibition-label visual style)
- **Tone**: Restrained, well-researched, modern; avoid the “heavy commemorative documentary” formula, emphasizing “seeing anew” and a professional architectural identity

### Color Scheme

| Role | HEX | Purpose |
| ---- | --- | ------- |
| **Background** | `#F6F1E8` | Main background, paper-like warm off-white |
| **Secondary bg** | `#EFE7DA` | Section background and light card fill |
| **Primary** | `#A44A3F` | Architectural brick red for main titles and key guide lines |
| **Accent** | `#6E7C80` | Blue-gray for structural lines and supporting labels |
| **Secondary accent** | `#B6915E` | Golden brown for emphasis and page-number decoration |
| **Body text** | `#1F1B16` | Deep ink-black body text |
| **Secondary text** | `#6A6258` | Figure captions, explanations, and annotations |
| **Tertiary text** | `#978C7E` | Footers and supporting information |
| **Border/divider** | `#D8CBB8` | Fine dividers and outline lines |
| **Success** | `#4F7A59` | Positive markers |
| **Warning** | `#B45B4C` | Risk, controversy, and historical-tension markers |

### Gradient Scheme (if needed, using SVG syntax)

```xml
<linearGradient id="titleGradient" x1="0%" y1="0%" x2="100%" y2="0%">
  <stop offset="0%" stop-color="#A44A3F"/>
  <stop offset="100%" stop-color="#B6915E"/>
</linearGradient>

<linearGradient id="paperFade" x1="0%" y1="0%" x2="0%" y2="100%">
  <stop offset="0%" stop-color="#F6F1E8"/>
  <stop offset="100%" stop-color="#EFE7DA"/>
</linearGradient>
```

---

## IV. Typography System

### Font Plan

**Typography direction**: editorial display + modern CJK sans

| Role | Chinese | English | Fallback |
| ---- | ------- | ------- | -------- |
| **Title** | Songti SC | Georgia | SimSun |
| **Body** | PingFang SC | Arial | Microsoft YaHei |
| **Emphasis** | SimHei | Arial | Microsoft YaHei |
| **Code** | - | Consolas | Courier New |

**Per-role font stacks**:
- Title: `Georgia, "Times New Roman", "Songti SC", SimSun, serif`
- Body: `"PingFang SC", "Microsoft YaHei", Arial, sans-serif`
- Emphasis: `"Microsoft YaHei", Arial, sans-serif`
- Code: `Consolas, "Courier New", monospace`

### Font Size Hierarchy

**Baseline**: Body font size = 20px

| Purpose | Ratio to body | 24px baseline (relaxed) | 18px baseline (dense) | Weight |
| ------- | ------------- | ---------------------- | -------------------- | ------ |
| Cover title (hero headline) | 2.5-5x | 60-120px | 45-90px | Bold / Heavy |
| Chapter / section opener | 2-2.5x | 48-60px | 36-45px | Bold |
| Page title | 1.5-2x | 36-48px | 27-36px | Bold |
| Hero number (consulting KPIs) | 1.5-2x | 36-48px | 27-36px | Bold |
| Subtitle | 1.2-1.5x | 29-36px | 22-27px | SemiBold |
| **Body content** | **1x** | **24px** | **18px** | Regular |
| Annotation / caption | 0.7-0.85x | 17-20px | 13-15px | Regular |
| Page number / footnote | 0.5-0.65x | 12-16px | 9-12px | Regular |

**Current project anchors**:
- Cover title: 64px
- Page title: 34px
- Subtitle: 24px
- Body: 20px
- Annotation: 14px
- Page number: 11px

---

## V. Layout Principles

### Page Structure

- **Header area**: 88px, tall header area with page number and chapter identifier
- **Content area**: 560px, main content area
- **Footer area**: 24px, source/page number/notes

### Layout Pattern Library (combine or break as content demands)

| Pattern | Suitable Scenarios |
| ------- | ----------------- |
| **Single column centered** | Cover, ending, core judgment |
| **Asymmetric split (4:6 / 5:5)** | Visual-verbal narrative, work descriptions |
| **Three-column cards** | Work mosaic, contribution breakdown |
| **Matrix grid (2×2)** | Side-by-side comparison of multiple images |
| **Z-pattern / waterfall** | Development of biography and methodology |
| **Figure-text overlap** | Cover, profile pages, monument page |
| **Negative-space-driven** | Emphasis page in the style of “rethink” |

### Spacing Specification

**Universal**:

| Element | Recommended Range | Current Project |
| ------- | ---------------- | --------------- |
| Safe margin from canvas edge | 40-60px | 48-64px |
| Content block gap | 24-40px | 28px |
| Icon-text gap | 8-16px | 10px |

**Card-based layouts**:

| Element | Recommended Range | Current Project |
| ------- | ---------------- | --------------- |
| Card gap | 20-32px | 24px |
| Card padding | 20-32px | 22px |
| Card border radius | 8-16px | 14px |
| Single-row card height | 530-600px | 540px |
| Double-row card height | 265-295px each | 268px |
| Three-column card width | 360-380px each | 356px |

**Non-card containers**:

- Use whitespace and thin dividers rather than many large dark cards
- Clearly separate captions from body text; image edges may slightly overlap the text to create an editorial feel
- Avoid placing multiple cards side by side on breathing pages

---

## VI. Icon Usage Specification

### Source

- **Built-in icon library**: `templates/icons/tabler-outline/`
- **Library**: `tabler-outline`
- **Usage method**: Placeholder format `{{icon:tabler-outline/icon-name}}`

### Recommended Icon List (fill as needed)

| Purpose | Icon Path | Page |
| ------- | --------- | ---- |
| Architectural identity | `{{icon:tabler-outline/building}}` | Slide 01, 03 |
| Monumental architecture | `{{icon:tabler-outline/building-monument}}` | Slide 05, 09 |
| Campus and education | `{{icon:tabler-outline/school}}` | Slide 04, 07 |
| Transportation architecture | `{{icon:tabler-outline/train}}` | Slide 03 |
| Surveying and fieldwork | `{{icon:tabler-outline/compass}}` | Slide 07, 08 |
| Papers and publications | `{{icon:tabler-outline/article}}` | Slide 06 |
| Academic publishing | `{{icon:tabler-outline/book-2}}` | Slide 07 |
| Seeing anew / viewing | `{{icon:tabler-outline/eye}}` | Slide 02 |
| Historical milestone | `{{icon:tabler-outline/timeline}}` | Slide 03 |
| Pioneer / direction | `{{icon:tabler-outline/flag}}` | Slide 07 |
| Human warmth | `{{icon:tabler-outline/heart}}` | Slide 08, 09 |
| Global perspective | `{{icon:tabler-outline/globe}}` | Slide 06 |

---

## VII. Visualization Reference List (if needed)

| Visualization Type | Reference Template | Used In |
| ------------------ | ------------------ | ------- |
| timeline | `templates/charts/timeline.svg` | Slide 03 |
| icon_grid | `templates/charts/icon_grid.svg` | Slide 07 |
| vertical_list | `templates/charts/vertical_list.svg` | Slide 06 |

---

## VIII. Image Resource List (if needed)

| Filename | Dimensions | Ratio | Purpose | Type | Status | Generation Description |
| -------- | --------- | ----- | ------- | ---- | ------ | --------------------- |
| lin_portrait.png | 640x703 | 0.91 | Main cover visual | Photography | Existing | - |
| jihai_station_old.png | 670x346 | 1.94 | Historical photo of Jihai Railway Terminus | Photography | Existing | - |
| jihai_station_new.png | 1080x608 | 1.78 | Photo of the restored Jihai Railway Terminus | Photography | Existing | - |
| pku_geology.png | 745x414 | 1.80 | Former site of Peking University Geology Museum | Photography | Existing | - |
| yingqiu_yuan.png | 792x606 | 1.31 | Historical photo of Yingqiu Courtyard | Photography | Existing | - |
| kunming_site.png | 1080x783 | 1.38 | Photos related to Lin Huiyin's Kunming residence | Photography | Existing | - |
| babaoshan.png | 1080x712 | 1.52 | Babaoshan Revolutionary Cemetery | Photography | Existing | - |
| monument.png | 960x1280 | 0.75 | Monument to the People's Heroes | Photography | Existing | - |
| lin_tomb.png | 1080x796 | 1.36 | Lin Huiyin's gravestone | Photography | Existing | - |
| first_paper.png | 1080x810 | 1.33 | Image from her first architectural paper | Photography | Existing | - |
| liang_lin_together.png | 1000x710 | 1.41 | Portrait of Liang Sicheng and Lin Huiyin together | Photography | Existing | - |
| lin_survey.png | 1080x1145 | 0.94 | Photo of field research on ancient architecture | Photography | Existing | - |
| lin_later.png | 640x640 | 1.00 | Portrait from her later years | Photography | Existing | - |

---

## IX. Content Outline

### Part 1: Seeing Her Anew

#### Slide 01 - Cover

- **Layout**: Large title on the left + vertical portrait photo on the right + exhibition-label-style subtitle below
- **Title**: Lin Huiyin
- **Subtitle**: Reconsider the Architect, Not the Legend
- **Content**:
  - Small heading: 70th anniversary of her death
  - Supporting text: Reexamining her place in Chinese architectural history through her work, theory, and actions
- **Image**: lin_portrait.png

#### Slide 02 - Why We Need to Reconsider Lin Huiyin Today

- **Layout**: breathing page, centered judgment statement + three parallel observation dimensions
- **Title**: What gets seen is often not what matters most about her
- **Content**:
  - She has long been overshadowed by labels like “gifted woman,” “romantic story,” and “literary aura”
  - But what truly underpins her historical standing is her architectural practice, theoretical framework, and foundational work in the discipline
  - This new understanding is not a correction of trivia, but a rewriting of the coordinates of knowledge

### Part 2: Her as an Architect

#### Slide 03 - Architectural Practice Is Not Absent

- **Layout**: Horizontal timeline above + three work milestones below
- **Title**: From Tombstones to Train Stations, Her Architectural Practice Followed a Clear Trajectory
- **Visualization**: timeline
- **Content**:
  - 1929 Liang Qichao Tombstone: the starting point after returning from study abroad
  - 1929 Stone House and Jihai Railway Terminus: modernity set alongside national symbolism
  - 1932–1940 Peking University, Yingqiu House, Southwest Associated University, and her Kunming residence: maintaining her architectural ideals amid wartime turmoil

#### Slide 04 - On Site: Architecture Is Not an Abstract Noun

- **Layout**: 2×2 image matrix + annotation column on the right
- **Title**: Four Sites, Four Architectural Responses
- **Content**:
  - Jihai Railway Terminus: symbolic expression of landmark public architecture
  - Peking University Geology Museum: a turn toward modernism
  - Yingqiu Yuan: local materials and vernacular residential experience
  - Kunming Residence: self-built architecture under wartime conditions
- **Image**: jihai_station_new.png, pku_geology.png, yingqiu_yuan.png, kunming_site.png

#### Slide 05 - Architectural Engagement at the National Scale

- **Layout**: Image left and text right, with a large monument image as the visual anchor
- **Title**: Her Architectural Work Ultimately Entered the National Memory
- **Content**:
  - Babaoshan Revolutionary Cemetery: Designed the principal layout
  - Monument to the People's Heroes: Proposed key revisions to enlarge the monument base and add double-tiered steps
  - The treatment of patterns and proportions reflects her understanding of the vocabulary of traditional Chinese architecture
  - She was ultimately laid to rest in a space she had helped design
- **Image**: monument.png, babaoshan.png

### Part 3: Her as a Theoretical Pioneer

#### Slide 06 - She Was Not an “Assistant,” but the Originator of the Theory

- **Layout**: Paper image on the left + vertical key points on the right
- **Title**: By 1932, She Was Already Defining “Chinese Architecture”
- **Visualization**: vertical_list
- **Content**:
  - *Several Characteristics of Chinese Architecture* was the first systematic discussion of Chinese architecture by a Chinese professional scholar
  - She challenged misinterpretations embedded in Western knowledge frameworks
  - She identified key characteristics of China’s timber-frame structural system
  - She laid the theoretical framework for later narratives of Chinese architectural history
- **Image**: first_paper.png

#### Slide 07 - Discipline, Method, and Foresight

- **Layout**: Three-column method cards + supplementary strip below
- **Title**: What she truly left behind was a methodology
- **Visualization**: icon_grid
- **Content**:
  - Research methodology: Equal emphasis on surveying, fieldwork, historical sources, and typological analysis
  - Institution building: Contributed to establishing the architecture departments at Northeastern University and Tsinghua University
  - Theoretical foresight: Preservation of vernacular dwellings, modern housing, and ordinary people’s housing conditions
  - Keywords: *Architectural Intent*, *Construction Standards*, *General Introduction to Housing*, *Preservation of Vernacular Architecture*
- **Image**: liang_lin_together.png

### Part 4: Her as an Activist

#### Slide 08 - How She Made It Through War and Illness

- **Layout**: Text left and image right, non-card long-form paragraphs + emphasized quotation
- **Title**: She Was Not Someone to Be Accompanied—She Was an Agent of Action
- **Content**:
  - She surveyed ancient architecture in the field, crossing mountains and rivers rather than merely observing
  - War, displacement, and years of illness did not halt her research or writing
  - “I still have so much to do” expressed a sense of professional mission, not a pose
  - She poured her life into the foundational moment of Chinese architectural scholarship
- **Image**: lin_survey.png, lin_later.png

#### Slide 09 - Conclusion

- **Layout**: Single-image commemorative close + central quotation
- **Title**: The Seven Words on the Tombstone Are Accurate Enough
- **Subtitle**: Architect Lin Huiyin's Tomb
- **Content**:
  - To understand her anew is not to move from legend back to gossip, but from gossip back to professional achievement
  - She was a key builder among the first generation of Chinese architectural scholars
  - What she left behind was not only a body of work, but also a language for how China understands its own architecture
- **Image**: lin_tomb.png

---

## X. Speaker Notes Requirements

- **File naming**: Match SVG names (e.g., `01_Cover.svg` → `notes/01_Cover.md`)
- **Total duration**: ~12 minutes
- **Notes style**: Explanatory + caption-style narration; restrained, precise, and understated
- **Presentation purpose**: Correct misconceptions + establish a professional impression
- **Content includes**: Key points for each page, transitions between pages, and necessary emphasis on historical facts

---

## XI. Technical Constraints Reminder

### SVG Generation Must Follow:

1. viewBox: `0 0 1280 720`
2. Background uses `<rect>` elements
3. Text wrapping uses `<tspan>` (`<foreignObject>` FORBIDDEN)
4. Transparency defaults to `fill-opacity` / `stroke-opacity`; `rgba()` remains converter-compatible
5. FORBIDDEN: `mask`, `<style>`, `class`, `foreignObject`
6. FORBIDDEN: `textPath`, `animate*`, `script`
7. Built-in icons use one library only: `tabler-outline`

### PPT Compatibility Rules:

- Prefer opacity on each child element; `<g opacity="...">` remains compatible with an approximate-fidelity warning
- Image transparency uses overlay mask layer (`<rect fill="bg-color" opacity="0.x"/>`)
- Inline styles only; external CSS and `@font-face` FORBIDDEN
