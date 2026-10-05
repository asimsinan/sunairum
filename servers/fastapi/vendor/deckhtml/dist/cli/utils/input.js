"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.resolveInputs = resolveInputs;
exports.materializeInputs = materializeInputs;
exports.resolveOutputFormat = resolveOutputFormat;
exports.deriveOutputPath = deriveOutputPath;
const promises_1 = __importDefault(require("fs/promises"));
const path_1 = __importDefault(require("path"));
const os_1 = __importDefault(require("os"));
const crypto_1 = require("crypto");
function isUrl(value) {
    return /^https?:\/\//i.test(value);
}
async function readStdin() {
    const chunks = [];
    for await (const chunk of process.stdin) {
        chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
    }
    return Buffer.concat(chunks).toString('utf-8');
}
async function writeTempHtml(content) {
    const dir = await promises_1.default.mkdtemp(path_1.default.join(os_1.default.tmpdir(), 'deckhtml-'));
    const filePath = path_1.default.join(dir, 'stdin.html');
    await promises_1.default.writeFile(filePath, content, 'utf-8');
    return filePath;
}
async function downloadUrl(url) {
    const response = await fetch(url);
    if (!response.ok) {
        throw new Error(`Failed to fetch ${url}: ${response.status} ${response.statusText}`);
    }
    const content = await response.text();
    const dir = await promises_1.default.mkdtemp(path_1.default.join(os_1.default.tmpdir(), 'deckhtml-'));
    let baseName = 'page.html';
    try {
        const parsed = new URL(url);
        baseName = path_1.default.basename(parsed.pathname) || 'page.html';
        if (!baseName.toLowerCase().endsWith('.html') && !baseName.toLowerCase().endsWith('.htm')) {
            baseName = `${baseName}.html`;
        }
    }
    catch {
        baseName = `page-${(0, crypto_1.randomBytes)(4).toString('hex')}.html`;
    }
    const filePath = path_1.default.join(dir, baseName);
    await promises_1.default.writeFile(filePath, content, 'utf-8');
    return filePath;
}
async function resolveInputs(inputs) {
    if (inputs.length === 0) {
        throw new Error('Missing input. Provide an HTML file, URL, or "-" for stdin.');
    }
    if (inputs.length === 1 && inputs[0] === '-') {
        if (process.stdin.isTTY) {
            throw new Error('No stdin data. Pipe HTML content or provide a file path.');
        }
        const html = await readStdin();
        if (!html.trim()) {
            throw new Error('Empty stdin input.');
        }
        const tempPath = await writeTempHtml(html);
        return { kind: 'stdin', tempPath };
    }
    const urls = inputs.filter(isUrl);
    const files = inputs.filter((item) => !isUrl(item));
    if (urls.length > 0 && files.length > 0) {
        throw new Error('Cannot mix URLs and local file paths in one invocation.');
    }
    if (urls.length > 0) {
        return { kind: 'url', urls };
    }
    const paths = [];
    for (const file of files) {
        try {
            await promises_1.default.access(file);
        }
        catch {
            throw new Error(`Input file not found: ${file}`);
        }
        paths.push(path_1.default.resolve(file));
    }
    return { kind: 'file', paths };
}
async function materializeInputs(resolved) {
    if (resolved.kind === 'file') {
        return { paths: resolved.paths, cleanup: async () => { } };
    }
    if (resolved.kind === 'stdin') {
        return {
            paths: [resolved.tempPath],
            cleanup: async () => {
                await promises_1.default.rm(path_1.default.dirname(resolved.tempPath), {
                    recursive: true,
                    force: true,
                });
            },
        };
    }
    const paths = [];
    const dirs = [];
    for (const url of resolved.urls) {
        const filePath = await downloadUrl(url);
        paths.push(filePath);
        dirs.push(path_1.default.dirname(filePath));
    }
    return {
        paths,
        cleanup: async () => {
            for (const dir of dirs) {
                await promises_1.default.rm(dir, { recursive: true, force: true });
            }
        },
    };
}
const FORMAT_BY_EXT = {
    '.pptx': 'pptx',
    '.pdf': 'pdf',
    '.png': 'png',
};
/**
 * Infer output format from `-o` extension.
 * Without `-o`, defaults to pptx (path is derived from the input).
 */
function resolveOutputFormat(explicitOutput) {
    if (!explicitOutput) {
        return 'pptx';
    }
    const ext = path_1.default.extname(explicitOutput).toLowerCase();
    if (!ext) {
        throw new Error(`Cannot infer format from output path "${explicitOutput}". Use a .pptx or .png extension.`);
    }
    const format = FORMAT_BY_EXT[ext];
    if (!format) {
        throw new Error(`Unsupported output extension "${ext}". Use .pptx or .png.`);
    }
    return format;
}
function deriveOutputPath(inputPaths, format, explicitOutput) {
    if (explicitOutput) {
        return path_1.default.resolve(explicitOutput);
    }
    if (inputPaths.length === 0) {
        throw new Error('--output is required when input path cannot be inferred.');
    }
    const ext = format === 'pptx' ? '.pptx' : format === 'pdf' ? '.pdf' : '.png';
    const first = inputPaths[0];
    if (format === 'png') {
        const base = path_1.default.basename(first, path_1.default.extname(first));
        return path_1.default.resolve(path_1.default.dirname(first), `${base || 'frames'}.png`);
    }
    if (inputPaths.length === 1) {
        const parsed = path_1.default.parse(first);
        return path_1.default.resolve(parsed.dir, `${parsed.name}${ext}`);
    }
    const parsed = path_1.default.parse(first);
    return path_1.default.resolve(parsed.dir, `deck${ext}`);
}
