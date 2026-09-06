/**
 * useWakeWord — continuous background speech recognition for wake word detection.
 * Uses the browser Web Speech API (Chrome/Edge). No server required.
 * Phrases: "hey jarvis", "jarvis", "ok jarvis"
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import type { SpeechRecognitionInstance } from './useSpeechRecognition'

const WAKE_PHRASES = ['hey jarvis', 'jarvis', 'ok jarvis']

interface UseWakeWordReturn {
  supported: boolean
  active: boolean
  enable: () => void
  disable: () => void
}

export function useWakeWord(onWake: () => void, enabled: boolean, paused = false): UseWakeWordReturn {
  const SpeechRecognitionCtor =
    typeof window !== 'undefined'
      ? window.SpeechRecognition ?? window.webkitSpeechRecognition
      : undefined

  const supported = SpeechRecognitionCtor != null
  const [active, setActive] = useState(false)
  const recRef = useRef<SpeechRecognitionInstance | null>(null)
  const enabledRef = useRef(enabled)
  const onWakeRef = useRef(onWake)
  const startRef = useRef<() => void>(() => undefined)

  useEffect(() => { enabledRef.current = enabled }, [enabled])
  useEffect(() => { onWakeRef.current = onWake }, [onWake])

  const stop = useCallback(() => {
    recRef.current?.abort()
    recRef.current = null
    setActive(false)
  }, [])

  const start = useCallback(() => {
    if (!SpeechRecognitionCtor || recRef.current) return
    const rec = new SpeechRecognitionCtor()
    rec.continuous = true
    rec.interimResults = true
    rec.lang = 'en-US'

    rec.onresult = (e) => {
      const results = e.results
      for (let i = results.length - 1; i >= 0; i--) {
        const text = results[i][0].transcript.toLowerCase().trim()
        if (WAKE_PHRASES.some((p) => text.includes(p))) {
          onWakeRef.current()
          return
        }
      }
    }

    rec.onend = () => {
      recRef.current = null
      if (enabledRef.current) startRef.current()
      else setActive(false)
    }

    rec.onerror = () => {
      recRef.current = null
      if (enabledRef.current) startRef.current()
    }

    recRef.current = rec
    rec.start()
    setActive(true)
  }, [SpeechRecognitionCtor])

  // Keep startRef in sync so onend/onerror can call latest version
  useEffect(() => { startRef.current = start }, [start])

  useEffect(() => {
    if (enabled && supported && !paused) start()
    else stop()
    return stop
  }, [enabled, supported, paused, start, stop])

  return { supported, active, enable: start, disable: stop }
}
