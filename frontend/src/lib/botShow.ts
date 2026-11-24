import type { ShowItem, ShowMeta } from '@/types'

// Pure helpers for the bot's `meta.show` payload. Used by the Bot Show
// dashboard tile and by the always-on-top overlay window, which get their data
// from different places (a zustand store vs. a raw `bot-response` listener) and
// only agree on shape.

/** "#aabbcc" → "rgba(170,187,204,a)". Undefined when the input isn't a valid hex. */
export function hexToRgba(hex: string | null | undefined, alpha: number): string | undefined {
  if (!hex) return undefined
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim())
  if (!m) return undefined
  const n = parseInt(m[1], 16)
  return `rgba(${(n >> 16) & 0xff}, ${(n >> 8) & 0xff}, ${n & 0xff}, ${alpha})`
}

/** The `show` block of a bot response's `meta`, or null if it carries none. */
export function pickShow(meta: unknown): ShowMeta | null {
  if (!meta || typeof meta !== 'object') return null
  const show = (meta as Record<string, unknown>).show
  if (!show || typeof show !== 'object') return null
  const items = (show as Record<string, unknown>).items
  if (!Array.isArray(items) || items.length === 0) return null
  return show as ShowMeta
}

/** A row is worth a line only if it has something to draw. */
export function hasContent(it: ShowItem): boolean {
  return Boolean(it.label || it.tiles || (it.pais && it.pais.length))
}

/**
 * Drawable rows of `show`, capped at `limit`.
 *
 * `limit` is the overlay's top-N. It is applied *after* the empty-row filter
 * so "top 3" always means three visible rows, not three candidates of which
 * some may render as nothing.
 */
export function visibleItems(show: ShowMeta | null, limit?: number): ShowItem[] {
  const items = show?.items.filter(hasContent) ?? []
  const visible = limit === undefined ? items : items.slice(0, Math.max(0, limit))
  const weighted = visible.filter((it) => typeof it.weight === 'number' && Number.isFinite(it.weight) && it.weight >= 0)
  const total = weighted.reduce((sum, it) => sum + it.weight!, 0)
  if (!weighted.length || !Number.isFinite(total) || total <= 0) return visible
  const exact = weighted.map((it) => it.weight! / total * 1000)
  const units = exact.map(Math.floor)
  const order = exact.map((value, i) => ({ i, remainder: value - units[i] }))
    .sort((a, b) => b.remainder - a.remainder || a.i - b.i)
  const remaining = 1000 - units.reduce((sum, value) => sum + value, 0)
  for (const { i } of order.slice(0, remaining)) units[i] += 1
  const percentages = new Map(weighted.map((it, i) => [it, units[i] / 10]))
  return visible.map((it) => {
    const percentage = percentages.get(it)
    return percentage === undefined ? it : { ...it, weight_percent: percentage, value: `${percentage.toFixed(1)}%` }
  })
}
