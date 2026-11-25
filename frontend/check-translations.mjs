import { readFileSync } from 'node:fs'

// Keep the release gate aligned with SUPPORTED_LANGS in src/i18n/index.ts.
const languages = ['en', 'ja', 'zh-CN', 'zh-TW']
const catalogs = new Map(languages.map(language => [
  language,
  flatten(JSON.parse(readFileSync(new URL(`./src/i18n/resources/${language}.json`, import.meta.url), 'utf8'))),
]))
const keys = new Set([...catalogs.values()].flatMap(catalog => [...catalog.keys()]))
const errors = []
// Japanese places the highlighted word first in these split sentences.
const optionalEmpty = new Set(['ja:setup.finish.click_finish_pre', 'ja:bots.install_repo_hint_pre'])

function flatten(node, prefix = '', result = new Map()) {
  for (const [key, value] of Object.entries(node)) {
    const path = prefix ? `${prefix}.${key}` : key
    if (value && typeof value === 'object' && !Array.isArray(value)) flatten(value, path, result)
    else result.set(path, value)
  }
  return result
}

for (const key of keys) {
  for (const [language, catalog] of catalogs) {
    const value = catalog.get(key)
    if (typeof value !== 'string' || (!value.trim() && !optionalEmpty.has(language + ':' + key))) errors.push(`${language}: missing text for ${key}`)
  }
}

if (errors.length) {
  console.error(errors.join('\n'))
  process.exitCode = 1
} else {
  console.log(`Translation check passed: ${keys.size} keys in ${languages.length} languages.`)
}
