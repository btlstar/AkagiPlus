import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import { invoke } from '@/lib/tauri'
import { useConfigStore } from '@/stores/configStore'

export function AmatsukiStyleCard() {
  const { t } = useTranslation()
  const config = useConfigStore(s => s.config)
  const setConfig = useConfigStore(s => s.setConfig)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  if (!config) return null
  const enabled = config.proxy.amatsuki?.cosmetics_enabled ?? true
  const change = async (value: boolean) => {
    setSaving(true); setError('')
    const next = { ...config, proxy: { ...config.proxy, amatsuki: {
      client_path: '', ...config.proxy.amatsuki, cosmetics_enabled: value,
    } } }
    try {
      await invoke('update_config', { newConfig: next })
      setConfig(next)
    } catch (e) { setError(String(e)) }
    finally { setSaving(false) }
  }
  return <Card>
    <CardHeader className="flex flex-row items-center justify-between gap-4">
      <CardTitle>{t('platform.plugin_title', { game: t('platform.amatsuki'), plugin: 'AmatsukiStyle' })}</CardTitle>
      <Switch aria-label="启用 AmatsukiStyle" checked={enabled} disabled={saving} onCheckedChange={v => void change(v)} />
    </CardHeader>
    <CardContent className="grid gap-3 text-sm text-muted-foreground">
      <p>{t(enabled ? 'platform.amatsuki_enabled' : 'platform.amatsuki_disabled')}</p>
      <p>{t('platform.amatsuki_cosmetics')}</p>
      <p>{t('platform.amatsuki_status_hint')}</p>
      <p>{t('platform.amatsuki_reset_hint')}</p>
      {error && <p className="text-destructive" role="alert">{error}</p>}
    </CardContent>
  </Card>
}
