import { createInstance } from 'i18next'
import { describe, expect, it } from 'vitest'
import { PLATFORMS } from './platforms'
import en from '@/i18n/resources/en.json'
import zhCN from '@/i18n/resources/zh-CN.json'
import zhTW from '@/i18n/resources/zh-TW.json'
import ja from '@/i18n/resources/ja.json'

describe('platform names and connection instructions', () => {
  it.each(Object.entries({ en, 'zh-CN': zhCN, 'zh-TW': zhTW, ja }))('resolves every visible platform in %s', async (lng, translation) => {
    const i18n = createInstance()
    await i18n.init({ lng, fallbackLng: false, resources: { [lng]: { translation } } })
    for (const platform of PLATFORMS) {
      expect(i18n.exists(platform.labelKey)).toBe(true)
      expect(i18n.exists(platform.descriptionKey)).toBe(true)
      expect(i18n.t(platform.labelKey)).not.toBe(platform.labelKey)
    }
    for (const key of ['amatsuki_guide', 'zhangxin_guide', 'native_advice_only', 'reconnect']) {
      expect(i18n.exists(`platform.${key}`)).toBe(true)
    }
    if (lng === 'zh-CN') {
      expect(i18n.t('platform.amatsuki')).toBe('天月麻雀')
      expect(i18n.t('platform.zhangxin')).toBe('掌心全民麻将')
    }
  })
})
