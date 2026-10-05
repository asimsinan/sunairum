export type ResolvedInput = {
    kind: 'file';
    paths: string[];
} | {
    kind: 'url';
    urls: string[];
} | {
    kind: 'stdin';
    tempPath: string;
};
export declare function resolveInputs(inputs: string[]): Promise<ResolvedInput>;
export declare function materializeInputs(resolved: ResolvedInput): Promise<{
    paths: string[];
    cleanup: () => Promise<void>;
}>;
export type OutputFormat = 'pptx' | 'pdf' | 'png';
/**
 * Infer output format from `-o` extension.
 * Without `-o`, defaults to pptx (path is derived from the input).
 */
export declare function resolveOutputFormat(explicitOutput?: string): OutputFormat;
export declare function deriveOutputPath(inputPaths: string[], format: OutputFormat, explicitOutput?: string): string;
