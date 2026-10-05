"use strict";
/**
 * Atomic, overwrite-safe file writing for the deckhtml CLI (DH-P0-008).
 *
 * Default policy: refuse to overwrite an existing file. Pass `overwrite: true`
 * (or use the CLI `--force` flag) to allow it. Writes always go to a temp file
 * in the same directory, then atomically renamed onto the target so a crash
 * never leaves a partially-written output.
 */
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.OutputExistsError = void 0;
exports.atomicWriteFile = atomicWriteFile;
const promises_1 = __importDefault(require("node:fs/promises"));
const node_path_1 = __importDefault(require("node:path"));
const node_crypto_1 = require("node:crypto");
class OutputExistsError extends Error {
    constructor(target) {
        super(`Refusing to overwrite existing file: ${target}. Re-run with --force to overwrite.`);
        this.target = target;
        this.ruleId = 'DECKHTML_OUTPUT_EXISTS';
        this.name = 'OutputExistsError';
    }
}
exports.OutputExistsError = OutputExistsError;
/**
 * Write `data` to `target` atomically. Refuses to overwrite by default.
 */
async function atomicWriteFile(target, data, options = {}) {
    const overwrite = options.overwrite ?? false;
    if (!overwrite) {
        let exists = false;
        try {
            await promises_1.default.access(target);
            exists = true;
        }
        catch {
            exists = false;
        }
        if (exists) {
            throw new OutputExistsError(target);
        }
    }
    await promises_1.default.mkdir(node_path_1.default.dirname(target), { recursive: true });
    const tmp = `${target}.${process.pid}.${(0, node_crypto_1.randomBytes)(4).toString('hex')}.tmp`;
    try {
        await promises_1.default.writeFile(tmp, data);
        await promises_1.default.rename(tmp, target);
    }
    catch (err) {
        await promises_1.default.rm(tmp, { force: true }).catch(() => { });
        throw err;
    }
}
