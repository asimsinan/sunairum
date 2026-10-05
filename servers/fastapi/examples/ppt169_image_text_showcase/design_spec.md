# Image-Text Showcase — Design Spec

> Human-readable design narrative. Machine-readable contract: `spec_lock.md`. On divergence, `spec_lock.md` wins.

## I. Project Information

| Item | Value |
| ---- | ----- |
| **Project Name** | Image-Text Showcase |
| **Canvas Format** | PPT 16:9 (1280×720) |
| **Page Count** | 20 |
| **Design Style** | A) General Versatile + editorial-showcase |
| **Target Audience** | Designers, PPT creators, and AI tool users |
| **Use Case** | Demonstration of image-text integration / visual sample collection |
| **Created Date** | 2026-05-15 |

---

## II. Canvas Specification

| Property | Value |
| -------- | ----- |
| **Format** | PPT 16:9 |
| **Dimensions** | 1280×720 |
| **viewBox** | `0 0 1280 720` |
| **Margins** | left/right 60px, top/bottom 50px |
| **Content Area** | 1160×620 (x=60, y=50) |

---

## III. Visual Theme

### Theme Style

- **Style**: A) General Versatile + editorial-showcase
- **Theme**: An independent theme for each page (dark/light varies by each page’s rendering)
- **Tone**: Multiple visual languages placed side by side; each page is an independent sample of visual style

### Color Scheme

> Each page’s colors follow its rendering × palette combination. The following are SVG structural colors (not image colors).

| Role | HEX | Purpose |
| ---- | --- | ------- |
| **Background** | `#0F1117` | Default dark background (may vary by page) |
| **Secondary bg** | `#1A1D2E` | Card / section background |
| **Primary** | `#7C6FF7` | Dominant purple-blue |
| **Accent** | `#F5A623` | Golden-orange emphasis |
| **Secondary accent** | `#4ECDC4` | Teal contrast |
| **Body text** | `#E8E8F0` | Light gray-white body text |
| **Secondary text** | `#9090A0` | Explanatory text |
| **Tertiary text** | `#5A5A72` | Page numbers / supplementary information |
| **Border/divider** | `#2A2D3E` | Borders and dividers |
| **Success** | `#4CAF50` | Positive indicators |
| **Warning** | `#EF5350` | Warning markers |

### AI Image Strategy

Each page independently specifies its rendering × palette (see §VIII and §IX), rather than using a uniform lock.

---

## IV. Typography System

**Typography direction**: contrast — serif title × sans body

| Role | Chinese | English | Fallback tail |
| ---- | ------- | ------- | ------------- |
| **Title** | `"Microsoft YaHei"` | `Georgia` | `serif` |
| **Body** | `"Microsoft YaHei", "PingFang SC"` | `Arial` | `sans-serif` |
| **Emphasis** | `"Microsoft YaHei"` | `Georgia` | `serif` |
| **Code** | — | `Consolas, "Courier New"` | `monospace` |

**Per-role font stacks**:
- Title: `Georgia, "Microsoft YaHei", serif`
- Body: `Arial, "Microsoft YaHei", "PingFang SC", sans-serif`
- Emphasis: `Georgia, "Microsoft YaHei", serif`
- Code: `Consolas, "Courier New", monospace`

**Baseline**: Body = 20px

| Purpose | Ratio | @ 20px |
| ------- | ----- | ------ |
| Cover title | 3-5x | 60-100px |
| Chapter opener | 2-2.5x | 40-50px |
| Page title | 1.5-2x | 30-40px |
| Subtitle | 1.2-1.5x | 24-30px |
| **Body** | **1x** | **20px** |
| Annotation | 0.7-0.85x | 14-17px |
| Page number | 0.5-0.65x | 10-13px |

---

## V. Layout Principles

### Page Structure

- **Header area**: y=0~80px, page title or whitespace
- **Content area**: y=80~670px, main content area
- **Footer area**: y=670~720px, page number/annotations

### Layout Pattern Library

Each page of this project uses a different layout; see §IX Content Outline for details.

### Spacing Specification

| Element | Value |
| ------- | ----- |
| Safe margin | 60px (left/right), 50px (top/bottom) |
| Content block gap | 32px |
| Card gap | 24px |
| Card padding | 28px |
| Card border radius | 12px |

---

## VI. Icon Usage Specification

**Library**: `tabler-outline`, stroke-width `2`

| Purpose | Icon Path | Page |
| ------- | --------- | ---- |
| Text-image integration | `tabler-outline/layout-collage` | P02 TOC |
| Full-bleed layout | `tabler-outline/frame` | P02 TOC |
| Two-column layout | `tabler-outline/layout-columns` | P02 TOC |
| Text-image overlay | `tabler-outline/layers-intersect` | P02 TOC |
| Card grid | `tabler-outline/layout-grid` | P02 TOC |
| Image | `tabler-outline/photo` | P02 TOC |
| Color palette | `tabler-outline/palette` | P02 TOC |
| Artboard | `tabler-outline/artboard` | P02 TOC |

---

## VII. Visualization Reference List

Catalog read: 71 templates

This project primarily uses image-and-text layouts, with no data visualization pages and no charts template library.

No-template-match: all pages use custom layouts designed to demonstrate image-text composition patterns.

---

## VIII. Image Resource List

One AI-generated image per page; rendering × palette are specified independently for each page.

| Filename | Dimensions | Ratio | Purpose | Type | Acquire Via | Status | Reference | text_policy | page_role |
| -------- | --------- | ----- | ------- | ---- | ----------- | ------ | --------- | ----------- | --------- |
| p01_cover.png | 1280×720 | 1.78 | Cover full-bleed background | Background | ai | Pending | Futuristic frosted glass panels layered over deep space; calm center reserved for title overlay; subtle light refractions at edges | none | hero_page |
| p03_left_img.png | 427×620 | 0.69 | Left one-third vertical image | Photography | ai | Pending | Professional editorial portrait: diverse creative team collaborating, modern studio, natural sidelighting, shallow depth of field | none | local |
| p04_right_img.png | 800×720 | 1.11 | Large right-side bleed image | Illustration | ai | Pending | Bold flat vector composition: abstract geometric cityscape with sharp color blocks; right edge bleeds off canvas | none | local |
| p05_top_img.png | 1280×320 | 4.0 | Full-width top horizontal image | Background | ai | Pending | Soft watercolor wash: mountain lake at dawn, wide panoramic, muted pastel reflections, top-heavy composition leaving bottom clear | none | local |
| p06_bottom_img.png | 1280×360 | 3.56 | Full-width bottom image | Illustration | ai | Pending | Hand-drawn sketch: cozy reading corner, warm pencil lines, pastel color fills, bottom-weighted scene with open sky at top | none | local |
| p07_z_img1.png | 560×200 | 2.8 | First Z-section image | Illustration | ai | Pending | Isometric 3D tech object: server rack or CPU chip, clean shadows, top-left anchor composition | none | local |
| p07_z_img2.png | 560×200 | 2.8 | Third Z-section image | Illustration | ai | Pending | Isometric 3D network diagram: connected nodes and cables, same isometric angle as img1 | none | local |
| p08_grid_center.png | 400×400 | 1.0 | Nine-grid center image | Illustration | ai | Pending | Blueprint-style technical schematic: circuit board with grid lines, monospace annotations, monochrome blue-on-dark | none | local |
| p09_circle_img.png | 400×400 | 1.0 | Circular center image | Illustration | ai | Pending | Digital dashboard interface fragment: glowing circular gauge, data rings, dark background, high-tech UI aesthetic | none | local |
| p10_bg_texture.png | 1280×720 | 1.78 | Full-bleed textured background | Background | ai | Pending | Pixel art cityscape at night: 8-bit buildings and neon signs tiled across the full canvas, vibrant saturated colors | none | hero_page |
| p11_papercut.png | 1280×720 | 1.78 | Layered paper-cut background | Illustration | ai | Pending | Layered paper-cut landscape: four depth layers of mountains and trees, each layer a different earthy green tone, soft cast shadows | none | hero_page |
| p12_poster_img.png | 256×720 | 0.36 | Narrow vertical magazine image | Illustration | ai | Pending | Mid-century vintage poster fragment: bold geometric shapes, halftone texture, limited three-color palette, vertical composition | none | local |
| p13_diagonal_img.png | 700×420 | 1.67 | Upper diagonal image | Illustration | ai | Pending | Fantasy animation style: dreamy forest scene with soft glowing particles, warm amber light filtering through canopy, Ghibli-inspired atmosphere | none | local |
| p14_fade_bg.png | 1280×720 | 1.78 | Faded background image | Background | ai | Pending | Ink-wash painting: abstract brushstrokes suggesting mountains and mist, desaturated earthy tones, large central negative space | none | hero_page |
| p15_bottom_img.png | 1280×360 | 3.56 | Lower-half image | Illustration | ai | Pending | Flat design scene: modern office workspace seen from above, geometric furniture shapes, jewel-tone color palette, clean flat view without isometric perspective | none | local |
| p16_center_img.png | 480×480 | 1.0 | Central circular image | Illustration | ai | Pending | Minimalist Swiss-style graphic: single bold geometric form (circle or square) centered on white field, aggressive negative space, Helvetica-era precision | none | local |
| p17_strip_img.png | 1280×240 | 5.33 | Narrow strip across the middle | Illustration | ai | Pending | Screen-print style banner: bold halftone pattern, limited two-color duotone treatment, horizontal rhythm of repeated graphic motifs | none | local |
| p18_polygon_img.png | 600×500 | 1.2 | Irregular polygon image | Illustration | ai | Pending | Organic nature illustration: lush tropical leaves and botanical elements arranged in a loose hexagonal cluster, earthy warm greens | none | local |
| p19_collage1.png | 380×320 | 1.19 | Montage image 1 | Photography | ai | Pending | Editorial magazine photo: urban architecture detail, dramatic shadow play, high contrast, cropped unconventionally | none | local |
| p19_collage2.png | 380×320 | 1.19 | Montage image 2 | Photography | ai | Pending | Editorial magazine photo: close-up textured surface — fabric or concrete, abstract pattern, monochromatic | none | local |
| p19_collage3.png | 460×320 | 1.44 | Montage image 3 (wide) | Photography | ai | Pending | Editorial magazine photo: motion-blurred street scene, long-exposure light trails, cool blue atmosphere | none | local |
| p20_closing.png | 1280×720 | 1.78 | Closing background | Background | ai | Pending | Chalk drawing on blackboard: simple constellation of dots and hand-drawn lines forming a subtle geometric pattern, warm white chalk marks on dark green surface | none | hero_page |

---

## IX. Content Outline

### Part 1: Cover & Navigation

#### Slide 01 — Cover

- **Layout**: Full-bleed background image + centered floating title block
- **Rendering × Palette**: `glassmorphism` × `dark-cinematic`
- **Image**: p01_cover.png (hero_page, full-bleed)
- **Title**: Image and Text Combined
- **Subtitle**: An Experiment in Juxtaposing 20 Visual Languages
- **Info**: PPT Master · 2026

#### Slide 02 — Contents

- **Layout**: Dark color block on the left + numbered list on the right (no image)
- **Rendering × Palette**: No image, using the project’s primary palette
- **Content**: A 20-page style overview, one line per entry

### Part 2: Image–Text Combination Samples

#### Slide 03 — Vertical Image on the Left 1/3 + Main Text on the Right

- **Layout**: Vertical image width=427px on the left, text area width=733px on the right
- **Rendering × Palette**: `corporate-photo` × `cool-corporate`
- **Image**: p03_left_img.png
- **Title**: Editorial Photography × Professional Blue
- **Content**: A vertical portrait sits on the left, while text expands across the right; an approximately 3:7 image-to-text ratio suits narrative pages centered on text

#### Slide 04 — Image on the Right, Text on the Left; Image Bleeds to the Right Edge

- **Layout**: Left text area width=440px, right image bleeding to the edge width=840px
- **Rendering × Palette**: `vector-illustration` × `frost-ice`
- **Image**: p04_right_img.png
- **Title**: Vector Illustration × Frost White
- **Content**: A flat vector illustration occupies and bleeds off the right side, while text floats on the left; a large image and small text create tension

#### Slide 05 — Full-Width Image at the Top + Three Columns of Text at the Bottom

- **Layout**: Upper half: full-width image, height=360px; lower half: three equal-width text columns, height=310px
- **Rendering × Palette**: `watercolor` × `warm-earth`
- **Image**: p05_top_img.png
- **Title**: Watercolor Rendering × Warm Earth Tones
- **Content**: A wide watercolor image fills the upper section, with three short text columns arranged below like captions

#### Slide 06 — Full-Width Image at the Bottom + Title at the Top + Text in the Middle

- **Layout**: Top title area height=120px, middle text area height=200px, full-width image at bottom height=360px
- **Rendering × Palette**: `sketch-notes` × `macaron`
- **Image**: p06_bottom_img.png
- **Title**: Hand-Drawn Sketches × Macaron
- **Content**: The image sits at the bottom like a stage set, with text floating above; warm, hand-drawn feel

#### Slide 07 — Three-Part Z-Shaped Alternating Text-and-Image Serpentine

- **Layout**: Three alternating rows: image left, text right → text left, image right → image left, text right; each section height≈190px
- **Rendering × Palette**: `3d-isometric` × `tech-neon`
- **Image**: p07_z_img1.png, p07_z_img2.png
- **Title**: Isometric 3D × neon tech
- **Content**: Z-shaped visual flow; two isometric 3D images interwoven with three text sections

#### Slide 08 — Nine-Grid Text-and-Image Layout

- **Layout**: 3×3 grid, center cell holds the image; the other 8 cells hold text/color blocks
- **Rendering × Palette**: `blueprint` × `editorial-classic`
- **Image**: p08_grid_center.png
- **Title**: Blueprint Technology × Editorial Classic
- **Content**: Circuit-board image centered, with the surrounding 8 cells filled with title, description, annotation, and other text elements

#### Slide 09 — Circular Image Centered + Text Radiating from the Four Corners

- **Layout**: Centered circular crop, diameter=380px, with one text block in each corner
- **Rendering × Palette**: `digital-dashboard` × `mono-ink`
- **Image**: p09_circle_img.png (circular `clipPath` crop)
- **Title**: Digital Dashboard × Monochrome Ink
- **Content**: A high-tech dashboard image displayed in a circle, with corner text radiating outward like annotations

#### Slide 10 — Full-Bleed Image Texture + Densely Arranged Text Information

- **Layout**: Full-frame tiled image background with a dark overlay; text densely distributed across four areas
- **Rendering × Palette**: `pixel-art` × `vivid-launch`
- **Image**: p10_bg_texture.png (hero_page)
- **Title**: Retro Pixel × Vivid Launch
- **Content**: Four information cards arranged over an 8-bit pixel background, with neon typography echoing the pixel aesthetic

#### Slide 11 — Layered Papercut Stacks + Text Embedded in Each Layer

- **Layout**: Full-bleed image as a paper-cut background, with text blocks embedded between the paper-cut layers
- **Rendering × Palette**: `paper-cut` × `nature-organic`
- **Image**: p11_papercut.png (hero_page)
- **Title**: Paper-Cut Art × Organic Nature
- **Content**: A multilayered paper-cut mountain scene, with text distributed across different depth layers to simulate lettering embedded in the paper

#### Slide 12 — Vertical Magazine: Narrow Image on the Left 20% + Large Horizontal Headline

- **Layout**: Vertical image strip width=256px on the left, large title + body text filling the remaining 1024px on the right
- **Rendering × Palette**: `vintage-poster` × `duotone`
- **Image**: p12_poster_img.png
- **Title**: Vintage Poster × Duotone
- **Content**: A narrow vertical image stands along the left edge like a book spine, while large typography on the right is arranged like a magazine cover

#### Slide 13 — Diagonal Split: Image Top Left, Text Bottom Right

- **Layout**: Diagonal split, with an image in the upper-left triangle and text in the lower-right triangle
- **Rendering × Palette**: `fantasy-animation` × `sunset-gradient`
- **Image**: p13_diagonal_img.png
- **Title**: Fantasy Animation × Sunset Gradient
- **Content**: A Ghibli-style forest image fills the upper left, with text arranged in the lower-right triangle; diagonal tension

#### Slide 14 — Image Faded into the Background + Large Overlaid Text

- **Layout**: Full-bleed, low-saturation image with oversized text (font-size≈80px) overlaid directly on top
- **Rendering × Palette**: `ink-notes` × `earthy-dusty`
- **Image**: p14_fade_bg.png (hero_page, low-saturation background)
- **Title**: Ink-Wash Notes × Dusty Earth
- **Content**: Ink-wash landscape faded into the background, overlaid with a single line of oversized text; the image is texture, the text is the protagonist

#### Slide 15 — Top and Bottom Halves: Text Above, Image Below

- **Layout**: Upper half height=340px text area, lower half height=340px full-width image (with a fine divider)
- **Rendering × Palette**: `flat` × `jewel-tone`
- **Image**: p15_bottom_img.png
- **Title**: Flat design × jewel tones
- **Content**: Large title + body above, flat overhead view below; image and text each occupy half the page in an equal dialogue

#### Slide 16 — Large Central Image + Text Annotations Arranged Around It

- **Layout**: Square image centered at size=480×480, with labeled text radiating in six directions and leader lines
- **Rendering × Palette**: `minimalist-swiss` × `editorial-classic`
- **Image**: p16_center_img.png
- **Title**: Minimalist Swiss × Editorial Classic
- **Content**: A Bauhaus-inspired minimalist graphic centered on the page, with six annotation lines radiating outward and text arranged like a product diagram

#### Slide 17 — Narrow Image Strip Across the Middle + One Paragraph Above and Below

- **Layout**: Top text area height=200px, middle image strip height=240px, bottom text area height=240px
- **Rendering × Palette**: `screen-print` × `vivid-launch`
- **Image**: p17_strip_img.png
- **Title**: Screen Print × Vivid Launch
- **Content**: A screen-printed horizontal strip runs across the middle of the page, with the upper and lower text forming separate sections; the image cuts through the text

#### Slide 18 — Irregular Polygonal Images + Text Filling the Gaps

- **Layout**: Offset hexagonal clipped image (clipPath polygon) on the left, with text blocks filling the open space on the right and in the corners
- **Rendering × Palette**: `nature` × `sunset-gradient`
- **Image**: p18_polygon_img.png (hexagonal clipPath crop)
- **Title**: Nature Illustration × Sunset Gradient
- **Content**: A tropical plant image is presented in a hexagon, with text freely arranged around the shape and in the corners

#### Slide 19 — Multi-Image Collage Montage + Large Text Spanning Multiple Images

- **Layout**: Three images tiled edge to edge across the full width, with large text (font-size≈72px) spanning across them
- **Rendering × Palette**: `editorial` × `dark-cinematic`
- **Image**: p19_collage1.png, p19_collage2.png, p19_collage3.png
- **Title**: Magazine editorial × dark cinema
- **Content**: Three editorial photography collages fill the page, with an oversized headline layered across them; a montage-driven narrative

#### Slide 20 — Ending: White Text on a Dark Background + A Single Centered Sentence

- **Layout**: Full-bleed chalkboard background, single-line text centered absolutely, with ≥60% negative space
- **Rendering × Palette**: `chalkboard` × `mono-ink`
- **Image**: p20_closing.png (hero_page)
- **Title**: Chalkboard Chalk × Monochrome Ink
- **Content**: A chalkboard constellation background, with one sentence centered to close; negative space is the content

---

## X. Speaker Notes Requirements

- File naming corresponds to SVGs: `01_cover.md` ↔ `01_cover.svg`
- Presentation duration: approximately 15 minutes
- Notes style: concise explanations highlighting the integration of visuals and text on each page
- Presentation purpose: showcase

---

## XI. Technical Constraints Reminder

1. viewBox: `0 0 1280 720`
2. Background uses `<rect>`
3. Text wrapping uses `<tspan>`; `<foreignObject>` is forbidden
4. Transparency defaults to `fill-opacity` / `stop-opacity`; `rgba()` remains converter-compatible
5. Forbidden: `mask`, `<style>`, `class`, `foreignObject`, `textPath`, `animate*`, `script`
6. Write text symbols as raw Unicode; HTML entities (`&nbsp;`, `&mdash;`, etc.) are forbidden
7. `clipPath` is only for `<image>` cropping (circular for P09, hexagonal for P18)
8. Use `<use data-icon="tabler-outline/xxx"/>` as an icon placeholder
