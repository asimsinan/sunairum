# Weaving Clouds and Moonlight, Turning Plants into Poetry — Design Spec

> This document is a human-readable design narrative—it includes the design rationale, audience, style, color choices, and content outline. It is read once by the downstream role (Executor) to establish context.
>
> The machine-readable execution contract is stored in `spec_lock.md` (a simplified short table of color / font / icon / image decisions). The Executor rereads `spec_lock.md` before generating each page’s SVG to resist long-document context drift. The two files must remain synchronized; in case of conflict, `spec_lock.md` takes precedence.

## I. Project Information

| Item | Value |
| ---- | ----- |
| **Project Name** | liziqi-plant-dye-colors |
| **Canvas Format** | PPT 16:9 (1280×720) |
| **Page Count** | 12 |
| **Design Style** | A) General Versatile — Eastern cultural storytelling |
| **Target Audience** | Culture enthusiasts, designers, traditional aesthetics learners, and museum/education professionals |
| **Use Case** | Cultural sharing events / designer lectures / museum talks / aesthetics courses |
| **Created Date** | 2026-04-21 |

---

## II. Canvas Specification

| Property | Value |
| -------- | ----- |
| **Format** | PPT 16:9 |
| **Dimensions** | 1280×720 |
| **viewBox** | `0 0 1280 720` |
| **Margins** | 60px left/right, 50px top/bottom |
| **Content Area** | 1160×620 |

---

## III. Visual Theme

### Theme Style

- **Style**: Eastern botanical-dye aesthetics · cultural storytelling
- **Theme**: Light (rice-paper beige background)
- **Tone**: Elegant · understated · poetic · warm · handmade

### Color Scheme (drawn from traditional colors actually present in the article)

| Role | HEX | Purpose |
| ---- | --- | ------- |
| **Background (xuan paper white)** | `#F7F2E8` | Main page background, evoking the texture of xuan paper |
| **Secondary bg (moon white)** | `#EDE5D3` | Cards, chapter backgrounds, secondary areas |
| **Primary (clear blue after rain)** | `#6B9AAE` | Main visual, chapter color, decorative lines |
| **Accent (Chinese tallow yellow)** | `#C99E62` | Subtitles, emphasis, secondary visual elements |
| **Secondary accent (malan blue-green)** | `#6F8F75` | Gradient transitions, secondary emphasis |
| **Accent 2 (dull red)** | `#B04A5C` | Keywords and key highlights, used sparingly |
| **Body text (tea-ink)** | `#3A3530` | Main body color |
| **Secondary text (evening-cloud gray)** | `#7A7068` | Notes, secondary text, quotations |
| **Tertiary text (light ink)** | `#9B948B` | Footers, metadata |
| **Border/divider (light beige-gray)** | `#D7CEB9` | Dividers, outlines, card borders |

### Gradient Scheme (using SVG syntax, without rgba)

```xml
<!-- Battle robe dip-dye gradient: smoke tree → indigo blue -->
<linearGradient id="diaoyanGradient" x1="0%" y1="0%" x2="0%" y2="100%">
  <stop offset="0%" stop-color="#C99E62"/>
  <stop offset="100%" stop-color="#6F8F75"/>
</linearGradient>

<!-- Rain-washed cerulean gradient for chapter title page -->
<linearGradient id="titleGradient" x1="0%" y1="0%" x2="100%" y2="0%">
  <stop offset="0%" stop-color="#6B9AAE"/>
  <stop offset="100%" stop-color="#6F8F75"/>
</linearGradient>

<!-- Background decoration (rain-washed cerulean wash) -->
<radialGradient id="bgDecor" cx="85%" cy="15%" r="55%">
  <stop offset="0%" stop-color="#6B9AAE" stop-opacity="0.10"/>
  <stop offset="100%" stop-color="#6B9AAE" stop-opacity="0"/>
</radialGradient>
```

---

## IV. Typography System

### Font Plan

**Recommended preset**: P3 (culture/art)

| Role | Chinese | English | Fallback |
| ---- | ------- | ------- | -------- |
| **Title** | KaiTi / STKaiti | Georgia | serif |
| **Body** | Microsoft YaHei / PingFang SC | Arial | sans-serif |
| **Code** | - | Consolas | Monaco |
| **Emphasis (quotes / color names)** | KaiTi | Georgia | serif |

**Font stack**: `"KaiTi", "STKaiti", "Microsoft YaHei", "PingFang SC", Georgia, serif`

### Font Size Hierarchy

**Baseline**: Body font size = **22px** (moderate density, conducive to reading long classical sentences)

| Purpose | Ratio | Size | Weight |
| ------- | ----- | ---- | ------ |
| Cover title | 3x | 66px | Bold |
| Chapter title | 2.3x | 50px | Bold |
| Content title | 1.6x | 36px | Bold |
| Subtitle | 1.2x | 26px | SemiBold |
| **Body content** | **1x** | **22px** | Regular |
| Annotation | 0.8x | 18px | Regular |
| Page number/date | 0.6x | 13px | Regular |

---

## V. Layout Principles

### Page Structure

- **Header area**: 72px high (page number + chapter line + small decorative stamp)
- **Content area**: 580px high (main visual area)
- **Footer area**: 40px high (footer / project name / divider)

### Common Layout Modes

| Mode | Pages Used |
| ---- | ------ |
| **Single column centered** | Cover, introduction, conclusion |
| **Left-right split (5:5)** | Two-color side-by-side comparison pages |
| **Left-right split (4:6)** | Image-text layout (image left, text right) |
| **Top-bottom split** | Historical timelines, process pages |
| **Four column cards** | Dye plant classification |

### Spacing Specification

| Element | Value |
| ------- | ----- |
| Card gap | 28px |
| Content block gap | 36px |
| Card padding | 26px |
| Card border radius | 12px |
| Icon-text gap | 12px |
| Single-row card height | 540px |
| Double-row card height | 275px each |

---

## VI. Icon Usage Specification

### Source

- **Library**: `tabler-filled` (rounded Bézier-curve style, suited to plants, nature, and Eastern aesthetics)
- **Usage method**: `{{icon:tabler-filled/<name>}}`

### Recommended Icon List

| Purpose | Icon Path | Page |
| ------- | --------- | ---- |
| Plant/leaf | `{{icon:tabler-filled/leaf}}` | 03, 09, 10 |
| Flower | `{{icon:tabler-filled/flower}}` | 09, 11 |
| Droplet/dye | `{{icon:tabler-filled/droplet}}` | 03, 10 |
| Color palette | `{{icon:tabler-filled/palette}}` | 05, 06, 07, 08 |
| Books | `{{icon:tabler-filled/book}}` | 04, 12 |
| History | `{{icon:tabler-filled/history}}` | 04 |
| Heart/healing | `{{icon:tabler-filled/heart}}` | 10 |
| Starlight | `{{icon:tabler-filled/sparkles}}` | 02, 12 |
| Paintbrush | `{{icon:tabler-filled/brush}}` | 03, 11 |
| Moon | `{{icon:tabler-filled/moon}}` | 06, 08 |

> The final usable list is confirmed and locked by the Executor using `ls templates/icons/tabler-filled/ | grep <keyword>`.

---

## VII. Visualization Reference List

| Visualization Type | Reference Template | Used In |
| ------------------ | ------------------ | ------- |
| `timeline` | `templates/charts/timeline.svg` | Slide 04 (timeline of plant-dyeing history) |
| `numbered_steps` | `templates/charts/numbered_steps.svg` | Slide 10 (plant-dyeing process steps) |
| `icon_grid` | `templates/charts/icon_grid.svg` | Slide 09 (classification of dye plants) |

---

## VIII. Image Resource List

> Images are sourced from the original public WeChat article and used directly in the presentation (for cultural-sharing purposes). All images are stored in `images/`.

| Filename | Dimensions | Ratio | Purpose | Type | Status |
| -------- | ---------- | ----- | ------- | ---- | ------ |
| `640.png` | 1080×605 | 1.79 | Spring Festival opening visual show screenshot (Li Ziqi) | Photography | Existing |
| `640_4.png` | 800×1291 | 0.62 | Full-body close-up of Li Ziqi in ceremonial attire | Photography | Existing |
| `640.jpg` | 900×1200 | 0.75 | Li Ziqi and Huang Ronghua collaborating on tie-dyeing | Photography | Existing |
| `640_1.png` | 1080×279 | 3.87 | Detail from *Court Ladies Preparing Newly Woven Silk* by Zhang Xuan of the Tang dynasty | Illustration | Existing |
| `640_5.png` | 1024×802 | 1.28 | Ru ware celadon-glazed round washer from the Song dynasty | Photography | Existing |
| `640_1.jpg` | 943×602 | 1.57 | Huang Ronghua dyeing a sky-blue silk scarf | Photography | Existing |
| `640_6.png` | 1080×720 | 1.50 | Grayish-yellow mood image | Photography | Existing |
| `640_7.png` | 1080×720 | 1.50 | Evening-cloud gray mood image | Photography | Existing |
| `640_8.png` | 400×265 | 1.51 | Tianshui jade color swatch | Photography | Existing |
| `640_10.png` | 800×600 | 1.33 | Huang Ronghua dyeing a silver-red silk scarf | Photography | Existing |
| `640_11.png` | 1080×684 | 1.58 | Still from *Farewell My Concubine* in reddish-brown tones | Photography | Existing |
| `640_12.png` | 403×228 | 1.77 | Dark cyan color swatch | Photography | Existing |
| `640_13.png` | 1080×721 | 1.50 | Lovesick gray mood image | Photography | Existing |
| `640_14.png` | 1080×699 | 1.55 | Dye plants (madder, safflower, etc.) | Photography | Existing |
| `640_15.png` | 640×640 | 1.00 | Plant-dyeing process | Photography | Existing |
| `640_17.png` | 1080×1072 | 1.01 | Xue Tao paper imagery in *Dream of Splendor* | Photography | Existing |
| `640_18.png` | 974×731 | 1.33 | Dyed Xue Tao paper finished product | Photography | Existing |

---

## IX. Content Outline

### Part 1: Opening — Dazzling at the Spring Festival Gala

#### Slide 01 - Cover

- **Layout**: Single centered column + vertical stamp-style title on the left + image on the right
- **Title**: Cutting Clouds, Weaving Moonlight · Turning Plants into Poetry
- **Subtitle**: The 300 Traditional Chinese Colors Made from Plants Behind Li Ziqi's Spring Festival Gala Gown
- **Image**: `640.png` (Spring Festival Gala screenshot) on the right · main vertical title on the left
- **Footer**: From · Phoenix Space | 2026.04

#### Slide 02 - Opening

- **Layout**: Two-column split (image left, text right; 0.62 portrait image centered on the left)
- **Title**: The Most Moving Colors
- **Image**: `640_4.png` (close-up of ceremonial attire, portrait 0.62)
- **Content**:
  - Core idea: "The most moving colors are not found in a Pantone swatch book—they have long been hidden among mountains, rivers, plants, and trees"
  - Visual show 《Welcoming Fortune》 at the 2025 Spring Festival Gala
  - Brings together 13 intangible cultural heritage techniques
  - Yellow-to-teal gradient · Transformed into a butterfly fairy

---

### Part 2: Decoding the Battle Outfit

#### Slide 03 - Decoding the Battle Robe: Five Directional Colors × Hand-Dyed Hanging Technique

- **Layout**: Split vertically · Two color blocks side by side above + tie-dye process diagram below
- **Title**: Decoding the battle robe · Five traditional colors × artisanal dip-dyeing
- **Image**: `640.jpg` (Li Ziqi and Huang Ronghua collaborating on dip-dyeing), small image on the right
- **Content**:
  - **Yellow**: Made from smoketree gathered in Shennongjia, Hubei → represents **the land**
  - **Cyan**: Made from malan grass in early spring in Jiangnan → represents **spring**
  - **Meaning**: Chinese land · Ever-renewing life
  - **Dip-dyeing process**: Suspend the fabric → immerse it in dye → pull it up 1 centimeter every 30 seconds → create an ink-wash-like gradient

#### Slide 04 - Plant Dyeing: A Millennium-Long Journey Through Dyeing Techniques

- **Layout**: Split vertically (decorative strip from *Court Ladies Preparing Newly Woven Silk* at the top + timeline below)
- **Title**: The art of dyeing · Dating back to the age of the Yellow Emperor
- **Visualization**: `timeline`
- **Image**: `640_1.png` (ultra-wide image of *Court Ladies Preparing Newly Woven Silk*, 3.87, as the top decorative strip)
- **Content** (5 milestones):
  - **Age of the Yellow Emperor**: The Yellow Emperor made dark crowns and yellow robes, using plant juices to dye decorative patterns
  - **Western Zhou**: Established a dedicated position for “dyeing officials”
  - **Qin dynasty**: Established the “Dyeing Office”
  - **Tang and Song dynasties**: Established “Dyeing Workshops”
  - **Ming and Qing dynasties**: Established the “Indigo Office”; techniques documented in *Essential Techniques for the Welfare of the People* and *The Exploitation of the Works of Nature*

---

### Part 3: Botanical Hues — Dyeing Nature’s Colors

#### Slide 05 - Colors of Vegetation (I): After-Rain Sky Blue × Yellow-Green

- **Layout**: Two-column split (5:5), two colors side by side
- **Title**: Colors of Plants and Trees (I) · Dyeing the Natural World
- **Image**: `640_5.png` (Ru kiln round basin) left + `640_6.png` (Canghuang) right
- **Content**:
  - **Rain-Cleared Sky Blue `#7AA4B6`** | Emperor Huizong of Song: “After rain, the sky turns blue as clouds part—make this color for me” | 95% earth indigo + 5% scutellaria, overdyeing
  - **Canghuang `#B29A55`** | The color of spring herald birds and young deer | Rhubarb + sappanwood, copper-vitriol mordant

#### Slide 06 - Colors of Vegetation (II): Twilight Cloud Gray × Sky-Water Jade

- **Layout**: Two-column split (5:5), two colors side by side
- **Title**: Colors of Plants and Trees (II) · Evening Clouds and Dew-Dyed Green
- **Image**: `640_7.png` (Evening Cloud Gray) left + `640_8.png` (Tianshui Green) right
- **Content**:
  - **Evening Cloud Gray `#7D6E74`** | Liu Yong: “A thousand miles of misty waves, dusk haze sinking deep”; Li Qingzhao: “The setting sun melts gold, evening clouds join jade” | Sappanwood dye, copper vitriol + ferrous vitriol mordants
  - **Tianshui Green `#8FB09A`** | Consort of Li Yu of Southern Tang · Silk dyed by staying overnight in the dew | Moon-white dyed with indigo, with minimal yellow overdyeing

---

### Part 4: Poetic Hues — Recreating Literary Atmosphere

#### Slide 07 - Poetic Colors (Part 1): Silver Red × Tawny

- **Layout**: Two-column split (5:5), two colors side by side
- **Title**: Poetic Colors (I) · Dawn-Tinted Rose and Wine-Flushed Cheeks
- **Image**: `640_10.png` (silver-red silk scarf) left + `640_11.png` (Farewell My Concubine) right
- **Content**:
  - **Silver Red `#E49AA5`** | Pale rose · dawn’s first blush · the rosy gauze shadow before Daiyu’s window | Safflower + sappanwood + cinnabar, alum mordant
  - **Tuo `#C86868`** | “A beauty about to drink, her vermilion face flushed” · The Drunken Concubine | Red-blue dye / sappanwood / madder, alum mordant

#### Slide 08 - Poetic Colors (Part 2): Deep Teal × Lovesick Gray

- **Layout**: Two-column split (5:5), two colors side by side
- **Title**: Poetic Colors (II) · Deep Brow Blue and Longing Turned Gray
- **Image**: `640_12.png` (Daiqing) left + `640_13.png` (Lovesick Gray) right
- **Content**:
  - **Daiqing `#3D4A5A`** | The color of painted brows · Wang Shifu’s *Romance of the Western Chamber*: “brows dark with a blue-green frown” | Indigo extracted from the indigo plant
  - **Lovesick Gray `#A69E98`** | Li Shangyin: “Let not spring desire compete with flowers; an inch of longing, an inch of ash” | Tea leaves + pomegranate peel, ferrous vitriol mordant

---

### Part 5: Botanical Healing — Hand Dyeing

#### Slide 09 - Plant Dyes: Four Colors from Plants

- **Layout**: Four-column cards (`icon_grid`)
- **Title**: Dye Plants · Four Colors, All Drawn from Nature
- **Visualization**: `icon_grid`
- **Image**: `640_14.png` (dye plants) as header decoration
- **Content** (4 color cards):
  - **Red**: Madder root / Sappanwood stem / Safflower petals
  - **Yellow**: Sophora flower buds / Gardenia fruit / Turmeric rhizome
  - **Blue**: Indigo plant / Buckthorn leaves and stems
  - **Black**: Walnut shells / Chestnut shells

#### Slide 10 - Hand-Dyeing with Plants · A Process of Self-Healing

- **Layout**: Image left + process flow right (4:6)
- **Title**: Hand-Dyeing with Plants · A Process of Self-Healing
- **Visualization**: `numbered_steps`
- **Image**: `640_15.png` (dyeing process), left
- **Content** (5 steps):
  1. **Boil water** — Bring clean water to a boil in a pot
  2. **Add materials** — Immerse the plant dye
  3. **Simmer** — Steep for 1–2 hours and strain out the dye bath
  4. **Dye** — Place the fabric in the dye bath
  5. **Set the color** — Warm it in the sun to fix the color
  - Closing: "The feelings of tension and anxiety gradually disappeared"

---

### Part 6: Cultural Context and Heritage

#### Slide 11 - Xue Tao Jian · Elegance Can Be Recreated

- **Layout**: Image left, text right (4:6)
- **Title**: Xue Tao Paper · A Thousand Years of Elegance, Recreated
- **Image**: `640_17.png` (The Longest Day in Chang'an) on the left, `640_18.png` as a secondary image
- **Content**:
  - Tang-dynasty poet **Xue Tao** pounded juice from **Huanhua Creek water + cotton rose bark + cotton rose flowers**
  - Dyed it into **“hibiscus red”** writing paper
  - Modern recreation: **sappanwood + alum** produces the best results
  - “A window into Eastern aesthetics”

#### Slide 12 - Closing: Color, the Bearer of Cultural Memory

- **Layout**: Single centered column + stamp-style ending
- **Title**: Color Is More Than Visual · It Carries Cultural Memory
- **Content**:
  - From the colors of plants shaped by heaven and earth
  - To the splendor of silk woven across millennia
  - **Traditional Chinese Colors** = Visual Experience × Cultural Memory
  - Reference: *300 Traditional Chinese Colors* (by Huang Ronghua · Jiangsu People's Press)
- **Footer**: The End

---

## X. Speaker Notes Requirements

- **Total duration**: Approximately 12–15 minutes
- **Notes style**: Explanatory · elegant formal language · moderate use of poetry quotations
- **Purpose**: Share (inspire + instruct)
- **File naming**: `notes/<slide_name>.md` (same name as the SVG)
- **Content per slide**: 3–5 sentences of key narration + transitional bridges + pacing cues

---

## XI. Technical Constraints Reminder

### SVG Generation Must Follow:

1. viewBox: `0 0 1280 720`
2. Background uses `<rect>`
3. Text wrapping uses `<tspan>` (`<foreignObject>` forbidden)
4. Transparency defaults to `fill-opacity` / `stroke-opacity`; `rgba()` remains converter-compatible
5. Forbidden: `clipPath` (except for images), `mask`, `<style>`, `class`, `foreignObject`
6. Forbidden: `textPath`, `<animate*>`, `<script>`, `<symbol>` + `<use>`
7. `marker-start` / `marker-end` conditionally allowed (defined in `<defs>`; arrows are triangles / diamonds / circles)

### PPT Compatibility Rules:

- Set opacity on child elements individually by default; `<g opacity="...">` can be converted but may produce an approximate-fidelity warning
- Use a masking rectangle overlay for image transparency
- Inline styles only; external CSS and `@font-face` are prohibited
- All icons must use the `tabler-filled/` prefix (this project is locked to a single icon library)
