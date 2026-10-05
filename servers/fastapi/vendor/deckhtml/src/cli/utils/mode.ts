export type ExecutionMode = 'auto' | 'local' | 'cloud';
export type ResolvedMode = 'local' | 'cloud';

export function resolveMode(
  requested: ExecutionMode,
  hasCredentials: boolean
): ResolvedMode {
  if (requested === 'local') return 'local';
  // Cloud mode no longer requires credentials up front: the SDK always sends
  // X-Auth-UUID and the server treats UUID-only requests as rate-limited
  // guests. A 401 response triggers the login / API-key guidance flow.
  if (requested === 'cloud') return 'cloud';
  return hasCredentials ? 'cloud' : 'local';
}

export interface CloudOnlyFlags {
  /** Historical; local mode now embeds deck fonts by default. Kept for API parity. */
  embedFonts?: boolean;
}

/**
 * Previously blocked `--embed-fonts` in local mode. Local conversion embeds
 * deck fonts via `embedDeckFonts` unconditionally, so the flag is allowed
 * (and treated as a no-op request for the cloud library path).
 */
export function validateCloudOnlyFlags(
  _mode: ResolvedMode,
  _flags: CloudOnlyFlags
): void {
  // no-op: --embed-fonts is valid in local and cloud
}
