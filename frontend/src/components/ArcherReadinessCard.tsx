import { useTranslation } from 'react-i18next'
import { CheckCircle2, CircleAlert, LoaderCircle, RotateCw } from 'lucide-react'
import type { ArcherReadiness } from '@/hooks/useOverlayShow'

export function ArcherReadinessCard({ status, recheck }: {
  status: ArcherReadiness
  recheck: () => void
}) {
  const { t } = useTranslation()
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
        <span className="text-sm font-medium" style={{ color }}>{t('archer_hud.' + (status.code || status.state), { defaultValue: status.message })}</span>
      </div>
      {status.models.length > 0 && (
        <div className="mt-2 space-y-1">
          {status.models.map((model) => (
            <div key={model.players} className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span className="size-1.5 shrink-0 rounded-full"
                style={{ backgroundColor: model.available ? '#6ee7b7' : '#fbbf24' }} />
              <span className="shrink-0">{t(model.players === 3 ? 'archer_hud.three' : 'archer_hud.four')}</span>
              <span className="truncate">{model.name}</span>
            </div>
          ))}
        </div>
      )}
      {ready && <p className="mt-2 text-xs text-muted-foreground">{t('archer_hud.waiting')}</p>}
      <button type="button" onClick={recheck} disabled={checking}
        style={{ pointerEvents: 'auto' }}
        className="mt-3 flex cursor-pointer items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground disabled:cursor-default disabled:opacity-50">
        <RotateCw aria-hidden="true" className="size-3" />
        {t(checking ? 'archer_hud.checking' : 'archer_hud.retry')}
      </button>
    </div>
  )
}
