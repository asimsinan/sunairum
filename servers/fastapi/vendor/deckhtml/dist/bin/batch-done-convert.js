#!/usr/bin/env ts-node
"use strict";
/**
 * Convert all HTML files in a benchmark/done subdirectory (sorted by name)
 * into a single out.pptx in that directory.
 *
 * Usage:
 *   ./src/bin/batch-done-convert.ts [dir] [local] [1280x720]
 *
 * Examples:
 *   ./src/bin/batch-done-convert.ts                    # all dirs under benchmark/done
 *   ./src/bin/batch-done-convert.ts local              # all dirs, allow file://
 *   ./src/bin/batch-done-convert.ts benchmark/done/0001
 *   ./src/bin/batch-done-convert.ts 0001 local
 */
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
const fs_1 = require("fs");
const path_1 = __importStar(require("path"));
const api_1 = require("../api");
const root = (0, path_1.resolve)(__dirname, '..', '..');
const DONE_ROOT = (0, path_1.resolve)(root, 'benchmark/done');
function parseViewportArg(arg) {
    if (!arg)
        return { width: 1280, height: 720 };
    const match = arg.match(/^(\d+)x(\d+)$/i);
    if (!match) {
        throw new Error(`Invalid viewport: ${arg}. Expected WxH e.g. 1280x720`);
    }
    return { width: parseInt(match[1], 10), height: parseInt(match[2], 10) };
}
function isFlagArg(arg) {
    return arg === 'local' || /^\d+x\d+$/i.test(arg);
}
function resolveDoneDir(dirArg) {
    const candidate = (0, path_1.resolve)(process.cwd(), dirArg);
    if ((0, fs_1.existsSync)(candidate)) {
        if (!(0, fs_1.statSync)(candidate).isDirectory()) {
            throw new Error(`Not a directory: ${candidate}`);
        }
        return candidate;
    }
    const underDone = (0, path_1.resolve)(DONE_ROOT, dirArg);
    if ((0, fs_1.existsSync)(underDone) && (0, fs_1.statSync)(underDone).isDirectory()) {
        return underDone;
    }
    throw new Error(`Directory not found: ${dirArg} (tried ${candidate} and ${underDone})`);
}
function listDoneSubdirs() {
    if (!(0, fs_1.existsSync)(DONE_ROOT))
        return [];
    return (0, fs_1.readdirSync)(DONE_ROOT)
        .filter((name) => {
        const full = (0, path_1.resolve)(DONE_ROOT, name);
        return (0, fs_1.existsSync)(full) && (0, fs_1.statSync)(full).isDirectory();
    })
        .sort((a, b) => a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' }));
}
function listHtmlFiles(dir) {
    return (0, fs_1.readdirSync)(dir)
        .filter((name) => name.toLowerCase().endsWith('.html'))
        .sort((a, b) => a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' }))
        .map((name) => (0, path_1.resolve)(dir, name));
}
function parseArgs(argv) {
    const args = argv.filter((a) => !a.startsWith('--'));
    const firstArg = args[0];
    const dirArg = firstArg && !isFlagArg(firstArg) ? firstArg : undefined;
    const viewportArg = args.find((a) => /^\d+x\d+$/i.test(a));
    return {
        dirArg,
        options: {
            allowLocalResources: args.includes('local'),
            viewport: parseViewportArg(viewportArg),
        },
    };
}
async function convertDoneDir(dirArg, options) {
    const { allowLocalResources, viewport } = options;
    const targetDir = resolveDoneDir(dirArg);
    const htmlFiles = listHtmlFiles(targetDir);
    if (htmlFiles.length === 0) {
        console.log(`No .html files found in ${targetDir}, skipped.`);
        return;
    }
    const outputPath = (0, path_1.resolve)(targetDir, 'out.pptx');
    console.log(`Directory: ${targetDir}`);
    console.log(`HTML files (${htmlFiles.length}, merged in order):`);
    htmlFiles.forEach((file, i) => {
        console.log(`  ${String(i + 1).padStart(3, ' ')}. ${path_1.default.basename(file)}`);
    });
    console.log(`Output:    ${outputPath}`);
    console.log(`Viewport:  ${viewport.width}×${viewport.height}px`);
    if (allowLocalResources)
        console.log('Local resources: allowed');
    console.log('');
    const startTime = Date.now();
    console.log('Converting...');
    const result = await (0, api_1.convertHtmlToPptx)({
        inputs: htmlFiles,
        viewportWidth: viewport.width,
        viewportHeight: viewport.height,
        allowLocalResources,
    });
    (0, fs_1.writeFileSync)(outputPath, result.data);
    const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
    console.log(`\nDone! ${result.slideCount} slide(s) → ${outputPath} (${elapsed}s)`);
}
function printUsage() {
    console.log('Usage: ./src/bin/batch-done-convert.ts [dir] [local] [1280x720]\n' +
        '  [dir]   Optional. Path under benchmark/done (e.g. 0001) or absolute path.\n' +
        '          Omit to convert every subdirectory under benchmark/done in order.\n' +
        '  local   Allow file:// subresources\n' +
        '  WxH     Viewport size, default 1280x720\n' +
        '\n' +
        'All .html files in each directory are merged in name order into out.pptx.');
}
async function main() {
    const rawArgs = process.argv.slice(2);
    if (rawArgs.includes('-h') || rawArgs.includes('--help')) {
        printUsage();
        process.exit(0);
    }
    const { dirArg, options } = parseArgs(rawArgs);
    if (dirArg) {
        await convertDoneDir(dirArg, options);
        process.exit(0);
    }
    const dirs = listDoneSubdirs();
    if (dirs.length === 0) {
        console.log(`No subdirectories found in ${DONE_ROOT}`);
        process.exit(0);
    }
    console.log(`Batch mode: ${dirs.length} director(y/ies) under ${DONE_ROOT}\n`);
    for (let i = 0; i < dirs.length; i++) {
        const name = dirs[i];
        console.log(`[${i + 1}/${dirs.length}] ${name}`);
        console.log('─'.repeat(40));
        await convertDoneDir(name, options);
        if (i < dirs.length - 1)
            console.log('');
    }
    console.log(`\nAll ${dirs.length} director(y/ies) completed.`);
    process.exit(0);
}
main().catch((error) => {
    console.error(error);
    process.exit(1);
});
