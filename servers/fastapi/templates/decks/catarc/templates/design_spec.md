---
deck_id: catarc
kind: deck
category: brand
summary: CATARC certification showcases, evaluation reports and technical exchange, used to build credible understanding and advance review or cooperation; professional deep-blue engineering visual identity.
keywords: [CATARC, certification, evaluation, technical exchange]
primary_color: "#004098"
canvas_format: ppt169
canvas_width: 1280
canvas_height: 720
canvas_viewbox: "0 0 1280 720"
source_canvas_width: 1280
source_canvas_height: 720
source_viewbox: "0 0 1280 720"
replication_mode: fidelity
native_structure_mode: structured
page_count: 5
---

# CATARC — Design Specification

## I. Template Overview

| Application context | Definition |
| --- | --- |
| Recurring presentation family | Product certification showcases, evaluation reports, technical promotion and business visits |
| Intended audiences and outcomes | Clients, technical reviewers, partners and visiting teams; helps audiences understand certification or evaluation capabilities and evidence of trust, and advance the next steps of review, exchange or cooperation |
| Delivery and reading assumptions | Primarily on-site presentation and technical exchange, while also allowing independent post-meeting reading; pages must retain key conclusions, evidence tags and necessary context |
| Representative narrative/page roles | The current prototype covers cover, contents, chapters, open content and closing; specific page selection, repetition, order and content handling are decided by the project's Strategist based on the material |

- The visual identity centers on CATARC deep blue, white content pages, square chapter numbers and a clean grid, emphasizing professionalism, credibility and engineering order.
- Structurally there are two reusable Master families: CATARC Dark serves the cover, section and closing pages, while CATARC Light serves the contents and body pages; they divide the work between dark and light visual systems rather than being duplicated Masters split from a single Layout.

## II. Color Scheme

| Role | Color | Application |
| --- | --- | --- |
| CATARC blue | #004098 | Dark page background, chapter number blocks, structural lines |
| Deep blue | #003B82 | Cover background |
| Panel gray | #F8FAFC | Content areas |
| Border gray | #E0E0E0 | Divider lines and panel borders |
| Primary text | #333333 | Content page titles and body text |
| White | #FFFFFF | Text on dark pages and Master background |

## III. Typography

| Role | Font stack | Application |
| --- | --- | --- |
| Chinese title and body | `"Microsoft YaHei", "PingFang SC", Arial, sans-serif` | Titles, body text, contents items and contact info |
| Latin label and folio | `Arial, "Microsoft YaHei", sans-serif` | English organization name, numbers, page numbers and short labels |

Font stacks use only common system fonts; Windows prefers Microsoft YaHei, macOS falls back to PingFang SC, with no additional font installation required.

## IV. Signature Design Elements

- White content pages use a stable header with a blue square chapter number, left-aligned title and top-right logo.
- Cover, section and ending pages keep the deep-blue background, low-opacity circles and fine grid, while removing complex gradients and dynamic image dependencies that carry no content value.
- The CATARC Dark Master carries the deep-blue background and top/bottom structural rules; section and ending pages each retain the circular geometry of the original draft, while the cover does not inherit the circles. The CATARC Light Master carries the white background, chapter number block, header logo, divider line and bottom blue rule.
- The contents page continues the row-style navigation with numbers and double vertical bars, and keeps the separate `object` slot on the right.
- General content carriers start at the top-left of the slot bounds; cover, section and ending pages plus the small chapter numbers are short focal content and may be centered within the full bounds.

## V. Page Roster

| File | Master | Layout key | PowerPoint picker name | Visual character | Reusable slots |
| --- | --- | --- | --- | --- | --- |
| `01_cover.svg` | CATARC Dark | cover | Cover | Deep-blue background, centered large logo and title cluster | Title, subtitle, organization, English organization |
| `02_toc.svg` | CATARC Light | agenda | Agenda | Numbered double-bar contents, right data panel | Page title, five contents items, data object, page number |
| `03_chapter.svg` | CATARC Dark | section | Section Header | Deep-blue chapter page, centered chapter number and title | Chapter number, chapter title, chapter subtitle |
| `04_content.svg` | CATARC Light | content | Title and Content | Square chapter number header and open content panel | Chapter number, page title, content object, page number |
| `05_ending.svg` | CATARC Dark | closing | Closing | Deep-blue grid background, centered logo and closing message | Closing title, English subtitle, contact info, footer |

## VI. Assets

| File | Intended usage |
| --- | --- |
| 大型 logo.png | Primary mark on cover and ending pages |
| 右上角 logo.png | Header mark on contents and content pages |
