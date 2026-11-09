import iconLight from '@/assets/logo/akagi-icon-light.svg'
import iconDark from '@/assets/logo/akagi-icon-dark.svg'
import { cn } from '@/lib/utils'

// The Akagi brand ships two inkings per asset: `-light` for light
// backgrounds (dark glyphs) and `-dark` for dark backgrounds (light glyphs).
// The theme store toggles the `.dark` class on <html>, so we render both and
// let Tailwind's `dark:` variant pick — this tracks light/dark/system without
// subscribing to the store.

/** The square mahjong-tile mark (no wordmark). Portrait ratio ≈ 0.84. */
export function AkagiIcon({ className }: { className?: string }) {
  return (
    <span className={cn('inline-flex shrink-0', className)}>
      <img src={iconLight} alt="" aria-hidden className="h-full w-auto dark:hidden" />
      <img src={iconDark} alt="" aria-hidden className="hidden h-full w-auto dark:block" />
    </span>
  )
}

/** The full logo: tile mark + "Akagi" wordmark. Wide ratio ≈ 2.87. */
export function AkagiWordmark({ className }: { className?: string }) {
  return <span className={cn('inline-flex items-center gap-2 font-semibold tracking-tight', className)}>
    <AkagiIcon className="h-full" /><span>Akagi<span className="text-muted-foreground">Plus</span></span>
  </span>
}
