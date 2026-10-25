import type { Lang } from '../i18n'

/** Speak a summary via window.speechSynthesis. hi -> hi-IN voice, else en-IN. */
export function speak(text: string, lang: Lang): void {
  if (typeof window === 'undefined' || !('speechSynthesis' in window)) return
  const synth = window.speechSynthesis
  synth.cancel()
  const clean = text
    .replace(/[\p{Extended_Pictographic}\u2600-\u27BF\uFE0F]/gu, ' ')
    .replace(/₹\s?/g, lang === 'hi' ? 'रुपये ' : 'rupees ')
    .replace(/\s+/g, ' ')
    .trim()
  if (!clean) return
  const utterance = new SpeechSynthesisUtterance(clean)
  utterance.lang = lang === 'hi' ? 'hi-IN' : 'en-IN'
  utterance.rate = 0.95
  synth.speak(utterance)
}
