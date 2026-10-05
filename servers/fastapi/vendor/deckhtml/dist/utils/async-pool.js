"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.resolveSlideInspectConcurrency = resolveSlideInspectConcurrency;
exports.runAsyncPool = runAsyncPool;
const node_os_1 = __importDefault(require("node:os"));
/** Playwright page pool size for multi-slide inspect: CPU cores − 2, at least 1. */
function resolveSlideInspectConcurrency() {
    const cores = node_os_1.default.cpus().length;
    return Math.max(1, cores - 2);
}
/**
 * Run async tasks with a fixed concurrency limit (work-stealing over indices).
 */
async function runAsyncPool(items, concurrency, fn) {
    if (items.length === 0)
        return [];
    const limit = Math.max(1, Math.min(concurrency, items.length));
    const results = new Array(items.length);
    let next = 0;
    async function worker() {
        while (true) {
            const index = next++;
            if (index >= items.length)
                return;
            results[index] = await fn(items[index], index);
        }
    }
    await Promise.all(Array.from({ length: limit }, () => worker()));
    return results;
}
