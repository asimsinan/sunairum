/**
 * Font Awesome font embedder for PPTX — thin wrapper around embedDeckFonts.
 *
 * Historical entry point kept for public API stability. Local conversion now
 * embeds all resolvable deck faces (FA + Source/Inter/Barlow/…) via
 * `embedDeckFonts`; calling this still embeds FA when present.
 */
import { embedDeckFonts } from './deck-font-embedder';

/**
 * Embed Font Awesome (and any other resolvable deck) fonts referenced by the PPTX.
 * @deprecated Prefer `embedDeckFonts` — this remains as a stable alias.
 */
export async function embedFontAwesomeFonts(pptxData: Buffer): Promise<Buffer> {
  return embedDeckFonts(pptxData);
}
