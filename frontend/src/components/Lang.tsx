import { useI18n } from '../i18n'
import type { Lang } from '../i18n'

/** EN / हिं language toggle, persisted in localStorage via the i18n provider. */
export function Lang() {
  const { lang, setLang } = useI18n()
  const options: Lang[] = ['en', 'hi']
  return (
    <div className="flex overflow-hidden rounded-lg border border-ink/20 bg-white text-sm font-bold" role="group" aria-label="Language">
      {options.map((l) => (
        <button
          key={l}
          type="button"
          onClick={() => setLang(l)}
          aria-pressed={lang === l}
          className={`min-h-[40px] px-3 transition-colors ${
            lang === l ? 'bg-brand text-white' : 'bg-white text-ink hover:bg-ivory'
          }`}
        >
          {l === 'en' ? 'EN' : 'हिं'}
        </button>
      ))}
    </div>
  )
}
