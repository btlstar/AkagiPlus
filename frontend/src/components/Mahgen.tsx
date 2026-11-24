import { warmSuggestionTiles } from '@/lib/cachedMahgen'
import { useEffect, useLayoutEffect, useRef, type RefObject } from 'react'
import {
  registerMahgen,
  unregisterMahgen,
  setMahgenSeq,
  type MahgenKind,
} from '@/lib/mahgenRegistry'

type Props = {
  seq: string
  kind: MahgenKind
  riverMode?: boolean
  /** Element whose clientWidth drives mahgen sizing. Defaults to the wrapper's parent. */
  containerRef?: RefObject<HTMLElement | null>
  className?: string
}

// Wraps a single <mah-gen> custom element, manages registry lifecycle, and
// uses decoded image caching for live suggestions.
export function Mahgen({ seq, kind, riverMode, containerRef, className }: Props) {
  const wrapperRef = useRef<HTMLSpanElement>(null)
  const elRef = useRef<HTMLElement | null>(null)

  useLayoutEffect(() => {
    const wrapper = wrapperRef.current
    if (!wrapper) return

    const cached = kind === 'bot-show' || kind === 'overlay-show'
    const el = document.createElement(cached ? 'ap-mahgen' : 'mah-gen') as HTMLElement
    if (riverMode) el.setAttribute('data-river-mode', '')
    if (seq) el.setAttribute('data-seq', seq)
    wrapper.appendChild(el)
    elRef.current = el

    const container = containerRef?.current ?? wrapper.parentElement
    registerMahgen(el as never, kind, container)

    return () => {
      unregisterMahgen(el as never)
      el.remove()
      elRef.current = null
    }
    // Mount once per kind/riverMode change. Seq is updated separately below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind, riverMode])

  useLayoutEffect(() => {
    const el = elRef.current
    if (!el) return
    setMahgenSeq(el as never, seq)
  }, [seq])

  useEffect(() => {
    if (kind === 'bot-show' || kind === 'overlay-show') warmSuggestionTiles()
  }, [kind])

  return <span ref={wrapperRef} className={className} style={{ display: 'inline-block', transition: 'opacity 120ms' }} />
}
