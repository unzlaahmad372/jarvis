/**
 * useSpeechSynthesis — wraps the browser SpeechSynthesis API for TTS.
 */

import { useCallback, useRef } from 'react'

interface UseSpeechSynthesisReturn {
  supported: boolean
  speak: (text: string) => void
  cancel: () => void
}

export function useSpeechSynthesis(): UseSpeechSynthesisReturn {
  const supported =
    typeof window !== 'undefined' && 'speechSynthesis' in window
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null)

  const speak = useCallback(
    (text: string) => {
      if (!supported) return
      window.speechSynthesis.cancel()
      const utterance = new SpeechSynthesisUtterance(text)
      utterance.rate = 1.0
      utterance.pitch = 1.0
      utteranceRef.current = utterance
      window.speechSynthesis.speak(utterance)
    },
    [supported],
  )

  const cancel = useCallback(() => {
    if (supported) window.speechSynthesis.cancel()
  }, [supported])

  return { supported, speak, cancel }
}
