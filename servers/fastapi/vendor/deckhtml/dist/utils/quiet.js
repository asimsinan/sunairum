"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.runQuietly = runQuietly;
let muteDepth = 0;
let savedLog;
let savedWarn;
/**
 * Suppress console.log / console.warn for the duration of fn when quiet is true.
 * Supports nested calls via a depth counter.
 */
async function runQuietly(quiet, fn) {
    if (!quiet) {
        return fn();
    }
    if (muteDepth === 0) {
        savedLog = console.log;
        savedWarn = console.warn;
        console.log = () => { };
        console.warn = () => { };
    }
    muteDepth += 1;
    try {
        return await fn();
    }
    finally {
        muteDepth -= 1;
        if (muteDepth === 0) {
            console.log = savedLog;
            console.warn = savedWarn;
        }
    }
}
