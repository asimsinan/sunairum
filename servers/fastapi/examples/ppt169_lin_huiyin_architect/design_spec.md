# Lin Huiyin: The Architectural Master Overshadowed by Literary Fame - Design Spec

> This document is the human-readable design narrative — rationale, audience, style, color choices, content outline. It is read once by downstream roles for context.
>
> The machine-readable execution contract lives in `spec_lock.md` (short form of color / typography / icon / image decisions). Executor re-reads `spec_lock.md` before every SVG page to resist context-compression drift. Keep the two files in sync; if they diverge, `spec_lock.md` wins.

## I. Project Information

| Item | Value |
| ---- | ----- |
| **Project Name** | Lin Huiyin: An Architectural Masterpiece Overshadowed by Her Literary Aura |
| **Canvas Format** | PPT 16:9 (1280×720) |
| **Page Count** | 10 |
| **Design Style** | General Versatile (A) |
| **Target Audience** | Culture enthusiasts, architecture audiences, and readers interested in history and the humanities |
| **Use Case** | Knowledge sharing, commemorative features, and cultural outreach |
| **Created Date** | 2026-04-21 |

---

## II. Canvas Specification

| Property | Value |
| -------- | ----- |
| **Format** | PPT 16:9 |
| **Dimensions** | 1280×720 |
| **viewBox** | `0 0 1280 720` |
| **Margins** | 60px left/right, 50px top/bottom |
| **Content Area** | 1160×620 (60,50 → 1220,670) |

---

## III. Visual Theme

### Theme Style

- **Style**: General Versatile — richly illustrated, visual storytelling
- **Theme**: Dark theme
- **Tone**: Chinese classical architectural aesthetics × humanistic commemoration. Use deep navy as the foundation and antique bronze gold as the soul to create a solemn, elegant sense of history spanning time and space

### Color Scheme

| Role | HEX | Purpose |
| ---- | --- | ------- |
| **Background** | `#1A1A2E` | Deep navy page background, restrained and substantial |
| **Secondary bg** | `#16213E` | Card and section background |
| **Primary** | `#C9A96E` | Antique bronze gold for title decoration, key sections, and icons |
| **Accent** | `#E8D5B7` | Warm ivory for highlighted data and key information |
| **Secondary accent** | `#8B6F47` | Dark brown for supporting emphasis and gradient transitions |
| **Body text** | `#E8E8E8` | Light gray-white body text |
| **Secondary text** | `#A0A0B0` | Gray annotation text |
| **Tertiary text** | `#6B6B80` | Page numbers and supporting information |
| **Border/divider** | `#2A2A4A` | Card borders and dividers |
| **Success** | `#4CAF50` | Positive indicators (green) |
| **Warning** | `#E57373` | Problem markers (red) |

### Gradient Scheme

```xml
<!-- Title gradient (gold tones) -->
<linearGradient id="titleGradient" x1="0%" y1="0%" x2="100%" y2="100%">
  <stop offset="0%" stop-color="#C9A96E"/>
  <stop offset="100%" stop-color="#E8D5B7"/>
</linearGradient>

<!-- Background decorative glow -->
<radialGradient id="bgDecor" cx="80%" cy="20%" r="50%">
  <stop offset="0%" stop-color="#C9A96E" stop-opacity="0.08"/>
  <stop offset="100%" stop-color="#C9A96E" stop-opacity="0"/>
</radialGradient>

<!-- Card gradient background -->
<linearGradient id="cardGradient" x1="0%" y1="0%" x2="0%" y2="100%">
  <stop offset="0%" stop-color="#16213E"/>
  <stop offset="100%" stop-color="#1A1A2E"/>
</linearGradient>
```

---

## IV. Typography System

### Font Plan

**Recommended preset**: P3 — Culture/Arts/Humanities

| Role | Chinese | English | Fallback |
| ---- | ------- | ------- | -------- |
| **Title** | KaiTi | Georgia | serif |
| **Body** | Microsoft YaHei | Arial | sans-serif |
| **Code** | - | Consolas | Monaco |
| **Emphasis** | SimHei | Arial | sans-serif |

**Font stack**: `"KaiTi", Georgia, serif` (headings) / `"Microsoft YaHei", Arial, sans-serif` (body text)

### Font Size Hierarchy

**Baseline**: Body font size = 22px (moderate content density)

| Purpose | Ratio | Size | Weight |
| ------- | ----- | ---- | ------ |
| Cover title | 2.5x | 54px | Bold |
| Chapter title | 2x | 44px | Bold |
| Content title | 1.5x | 32px | Bold |
| Subtitle | 1.3x | 28px | SemiBold |
| **Body content** | **1x** | **22px** | Regular |
| Annotation | 0.73x | 16px | Regular |
| Page number/date | 0.55x | 12px | Regular |

---

## V. Layout Principles

### Page Structure

- **Header area**: 80px high — page title + gold decorative line
- **Content area**: 540px high — main content area
- **Footer area**: 40px high — page number + source information

### Common Layout Modes

| Mode | Suitable Scenarios |
| ---- | ----------------- |
| **Single column centered** | Cover, ending, key quotations |
| **Left-right split (4:6)** | Image-text layouts (image + text description) |
| **Left-right split (5:5)** | Two-concept comparisons |
| **Three-column cards** | Parallel points, work showcases |
| **Top-bottom split** | Ultra-wide image + text |
| **Timeline** | Life trajectories, chronological overviews |

### Spacing Specification

| Element | Value |
| ------- | ----- |
| Card gap | 24px |
| Content block gap | 32px |
| Card padding | 24px |
| Card border radius | 12px |
| Icon-text gap | 12px |
| Single-row card height | 540px |
| Double-row card height | 260px each |
| Three-column card width | 360px each |

---

## VI. Icon Usage Specification

### Source

- **Built-in icon library**: `templates/icons/chunk/` (straight-line geometric style suited to an elegant, dignified tone)
- **Library**: `chunk`
- **Usage method**: Placeholder format `{{icon:chunk/icon-name}}`

### Recommended Icon List

| Purpose | Icon Path | Page |
| ------- | --------- | ---- |
| Architecture/design | `{{icon:chunk/building}}` | Slide 03, 04 |
| Castle/historic architecture | `{{icon:chunk/castle}}` | Slide 03 |
| Museum/culture | `{{icon:chunk/museum}}` | Slide 04 |
| Map/field study | `{{icon:chunk/map}}` | Slide 05 |
| Compass/drafting | `{{icon:chunk/compass-drafting}}` | Slide 06 |
| Book/academia | `{{icon:chunk/book-open}}` | Slide 07 |
| Pen nib/writing | `{{icon:chunk/pen-nib}}` | Slide 08 |
| Crown/master | `{{icon:chunk/crown}}` | Slide 01, 10 |
| Star/achievement | `{{icon:chunk/star}}` | Slide 09 |
| Flag/pioneer | `{{icon:chunk/flag}}` | Slide 09 |
| Heart/passion | `{{icon:chunk/heart}}` | Slide 10 |
| Eye/seeing anew | `{{icon:chunk/eye}}` | Slide 02 |
| Clock/time | `{{icon:chunk/clock}}` | Slide 02 |
| Global/influence | `{{icon:chunk/globe}}` | Slide 07 |

---

## VII. Visualization Reference List

| Visualization Type | Reference Template | Used In | Purpose |
| ------------------ | ------------------ | ------- | ------- |
| timeline | `templates/charts/timeline.svg` | Slide 02 | Timeline of key moments in Lin Huiyin's life |
| icon_grid | `templates/charts/icon_grid.svg` | Slide 03 | Overview of architectural works (multi-project cards) |
| vertical_list | `templates/charts/vertical_list.svg` | Slide 07 | List of key academic contributions |

---

## VIII. Image Resource List

| Filename | Dimensions | Ratio | Purpose | Type | Status | Generation Description |
| -------- | --------- | ----- | ------- | ---- | ------ | --------------------- |
| cover_bg.png | 1280x720 | 1.78 | Cover background | Background | Pending generation | Chinese traditional architectural elements (curved tile rooflines, wooden brackets/dougong) silhouetted against a deep navy-to-midnight blue gradient sky (#1A1A2E to #16213E), golden light (#C9A96E) glowing along the roofline edges, subtle mist/cloud in lower third, clean center area reserved for title text overlay, cinematic atmospheric style |
| lin_portrait.png | 640x703 | 0.91 | Cover portrait | Photography | Existing | - |
| jihai_station_old.png | 670x346 | 1.94 | Historical photo of Jihai Railway Terminus | Photography | Existing | - |
| jihai_station_new.png | 1080x608 | 1.78 | Restored Jihai Railway Terminus | Photography | Existing | - |
| pku_geology.png | 745x414 | 1.80 | Former site of Peking University Geology Museum | Photography | Existing | - |
| yingqiu_院.png | 792x606 | 1.31 | Historical photo of Yingqiuqiu Courtyard | Photography | Existing | - |
| kunming_site.png | 1080x783 | 1.38 | Kunming construction site | Photography | Existing | - |
| babaoshan.png | 1080x712 | 1.52 | Babaoshan Revolutionary Cemetery | Photography | Existing | - |
| lin_tomb.png | 1080x796 | 1.36 | Lin Huiyin’s tombstone | Photography | Existing | - |
| monument.png | 960x1280 | 0.75 | Monument to the People’s Heroes | Photography | Existing | - |
| liang_lin_together.png | 1000x710 | 1.41 | Liang Sicheng and Lin Huiyin together | Photography | Existing | - |
| first_paper.png | 1080x810 | 1.33 | First architectural paper | Photography | Existing | - |
| lin_survey.png | 1056x1080 | 0.98 | Lin Huiyin surveying ancient architecture | Photography | Existing | - |
| lin_later.png | 857x804 | 1.07 | Lin Huiyin in later life | Photography | Existing | - |

---

## IX. Content Outline

### Part 1: Introduction

#### Slide 01 - Cover

- **Layout**: Full-screen background image + centered vertical title + figure silhouette
- **Title**: Lin Huiyin: The Architectural Master Overshadowed by a Literary Aura
- **Subtitle**: 70th Anniversary of Her Death · Rediscovering the Power of Women in Chinese Architectural History
- **Info**: Phoenix Space · 2025
- **Image**: cover_bg.png (full-screen background), lin_portrait.png (right side)

#### Slide 02 - Overview of Her Life and Career

- **Layout**: Horizontal timeline
- **Title**: The Life of an Architectural Master
- **Visualization**: timeline
- **Content**:
  - 1904 Born in Hangzhou
  - 1924 Went to the United States to study at the University of Pennsylvania
  - 1928 Married Liang Sicheng and returned to China
  - 1930 Joined the Society for Research in Chinese Architecture
  - 1932 Published her first architectural paper
  - 1937–1946 Displaced during wartime, she continued her research
  - 1949 Participated in the design of the national emblem
  - 1952 Participated in the design of the Monument to the People's Heroes
  - 1955 Died; her gravestone was inscribed "Tomb of Architect Lin Huiyin"

### Part 2: The Architect Lin Huiyin

#### Slide 03 - A Few Architectural Works (Part 1)

- **Layout**: Three-column card layout
- **Title**: Architectural practice after returning to China
- **Visualization**: icon_grid
- **Content**:
  - 1929 Liang Qichao Tomb Monument — Her first work after returning from abroad
  - 1929 Jilin University Stone Building — Participated in the design through the “Liang-Chen-Tong-Cai Construction Office”
  - 1929 Jihai Railway Terminal — Lin Huiyin designed the overall appearance, featuring a Gothic lion motif

#### Slide 04 - A Few Architectural Works (Part 2)

- **Layout**: Two-column split (4:6), image left and text right
- **Title**: Architectural Ideals Amidst War
- **Content**:
  - 1932 Peking University Geology Building and women’s dormitory — among China’s earliest introductions of Western modernist architecture
  - 1938 Yunnan University Yingqiu Hall — integrating elements of Yunnan vernacular architecture
  - 1938 Southwest Associated University campus buildings — “the most painful and aggrieved design of my life”
  - 1940 Kunming residence — the only house the two architects ever designed for themselves
- **Image**: kunming_site.png

#### Slide 05 - Landmark Works

- **Layout**: Two-column split (5:5), text left and image right
- **Title**: Architectural Imprints on the Nation’s Monuments
- **Content**:
  - 1950 Babaoshan Revolutionary Cemetery — designed the main architectural layout
  - 1952 Monument to the People’s Heroes — proposed creative revisions
  - Personally designed the complete ornamental patterns and garland reliefs on the pedestal
  - Based on Tang-dynasty style, expressing the aesthetics of traditional Chinese architecture
  - Only seven characters appear on the tombstone: Architect Lin Huiyin’s Tomb
- **Image**: monument.png

### Part 3: An Underestimated Academic Pioneer

#### Slide 06 - A Pioneer of Chinese Architectural Theory

- **Layout**: Two-column split (4:6), image left and text right
- **Title**: Her First Architectural Paper: A Stunning Debut
- **Content**:
  - 1932 *Several Characteristics of Chinese Architecture* — the first architectural theory paper published by a Chinese professional scholar
  - The first theoretical definition of the basic characteristics of China’s timber-frame structural system
  - Challenged Western scholars’ misinterpretations of Chinese architecture
  - Outlined a complete conceptual framework for Chinese architectural history
- **Image**: first_paper.png

#### Slide 07 - Original Concepts and Ahead-of-the-Curve Thinking

- **Layout**: Vertical key-point list
- **Title**: Overview of Academic Contributions
- **Visualization**: vertical_list
- **Content**:
  - The concept of “architectural meaning” — An original Chinese architectural philosophy in which architecture brings together technology, beauty, history, and human feeling
  - Introduction to *Examples of Qing-Style Construction* — Summarized the theoretical framework of Chinese architecture
  - Pioneer in vernacular architecture research — First in Chinese architectural circles to advocate the preservation of vernacular buildings
  - *References for Modern Housing Design* — Foresightedly proposed designing architecture for ordinary people after the war
  - First to offer a “General Introduction to Housing” course — Systematically taught modern housing design theory at Tsinghua University for the first time in 1949

### Part 4: Powerhouses and Spirit

#### Slide 08 - A Life Far More Astonishing Than the Rumors

- **Layout**: Two-column split (5:5), text left and image right
- **Title**: An Architectural Warrior Through the Flames of War
- **Content**:
  - Surveyed ancient architecture in remote valleys and wilderness, braving the elements without retreat
  - "Whatever Mr. Liang dared to climb, Mr. Lin dared to climb too"
  - Suffered a bout of pneumonia while displaced by war and never fully recovered afterward
  - Persisted with her illness, documenting Chinese architectural history stroke by stroke in remote towns
  - "What do I care about beauty or anything else? I still have so much to do!"
- **Image**: lin_survey.png

#### Slide 09 - The Work She Wants to Pursue for a Lifetime

- **Layout**: Introductory quote card + achievement summary
- **Title**: An Architect Beyond Question
- **Content**:
  - Introduction: "I myself have reached a considerable age, yet I have achieved nothing… I cannot help but feel sad" — from a letter to Hu Shi at age 28
  - Co-founded the architecture departments at Northeastern University and Tsinghua University with Liang Sicheng
  - Measured ancient architecture inch by inch in desolate regions
  - Devoted her final efforts to the national emblem and the Monument to the People's Heroes
  - She was not only a founder of the discipline, but also a pioneer in thought

#### Slide 10 - Conclusion

- **Layout**: Single centered column, quotation style
- **Title**: Architect Lin Huiyin's Tomb
- **Subtitle**: She Spent Her Life Proving That She Was an Architect in Every Sense of the Word
- **Content**:
  - Central gold vertical-line decoration
  - Quotation from the tombstone inscription
  - Tribute
  - Source information

---

## X. Speaker Notes Requirements

- **File naming**: Match SVG names (e.g., `01_cover.svg` → `notes/01_cover.md`)
- **Total duration**: ~15 minutes
- **Notes style**: Narrative, combining historical gravitas with human warmth
- **Presentation purpose**: Inspire + Inform (tribute and knowledge sharing)
- **Content includes**: Key points for each page, supplementary historical details, and transition phrases

---

## XI. Technical Constraints Reminder

### SVG Generation Must Follow:

1. viewBox: `0 0 1280 720`
2. Background uses `<rect>` elements
3. Text wrapping uses `<tspan>` (`<foreignObject>` FORBIDDEN)
4. Transparency defaults to `fill-opacity` / `stroke-opacity`; `rgba()` remains converter-compatible
5. FORBIDDEN: `mask`, `<style>`, `class`, `foreignObject`
6. FORBIDDEN: `textPath`, `animate*`, `script`
7. `marker-start` / `marker-end` conditionally allowed: `<marker>` must be in `<defs>`, `orient="auto"`, shape must be triangle / diamond / circle

### PPT Compatibility Rules:

- Prefer opacity on each child element; `<g opacity="...">` remains compatible with an approximate-fidelity warning
- Image transparency uses overlay mask layer (`<rect fill="bg-color" opacity="0.x"/>`)
- Inline styles only; external CSS and `@font-face` FORBIDDEN
