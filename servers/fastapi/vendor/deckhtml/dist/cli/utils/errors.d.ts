export declare const ExitCode: {
    readonly SUCCESS: 0;
    readonly ERROR: 1;
    readonly USAGE_ERROR: 2;
};
export interface OutputErrorOptions {
    apiBase?: string;
}
export declare function outputError(error: Error, jsonMode: boolean, code?: string, options?: OutputErrorOptions): void;
