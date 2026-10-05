export type ExecutionMode = 'auto' | 'local' | 'cloud';
export type ResolvedMode = 'local' | 'cloud';
export declare function resolveMode(requested: ExecutionMode, hasCredentials: boolean): ResolvedMode;
export interface CloudOnlyFlags {
    /** Historical; local mode now embeds deck fonts by default. Kept for API parity. */
    embedFonts?: boolean;
}
/**
 * Previously blocked `--embed-fonts` in local mode. Local conversion embeds
 * deck fonts via `embedDeckFonts` unconditionally, so the flag is allowed
 * (and treated as a no-op request for the cloud library path).
 */
export declare function validateCloudOnlyFlags(_mode: ResolvedMode, _flags: CloudOnlyFlags): void;
