/**
 * Suppress console.log / console.warn for the duration of fn when quiet is true.
 * Supports nested calls via a depth counter.
 */
export declare function runQuietly<T>(quiet: boolean, fn: () => Promise<T>): Promise<T>;
