# Sunairum fidelity patches (vendored deckhtml)

Full tracker: **[DECKHTML_ISSUES.md](./DECKHTML_ISSUES.md)** (listed issues closed in vendor + MathML/OMML pipeline). Editable PPTX aims for visual match to `html_output/`, not pixel-identical; PDF stays hi-DPI HTML screenshots.

**Closed-loop fidelity** (structural): embed deck fonts locally (`embedDeckFonts`), freeze L1 text (`wrap:none`, no `normAutofit`), emit `.shape-map.json`, and gate with LibreOffice SSIM vs HTML previews — see [LAYOUT_FAITHFUL.md](./LAYOUT_FAITHFUL.md) and [FIDELITY_CALIBRATION.md](./FIDELITY_CALIBRATION.md).

Highlights:

1. Paint order + slide-bounds clamp  
2. Formula/figure content-box letterbox contain  
3. Flex icon / circle badge canvas bake  
4. Native tables + chrome shape (screenshot last resort)  
5. Text occlusion repair + text line-height fidelity  
6. MathML hosts → editable OMML equations  
7. `data-chart-payload` → native pptxgen charts  
8. Outline / flex-item pill chips (slide-space insets + font fit)  
9. Short flex chips + collision-aware grow + negative letter-spacing (O14–O16)  
10. Title wrap fit vs accent bars (`fitWrappedTextBox`, O17)  
11. Column walls so titles do not grow into opaque panels (O18)  
12. Unicode flex-badge screenshot when canvas `fillText` has no ink (O19)  
13. Parent `overflow:hidden` clip on emission (O20)  
14. CSS border-triangle screenshot (O21)  
15. **L1 layout-faithful text** — Chromium line boxes + `wrap:none` + no box grow ([LAYOUT_FAITHFUL.md](./LAYOUT_FAITHFUL.md))

Rebuild: `npm run build` in this directory. Then smoke `html_to_pptx` on a project `html_output/`.

Layout-faithful conversion is always on. `DECKHTML_LAYOUT_FAITHFUL=strict` additionally hard-fails unsupported mandatory text.
