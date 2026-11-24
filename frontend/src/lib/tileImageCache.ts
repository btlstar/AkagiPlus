/** Bounded, promise-coalescing image cache, including decode before publication. */
export class TileImageCache {
  private entries = new Map<string, { image?: string; pending: Promise<string> }>()
  private render: (seq: string, river: boolean) => Promise<string>
  private limit: number
  constructor(render: (seq: string, river: boolean) => Promise<string>, limit = 256) {
    this.render = render
    this.limit = limit
  }
  private key(seq: string, river: boolean) { return `${river ? 1 : 0}:${seq}` }
  peek(seq: string, river = false) { return this.entries.get(this.key(seq, river))?.image }
  get(seq: string, river = false): Promise<string> {
    const key = this.key(seq, river)
    const cached = this.entries.get(key)
    if (cached) {
      this.entries.delete(key)
      this.entries.set(key, cached)
      return cached.pending
    }
    const entry: { image?: string; pending: Promise<string> } = {
      pending: Promise.resolve().then(() => this.render(seq, river)),
    }
    entry.pending = entry.pending.then((image) => {
      entry.image = image
      return image
    }, (error) => {
      if (this.entries.get(key) === entry) this.entries.delete(key)
      throw error
    })
    this.entries.set(key, entry)
    if (this.entries.size > this.limit) this.entries.delete(this.entries.keys().next().value!)
    return entry.pending
  }
}

/** Older renders may finish later; only the current sequence can publish. */
export class TileImageRequest {
  private generation = 0
  private cache: TileImageCache
  constructor(cache: TileImageCache) { this.cache = cache }
  update(seq: string, river: boolean, publish: (src?: string) => void): void {
    const generation = ++this.generation
    const image = this.cache.peek(seq, river)
    publish(image)
    if (image || !seq) return
    void this.cache.get(seq, river).then((src) => {
      if (generation === this.generation) publish(src)
    }, () => {
      if (generation === this.generation) publish(undefined)
    })
  }
  cancel() { this.generation++ }
}
