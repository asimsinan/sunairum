# 2026 Home Trends - Design Spec

> This document is the human-readable design narrative — rationale, audience, style, color choices, content outline. It is read once by downstream roles for context.
>
> The machine-readable execution contract lives in `spec_lock.md` (short form of color / typography / icon / image decisions). Executor re-reads `spec_lock.md` before every SVG page to resist context-compression drift. Keep the two files in sync; if they diverge, `spec_lock.md` wins.

## I. Project Information

| Item | Value |
| ---- | ----- |
| **Project Name** | 2026 Home Trends: Returning to the “Human Scale” |
| **Canvas Format** | PPT 16:9 (1280×720) |
| **Page Count** | 12 |
| **Design Style** | General Versatile (A) |
| **Target Audience** | Interior designers, home enthusiasts, and people planning renovations |
| **Use Case** | Home design trend sharing/training presentation |
| **Created Date** | 2026-04-22 |

---

## II. Canvas Specification

| Property | Value |
| -------- | ----- |
| **Format** | PPT 16:9 |
| **Dimensions** | 1280×720 |
| **viewBox** | `0 0 1280 720` |
| **Margins** | left/right 60px, top/bottom 50px |
| **Content Area** | 1160×620 |

---

## III. Visual Theme

### Theme Style

- **Style**: General Versatile — magazine-quality image-and-text composition
- **Theme**: Dark theme (dark, warm-toned background)
- **Tone**: Premium, warm, natural, humanistic, magazine-like

### Color Scheme

| Role | HEX | Purpose |
| ---- | --- | ------- |
| **Background** | `#1A1714` | Deep brown warm-black background |
| **Secondary bg** | `#2A2520` | Card / area background |
| **Primary** | `#C4A882` | Title decoration and warm golden tones |
| **Accent** | `#D4956A` | Data highlights and key information |
| **Secondary accent** | `#8B7355` | Gradient transitions and secondary decoration |
| **Body text** | `#E8E0D4` | Main text (light warm white) |
| **Secondary text** | `#B0A08E` | Annotations and explanations |
| **Tertiary text** | `#7A6E60` | Supplementary information and footers |
| **Border/divider** | `#3D362E` | Card borders and dividers |
| **Success** | `#7BA37B` | Sustainability / positive indicators |
| **Warning** | `#C06048` | Emphasis / warnings |

### Gradient Scheme

```xml
<!-- Title gradient -->
<linearGradient id="titleGradient" x1="0%" y1="0%" x2="100%" y2="0%">
  <stop offset="0%" stop-color="#C4A882"/>
  <stop offset="100%" stop-color="#D4956A"/>
</linearGradient>

<!-- Background decorative gradient -->
<radialGradient id="bgDecor" cx="80%" cy="20%" r="50%">
  <stop offset="0%" stop-color="#C4A882" stop-opacity="0.08"/>
  <stop offset="100%" stop-color="#C4A882" stop-opacity="0"/>
</radialGradient>
```

---

## IV. Typography System

### Font Plan

**Typography direction**: Editorial Display — serif titles convey sophistication, while sans-serif body text ensures readability.

| Role | Chinese | English | Fallback tail |
| ---- | ------- | ------- | ------------- |
| **Title** | `SimSun` | `Georgia` | `serif` |
| **Body** | `"Microsoft YaHei"`, `"PingFang SC"` | `Arial` | `sans-serif` |
| **Emphasis** | `SimSun` | `Georgia` | `serif` |
| **Code** | — | `Consolas, "Courier New"` | `monospace` |

**Per-role font stacks**:

- Title: `Georgia, SimSun, serif`
- Body: `"Microsoft YaHei", "PingFang SC", Arial, sans-serif`
- Emphasis: `Georgia, SimSun, serif`
- Code: `Consolas, "Courier New", monospace`

### Font Size Hierarchy

**Baseline**: Body font size = 22px (moderate content density, typically 3–5 key points per page)

| Purpose | Ratio to body | Size | Weight |
| ------- | ------------- | ---- | ------ |
| Cover title | 3.6x | 80px | Bold |
| Chapter opener | 2.2x | 48px | Bold |
| Page title | 1.5x | 32px | Bold |
| Subtitle | 1.3x | 28px | SemiBold |
| **Body content** | **1x** | **22px** | Regular |
| Annotation / caption | 0.73x | 16px | Regular |
| Page number / footnote | 0.55x | 12px | Regular |

---

## V. Layout Principles

### Page Structure

- **Header area**: 50-80px, including the page title and decorative elements
- **Content area**: 560-620px, primary visual and textual content area
- **Footer area**: 30-40px, page number and source information

### Layout Pattern Library

This project centers on image-and-text layouts and primarily uses the following formats:

| Pattern | Used In |
| ------- | ------- |
| **Full-bleed + floating text** | P01 cover, P10 sustainable luxury |
| **Asymmetric split (4:6 / 3:7)** | P03 color, P05 material, P06 texture, P08 cream aesthetic |
| **Symmetric split (5:5)** | P04 color practice, P09 bohemian & vintage |
| **Center-radiating** | P07 CMT system |
| **Single column centered** | P02 introduction |
| **Three-column cards** | P11 book recommendations |
| **Negative-space-driven** | P12 conclusion |

### Spacing Specification

**Universal**:

| Element | Current Project |
| ------- | --------------- |
| Safe margin from canvas edge | 60px |
| Content block gap | 30px |
| Icon-text gap | 10px |

**Card-based layouts** (P07, P11):

| Element | Current Project |
| ------- | --------------- |
| Card gap | 24px |
| Card padding | 24px |
| Card border radius | 12px |

---

## VI. Icon Usage Specification

### Source

- **Built-in icon library**: `templates/icons/tabler-filled/` — rounded Bezier curves that suit a warm home/lifestyle aesthetic
- **Usage method**: Placeholder format `{{icon:tabler-filled/icon-name}}`

### Recommended Icon List

| Purpose | Icon Path | Page |
| ------- | --------- | ---- |
| Color theme | `{{icon:tabler-filled/palette}}` | P03, P04 |
| Material theme | `{{icon:tabler-filled/diamond}}` | P05 |
| Texture theme | `{{icon:tabler-filled/paint}}` | P06 |
| Home | `{{icon:tabler-filled/home}}` | P01, P02 |
| Sun/light | `{{icon:tabler-filled/sun}}` | P05 |
| Leaf/nature | `{{icon:tabler-filled/leaf}}` | P10 |
| Star/highlight | `{{icon:tabler-filled/sparkles}}` | P07 |
| Heart/emotion | `{{icon:tabler-filled/heart}}` | P12 |
| Books | `{{icon:tabler-filled/book}}` | P11 |
| Eye/vision | `{{icon:tabler-filled/eye}}` | P06 |
| Adjustments | `{{icon:tabler-filled/adjustments}}` | P07 |
| Star marker | `{{icon:tabler-filled/star}}` | P08 |

---

## VII. Visualization Reference List

| Visualization Type | Reference Template | Used In |
| ------------------ | ------------------ | ------- |
| concentric_circles | `templates/charts/concentric_circles.svg` | P07 (three-layer CMT system) |

---

## VIII. Image Resource List

| Filename | Dimensions | Ratio | Purpose | Intent | Type | Status |
| -------- | ---------- | ----- | ------- | ------ | ---- | ------ |
| intro_living.png | 1080x608 | 1.78 | P01 cover full-screen background | Hero | Photography | Existing |
| space_overview.png | 800x540 | 1.48 | P02 introduction image | Side-by-side | Photography | Existing |
| color_wheel.png | 559x823 | 0.68 | P03 color theory image | Side-by-side | Diagram | Existing |
| brown_cozy.png | 658x496 | 1.33 | P03 cozy brown space | Accent | Photography | Existing |
| light_tone_room.png | 749x749 | 1.00 | P04 light-toned space | Side-by-side | Photography | Existing |
| saturated_room.png | 853x671 | 1.27 | P04 highly saturated space | Side-by-side | Photography | Existing |
| material_detail.png | 749x708 | 1.06 | P05 material details | Side-by-side | Photography | Existing |
| light_material.png | 800x1000 | 0.80 | P05 light and material | Accent | Photography | Existing |
| texture_tactile.png | 615x398 | 1.55 | P06 tactile texture | Side-by-side | Photography | Existing |
| texture_visual.png | 519x569 | 0.91 | P06 visual texture | Side-by-side | Photography | Existing |
| cmt_overview.png | 990x744 | 1.33 | P07 CMT system overview | Side-by-side | Photography | Existing |
| cmt_neutral_mix.png | 1023x636 | 1.61 | P07 neutral color combination | Accent | Photography | Existing |
| dark_tone_luxury.png | 614x423 | 1.45 | P07 dark-toned luxury | Accent | Photography | Existing |
| cream_style.png | 681x499 | 1.36 | P08 cream-style space | Side-by-side | Photography | Existing |
| bohemian_style.png | 615x924 | 0.67 | P09 bohemian style | Side-by-side | Photography | Existing |
| retro_style.png | 1080x608 | 1.78 | P09 nostalgic retro style | Side-by-side | Photography | Existing |
| sustainable_luxury.png | 417x500 | 0.83 | P10 sustainable luxury | Side-by-side | Photography | Existing |
| book_cover1.png | 1080x732 | 1.48 | P11 book cover | Side-by-side | Photography | Existing |
| book_cover2.png | 1080x735 | 1.47 | P11 back cover | Accent | Photography | Existing |
| book_inside1.png | 1080x741 | 1.46 | P11 book interior spread | Accent | Photography | Existing |
| book_inside2.png | 1080x738 | 1.46 | P11 book interior spread | Accent | Photography | Existing |
| book_display1.png | 1080x727 | 1.49 | P12 book display | Side-by-side | Photography | Existing |
| book_display2.png | 1080x743 | 1.45 | P12 book display | Accent | Photography | Existing |

---

## IX. Content Outline

### Part 1: Introduction

#### Slide 01 - Cover

- **Layout**: Full-bleed + floating text
- **Title**: 2026 Home Trends
- **Subtitle**: Returning to the "human scale," letting colour, material, and texture shape the "sophistication of space"
- **Info**: Based on *The Sophistication of Space* · 2026
- **Images**: `intro_living.png` (full-screen hero, with a dark gradient overlay to ensure text legibility)

#### Slide 02 - From "Influencer Aesthetic" to "Human Scale"

- **Layout**: Single column centered + side-by-side image
- **Title**: From “Instagrammable style” to “human scale”
- **Images**: `space_overview.png`
- **Content**:
  - Home “Instagrammable styles” have changed rapidly over the past few years
  - The shift in 2026: from piling up visual symbols to returning to human-centered care
  - Sophistication = a refined combination of color + materials + textures
  - Visually appealing, with greater warmth and emotional resonance

### Part 2: Three Foundational Elements

#### Slide 03 - Color: The Emotional Magician of Space

- **Layout**: Asymmetric split (4:6) — Image left, text right
- **Title**: Colour: The "Mood Magician" of Space
- **Images**: `color_wheel.png` (main image on the left), `brown_cozy.png` (small accent image at the bottom right)
- **Content**:
  - Colour is a space's first impression
  - It can alter visual scale and create atmosphere
  - Warm tones → a gentle enveloping feeling; cool tones → openness and calm
  - Different colours convey different signals and psychological responses

#### Slide 04 - Color Practice: The Spatial Effects of Warm and Cool Tones

- **Layout**: Symmetric split (5:5) — side-by-side comparison
- **Title**: Comparing the spatial effects of cool and warm tones
- **Images**: `light_tone_room.png` (left, light tones), `saturated_room.png` (right, high saturation)
- **Content**:
  - Left: Light tones → greater light reflection → a more spacious feel
  - Right: High saturation → a more compact, intimate room
  - Gray-green → calm focus; coffee brown → wrapped in sunlight; accent colors → personality and energy

#### Slide 05 - Materiality: A Tangible Spatial Language

- **Layout**: Asymmetric split (3:7) — large image on the right
- **Title**: Material: A Spatial Language Within Reach
- **Images**: `material_detail.png` (main image), `light_material.png` (secondary/accent image)
- **Content**:
  - Materials are the physical foundation of color pairing
  - Natural wood flooring → rustic warmth; handwoven textiles → relaxed ease
  - Light itself is also a material
  - Clever lighting + colored light and shadow → a premium feel without relying on expensive materials

#### Slide 06 - Texture: Details That Give Space Its Soul

- **Layout**: Asymmetric split (5:5) — Side-by-side
- **Title**: Texture: Details That Give a Space Its Soul
- **Images**: `texture_tactile.png` (left, tactile), `texture_visual.png` (right, visual)
- **Content**:
  - Texture = a space's "fingerprint," with unique recognisability
  - Tactile texture: wool carpet → soft and warm; rough ceramic vase → raised and recessed surface
  - Visual texture: wallpaper patterns → the eyes "feel" the texture

### Part 3: The CMT Framework

#### Slide 07 - CMT System: A Symphony of Color, Material, and Texture

- **Layout**: Center-radiating + accent images
- **Title**: The CMT System: Weaving a Fully Sensory Experience
- **Visualization**: concentric_circles (three CMT layers)
- **Images**: `cmt_overview.png` (main visual), `cmt_neutral_mix.png` (neutral-toned example), `dark_tone_luxury.png` (dark-toned example)
- **Content**:
  - CMT = Colour + Material + Texture
  - Physical layer: smooth/rough, transparent/opaque, glossy/matte
  - Psychological layer: handmade/industrial, simple/luxurious, comforting/stimulating
  - Not simple layering, but systematic weaving — like the conductor of a symphony orchestra

### Part 4: 2026 Trend Styles

#### Slide 08 - The Evolution of the Cream Aesthetic

- **Layout**: Asymmetric split (4:6) — Text left, image right
- **Title**: Cream Style 2.0: From Formulaic to Nuanced Expression
- **Images**: `cream_style.png`
- **Content**:
  - Cream style is undergoing a profound "evolution"
  - No longer just the formula of "off-white walls + natural wood furniture"
  - Colour base: cream, oatmeal, off-white
  - Material accents: wool, linen, naturally knotted wood, handmade ceramics
  - A truly healing space = touchable + perceptible

#### Slide 09 - Bohemian & Nostalgic Retro

- **Layout**: Symmetric split (5:5) — two contrasting styles
- **Title**: Free spirits and memories of time
- **Images**: `bohemian_style.png` (left, bohemian), `retro_style.png` (right, nostalgic retro)
- **Content**:
  - Bohemian: Bold colors + free-flowing textiles + handmade tapestries → “layered nonconformity”
  - Nostalgic retro: Weathered wood + wrought iron + wicker → a “sense of time” marked by use
  - Shared trait: A longing for authenticity and emotion

#### Slide 10 - Sustainable Luxury

- **Layout**: Full-bleed + floating text (breathing page)
- **Title**: Sustainable Luxury: Responsible Aesthetics
- **Images**: `sustainable_luxury.png`
- **Content**:
  - In 2026, luxury is no longer an accumulation of expensive materials
  - Eco-friendly finishes, natural light, reclaimed wood, cork, and jute fibres
  - From "conspicuous consumption" to "responsible aesthetics"
  - A philosophy of living in harmony with the world

### Part 5: Closing Remarks

#### Slide 11 - One Book Unlocks a Sophisticated Sense of Space

- **Layout**: Three-column cards (book display)
- **Title**: *The Sophistication of Space* — A deconstructable, replicable, and verifiable aesthetic system
- **Images**: `book_cover1.png`, `book_cover2.png`, `book_inside1.png`, `book_inside2.png`
- **Content**:
  - Author: Song Wenwen (Executive Deputy Director, Color Research Institute, Tsinghua University)
  - Introduces the innovative CMF → CMT framework
  - Color + Materials + Textures + Synthesis
  - Suitable for: Professional development for designers / self-study for homeowners

#### Slide 12 - Closing

- **Layout**: Negative-space-driven + accent image
- **Title**: Bring Home Back to the Human Scale
- **Images**: `book_display1.png`, `book_display2.png`
- **Content**:
  - The essence of sophistication: a subtle resonance of color, material, and texture
  - Beautiful to look at, yet full of warmth and emotion
  - Reference: "The Sophistication of Space — A Designer's Guide to Combining Color, Material, and Texture"

---

## X. Speaker Notes Requirements

Generate corresponding speaker note files for each page, saved to the `notes/` directory:

- **File naming**: Match SVG names, e.g., `01_cover.md`
- **Content includes**: Script key points, timing cues, transition phrases
- **Style**: Natural and conversational, suitable for design trend-sharing sessions
- **Duration**: Approximately 15-20 minutes total
- **Purpose**: Inform + Inspire

---

## XI. Technical Constraints Reminder

### SVG Generation Must Follow:

1. viewBox: `0 0 1280 720`
2. Background uses `<rect>` elements
3. Text wrapping uses `<tspan>` (`<foreignObject>` FORBIDDEN)
4. Transparency defaults to `fill-opacity` / `stroke-opacity`; `rgba()` remains converter-compatible
5. FORBIDDEN: `clipPath`, `mask`, `<style>`, `class`, `foreignObject`
6. FORBIDDEN: `textPath`, `animate*`, `script`
7. `marker-start` / `marker-end` conditionally allowed: `<marker>` must be in `<defs>`, `orient="auto"`, shape must be triangle / diamond / circle

### PPT Compatibility Rules:

- Prefer opacity on each child element; `<g opacity="...">` remains compatible with an approximate-fidelity warning
- Image transparency uses overlay mask layer (`<rect fill="bg-color" opacity="0.x"/>`)
- Inline styles only; external CSS and `@font-face` FORBIDDEN
