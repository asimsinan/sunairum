/**
 * Atomic, overwrite-safe file writing for the deckhtml CLI (DH-P0-008).
 *
 * Default policy: refuse to overwrite an existing file. Pass `overwrite: true`
 * (or use the CLI `--force` flag) to allow it. Writes always go to a temp file
 * in the same directory, then atomically renamed onto the target so a crash
 * never leaves a partially-written output.
 */
export declare class OutputExistsError extends Error {
    readonly target: string;
    readonly ruleId = "DECKHTML_OUTPUT_EXISTS";
    constructor(target: string);
}
export interface AtomicWriteOptions {
    /** When true, overwrite an existing target file. Default: false (refuse). */
    overwrite?: boolean;
}
/**
 * Write `data` to `target` atomically. Refuses to overwrite by default.
 */
export declare function atomicWriteFile(target: string, data: string | Uint8Array, options?: AtomicWriteOptions): Promise<void>;
