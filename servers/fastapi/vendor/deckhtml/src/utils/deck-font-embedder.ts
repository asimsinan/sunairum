/**
 * Embed deck fonts into a local-mode PPTX so PowerPoint / LibreOffice open
 * with the same glyph metrics Chromium measured (no silent substitution).
 *
 * Strategy:
 * 1. Font Awesome faces → prebuilt EOTs under assets/fonts/font-awesome/
 * 2. All other typefaces referenced in slide XML → matching TTF/OTF from
 *    DECKHTML_FONTS_DIR / SUNAIRUM_FONTS_DIR / ../../assets/fonts (relative
 *    to the FastAPI tree when vendored) / package assets.
 *
 * Bytes are written as ppt/fonts/fontN.fntdata and wired through
 * [Content_Types].xml, presentation.xml.rels, and p:embeddedFontLst —
 * same OOXML path as the historical FA-only embedder.
 */
import * as fs from 'fs';
import * as path from 'path';
import JSZip from 'jszip';

/** PPTX typeface → EOT asset path (relative to this package's assets/ dir). */
const FONT_AWESOME_EOT_MAP: Record<string, string> = {
  'Font Awesome 6 Free Solid': 'fonts/font-awesome/6/fa-solid-900.eot',
  'Font Awesome 6 Free Regular': 'fonts/font-awesome/6/fa-regular-400.eot',
  'Font Awesome 6 Brands': 'fonts/font-awesome/6/fa-brands-400.eot',
  'Font Awesome 6 Brands Regular': 'fonts/font-awesome/6/fa-brands-400.eot',
  'Font Awesome 5 Brands': 'fonts/font-awesome/5/fa-brands-400.eot',
  'Font Awesome 5 Brands Regular': 'fonts/font-awesome/5/fa-brands-400.eot',
  'Font Awesome v4 Compatibility': 'fonts/font-awesome/6/fa-v4compatibility.eot',
  'Font Awesome v4 Compatibility Regular':
    'fonts/font-awesome/6/fa-v4compatibility.eot',
  'Font Awesome 5 Free Solid': 'fonts/font-awesome/5/fa-solid-900.eot',
  'Font Awesome 5 Free Regular': 'fonts/font-awesome/5/fa-regular-400.eot',
};

/**
 * Canonical family stem → filename prefix used under assets/fonts/.
 * Keys are lowercased family names without style suffixes.
 * Office / system aliases map onto the curated Source/Inter/Barlow pack so
 * LibreOffice + PowerPoint open with the same metrics Chromium measured after
 * platform remapping (see release_export._write_fontconfig).
 */
const FAMILY_FILE_PREFIX: Record<string, string> = {
  'source sans 3': 'source-sans-3',
  'source serif 4': 'source-serif-4',
  inter: 'inter',
  'barlow condensed': 'barlow-condensed',
  'source sans pro': 'source-sans-3',
  'source serif pro': 'source-serif-4',
  // Office / generic aliases → curated pack
  arial: 'source-sans-3',
  helvetica: 'source-sans-3',
  'helvetica neue': 'source-sans-3',
  calibri: 'source-sans-3',
  'segoe ui': 'source-sans-3',
  verdana: 'source-sans-3',
  'liberation sans': 'source-sans-3',
  georgia: 'source-serif-4',
  cambria: 'source-serif-4',
  'times new roman': 'source-serif-4',
  times: 'source-serif-4',
  'liberation serif': 'source-serif-4',
  // Monospace. Liberation Mono ships with the image (fonts-liberation) and is
  // copied into the embed dir, so code text is embedded like any other face
  // instead of being resolved by whatever the reader happens to have.
  'liberation mono': 'liberation-mono',
  consolas: 'liberation-mono',
  'courier new': 'liberation-mono',
  courier: 'liberation-mono',
  menlo: 'liberation-mono',
  monaco: 'liberation-mono',
  'sf mono': 'liberation-mono',
  'dejavu sans mono': 'liberation-mono',
  'jetbrains mono': 'liberation-mono',
  'source code pro': 'liberation-mono',
};

const FONTS_DIR = 'ppt/fonts';
const CONTENT_TYPES_PATH = '[Content_Types].xml';
const PRESENTATION_PATH = 'ppt/presentation.xml';
const PRESENTATION_RELS_PATH = 'ppt/_rels/presentation.xml.rels';
const FONT_CONTENT_TYPE = 'application/x-fontdata';
const FONT_REL_TYPE =
  'http://schemas.openxmlformats.org/officeDocument/2006/relationships/font';

/** Skip theme generics and empty placeholders. */
const SKIP_TYPEFACES = new Set([
  '',
  '+mj-lt',
  '+mn-lt',
  '+mj-ea',
  '+mn-ea',
  '+mj-cs',
  '+mn-cs',
]);

interface EmbeddedFontInfo {
  typeface: string;
  zipPath: string;
  relTarget: string;
  rId: string;
}

function resolvePackageAssetsDir(): string {
  const candidates = [
    path.resolve(__dirname, '..', '..', 'assets'),
    path.resolve(process.cwd(), 'assets'),
  ];
  for (const c of candidates) {
    if (fs.existsSync(c)) return c;
  }
  return candidates[0]!;
}

/** Directories that may contain TTF/OTF faces for non-FA embedding. */
export function resolveDeckFontDirs(): string[] {
  const dirs: string[] = [];
  const envDirs = [
    process.env.DECKHTML_FONTS_DIR,
    process.env.SUNAIRUM_FONTS_DIR,
  ];
  for (const raw of envDirs) {
    const v = (raw || '').trim();
    if (v && fs.existsSync(v)) dirs.push(path.resolve(v));
  }
  // Vendored under servers/fastapi/vendor/deckhtml → ../../assets/fonts
  const fastapiAssets = path.resolve(__dirname, '..', '..', '..', '..', 'assets', 'fonts');
  if (fs.existsSync(fastapiAssets)) dirs.push(fastapiAssets);
  const pkgFonts = path.join(resolvePackageAssetsDir(), 'fonts');
  if (fs.existsSync(pkgFonts)) dirs.push(pkgFonts);
  // Dedup while preserving order.
  return [...new Set(dirs)];
}

async function collectTypefaces(zip: JSZip): Promise<Set<string>> {
  const typefaces = new Set<string>();
  const typefaceRe = /\btypeface\s*=\s*"([^"]+)"/g;
  // Only slide XMLs — theme masters list dozens of unused Asian fallbacks.
  for (const filePath of Object.keys(zip.files)) {
    if (!filePath.startsWith('ppt/slides/') || !filePath.endsWith('.xml')) {
      continue;
    }
    const file = zip.file(filePath);
    if (!file) continue;
    const xml = await file.async('text');
    let m: RegExpExecArray | null;
    while ((m = typefaceRe.exec(xml)) !== null) {
      if (m[1]) typefaces.add(m[1]);
    }
  }
  return typefaces;
}

function nextFontPath(zip: JSZip): string {
  let n = 1;
  while (zip.file(`${FONTS_DIR}/font${n}.fntdata`)) n += 1;
  return `${FONTS_DIR}/font${n}.fntdata`;
}

function escapeXml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

async function updateContentTypes(zip: JSZip): Promise<void> {
  const file = zip.file(CONTENT_TYPES_PATH);
  if (!file) return;
  let xml = await file.async('text');
  const defaultTag = `<Default Extension="fntdata" ContentType="${FONT_CONTENT_TYPE}"/>`;
  if (!xml.includes('Extension="fntdata"')) {
    xml = xml.replace('</Types>', `  ${defaultTag}\n</Types>`);
    zip.file(CONTENT_TYPES_PATH, xml);
  }
}

function generateEmbeddedFontLst(fonts: EmbeddedFontInfo[]): string {
  let xml = '<p:embeddedFontLst>';
  for (const font of fonts) {
    xml += '<p:embeddedFont>';
    xml += `<p:font typeface="${escapeXml(font.typeface)}" pitchFamily="34" charset="0"/>`;
    xml += `<p:regular r:id="${font.rId}"/>`;
    xml += '</p:embeddedFont>';
  }
  xml += '</p:embeddedFontLst>';
  return xml;
}

async function updatePresentationXml(
  zip: JSZip,
  fonts: EmbeddedFontInfo[],
): Promise<void> {
  const file = zip.file(PRESENTATION_PATH);
  if (!file) return;
  let xml = await file.async('text');

  if (!xml.includes('embedTrueTypeFonts')) {
    xml = xml.replace(
      /(<p:presentation[^>]*)(>)/,
      '$1 embedTrueTypeFonts="1"$2',
    );
  }
  if (!xml.includes('saveSubsetFonts')) {
    xml = xml.replace(
      /(<p:presentation[^>]*)(>)/,
      '$1 saveSubsetFonts="1"$2',
    );
  }

  // Replace or insert embeddedFontLst so re-runs stay idempotent.
  const lst = generateEmbeddedFontLst(fonts);
  if (xml.includes('<p:embeddedFontLst>')) {
    xml = xml.replace(/<p:embeddedFontLst>[\s\S]*?<\/p:embeddedFontLst>/, lst);
  } else if (/<p:notesSz[^>]*\/>|<\/p:notesSz>/.test(xml)) {
    xml = xml.replace(/(<p:notesSz[^>]*\/>|<\/p:notesSz>)/, `$1${lst}`);
  } else {
    xml = xml.replace('</p:presentation>', `${lst}</p:presentation>`);
  }

  zip.file(PRESENTATION_PATH, xml);
}

async function updatePresentationRels(
  zip: JSZip,
  fonts: EmbeddedFontInfo[],
): Promise<void> {
  const file = zip.file(PRESENTATION_RELS_PATH);
  if (!file) return;
  let xml = await file.async('text');

  let maxRId = 0;
  const rIdRe = /Id="rId(\d+)"/g;
  let m: RegExpExecArray | null;
  while ((m = rIdRe.exec(xml)) !== null) {
    const n = parseInt(m[1]!, 10);
    if (n > maxRId) maxRId = n;
  }

  let relsToAdd = '';
  fonts.forEach((font, index) => {
    font.rId = `rId${maxRId + index + 1}`;
    relsToAdd += `<Relationship Id="${font.rId}" Type="${FONT_REL_TYPE}" Target="${font.relTarget}"/>`;
  });

  xml = xml.replace('</Relationships>', `${relsToAdd}</Relationships>`);
  zip.file(PRESENTATION_RELS_PATH, xml);
}

function normalizeFamilyKey(typeface: string): string {
  return typeface
    .replace(/\s+(Bold|Italic|Regular|Medium|SemiBold|Light|Black|Thin)\b/gi, '')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase();
}

function styleSuffix(typeface: string): { bold: boolean; italic: boolean } {
  const t = typeface.toLowerCase();
  return {
    bold: /\bbold\b|\bsemibold\b|\bblack\b/.test(t),
    italic: /\bitalic\b|\boblique\b/.test(t),
  };
}

function weightToken(bold: boolean): string {
  return bold ? '700' : '400';
}

function italicToken(italic: boolean): string {
  return italic ? '-italic' : '';
}

/** Resolve a typeface name to a local TTF/OTF/EOT buffer + source label. */
export function resolveFontBytesForTypeface(
  typeface: string,
  fontDirs: string[],
  packageAssetsDir: string,
): { bytes: Buffer; source: string } | null {
  if (typeface in FONT_AWESOME_EOT_MAP) {
    const rel = FONT_AWESOME_EOT_MAP[typeface]!;
    const abs = path.resolve(packageAssetsDir, rel);
    if (fs.existsSync(abs)) {
      return { bytes: fs.readFileSync(abs), source: rel };
    }
    return null;
  }

  const familyKey = normalizeFamilyKey(typeface);
  const prefix = FAMILY_FILE_PREFIX[familyKey];
  if (!prefix) {
    // Fuzzy: look for any file whose basename starts with a slug of the family.
    const slug = familyKey.replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
    if (!slug) return null;
    const { bold, italic } = styleSuffix(typeface);
    const preferred = [
      `${slug}-${weightToken(bold)}${italicToken(italic)}.ttf`,
      `${slug}-${weightToken(bold)}${italicToken(italic)}.otf`,
      `${slug}-400.ttf`,
      `${slug}-400.otf`,
      `${slug}.ttf`,
      `${slug}.otf`,
    ];
    for (const dir of fontDirs) {
      for (const name of preferred) {
        const abs = path.join(dir, name);
        if (fs.existsSync(abs)) {
          return { bytes: fs.readFileSync(abs), source: abs };
        }
      }
      // Last resort: any file containing the slug.
      try {
        const entries = fs.readdirSync(dir);
        const hit = entries.find(
          (e) =>
            e.toLowerCase().includes(slug) &&
            (e.endsWith('.ttf') || e.endsWith('.otf')),
        );
        if (hit) {
          const abs = path.join(dir, hit);
          return { bytes: fs.readFileSync(abs), source: abs };
        }
      } catch {
        /* ignore */
      }
    }
    return null;
  }

  const { bold, italic } = styleSuffix(typeface);
  const candidates = [
    `${prefix}-${weightToken(bold)}${italicToken(italic)}.ttf`,
    `${prefix}-${weightToken(bold)}${italicToken(italic)}.otf`,
    `${prefix}-400.ttf`,
    `${prefix}-400.otf`,
  ];
  for (const dir of fontDirs) {
    for (const name of candidates) {
      const abs = path.join(dir, name);
      if (fs.existsSync(abs)) {
        return { bytes: fs.readFileSync(abs), source: abs };
      }
    }
  }
  return null;
}

/**
 * Embed every resolvable typeface referenced by the PPTX into the package.
 * Returns the original buffer when nothing could be embedded.
 */
export async function embedDeckFonts(pptxData: Buffer): Promise<Buffer> {
  const zip = await JSZip.loadAsync(pptxData);
  const typefaces = [...(await collectTypefaces(zip))].filter(
    (t) => !SKIP_TYPEFACES.has(t) && !t.startsWith('+'),
  );
  if (typefaces.length === 0) return pptxData;

  const packageAssetsDir = resolvePackageAssetsDir();
  const fontDirs = resolveDeckFontDirs();
  const fontsInfo: EmbeddedFontInfo[] = [];
  const embeddedTypefaces = new Set<string>();
  let embeddedCount = 0;

  for (const typeface of typefaces) {
    if (embeddedTypefaces.has(typeface)) continue;
    const resolved = resolveFontBytesForTypeface(
      typeface,
      fontDirs,
      packageAssetsDir,
    );
    if (!resolved) {
      console.warn(
        `⚠️  No local font file for typeface "${typeface}" — leaving unembedded`,
      );
      continue;
    }
    const zipPath = nextFontPath(zip);
    const relTarget = zipPath.replace(/^ppt\//, '');
    zip.file(zipPath, resolved.bytes);
    fontsInfo.push({ typeface, zipPath, relTarget, rId: 'pending' });
    embeddedTypefaces.add(typeface);
    embeddedCount += 1;
    console.log(
      `✓ Embedded font: ${typeface} (${resolved.source}, ${resolved.bytes.length} bytes)`,
    );
  }

  if (embeddedCount === 0) return pptxData;

  await updateContentTypes(zip);
  await updatePresentationRels(zip, fontsInfo);
  await updatePresentationXml(zip, fontsInfo);

  const modified = await zip.generateAsync({
    type: 'nodebuffer',
    compression: 'DEFLATE',
  });

  console.log(`\n✅ Embedded ${embeddedCount} font(s) into PPTX\n`);
  return modified;
}
