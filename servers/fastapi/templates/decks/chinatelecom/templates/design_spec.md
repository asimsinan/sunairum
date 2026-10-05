---
deck_id: chinatelecom
kind: deck
category: brand
summary: China Telecom government-enterprise digital transformation proposals, transformation planning and internal review, used to present solutions and align decisions and next steps; restrained red-gray corporate visual identity.
keywords: [China Telecom, government-enterprise, digital transformation, corporate reporting]
primary_color: "#C00000"
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

# China Telecom — Design Specification

## I. Template Overview

| Application context | Definition |
| --- | --- |
| Recurring presentation family | Government-enterprise digital transformation proposals, transformation planning, internal review and client reporting |
| Intended audiences and outcomes | Decision makers at government-enterprise clients, project stakeholders and internal reviewers; helps audiences understand background and solutions, form judgments, and clarify next steps |
| Delivery and reading assumptions | Primarily presented in meetings, with post-meeting circulation and review; pages must retain key conclusions and necessary evidence so the topic is recognizable without verbal explanation |
| Representative narrative/page roles | The current prototype covers cover, contents, chapters, open content and closing; specific page selection, repetition, order and content handling are decided by the project's Strategist based on the material |

- The visual tone uses a white background, telecom-red structural bands, silver-gray content areas and subtle city line art, emphasizing authority, clarity and restraint.
- Structurally there are two reusable Master families: China Telecom Brand serves the cover, section and closing pages, while China Telecom Content serves the contents and body pages; they divide the work by visual system rather than being duplicated Masters split from a single Layout.

## II. Color Scheme

| Role | Color | Application |
| --- | --- | --- |
| Telecom red | #C00000 | Header capsule, numbers, divider lines and key accents |
| Silver gray | #D9D9D9 | Header structural band |
| Panel gray | #F8FAFC | Content areas and brand cards |
| Graphite | #111827 | Titles and key text |
| Muted gray | #6B7280 | Auxiliary notes and footer |
| White | #FFFFFF | Master background and white-on-color text |

## III. Typography

| Role | Font stack | Application |
| --- | --- | --- |
| Chinese title and body | `"Microsoft YaHei", "PingFang SC", Arial, sans-serif` | Titles, body text, contents items and Chinese brand descriptions |
| Latin label and folio | `Arial, "Microsoft YaHei", sans-serif` | English labels, dates and page numbers |

Font stacks use only common system fonts; Windows prefers Microsoft YaHei, macOS falls back to PingFang SC, with no additional font installation required.

## IV. Signature Design Elements

- Content and contents pages use a "red capsule + silver-gray band" header structure, with a horizontal brand graphic retained on the right.
- Cover, section and ending pages reuse the red slogan, city line art and bottom red ribbon, contained within dedicated brand cards.
- The China Telecom Brand Master carries the white background, top red rule, bottom brand ribbon and English label; the China Telecom Content Master carries the red-gray header, horizontal brand mark and footer divider line.
- Content areas use light-gray rounded panels; actual content is carried by a boundary-complete `object` slot (PowerPoint content placeholder area) without hint-style dashed outlines.
- Titles and general content stay left-aligned; centered composition is used only inside brand graphics.

## V. Page Roster

| File | Master | Layout key | PowerPoint picker name | Visual character | Reusable slots |
| --- | --- | --- | --- | --- | --- |
| `01_cover.svg` | China Telecom Brand | cover | Cover | Left title cluster, right brand card, bottom ribbon | Title, subtitle, organization, date |
| `02_toc.svg` | China Telecom Content | agenda | Agenda | Left brand description card, right four-row numbered contents | Page title, four contents items, page number |
| `03_chapter.svg` | China Telecom Brand | section | Section Header | Left chapter info, right brand card, bottom ribbon | Chapter number, chapter title, chapter subtitle |
| `04_content.svg` | China Telecom Content | content | Title and Content | Red-gray header and large light-gray open content area | Section name, page title, content object, source, page number |
| `05_ending.svg` | China Telecom Brand | closing | Closing | Left closing message, right brand card, bottom ribbon | Closing title, subtitle, contact info, page number |

## VI. Assets

| File | Intended usage |
| --- | --- |
| logo.png | Brand mark on cover, section and ending pages |
| header_brand.png | Horizontal header mark on contents and content pages |
| footer_ribbon.png | Bottom brand ribbon on cover, section and ending pages |
| slogan_red.png | Slogan on right-side brand cards |
| skyline_bg.png | City line art on right-side brand cards |
| top_emblem.png | Reserved alternate horizontal brand asset |
