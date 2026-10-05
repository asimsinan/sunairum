"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.writeTaskOutput = writeTaskOutput;
exports.attachSimplifiedToEnvelope = attachSimplifiedToEnvelope;
exports.printSimplifiedNotice = printSimplifiedNotice;
exports.printFontEmbedNotice = printFontEmbedNotice;
exports.printSuccess = printSuccess;
exports.logVerbose = logVerbose;
exports.logProgress = logProgress;
const promises_1 = __importDefault(require("fs/promises"));
const path_1 = __importDefault(require("path"));
async function writeTaskOutput(task, outPath, downloadResult) {
    const files = collectOutputFiles(downloadResult);
    if (files.length === 0) {
        const target = await resolveSingleOutputPath(outPath, task.id, '.json');
        await promises_1.default.mkdir(path_1.default.dirname(target), { recursive: true });
        await promises_1.default.writeFile(target, `${JSON.stringify(downloadResult ?? task.result ?? task, null, 2)}\n`);
        return { kind: 'json', path: path_1.default.resolve(target) };
    }
    if (files.length === 1) {
        const file = files[0];
        const target = await resolveSingleOutputPath(outPath, task.id, file.ext);
        const bytes = await downloadFile(file.url);
        await promises_1.default.mkdir(path_1.default.dirname(target), { recursive: true });
        await promises_1.default.writeFile(target, bytes);
        return { kind: 'file', path: path_1.default.resolve(target) };
    }
    const outIsExistingDirectory = await isDirectory(outPath);
    const downloaded = await Promise.all(files.map(async (file) => ({
        file,
        bytes: await downloadFile(file.url),
    })));
    await promises_1.default.mkdir(outPath, { recursive: true });
    const written = [];
    for (let i = 0; i < downloaded.length; i += 1) {
        const item = downloaded[i];
        if (!item)
            continue;
        const target = path_1.default.join(outPath, orderedFileName(i, files.length, item.file.ext));
        await promises_1.default.writeFile(target, item.bytes);
        written.push(path_1.default.resolve(target));
    }
    if (!outIsExistingDirectory && path_1.default.extname(outPath).toLowerCase() === '.zip') {
        return { kind: 'file', path: path_1.default.resolve(outPath) };
    }
    return { kind: 'directory', path: path_1.default.resolve(outPath), files: written };
}
function collectOutputFiles(value) {
    const files = [];
    visitOutputValue(value, files);
    return files;
}
function visitOutputValue(value, files) {
    if (isFileTuple(value)) {
        addOutputFile(value[0], files);
        return;
    }
    if (Array.isArray(value)) {
        for (const item of value) {
            visitOutputValue(item, files);
        }
        return;
    }
    if (value && typeof value === 'object') {
        const record = value;
        if (typeof record.downloadUrl === 'string') {
            addOutputFile(record.downloadUrl, files);
        }
        for (const item of Object.values(record)) {
            visitOutputValue(item, files);
        }
    }
}
function addOutputFile(url, files) {
    if (!/^https?:\/\//i.test(url)) {
        return;
    }
    files.push({ url, ext: extensionFromUrl(url) });
}
function isFileTuple(value) {
    return Array.isArray(value) && typeof value[0] === 'string';
}
function extensionFromUrl(url) {
    try {
        const parsed = new URL(url);
        const ext = path_1.default.extname(parsed.pathname);
        return ext ? ext.toLowerCase() : '.bin';
    }
    catch {
        return '.bin';
    }
}
async function resolveSingleOutputPath(outPath, taskId, expectedExt) {
    const normalizedExpectedExt = expectedExt.startsWith('.')
        ? expectedExt.toLowerCase()
        : `.${expectedExt.toLowerCase()}`;
    const outExt = path_1.default.extname(outPath).toLowerCase();
    const outIsDirectory = (await isDirectory(outPath)) || !outExt || outExt !== normalizedExpectedExt;
    if (outIsDirectory) {
        return path_1.default.join(outPath, `${taskId}${normalizedExpectedExt}`);
    }
    return outPath;
}
async function isDirectory(target) {
    try {
        return (await promises_1.default.stat(target)).isDirectory();
    }
    catch {
        return false;
    }
}
async function downloadFile(url) {
    const response = await fetch(url);
    if (!response.ok) {
        throw new Error(`Failed to download ${url}: ${response.status} ${response.statusText}`);
    }
    return Buffer.from(await response.arrayBuffer());
}
function orderedFileName(index, total, ext) {
    const width = Math.max(2, String(total).length);
    const normalized = ext.startsWith('.') ? ext : `.${ext}`;
    return `${String(index + 1).padStart(width, '0')}${normalized}`;
}
const SIMPLIFIED_REASON_LABELS = {
    'chart-canvas': 'canvas chart',
    'svg-diagram': 'SVG diagram',
    'svg-flowchart': 'SVG flowchart (Mermaid, etc.)',
    'gradient-layered': 'layered gradient background',
    'gradient-tiled-radial': 'tiled radial gradient',
    'gradient-hard-stop': 'hard-stop gradient',
    'background-url': 'background-image url()',
    'page-background': 'page background',
    'math-fallback': 'math formula (OMML fallback)',
};
function attachSimplifiedToEnvelope(envelope) {
    const simplified = envelope.stats?.simplified ?? envelope.simplified;
    if (!simplified)
        return envelope;
    return { ...envelope, simplified };
}
/** PPTX-only: which elements were rasterized during simplified conversion. */
function printSimplifiedNotice(simplified, mode, quiet, jsonOutput) {
    if (quiet || !simplified || simplified.total === 0)
        return;
    if (!jsonOutput) {
        console.error(`Rasterized ${simplified.total} element(s) (simplified conversion):`);
        for (const [reason, count] of Object.entries(simplified.byReason).sort()) {
            const label = SIMPLIFIED_REASON_LABELS[reason] ?? reason;
            console.error(`  ${label}: ${count}`);
        }
        console.error('');
    }
}
/** PPTX-only: cloud embed library match tip. Not shown for PNG. */
function printFontEmbedNotice(fonts, mode, embedFonts, quiet, jsonOutput) {
    if (quiet || jsonOutput || !fonts?.embed)
        return;
    const { matched, unmatched, indexMeta } = fonts.embed;
    if (matched.length === 0 && unmatched.length === 0)
        return;
    console.error(`Cloud embed font library (${indexMeta.familyCount} families from fonts-index.ts):`);
    for (const item of matched) {
        const note = item.used === item.matchedFamily
            ? 'matched'
            : `matched → ${item.matchedFamily}`;
        console.error(`  ✓ ${item.used} (${note})`);
    }
    for (const name of unmatched) {
        console.error(`  ✗ ${name} (not in library)`);
    }
    console.error('');
    if (mode === 'cloud' && embedFonts && matched.length > 0) {
        console.error('Matched fonts will be embedded into the PPTX so anyone opening the file sees the same typography.');
        console.error('');
    }
    else if (matched.length > 0) {
        const tip = mode === 'cloud'
            ? 'Tip: use --embed-fonts to embed matched fonts into the PPTX so anyone opening the file sees the same typography.'
            : 'Tip: use --mode cloud --embed-fonts to embed matched fonts into the PPTX so anyone opening the file sees the same typography.';
        console.error(tip);
        console.error('');
    }
}
function printSuccess(envelope, jsonOutput) {
    if (jsonOutput) {
        console.log(JSON.stringify(envelope));
        return;
    }
    const paths = envelope.outputs && envelope.outputs.length > 0
        ? envelope.outputs
        : [envelope.output];
    for (const p of paths) {
        console.log(p);
    }
}
function logVerbose(verbose, quiet, message) {
    if (verbose && !quiet) {
        console.error(message);
    }
}
function logProgress(quiet, message) {
    if (!quiet) {
        console.error(message);
    }
}
