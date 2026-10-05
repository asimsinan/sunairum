# Sunairum runtime scripts

Scripts used by the FastAPI/Celery worker for images and leftover PPTX helpers.
PPTX compile is `tasks/html_to_pptx.py` (html_output → deckhtml).

## Keep set

| Path | Role |
|------|------|
| `template_text_slots.py` | Text-slot analysis helpers |
| `image_search.py` + `image_sources/` | Stock image search |
| `image_gen.py` + `image_backends/` | AI image backends |
| `config.py`, `console_encoding.py` | Shared helpers |
| `language_tags.py`, `native_payloads.py` | Compile / QA siblings |
| `pptx_animations.py`, `pptx_transitions.py`, `pptx_animation_presets.json` | Native animation/transition support |
| `pptx_opc_validation.py`, `pptx_effects.py` | PPTX package helpers |
| `resource_paths.py`, `project_utils.py`, `project_specs.py` | Path/spec helpers |
| `update_spec.py`, `slide_roster.py`, `project_management/` | Spec-lock parse |

## Common commands

```bash
python3 sunairum_scripts/image_search.py --help
python3 sunairum_scripts/image_gen.py --list-backends
```
