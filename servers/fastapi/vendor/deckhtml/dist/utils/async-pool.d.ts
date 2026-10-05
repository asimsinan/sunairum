/** Playwright page pool size for multi-slide inspect: CPU cores − 2, at least 1. */
export declare function resolveSlideInspectConcurrency(): number;
/**
 * Run async tasks with a fixed concurrency limit (work-stealing over indices).
 */
export declare function runAsyncPool<T, R>(items: readonly T[], concurrency: number, fn: (item: T, index: number) => Promise<R>): Promise<R[]>;
