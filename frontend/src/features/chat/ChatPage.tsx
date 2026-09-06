import { useRef, useState, useEffect, useCallback } from 'react'
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query'
import ReactMarkdown from 'react-markdown'
import { JarvisCore } from '@/components/hud/JarvisCore'
import type { CoreState } from '@/components/hud/JarvisCore'
import { chatApi, conversationsApi, toolsApi, visionApi, voiceApi } from '@/services/api/client'
import { useChatStore } from '@/app/stores/chatStore'
import { useSpeechRecognition } from '@/hooks/useSpeechRecognition'
import { useSpeechSynthesis } from '@/hooks/useSpeechSynthesis'
import { useWakeWord } from '@/hooks/useWakeWord'
import type {
  CitationOut,
  ConfirmationOut,
  MessageOut,
  PlanStep,
  ResponseCompletePayload,
  SSEEvent,
} from '@/types/api'
import styles from './ChatPage.module.css'

// ── Risk colour map ───────────────────────────────────────────────────────────

const RISK_COLORS: Record<string, string> = {
  READ_ONLY: 'var(--hud-success)',
  LOW_RISK: 'var(--hud-info)',
  SENSITIVE: 'var(--hud-warning)',
  DANGEROUS: 'var(--hud-danger)',
}

// ── Tool approval panel ───────────────────────────────────────────────────────

function ToolApprovalPanel({
  confirmation,
  onApprove,
  onDeny,
}: {
  confirmation: ConfirmationOut
  onApprove: () => void
  onDeny: () => void
}) {
  const expiresAt = new Date(confirmation.expires_at)
  const riskColor = RISK_COLORS[confirmation.risk_level] ?? 'var(--hud-text-secondary)'

  return (
    <div className={styles.approvalPanel} role="dialog" aria-modal="true" aria-label="Tool approval required">
      <div className={styles.approvalHeader}>
        <span className={styles.approvalIcon} aria-hidden="true">⚠</span>
        <span className={styles.approvalTitle}>ACTION REQUIRES APPROVAL</span>
      </div>
      <dl className={styles.approvalDetails}>
        <dt>Tool</dt>
        <dd className={styles.mono}>{confirmation.tool_name}</dd>
        <dt>Risk</dt>
        <dd style={{ color: riskColor }}>{confirmation.risk_level}</dd>
        <dt>Policy rule</dt>
        <dd className={styles.mono}>{confirmation.policy_rule}</dd>
        <dt>Action digest</dt>
        <dd className={`${styles.mono} ${styles.digest}`}>{confirmation.action_digest.slice(0, 16)}…</dd>
        <dt>Expires</dt>
        <dd className={styles.mono}>{expiresAt.toLocaleTimeString()}</dd>
      </dl>
      <div className={styles.approvalActions}>
        <button className={styles.denyBtn} onClick={onDeny} aria-label="Deny this action">✕ Deny</button>
        <button className={styles.approveBtn} onClick={onApprove} aria-label="Approve this action">✓ Approve</button>
      </div>
    </div>
  )
}

// ── Plan steps bar ────────────────────────────────────────────────────────────

function PlanStepsBar({ steps, intent }: { steps: PlanStep[]; intent: string | null }) {
  if (steps.length === 0) return null
  return (
    <div className={styles.planSteps} aria-label="Tool activity">
      {intent && <span className={styles.intentBadge}>{intent}</span>}
      {steps.map((s, i) => (
        <span
          key={i}
          className={`${styles.planStep} ${s.success ? styles.planStepOk : styles.planStepFail}`}
          title={s.error ?? s.policy_decision}
        >
          {s.success ? '✓' : s.requires_confirmation ? '⏳' : '✗'} {s.tool_name}
        </span>
      ))}
    </div>
  )
}

// ── Citation cards ────────────────────────────────────────────────────────────

function CitationCards({ citations }: { citations: CitationOut[] }) {
  if (citations.length === 0) return null
  return (
    <div className={styles.citations} aria-label="Sources">
      <span className={styles.citationsLabel}>Sources</span>
      {citations.map((c, i) => (
        <span key={i} className={styles.citationCard} title={`Score: ${c.score}`}>
          <span className={styles.citationIndex}>[{i + 1}]</span>
          <span className={styles.citationFile}>{c.filename}</span>
          {c.page != null && <span className={styles.citationPage}>p.{c.page}</span>}
        </span>
      ))}
    </div>
  )
}

// ── Context usage bar ─────────────────────────────────────────────────────────

function ContextBar({
  contextTokens,
  maxTokens,
}: {
  contextTokens: number | null
  maxTokens: number
}) {
  if (contextTokens == null) return null
  const pct = Math.min(100, Math.round((contextTokens / maxTokens) * 100))
  const color =
    pct >= 90 ? 'var(--hud-danger)' :
    pct >= 70 ? 'var(--hud-warning)' :
    'var(--hud-accent-muted)'

  return (
    <div className={styles.contextBar} title={`${contextTokens.toLocaleString()} / ${maxTokens.toLocaleString()} tokens`}>
      <span className={styles.contextLabel}>ctx</span>
      <div className={styles.contextTrack} aria-label={`Context usage ${pct}%`}>
        <div className={styles.contextFill} style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className={styles.contextPct} style={{ color }}>{pct}%</span>
    </div>
  )
}

// ── Markdown message content ──────────────────────────────────────────────────

function MarkdownContent({ content }: { content: string }) {
  return (
    <div className={styles.markdownContent}>
      <ReactMarkdown
        components={{
          code({ className, children, ...props }) {
            const isBlock = className?.startsWith('language-')
            if (isBlock) {
              return (
                <pre className={styles.codeBlock}>
                  <code className={className} {...props}>{children}</code>
                </pre>
              )
            }
            return <code className={styles.inlineCode} {...props}>{children}</code>
          },
          pre({ children }) {
            // react-markdown wraps code in pre; we handle it in code component
            return <>{children}</>
          },
          a({ href, children }) {
            return <a href={href} target="_blank" rel="noopener noreferrer" className={styles.mdLink}>{children}</a>
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}

// ── Message bubble ────────────────────────────────────────────────────────────

function MessageBubble({
  message,
  onCopy,
}: {
  message: MessageOut
  onCopy: (text: string) => void
}) {
  const isUser = message.role === 'user'
  const [copied, setCopied] = useState(false)

  const handleCopy = () => {
    onCopy(message.content)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div className={`${styles.message} ${isUser ? styles.user : styles.assistant}`}>
      <div className={styles.messageHeader}>
        <span className={styles.messageRole} aria-label={`${message.role} message`}>
          {isUser ? 'YOU' : 'JARVIS'}
        </span>
        {!isUser && (
          <button
            className={styles.copyBtn}
            onClick={handleCopy}
            aria-label="Copy message"
            title="Copy"
          >
            {copied ? '✓' : '⎘'}
          </button>
        )}
      </div>
      <div className={styles.messageContent}>
        {isUser
          ? <div className={styles.userText}>{message.content}</div>
          : <MarkdownContent content={message.content} />
        }
      </div>
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
      <div className={styles.messageHeader}>
        <span className={styles.messageRole}>JARVIS</span>
      </div>
      <div className={styles.messageContent}>
        {content
          ? <MarkdownContent content={content} />
          : <span className={styles.thinkingDots} aria-label="Thinking">···</span>
        }
      </div>
    </div>
  )
}

// ── Conversation title / rename ───────────────────────────────────────────────

function ConvTitle({
  title,
  convId,
  onRename,
}: {
  title: string | null
  convId: number
  onRename: (newTitle: string) => void
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(title ?? '')
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (editing) inputRef.current?.select()
  }, [editing])

  const commit = () => {
    const trimmed = draft.trim()
    if (trimmed && trimmed !== title) onRename(trimmed)
    setEditing(false)
  }

  if (editing) {
    return (
      <input
        ref={inputRef}
        className={styles.titleInput}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === 'Enter') commit()
          if (e.key === 'Escape') setEditing(false)
        }}
        aria-label="Rename conversation"
      />
    )
  }

  return (
    <button
      className={styles.titleBtn}
      onClick={() => { setDraft(title ?? ''); setEditing(true) }}
      title="Click to rename"
      aria-label={`Conversation: ${title ?? `#${convId}`}. Click to rename.`}
    >
      {title ?? `conv #${convId}`}
      <span className={styles.editIcon} aria-hidden="true">✎</span>
    </button>
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
    pendingConfirmation,
    lastPlanSteps,
    lastIntent,
    lastCitations,
    lastTokenUsage,
    startStreaming,
    appendStreamChunk,
    finishStreaming,
    setError,
    clearError,
    setJarvisState,
    setPendingConfirmation,
    setLastPlanSteps,
    setLastCitations,
    setLastTokenUsage,
    wakeWordEnabled,
    toggleWakeWord,
  } = useChatStore()

  const [input, setInput] = useState('')
  const [summaryPanel, setSummaryPanel] = useState<string | null>(null)
  const [_visionResult, setVisionResult] = useState<string | null>(null)
  const [visionLoading, setVisionLoading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const stt = useSpeechRecognition()
  const tts = useSpeechSynthesis()

  const { data: voiceSettings } = useQuery({
    queryKey: ['voice-settings'],
    queryFn: () => voiceApi.settings(),
    staleTime: Infinity,
  })

  const voiceEnabled = voiceSettings?.enabled ?? false
  const voiceAutoSpeak = voiceSettings?.auto_speak ?? true

  // Stable ref so handleWake doesn't re-create on every stt object change (M5)
  const sttStartRef = useRef(stt.start)
  useEffect(() => { sttStartRef.current = stt.start }, [stt.start])

  const handleWake = useCallback(() => {
    if (isStreaming) return
    setJarvisState('LISTENING')
    sttStartRef.current()
  }, [isStreaming, setJarvisState])

  useWakeWord(handleWake, voiceEnabled && wakeWordEnabled, stt.listening)

  // Max context tokens from env or sensible default
  const maxContextTokens = parseInt(import.meta.env.VITE_MAX_CONTEXT_TOKENS ?? '8192', 10)

  // Auto-send after STT finishes (wake word flow) and resume wake listener
  useEffect(() => {
    if (!stt.transcript) return
    const text = stt.transcript
    stt.reset()
    setInput(text)
    if (wakeWordEnabled && voiceEnabled) {
      // Small delay so input state settles, then auto-send
      setTimeout(() => {
        setInput('')
        void (async () => {
          if (!text.trim() || isStreaming) return
          startStreaming()
          abortRef.current = new AbortController()
          try {
            let finalConversationId = activeConversationId
            for await (const event of chatApi.stream(
              { message: text, conversation_id: activeConversationId ?? undefined },
              abortRef.current.signal,
            )) {
              handleSSEEvent(event, (id) => { finalConversationId = id })
            }
            if (finalConversationId != null) {
              finishStreaming(finalConversationId)
              await queryClient.invalidateQueries({ queryKey: ['conversation', finalConversationId] })
              await queryClient.invalidateQueries({ queryKey: ['conversations'] })
            }
          } catch (err) {
            if (err instanceof Error && err.name !== 'AbortError')
              setError(err instanceof Error ? err.message : 'Unknown error')
            else setJarvisState('IDLE')
          }
        })()
      }, 100)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stt.transcript])

  const { data: conversation, refetch: refetchConversation } = useQuery({
    queryKey: ['conversation', activeConversationId],
    queryFn: () =>
      activeConversationId ? conversationsApi.get(activeConversationId) : null,
    enabled: activeConversationId != null,
  })

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [conversation?.messages, streamingContent, pendingConfirmation])

  const handleCopy = useCallback((text: string) => {
    void navigator.clipboard.writeText(text)
  }, [])

  const summarizeMutation = useMutation({
    mutationFn: () => conversationsApi.summarize(activeConversationId!),
    onSuccess: (data) => setSummaryPanel(data.summary),
  })

  const handleRename = async (newTitle: string) => {
    if (!activeConversationId) return
    try {
      await conversationsApi.rename(activeConversationId, newTitle)
      await queryClient.invalidateQueries({ queryKey: ['conversations'] })
      await refetchConversation()
    } catch {
      // non-critical — title stays as-is
    }
  }

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
        const p = event.payload as unknown as ResponseCompletePayload
        onComplete(p.conversation_id)
        if (p.citations?.length) setLastCitations(p.citations)
        setLastTokenUsage({
          input: p.input_tokens,
          output: p.output_tokens,
          context: p.context_tokens,
        })
        if (p.plan_steps?.length) {
          setLastPlanSteps(p.plan_steps, p.intent ?? 'GENERAL_CHAT')
          const pendingStep = p.plan_steps.find(
            (s) => s.requires_confirmation && s.confirmation_id
          )
          if (pendingStep?.confirmation_id) {
            toolsApi.getConfirmation(pendingStep.confirmation_id)
              .then((conf) => setPendingConfirmation(conf))
              .catch(() => { /* confirmation may have expired */ })
          }
        }
        if (voiceEnabled && voiceAutoSpeak && tts.supported) tts.speak(p.content)
        break
      }
      case 'ERROR': {
        const p = event.payload as { message?: string }
        setError(p.message ?? 'Unknown error')
        break
      }
    }
  }

  const handleApprove = async () => {
    if (!pendingConfirmation) return
    try {
      await toolsApi.confirm({
        confirmation_id: pendingConfirmation.confirmation_id,
        tool_name: pendingConfirmation.tool_name,
        parameters: {},
      })
      setPendingConfirmation(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Confirmation failed')
    }
  }

  const handleDeny = () => {
    setPendingConfirmation(null)
    setJarvisState('IDLE')
  }

  const handleCancel = () => {
    abortRef.current?.abort()
    tts.cancel()
  }

  const handleImageAttach = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setVisionLoading(true)
    setVisionResult(null)
    try {
      const res = await visionApi.analyse(file)
      if (res.success) {
        setVisionResult(res.description)
        setInput((prev) => prev + (prev ? '\n' : '') + `[Image: ${file.name}]\n${res.description}`)
      } else {
        setVisionResult(`Error: ${res.error ?? 'Unknown'}`)
      }
    } catch (err) {
      setVisionResult(err instanceof Error ? err.message : 'Vision failed')
    } finally {
      setVisionLoading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
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
      {/* Conversation header */}
      {activeConversationId && (
        <>
          <div className={styles.convHeader}>
            <ConvTitle
              title={conversation?.title ?? null}
              convId={activeConversationId}
              onRename={handleRename}
            />
            <div className={styles.convHeaderRight}>
              <button
                className={styles.summarizeBtn}
                onClick={() => summarizeMutation.mutate()}
                disabled={summarizeMutation.isPending || isStreaming}
                title="Summarize conversation"
                aria-label="Summarize conversation"
              >
                {summarizeMutation.isPending ? '⏳' : '∑'}
              </button>
              <ContextBar
                contextTokens={lastTokenUsage?.context ?? null}
                maxTokens={maxContextTokens}
              />
            </div>
          </div>
          {summaryPanel && (
            <div className={styles.summaryPanel} role="region" aria-label="Conversation summary">
              <span className={styles.summaryText}>{summaryPanel}</span>
              <button
                className={styles.summaryDismiss}
                onClick={() => setSummaryPanel(null)}
                aria-label="Dismiss summary"
              >✕</button>
            </div>
          )}
        </>
      )}

      {/* Messages */}
      <div className={styles.messages} role="log" aria-live="polite" aria-label="Conversation">
        {messages.length === 0 && !isStreaming && (
          <div className={styles.empty}>
            <JarvisCore state={({
              IDLE: 'IDLE', LISTENING: 'LISTENING', THINKING: 'THINKING',
              USING_TOOL: 'THINKING', WAITING_FOR_APPROVAL: 'THINKING',
              ERROR: 'ERROR', OFFLINE: 'OFFLINE',
            }[jarvisState] ?? 'IDLE') as CoreState} size={200} />
            <div className={styles.emptySubtitle}>How can I assist you?</div>
          </div>
        )}

        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} onCopy={handleCopy} />
        ))}

        {isStreaming && <StreamingBubble content={streamingContent} />}

        {/* Citation cards — shown after last assistant turn */}
        {!isStreaming && lastCitations.length > 0 && (
          <CitationCards citations={lastCitations} />
        )}

        {pendingConfirmation && (
          <ToolApprovalPanel
            confirmation={pendingConfirmation}
            onApprove={() => void handleApprove()}
            onDeny={handleDeny}
          />
        )}

        {lastError && (
          <div className={styles.error} role="alert">
            <span>⚠ {lastError}</span>
            <button onClick={clearError} aria-label="Dismiss error">✕</button>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Plan steps bar */}
      <PlanStepsBar steps={lastPlanSteps} intent={lastIntent} />

      {/* Input area */}
      <div className={styles.inputArea}>
        <div className={styles.inputRow}>
          {voiceEnabled && stt.supported && (
            <>
              <button
                className={`${styles.micBtn} ${stt.listening ? styles.micActive : ''}`}
                onClick={stt.listening ? stt.stop : stt.start}
                disabled={isStreaming}
                aria-label={stt.listening ? 'Stop recording' : 'Start voice input'}
                title={stt.listening ? 'Stop recording' : 'Push to talk'}
              >
                {stt.listening ? '⏹' : '🎤'}
              </button>
              <button
                className={`${styles.wakeBtn} ${wakeWordEnabled ? styles.wakeActive : ''}`}
                onClick={toggleWakeWord}
                title={wakeWordEnabled ? 'Wake word active — say "Hey JARVIS"' : 'Enable wake word'}
                aria-label={wakeWordEnabled ? 'Disable wake word' : 'Enable wake word'}
                aria-pressed={wakeWordEnabled}
              >
                {wakeWordEnabled ? '👂' : '🔇'}
              </button>
            </>
          )}
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            style={{ display: 'none' }}
            onChange={handleImageAttach}
            aria-label="Attach image"
          />
          <button
            className={styles.attachBtn}
            onClick={() => fileInputRef.current?.click()}
            disabled={isStreaming || visionLoading}
            title="Attach image for vision analysis"
            aria-label="Attach image"
          >
            {visionLoading ? '⏳' : '🖼️'}
          </button>
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
          {lastTokenUsage && (
            <span className={styles.tokenSummary}>
              {lastTokenUsage.input != null && `↑${lastTokenUsage.input}`}
              {lastTokenUsage.output != null && ` ↓${lastTokenUsage.output}`}
            </span>
          )}
        </div>
      </div>
    </div>
  )
}
