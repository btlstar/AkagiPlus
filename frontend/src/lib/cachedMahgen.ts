import { Mahgen as Renderer } from 'mahgen'
import { TileImageCache, TileImageRequest } from './tileImageCache'

const images = new TileImageCache(async (seq, river) => {
  const src = await Renderer.render(seq, river)
  const image = new Image()
  image.src = src
  await image.decode()
  return src
})

class CachedMahgenElement extends HTMLElement {
  private image = document.createElement('img')
  private request = new TileImageRequest(images)
  static get observedAttributes() { return ['data-seq', 'data-river-mode'] }
  constructor() {
    super()
    this.attachShadow({ mode: 'open' }).append(this.image)
    this.image.style.display = 'block'
    this.image.decoding = 'sync'
  }
  connectedCallback() { this.update() }
  disconnectedCallback() { this.request.cancel() }
  attributeChangedCallback() { this.update() }
  private update() {
    const seq = this.getAttribute('data-seq') ?? ''
    this.request.update(seq, this.hasAttribute('data-river-mode'), (src) => {
      // Hide the previous tile immediately, before a new percentage can paint.
      this.image.style.visibility = src ? 'visible' : 'hidden'
      if (src) this.image.src = src
      else this.image.removeAttribute('src')
    })
  }
}

if (!customElements.get('ap-mahgen')) customElements.define('ap-mahgen', CachedMahgenElement)

let warmed = false
export function warmSuggestionTiles(): void {
  if (warmed) return
  warmed = true
  // Batch gradually while the overlay is idle, never blocking its first paint.
  const sequences = ['m', 'p', 's'].flatMap((suit) =>
    Array.from({ length: 10 }, (_, rank) => `${rank}${suit}`))
    .concat(Array.from({ length: 7 }, (_, rank) => `${rank + 1}z`))
  let index = 0
  const batch = () => {
    for (let n = 0; n < 4 && index < sequences.length; n++, index++) {
      void images.get(sequences[index]).catch(() => {})
    }
    if (index < sequences.length) window.setTimeout(batch, 25)
  }
  window.setTimeout(batch, 0)
}
