/**
 * useWakeWord — continuous background wake word detection via Web Speech API.
 *
 * Mic-release pattern:
 * - start() debounced at 250ms so StrictMode stop/start storms settle AND
 *   Chrome has time to release the mic after abort().
 * - If onend fires without onaudiostart (mic still busy), retries up to
 *   MAX_RETRIES times with RETRY_MS backoff.
 *
 * Phase 34 (dedicated wake word engine) is planned but deferred.
 * See JARVIS_MASTER_SPEC.md Section 87 for details.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import type { SpeechRecognitionInstance } from './useSpeechRecognition'

const WAKE_PHRASES = [
  'hey jarvis', 'jarvis', 'ok jarvis', 'hello jarvis', 'hi jarvis',
  'hey arvis', 'arvis', 'hey travis', 'travis', 'hey davis', 'davis',
]
const WAKE_REGEX = /\b(hey\s+)?[jt]?arvis\b/
const DEBOUNCE_MS = 250
const MAX_RETRIES = 8
const RETRY_MS = 200

interface UseWakeWordReturn {
  supported: boolean
  active: boolean
  enable: () => void
  disable: () => void
}

function getCtor() {
  if (typeof window === 'undefined') return undefined
  return window.SpeechRecognition ?? window.webkitSpeechRecognition
}

function isWakePhrase(text: string): boolean {
  return WAKE_PHRASES.some((p) => text.includes(p)) || WAKE_REGEX.test(text)
}

export function useWakeWord(onWake: () => void, enabled: boolean): UseWakeWordReturn {
  const supported = getCtor() != null

  const [active, setActive] = useState(false)
  const recRef = useRef<SpeechRecognitionInstance | null>(null)
  const enabledRef = useRef(enabled)
  const onWakeRef = useRef(onWake)
  const stoppedRef = useRef(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => { enabledRef.current = enabled }, [enabled])
  useEffect(() => { onWakeRef.current = onWake }, [onWake])

  const clearTimer = useCallback(() => {
    if (timerRef.current != null) { clearTimeout(timerRef.current); timerRef.current = null }
  }, [])

  const startNow = useCallback((attempt = 0) => {
    const Ctor = getCtor()
    if (!Ctor || recRef.current || stoppedRef.current) return
    console.log('[wake] startNow attempt', attempt)

    const rec = new Ctor() as SpeechRecognitionInstance
    rec.continuous = true
    rec.interimResults = true
    rec.lang = 'en-US'

    let wakeDetected = false
    let micOpened = false

    ;(rec as unknown as { onaudiostart: () => void }).onaudiostart = () => {
      console.log('[wake] onaudiostart — mic live')
      micOpened = true
      setActive(true)
    }

    rec.onresult = (e) => {
      for (let i = e.results.length - 1; i >= 0; i--) {
        const chunk = e.results[i][0].transcript.toLowerCase().trim()
        if (isWakePhrase(chunk)) {
          console.log('[wake] DETECTED:', JSON.stringify(chunk))
          wakeDetected = true
          stoppedRef.current = true
          rec.abort()
          recRef.current = null
          setActive(false)
          onWakeRef.current()
          return
        }
      }
    }

    rec.onend = () => {
      console.log('[wake] onend — micOpened=', micOpened, 'wakeDetected=', wakeDetected, 'stopped=', stoppedRef.current)
      recRef.current = null
      setActive(false)
      if (stoppedRef.current || wakeDetected) return
      if (!micOpened && attempt < MAX_RETRIES) {
        console.log('[wake] mic busy, retry', attempt + 1)
        timerRef.current = setTimeout(() => startNow(attempt + 1), RETRY_MS)
      } else if (enabledRef.current) {
        console.log('[wake] normal end — restarting')
        timerRef.current = setTimeout(() => startNow(0), 200)
      }
    }

    rec.onerror = (e: unknown) => {
      const err = (e as { error?: string }).error
      console.log('[wake] onerror:', err, 'attempt=', attempt)
      recRef.current = null
      setActive(false)
      if (err === 'aborted' || stoppedRef.current || wakeDetected) return
      if (!micOpened && attempt < MAX_RETRIES) {
        timerRef.current = setTimeout(() => startNow(attempt + 1), RETRY_MS)
      } else if (enabledRef.current) {
        timerRef.current = setTimeout(() => startNow(0), 300)
      }
    }

    recRef.current = rec
    try {
      rec.start()
      console.log('[wake] rec.start() called, attempt', attempt)
    } catch (err) {
      console.warn('[wake] rec.start() threw:', err)
      recRef.current = null
      if (!stoppedRef.current && attempt < MAX_RETRIES) {
        timerRef.current = setTimeout(() => startNow(attempt + 1), RETRY_MS)
      }
    }
  }, [clearTimer])

  const start = useCallback(() => {
    clearTimer()
    stoppedRef.current = false
    timerRef.current = setTimeout(() => startNow(0), DEBOUNCE_MS)
  }, [clearTimer, startNow])

  const stop = useCallback(() => {
    console.log('[wake] stop called')
    clearTimer()
    stoppedRef.current = true
    recRef.current?.abort()
    recRef.current = null
    setActive(false)
  }, [clearTimer])

  useEffect(() => {
    if (enabled && supported) start()
    else stop()
    return stop
  }, [enabled, supported, start, stop])

  return { supported, active, enable: start, disable: stop }
}
