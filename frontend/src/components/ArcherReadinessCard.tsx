import { CheckCircle2, CircleAlert, LoaderCircle, RotateCw } from 'lucide-react'
import type { ArcherReadiness } from '@/hooks/useOverlayShow'

export function ArcherReadinessCard({ status, recheck }: {
  status: ArcherReadiness
  recheck: () => void
}) {
  const checking = status.state === 'checking'
  const ready = status.state === 'ready'
  const Icon = checking ? LoaderCircle : ready ? CheckCircle2 : CircleAlert
  const color = checking ? '#94a3b8' : ready ? '#6ee7b7' : '#fbbf24'
  return (
    <div role="status" aria-live="polite" className="rounded-md border border-border p-2.5"
      style={{ borderLeft: `3px solid ${color}` }}>
      <div className="flex items-center gap-2">
        <Icon aria-hidden="true" className={`size-4 shrink-0 ${checking ? 'animate-spin' : ''}`}
          style={{ color }} />
        <span className="text-sm font-medium" style={{ color }}>{status.message}</span>
      </div>
      {status.models.length > 0 && (
        <div className="mt-2 space-y-1">
          {status.models.map((model) => (
            <div key={model.players} className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span className="size-1.5 shrink-0 rounded-full"
                style={{ backgroundColor: model.available ? '#6ee7b7' : '#fbbf24' }} />
              <span className="shrink-0">{model.players === 3 ? '三麻' : '四麻'}</span>
              <span className="truncate">{model.name}</span>
            </div>
          ))}
        </div>
      )}
      {ready && <p className="mt-2 text-xs text-muted-foreground">等待对局开始</p>}
      <button type="button" onClick={recheck} disabled={checking}
        style={{ pointerEvents: 'auto' }}
        className="mt-3 flex cursor-pointer items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground disabled:cursor-default disabled:opacity-50">
        <RotateCw aria-hidden="true" className="size-3" />
        {checking ? '检测中' : '重新检测'}
      </button>
    </div>
  )
}
