export function formatRelativeTime(
  unixSeconds: number | null | undefined,
  t: (key: string, vars?: Record<string, string | number>) => string,
  locale: string,
): string {
  if (!unixSeconds) {
    return new Date(0).toLocaleString(locale)
  }
  const then = unixSeconds * 1000
  const deltaSec = Math.max(0, Math.round((Date.now() - then) / 1000))
  if (deltaSec < 60) return t('libraryRelativeJustNow')
  if (deltaSec < 3600) return t('libraryRelativeMinutes', { n: Math.floor(deltaSec / 60) })
  if (deltaSec < 86400) return t('libraryRelativeHours', { n: Math.floor(deltaSec / 3600) })
  if (deltaSec < 86400 * 14) return t('libraryRelativeDays', { n: Math.floor(deltaSec / 86400) })
  return new Date(then).toLocaleString(locale)
}
