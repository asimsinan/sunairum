# Third-party and upstream notices

Sunairum original code is licensed under the PolyForm Shield License 1.0.0
(see `LICENSE`). The components below keep their original licenses.

## ppt-master

Sunairum includes example style packs from [ppt-master](https://github.com/hugohe3/ppt-master)
by [@hugohe3](https://github.com/hugohe3). Those portions remain under the MIT License.
Their copyright and MIT terms continue to apply. Sunairum’s generation path
(Constrained HTML, measure, Slide IR, native PPTX) is separate original work.

## Fonts

Vendored fonts under `servers/fastapi/assets/` are licensed under the
SIL Open Font License 1.1. See the matching files in
`servers/fastapi/assets/licenses/`.

## Icons

Phosphor icons and related icon assets keep their original MIT (or other)
licenses. See `servers/fastapi/assets/licenses/` and in-tree license notes.

## deckhtml

Sunairum vendors a copy of [@deckflow/deckhtml](https://github.com/deckflow/deckhtml)
(MIT) under `servers/fastapi/vendor/deckhtml` for local HTML→PPTX export.
Upstream copyright and MIT terms continue to apply; see that directory’s
`LICENSE`. Sunairum may carry local fidelity patches on top of the vendored
sources.
