import { useRef, useState, useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { chatApi, conversationsApi, voiceApi } from '@/services/api/client'
import { useChatStore } from '@/app/stores/chatStore'
import { useSpeechRecognition } from '@/hooks/useSpeechRecognition'
import { useSpeechSynthesis } from '@/hooks/useSpeechSynthesis'
import type { MessageOut, ResponseCompletePayload, SSEEvent } from '@/types/api'
import styles from './ChatPage.module.css'

// ── Message bubble ────────────────────────────────────────────────────────────

function MessageBubble({ message }: { message: MessageOut }) {
  const isUser = message.role === 'user'
  return (
    <div className={`${styles.message} ${isUser ? styles.user : styles.assistant}`}>
      <div className={styles.messageRole} aria-label={`${message.role} message`}>
        {isUser ? 'YOU' : 'JARVIS'}
      </div>
      <div className={styles.messageContent}>{message.content}</div>
      {message.token_usage && (
        <div className={styles.tokenInfo} aria-label="Token usage">
          {message.token_usage.input_tokens != null && (
            <span>in:{message.token_usage.input_tokens}</span>
          )}
          {message.token_usage.output_tokens != null && (
            <span>out:{message.token_usage.output_tokens}</span>
          )}
        </div>
      )}
    </div>
  )
}

// ── Streaming bubble ──────────────────────────────────────────────────────────

function StreamingBubble({ content }: { content: string }) {
  return (
    <div className={`${styles.message} ${styles.assistant} ${styles.streaming}`}>
      <div className={styles.messageRole}>JARVIS</div>
      <div className={styles.messageContent}>
        {content || <span className={styles.thinkingDots} aria-label="Thinking">···</span>}
      </div>
    </div>
  )
}

// ── Chat page ─────────────────────────────────────────────────────────────────

export function ChatPage() {
  const queryClient = useQueryClient()
  const {
    activeConversationId,
    isStreaming,
    streamingContent,
    jarvisState,
    lastError,
    startStreaming,
    appendStreamChunk,
    finishStreaming,
    setError,
    clearError,
    setActiveConversation,
    setJarvisState,
  } = useChatStore()

  const [input, setInput] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const stt = useSpeechRecognition()
  const tts = useSpeechSynthesis()

  // Fetch voice settings once
  const { data: voiceSettings } = useQuery({
    queryKey: ['voice-settings'],
    queryFn: () => voiceApi.settings(),
    staleTime: Infinity,
  })

  const voiceEnabled = voiceSettings?.enabled ?? false
  const autoSpeak = voiceSettings?.auto_speak ?? false

  // When STT produces a transcript, fill the input and auto-send
  useEffect(() => {
    if (!stt.transcript) return
    setInput(stt.transcript)
    stt.reset()
  }, [stt.transcript, stt])

  // Load conversation messages
  const { data: conversation } = useQuery({
    queryKey: ['conversation', activeConversationId],
    queryFn: () =>
      activeConversationId ? conversationsApi.get(activeConversationId) : null,
    enabled: activeConversationId != null,
  })

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [conversation?.messages, streamingContent])

  const handleSend = async () => {
    const message = input.trim()
    if (!message || isStreaming) return

    setInput('')
    startStreaming()

    abortRef.current = new AbortController()

    try {
      let finalConversationId = activeConversationId

      for await (const event of chatApi.stream(
        { message, conversation_id: activeConversationId ?? undefined },
        abortRef.current.signal,
      )) {
        handleSSEEvent(event, (id) => { finalConversationId = id })
      }

      if (finalConversationId != null) {
        finishStreaming(finalConversationId)
        // Invalidate queries to reload conversation
        await queryClient.invalidateQueries({ queryKey: ['conversation', finalConversationId] })
        await queryClient.invalidateQueries({ queryKey: ['conversations'] })
      }
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') {
        setJarvisState('IDLE')
      } else {
        setError(err instanceof Error ? err.message : 'Unknown error')
      }
    }
  }

  const handleSSEEvent = (
    event: SSEEvent,
    onComplete: (conversationId: number) => void,
  ) => {
    switch (event.type) {
      case 'THINKING':
        setJarvisState('THINKING')
        break
      case 'RESPONSE_STREAMING': {
        const p = event.payload as { chunk?: string }
        if (p.chunk) appendStreamChunk(p.chunk)
        break
      }
      case 'RESPONSE_COMPLETE': {
        const p = event.payload as ResponseCompletePayload
        onComplete(p.conversation_id)
        if (autoSpeak && tts.supported) {
          tts.speak(p.content)
        }
        break
      }
      case 'ERROR': {
        const p = event.payload as { message?: string }
        setError(p.message ?? 'Unknown error')
        break
      }
    }
  }

  const handleCancel = () => {
    abortRef.current?.abort()
    tts.cancel()
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void handleSend()
    }
  }

  const messages = conversation?.messages ?? []

  return (
    <div className={styles.page}>
      {/* Conversation history */}
      <div className={styles.messages} role="log" aria-live="polite" aria-label="Conversation">
        {messages.length === 0 && !isStreaming && (
          <div className={styles.empty}>
            <div className={styles.emptyTitle}>JARVIS</div>
            <div className={styles.emptySubtitle}>How can I assist you?</div>
          </div>
        )}

        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}

        {isStreaming && <StreamingBubble content={streamingContent} />}

        {lastError && (
          <div className={styles.error} role="alert">
            <span>⚠ {lastError}</span>
            <button onClick={clearError} aria-label="Dismiss error">✕</button>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div className={styles.inputArea}>
        <div className={styles.inputRow}>
          {voiceEnabled && stt.supported && (
            <button
              className={`${styles.micBtn} ${stt.listening ? styles.micActive : ''}`}
              onClick={stt.listening ? stt.stop : stt.start}
              disabled={isStreaming}
              aria-label={stt.listening ? 'Stop recording' : 'Start voice input'}
              title={stt.listening ? 'Stop recording' : 'Push to talk'}
            >
              {stt.listening ? '⏹' : '🎤'}
            </button>
          )}
          <textarea
            ref={textareaRef}
            className={styles.textarea}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Message JARVIS… (Enter to send, Shift+Enter for newline)"
            disabled={isStreaming}
            rows={1}
            aria-label="Message input"
            aria-disabled={isStreaming}
          />
          {isStreaming ? (
            <button
              className={`${styles.sendBtn} ${styles.cancelBtn}`}
              onClick={handleCancel}
              aria-label="Cancel generation"
            >
              ■ Stop
            </button>
          ) : (
            <button
              className={styles.sendBtn}
              onClick={() => void handleSend()}
              disabled={!input.trim()}
              aria-label="Send message"
            >
              Send ▶
            </button>
          )}
        </div>
        <div className={styles.statusBar}>
          <span className={styles.stateLabel} aria-live="polite">
            {jarvisState !== 'IDLE' && jarvisState}
          </span>
          {activeConversationId && (
            <span className={styles.convId}>
              conv #{activeConversationId}
            </span>
          )}
        </div>
      </div>
    </div>
  )
}
