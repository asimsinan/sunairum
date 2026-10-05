# Concealing One’s Talent - Design Spec

## I. Project Information

| Item | Value |
| ---- | ----- |
| **Project Name** | cangzhuo (《The Ultimate Man's Strategic Reserve: Concealing One's Strength》) |
| **Canvas Format** | PPT 16:9 (1280×720) |
| **Page Count** | 14 |
| **Design Style** | A) General Audience + New Chinese Ink-Wash Minimalism |
| **Target Audience** | Male professionals 30+ / readers interested in self-cultivation / WeChat Official Account sharing |
| **Use Case** | Social sharing, book discussions, and personal growth course materials |
| **Created Date** | 2026-05-16 |

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

- **Style**: Neo-Chinese / ink-wash whitespace / literati sensibility
- **Theme**: Light theme (rice-paper background)
- **Tone**: Quiet, restrained, literary, imbued with Eastern philosophy

### Color Scheme

| Role | HEX | Purpose |
| ---- | --- | ------- |
| **Background** | `#F5F1E8` | Xuan-paper ivory, full-page background |
| **Secondary bg** | `#EFEAD9` | Secondary background / card background (slightly darker than the main background) |
| **Primary** | `#1A1A1A` | Ink black for titles, body text, and dark blocks |
| **Accent** | `#A52A2A` | Cinnabar for key text, seals, and key-argument emphasis |
| **Body text** | `#1A1A1A` | Body text |
| **Secondary text** | `#5C5852` | Secondary text and quotation sources |
| **Tertiary text** | `#8B8680` | Distant-mountain gray for supporting elements, page numbers, and notes |
| **Border/divider** | `#C8C0AE` | Dividers and seal outlines |

### AI Image Strategy

- **Image Rendering**: `ink-notes`
- **Image Palette**: `mono-ink`

---

## IV. Typography System

### Font Plan

**Typography direction**: Kai-style titles + modern Black-style body text (the Kai × Hei contrast axis)

| Role | Chinese | English | Fallback tail |
| ---- | ------- | ------- | ------------- |
| **Title** | `KaiTi` | `Georgia` | `serif` |
| **Body** | `"Microsoft YaHei", "PingFang SC"` | `Arial` | `sans-serif` |
| **Emphasis** | `KaiTi` | `Georgia` | `serif` |
| **Code** | — | `Consolas, "Courier New"` | `monospace` |

**Per-role font stacks**:

- Title: `KaiTi, Georgia, serif`
- Body: `"Microsoft YaHei", "PingFang SC", Arial, sans-serif`
- Emphasis: `KaiTi, Georgia, serif`
- Code: `Consolas, "Courier New", monospace`

### Font Size Hierarchy

**Baseline**: Body = 24px (relaxed pacing, prioritizing ease of reading and sharing)

| Purpose | Ratio | Size |
| ------- | ----- | ---- |
| Cover title | 3.3x | 80px |
| Chapter / section opener | 2.5x | 60px |
| Page title | 1.5–1.8x | 36–44px |
| Hero number / large quotation text | 2x | 48px |
| Subtitle | 1.3x | 32px |
| **Body** | **1x** | **24px** |
| Annotation / caption | 0.75x | 18px |
| Page number / footer | 0.6x | 14px |

---

## V. Layout Principles

### Page Structure

- **Header area**: 60–80px (header stamp or section number, optional)
- **Content area**: 500–560px (main content)
- **Footer area**: 40px (page number / signature)

### Layout Pattern Library (combine or break as content demands)

| Pattern | Use in this deck |
| ------- | ----------------- |
| Single column centered | Cover / introduction / conclusion |
| Symmetric split (5:5) | Strategic reserve vs passive withdrawal comparison |
| Asymmetric split (3:7 / 2:8) | Introduction + interpretation |
| Three/four column cards | Three qualities of top-tier composure |
| Full-bleed + floating text | Breathing page (cover, introduction, chapter transition) |
| Negative-space-driven | Standalone proof page (Crouching Dragon, Hidden Talent / The Tall Tree Catches the Wind) |
| Figure-text overlap | Han Xin anecdote page |

### Spacing Specification

**Universal**:

| Element | Value |
| ------- | ----- |
| Safe margin | 60px left and right / 50px top and bottom |
| Content block gap | 32px |
| Icon-text gap | 12px |

**Card-based**:

| Element | Value |
| ------- | ----- |
| Card gap | 24px |
| Card padding | 28px |
| Card border radius | 8px |
| Three-column card width | 360px |
| Four-column card width | 268px |

**Non-card**: Line-height = 1.6×; on breathing pages, body text is centered within a 720–900px width and adjusted freely according to content volume.

---

## VI. Icon Usage Specification

### Source

- **Built-in icon library**: `tabler-outline` (stroke_width = 1.5, light linear style that complements the ink-wash negative-space aesthetic)
- **Usage method**: SVG placeholder `<use data-icon="tabler-outline/<name>" stroke-width="1.5"/>`

### Recommended Icon List

| Purpose | Icon Path | Page |
| ------- | --------- | ---- |
| Chapter symbol / quotation | `tabler-outline/quote` | P02, P05, P10 |
| No-show / hidden | `tabler-outline/eye-off` | P04, P07 |
| Edge / weapon | `tabler-outline/sword` | P06, P09 |
| Shield / defense | `tabler-outline/shield` | P09 |
| Time / waiting | `tabler-outline/hourglass` | P10, P12 |
| Mountain / stability | `tabler-outline/mountain` | P12 |
| Heart / emotion | `tabler-outline/heart` | P13 |
| Bullet / list | `tabler-outline/point-filled` | General |

---

## VII. Visualization Reference List

> This is a humanistic philosophical essay, with very few data-visualization pages. Only 2 pages use chart templates as structural scaffolding; all others use freeform layouts.

Catalog read: 71 templates

| Page | Template | Path | Summary-quote (verbatim) | Usage |
| ---- | -------- | ---- | ------------------------ | ----- |
| P11 | pros_cons_chart | `templates/charts/pros_cons_chart.svg` | "Pick for bilateral pros/cons list, 2-5 items per side. Skip for full feature comparison (use comparison_table) or numeric A/B mirror data (u…)" | Four-dimensional comparison: strategic reserve vs passive withdrawal |
| P13 | vertical_list | `templates/charts/vertical_list.svg` | "Pick for 3-6 numbered key points each with a short description — design principles, core tenets, action items, key takeaways, recommendation…" | Hide four things → cultivate four strengths (core output page) |

**Runners-up considered** (fewer than 3 viz pages, runners-up listed per page):

- `comparison_table` | rejected for P11: Only four dimensions and two columns are being compared; pros_cons is visually cleaner. `comparison_table` is better suited to dense multi-column, multi-row matrices
- `principles_grid` (not in the library) → `vertical_pillars` | rejected for P13: The four “conceal → nurture” pairs are homogeneous entries; `vertical_list`’s “number + title + description” format is a better fit
- `numbered_steps` | rejected for P13: This page presents four parallel principles, not sequential steps; turning them into steps would mislead readers into assuming an order

---

## VIII. Image Resource List

| Filename | Dimensions | Ratio | Purpose | Type | Layout pattern | Acquire Via | Status | Reference | text_policy | page_role |
| -------- | --------- | ----- | ------- | ---- | -------------- | ----------- | ------ | --------- | ----------- | --------- |
| cover_bg.png | 1280×720 | 1.78 | Cover background: distant ink-wash mountains with negative space | Background | #1 full-bleed background with floating title + #29 two-stop scrim | ai | Pending | Distant misty mountain range in ink wash style, vast empty paper sky on top three-fifths reserved for vertical title, sparse brushstrokes, a single tiny boatman silhouette on a lake at lower right; deep silence and restraint | none | hero_page |
| yinzi_bg.png | 1280×720 | 1.78 | Introduction background: hidden-edge atmosphere | Background | #12 faded image as backdrop with oversized overlay text + #30 flat semi-transparent rectangle overlay | ai | Pending | A half-sheathed brushstroke or ink trail receding into white paper, calm left two-thirds reserved for floating quotation text, a single faint seal mark in the lower-right corner; suggests withdrawn force without revealing it | none | hero_page |
| hanxin_bridge.png | 1280×720 | 1.78 | Han Xin humiliation-under-the-legs scene | Illustration | #4 right image bleeding off the canvas edge + #29 two-stop scrim | ai | Pending | Lone scholar-warrior figure standing quietly under a stone bridge in an ancient market street, ink-wash brushwork, no facial detail, body language steady rather than humbled, crowd as faint ink dots in background; restraint as strength | none | local |
| qianlong_pool.png | 1280×720 | 1.78 | Qianlong Wuyong atmosphere | Background | #1 full-bleed background with floating title + #28 radial gradient vignette | ai | Pending | Deep still pool surrounded by craggy ink-wash cliffs, suggestion of a coiled dragon shape barely visible beneath the water surface as faint darker ink swirls, mist rising; latent power waiting for its time | none | hero_page |
| zengguofan_lamp.png | 1280×720 | 1.78 | Zeng Guofan “dumb work” atmosphere | Illustration | #2 left-third image + right text body + #21 rounded rectangle crop | ai | Pending | Single oil lamp on a wooden desk with stacked ancient books and an open ink-stone, no human figure, view through a paper window showing pre-dawn darkness; persistence in solitude | none | local |
| closing_mountain.png | 1280×720 | 1.78 | Conclusion: There is always another mountain beyond | Background | #1 full-bleed background with floating title + #29 two-stop scrim | ai | Pending | Layered ink-wash mountain ridges receding into the distance, foreground sharp dark mountain, middle and far ridges progressively lighter into mist, vast empty sky reserved for closing quote; depth and patience | none | hero_page |

> **Image-as-canvas (#38–#46) coverage note**: This piece is a literary and philosophical essay, with no pages requiring a "structured information layer overlaid on the image," such as KPIs / process nodes / dashboards / network architecture diagrams; all image-bearing pages are atmosphere-driven (hero / atmosphere), while native SVG text layers independently carry the information, so the #38–46 family is not needed. This is a reasonable deviation determined by the nature of this deck's content.

---

## IX. Content Outline

### Part 1: Introduction

#### Slide 01 — Cover

- **Layout**: Full-bleed background image + centered vertical title + subtitle + byline（page_rhythm: anchor）
- **Title**: The Highest Form of Male Composure: Concealing Your Strength
- **Subtitle**: Stay steady, stay discreet, wait it out
- **Info**: The Art of Strategy · The Logic of Getting Things Done

#### Slide 02 — Opening

- **Layout**: Full-bleed faded backdrop + large centered quote（page_rhythm: breathing）
- **Title**:（No title; the quote is the subject）
- **Content**: "Showing your cards too early is handing someone else a knife."

### Part 2: Seeing the Problem

#### Slide 03 — The Barbecue Stall Story

- **Layout**: Side-by-side comparison (5:5 split) + one-line summary at the bottom (page_rhythm: dense)
- **Title**: Two Kinds of People at a Barbecue Stall
- **Content**:
  - Left: The newly promoted person—opens by talking about resources, connections, and projects; onlookers flatter him verbally while calculating silently
  - Right: Another man—says little, asks only the key questions, and has figured out seven or eight tenths of everyone’s hand by the time they leave
  - Bottom: "Many games in this world are not lost because of a lack of ability, but because people reveal their abilities too soon"

#### Slide 04 — What Is Concealing One’s Talent

- **Layout**: Three-column cards (page_rhythm: dense)
- **Title**: Concealing your strengths ≠ playing dumb ≠ giving up
- **Content**: Three core actions
  - Put your sharpness away
  - Keep your desires in check
  - Move yourself out of the center of other people’s attention

#### Slide 05 — The Tree That Stands Out in the Forest

- **Layout**: Full-bleed + large centered quotation (page_rhythm: breathing)
- **Title**: (Quotation page, no subtitle)
- **Content**: "When a tree stands out in the forest, the wind will destroy it" — *Zengguang Xianwen*
- Interpretation: When your strength is not yet enough to protect you, standing out becomes a risk

### Part 3: Common Errors

#### Slide 06 — The Mistake Young People Make Most Easily

- **Layout**: 2x2 grid cards + one sentence at the bottom (page_rhythm: dense)
- **Title**: Mistaking "Being Seen" for "Being Respected"
- **Content**:
  - The moment they achieve a little, they want everyone to know
  - The moment they gain some resources, they cannot resist showing them off
  - The moment they see through a little of human nature, they rush to expose it
  - Bottom: People in the spotlight have no cover; every probe, envy, attempt to leverage them, and act of sabotage comes their way first

#### Slide 07 — How to Hide Your Weaknesses

- **Layout**: Three-column comparison + quote at bottom (page_rhythm: dense)
- **Title**: Don’t waste your edge on small stages
- **Content**:
  - At dinners — Don’t interrupt
  - In meetings — Don’t rush to take a position
  - In a crowd — Don’t hurry to flaunt your connections
  - Bottom: “Silence is not emptiness; it is gathering information. Yielding is not weakness; it is refusing to waste ammunition on worthless targets.”

### Part 4: Historical Evidence

#### Slide 08 — Han Xin’s Humiliation Under the Legs

- **Layout**: Full-bleed image on the right + text on the left (page_rhythm: anchor)
- **Title**: Han Xin's Humiliation Under the Crotch
- **Content**:
  - Not to glorify humiliation
  - But because he refused to stake his life on a street confrontation
  - Winning the small battle might only vent one's anger; winning the larger game earns the chance to turn one's life around

#### Slide 09 — The Art of Concealing One's Strengths

- **Layout**: Four-row table (`page_rhythm: dense`)
- **Title**: Turn “Clumsiness” into a Shield
- **Content**: Performance × Others’ Reactions, four-row comparison
  - Too smart → They guard against you
  - Too forceful → They avoid you
  - Too eager → Resource holders drive down your price
  - Too determined to win → Opponents drag you into the game
  - Bottom: Being a little slower, duller, and more understated can actually reduce unnecessary exhaustion

#### Slide 10 — The Hidden Dragon Awaits Its Time

- **Layout**: Full-bleed + centered quotation (page_rhythm: breathing)
- **Title**: (Quotation page)
- **Content**: "The hidden dragon must not act" — *I Ching*
- Interpretation: When the dragon is in the abyss, it is not without power; the time has simply not yet come

### Part 5: Distinguishing the Differences

#### Slide 11 — Concealing One’s Strengths ≠ Passive Withdrawal from the World

- **Layout**: pros_cons_chart, two-column comparison (page_rhythm: dense)
- **Title**: Concealing your strengths ≠ passive withdrawal from the world
- **Visualization**: pros_cons_chart
- **Content**: Four-dimensional comparison
  - Motivation: passivity = fear of losing vs concealing your strengths = preparing to win
  - State: passivity = the more you hide, the weaker you become vs concealing your strengths = the more you hide, the deeper you grow
  - Silence: passivity = an excuse vs concealing your strengths = gathering strength
  - Inner world: passivity = resentment vs concealing your strengths = strategic positioning

#### Slide 12 — The Zeng Guofan Archetype

- **Layout**: Image left + text right (page_rhythm: anchor)
- **Title**: Zeng Guofan: The Hard Work, Slow Work, and Deep Work
- **Content**:
  - He was not known for his intelligence early in life and was even considered slow-witted
  - What he relied on: hard work / slow work / deep work
  - He did not chase momentary speed or grasp for the slightest clever shortcut
  - At its deepest, clumsiness becomes composure; once composure is strong enough, circumstances gradually begin to turn in his favor

### Part 6: Core Deliverables

#### Slide 13 — Hide Four Things, Cultivate Four Strengths

- **Layout**: vertical_list, four numbered principles (page_rhythm: dense)
- **Title**: Conceal four things, cultivate four kinds of strength
- **Visualization**: vertical_list
- **Content**:
  - 01 Conceal your emotions → Don’t let a few words provoke you
  - 02 Conceal your ambitions → Don’t let others prepare for you prematurely
  - 03 Conceal your capabilities → Don’t let others exhaust you too early
  - 04 Conceal your judgment → Don’t be forced to take sides before the situation is clear

#### Slide 14 — Closing Remarks

- **Layout**: Full-bleed distant mountain landscape + three centered lines of short phrases + byline（page_rhythm: anchor）
- **Title**: Ultimate Composure = Restrain the Need to Show Off × Keep Your Competitive Nerve Steady × Delay Gratification
- **Content**:
  - Stay steady, and you won't fear being temporarily underestimated
  - Stay discreet, and you won't fear a moment without applause
  - Be willing to wait, and you'll earn the right to let the results speak for themselves when the moment to act arrives

---

## X. Speaker Notes Requirements

- File naming: `notes/01_cover.md` … `notes/14_closing.md`
- Style: conversational (prose-like, avoiding business jargon)
- Purpose: inspire (spread ideas / build resonance / trigger reflection)
- Duration per page: approximately 30–45 seconds of narration

---

## XI. Technical Constraints Reminder

### SVG Generation Must Follow:

1. viewBox: `0 0 1280 720`
2. Use `<rect>` elements for the background color
3. Text wrapping uses `<tspan>` (`<foreignObject>` forbidden)
4. Transparency defaults to `fill-opacity` / `stroke-opacity`; `rgba()` remains converter-compatible
5. Forbidden: `mask` / `<style>` / `class` / `foreignObject` / `textPath` / `animate*` / `script`
6. Write characters in text directly as Unicode (`— · → " " ©`); HTML entities (`&nbsp;`, `&mdash;`, etc.) are forbidden; escape XML reserved characters as needed (`&amp;`, `&lt;`)

### PPT Compatibility Rules:

- Set opacity on child elements by default; `<g opacity="...">` can be converted but may produce an approximate-fidelity warning
- Use an overlay rectangle for image transparency (`<rect fill="bg-color" opacity="0.x"/>`)
- Inline styles only; external CSS and `@font-face` are prohibited
