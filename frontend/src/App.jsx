import { useState, useRef, useEffect } from 'react'

const SUGGESTIONS = [
  "What is Combo Breaker?",
  "Who are the legendary players here?",
  "Tell me about some hype matches or comebacks",
  "Are there any amazing underdog runs?",
  "Which game is the most popular?",
]

function formatTime(date) {
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function getComicWord(index) {
  const words = ['BAM!', 'BOOM!', 'HYPE!', 'K.O.!', 'CRUSH!', 'COMBO!', 'FIST!']
  return words[index % words.length]
}

export default function App() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [crackles, setCrackles] = useState([])
  const [showMobileWelcome, setShowMobileWelcome] = useState(false)
  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)

  const [commentaryEnabled, setCommentaryEnabled] = useState(() => {
    const saved = localStorage.getItem('fist_commentary_enabled')
    if (saved === null) {
      localStorage.setItem('fist_commentary_enabled', 'true')
      return true
    }
    return saved !== 'false'
  })
  const [playingMessageId, setPlayingMessageId] = useState(null)
  const [loadingSpeechMessageId, setLoadingSpeechMessageId] = useState(null)
  const currentAudioRef = useRef(null)
  const commentaryEnabledRef = useRef(commentaryEnabled)

  useEffect(() => {
    commentaryEnabledRef.current = commentaryEnabled
  }, [commentaryEnabled])

  useEffect(() => {
    return () => {
      if (currentAudioRef.current) {
        currentAudioRef.current.pause()
      }
    }
  }, [])

  // Detect mobile view and check if welcome popup should be shown
  useEffect(() => {
    const checkMobile = () => {
      const mobile = window.innerWidth < 768
      if (mobile && !sessionStorage.getItem('fist_mobile_welcome_dismissed')) {
        setShowMobileWelcome(true)
      }
    }
    checkMobile()
    window.addEventListener('resize', checkMobile)
    return () => window.removeEventListener('resize', checkMobile)
  }, [])

  // Generate background Kirby Crackle dots on mount
  useEffect(() => {
    const dots = []
    const numDots = 30
    for (let i = 0; i < numDots; i++) {
      const size = Math.random() * 12 + 4
      dots.push({
        id: i,
        size,
        left: `${Math.random() * 100}%`,
        top: `${Math.random() * 100}%`,
        opacity: Math.random() * 0.5 + 0.1,
      })
    }
    setCrackles(dots)
  }, [])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  function cleanTextForTTS(text) {
    if (!text) return ''
    return text
      .replace(/[#*`~_]/g, '')
      .replace(/[-+•]\s+/g, '')
      .replace(/\[Thinking Process\].*?\[Answer\]/gs, '')
      .replace(/\s+/g, ' ')
      .trim()
  }

  async function playSpeech(text, messageId) {
    if (currentAudioRef.current) {
      currentAudioRef.current.pause()
      currentAudioRef.current = null
    }
    setPlayingMessageId(null)
    setLoadingSpeechMessageId(messageId)

    try {
      const cleaned = cleanTextForTTS(text)
      if (!cleaned) {
        setLoadingSpeechMessageId(null)
        return
      }

      const res = await fetch('/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: cleaned })
      })

      if (!res.ok) {
        throw new Error(`TTS API error: ${res.status}`)
      }

      const blob = await res.blob()
      const audioUrl = URL.createObjectURL(blob)
      const audio = new Audio(audioUrl)

      currentAudioRef.current = audio
      setPlayingMessageId(messageId)
      setLoadingSpeechMessageId(null)

      audio.onended = () => {
        setPlayingMessageId(null)
        currentAudioRef.current = null
      }

      audio.onerror = (e) => {
        console.error("Audio playback error:", e)
        setPlayingMessageId(null)
        currentAudioRef.current = null
      }

      await audio.play()
    } catch (err) {
      console.error("Speech synthesis failed:", err)
      setLoadingSpeechMessageId(null)
      setPlayingMessageId(null)
    }
  }

  function togglePlaySpeech(msg) {
    if (playingMessageId === msg.id) {
      if (currentAudioRef.current) {
        currentAudioRef.current.pause()
        currentAudioRef.current = null
      }
      setPlayingMessageId(null)
    } else {
      playSpeech(msg.text, msg.id)
    }
  }

  function updateMessage(messageId, updater) {
    setMessages(prev => prev.map(msg => (msg.id === messageId ? updater(msg) : msg)))
  }

  function parseStreamLine(line, onEvent) {
    const trimmed = line.trim()
    if (!trimmed) return
    try {
      onEvent(JSON.parse(trimmed))
    } catch (err) {
      throw new Error(`Invalid stream chunk: ${trimmed.slice(0, 120)}`, { cause: err })
    }
  }

  async function sendMessage(text) {
    const question = (text || input).trim()
    if (!question || loading) return

    const userId = crypto.randomUUID()
    const assistantId = crypto.randomUUID()
    const startedAt = performance.now()
    const userMsg = { id: userId, role: 'user', text: question, time: new Date() }
    const assistantMsg = {
      id: assistantId,
      role: 'ai',
      text: 'Reading bracket data...',
      time: new Date(),
      streaming: true,
      pending: true,
      fullText: '',
      thinking: '',
      isThinking: false,
    }

    setMessages(prev => [...prev, userMsg, assistantMsg])
    setInput('')
    setLoading(true)

    try {
      let lastFullText = ''
      const res = await fetch('/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      })
      if (!res.ok) throw new Error(`Server error ${res.status}`)
      if (!res.body) throw new Error('Streaming is unavailable in this browser')

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { value, done } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        for (const line of lines) {
          parseStreamLine(line, (event) => {
            if (event.type === 'meta') {
              return
            }

            if (event.type === 'status') {
              updateMessage(assistantId, (msg) => ({
                ...msg,
                text: msg.pending ? event.text : msg.text,
              }))
              return
            }

            if (event.type === 'delta') {
              const token = event.text ?? ''
              lastFullText += token
              updateMessage(assistantId, (msg) => {
                const fullText = msg.pending ? token : `${msg.fullText ?? ''}${token}`
                const { thinking, answer } = parseThinkingAndAnswer(fullText)
                return {
                  ...msg,
                  fullText,
                  thinking,
                  text: answer,
                  isThinking: fullText.startsWith('[Thinking Process]\n') && !fullText.includes('\n\n[Answer]\n'),
                  pending: false,
                }
              })
              return
            }

            if (event.type === 'done') {
              const latency = ((performance.now() - startedAt) / 1000).toFixed(2)
              updateMessage(assistantId, (msg) => {
                const finalRaw = msg.pending ? 'No answer came back. Try again in a moment.' : (msg.fullText ?? msg.text)
                const { thinking, answer } = parseThinkingAndAnswer(finalRaw)
                return {
                  ...msg,
                  streaming: false,
                  fullText: finalRaw,
                  thinking,
                  text: answer,
                  isThinking: false,
                  pending: false,
                  latency,
                }
              })
              return
            }

            if (event.type === 'error') {
              throw new Error(event.message || 'Stream error')
            }
          })
        }
      }

      if (buffer.trim()) {
        parseStreamLine(buffer, (event) => {
          if (event.type === 'delta') {
            const token = event.text ?? ''
            lastFullText += token
            updateMessage(assistantId, (msg) => {
              const fullText = msg.pending ? token : `${msg.fullText ?? ''}${token}`
              const { thinking, answer } = parseThinkingAndAnswer(fullText)
              return {
                ...msg,
                fullText,
                thinking,
                text: answer,
                isThinking: fullText.startsWith('[Thinking Process]\n') && !fullText.includes('\n\n[Answer]\n'),
                pending: false,
              }
            })
          }
        })
      }

      const { thinking, answer } = parseThinkingAndAnswer(lastFullText)
      const finalAnswerText = answer || 'No answer came back. Try again in a moment.'
      const elapsedLatency = ((performance.now() - startedAt) / 1000).toFixed(2)

      updateMessage(assistantId, (msg) => {
        return {
          ...msg,
          streaming: false,
          fullText: lastFullText,
          thinking,
          text: finalAnswerText,
          isThinking: false,
          pending: false,
          latency: msg.latency ?? elapsedLatency,
        }
      })

      if (commentaryEnabledRef.current && finalAnswerText && finalAnswerText !== 'Reading bracket data...' && finalAnswerText !== 'No answer came back. Try again in a moment.' && !finalAnswerText.startsWith('Error:')) {
        playSpeech(finalAnswerText, assistantId)
      }
    } catch (err) {
      const elapsed = ((performance.now() - startedAt) / 1000).toFixed(2)
      updateMessage(assistantId, (msg) => ({
        ...msg,
        text: `Error: ${err.message}`,
        streaming: false,
        pending: false,
        error: true,
        latency: elapsed,
      }))
    } finally {
      setLoading(false)
      inputRef.current?.focus()
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  const hasMessages = messages.length > 0

  return (
    <div className="flex-1 flex flex-col h-dvh overflow-hidden relative font-body-md">
      {/* Ambient Effects */}
      <div className="fixed inset-0 pointer-events-none opacity-20 bg-speedlines z-0" />
      <div className="fixed inset-0 pointer-events-none z-0 overflow-hidden" id="crackle-container">
        {crackles.map((dot) => (
          <div
            key={dot.id}
            className="kirby-crackle"
            style={{
              width: `${dot.size}px`,
              height: `${dot.size}px`,
              left: dot.left,
              top: dot.top,
              opacity: dot.opacity,
            }}
          />
        ))}
      </div>

      {/* Mobile Navigation Container (Mobile Only) */}
      <header className="flex md:hidden justify-between items-center w-full px-4 py-3 z-50 overflow-hidden border-b-2 border-primary-container bg-background">
        <h1 className="font-display-lg text-xl text-primary-container italic skew-x-[-12deg] tracking-wider uppercase font-bold">
          PATH OF THE FIST
        </h1>
        <button
          onClick={() => setShowMobileWelcome(true)}
          className="p-1.5 hover:bg-primary-container hover:text-on-primary-container transition-colors skew-x-[-12deg] border border-primary-container flex items-center justify-center"
        >
          <span className="material-symbols-outlined text-primary-container hover:text-on-primary-container text-lg font-bold">
            help
          </span>
        </button>
      </header>

      {/* Top Navigation Container (Desktop) / Header */}
      <header className="hidden md:flex justify-between items-center w-full px-margin-desktop py-4 z-50 overflow-hidden border-b-4 border-primary-container bg-background">
        <div className="flex items-center gap-8">
          <h1 className="font-display-lg text-display-lg text-primary-container italic skew-x-[-12deg] tracking-tighter">
            PATH OF THE FIST
          </h1>
          <nav className="flex gap-6 mt-2">
            <span className="text-on-surface-variant font-label-caps text-label-caps px-2 py-1 select-none">
              YOUR COMBO BREAKER ANALYTICS ASSISTANT
            </span>
          </nav>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex gap-2">
            <button className="p-2 hover:bg-primary-container hover:text-on-primary-container transition-colors skew-x-[-12deg]">
              <span className="material-symbols-outlined text-primary-container hover:text-on-primary-container">
                notifications
              </span>
            </button>
            <button className="p-2 hover:bg-primary-container hover:text-on-primary-container transition-colors skew-x-[-12deg]">
              <span className="material-symbols-outlined text-primary-container hover:text-on-primary-container">
                person
              </span>
            </button>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 min-h-0 flex flex-col overflow-hidden relative z-10">

        {/* Center: Hype Chat Panel */}
        <section className="min-h-0 flex flex-col p-3 sm:p-4 md:p-8 h-full overflow-hidden w-full max-w-3xl mx-auto">


          {/* Chat Messages Area */}
          <div className="flex-1 min-h-0 overflow-y-auto pr-1 sm:pr-2 flex flex-col gap-4 md:gap-6 custom-scrollbar pb-4 md:pb-6">
            {/* Empty State / Welcome */}
            {!hasMessages && (
              <div className="flex-1 flex flex-col items-center justify-center text-center p-4 sm:p-6 bg-surface-container-high border-2 border-dashed border-outline-variant max-w-2xl mx-auto my-auto sm:skew-x-[-6deg] flex-shrink-0">
                <div className="sm:skew-x-[6deg] flex flex-col items-center gap-4">
                  <span className="material-symbols-outlined text-primary-container text-5xl animate-bounce">
                    sports_kabaddi
                  </span>
                  <h3 className="font-headline-lg text-headline-lg text-primary-fixed uppercase tracking-wide">
                    ENTER THE ARENA
                  </h3>
                  <p className="text-on-surface-variant font-body-md text-sm max-w-md">
                    Ask me anything about Combo Breaker from 2022 through 2026, including brackets, matchups, player runs, and standout performances.
                  </p>
                  <div className="flex flex-wrap gap-3 justify-center mt-4">
                    {SUGGESTIONS.map((s) => (
                      <button
                        key={s}
                        className="bg-surface text-on-surface font-label-caps text-label-caps px-4 py-2 border-2 border-primary-container hover:bg-primary-container hover:text-on-primary-container transition-all hover:scale-95 duration-100 skew-x-[-12deg]"
                        onClick={() => sendMessage(s)}
                      >
                        <span className="inline-block skew-x-[12deg]">{s}</span>
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* Messages list */}
            {messages.map((msg, i) => (
              <div
                key={msg.id || i}
                className={`flex flex-col gap-1 max-w-[94%] sm:max-w-[85%] relative ${
                  msg.role === 'user' ? 'items-end self-end' : 'items-start self-start mt-4'
                }`}
              >
                {/* Meta details header */}
                <div className="flex items-center gap-2 mb-1">
                  {msg.role === 'user' ? (
                    <>
                      <span className="font-label-caps text-label-caps text-primary-fixed">
                        YOU
                      </span>
                      <div className="w-6 h-6 rounded-sm bg-surface-variant overflow-hidden border border-outline flex items-center justify-center">
                        <span className="material-symbols-outlined text-sm text-outline-variant">
                          person
                        </span>
                      </div>
                    </>
                  ) : (
                    <>
                      <div className="w-8 h-8 bg-tertiary-container border-2 border-on-tertiary-container flex items-center justify-center -skew-x-12">
                        <span
                          className="material-symbols-outlined text-on-tertiary-container font-bold skew-x-12"
                          style={{ fontVariationSettings: "'FILL' 1" }}
                        >
                          smart_toy
                        </span>
                      </div>
                      <span className="font-label-caps text-label-caps text-tertiary-container bg-on-tertiary-container px-2 py-0.5">
                        FIST BOT
                      </span>
                      {msg.latency && (
                        <span className="font-label-caps text-[10px] text-outline-variant bg-surface-container-low px-2 py-0.5 flex items-center gap-1 border border-outline-variant">
                          <span className="material-symbols-outlined text-[12px]">timer</span>{' '}
                          {msg.latency}s
                        </span>
                      )}
                    </>
                  )}
                </div>

                {/* Message Bubble Body */}
                <div
                  className={`relative font-chat-msg text-chat-msg ${
                    msg.role === 'user'
                      ? 'p-4 bg-surface-bright text-on-surface border-2 border-primary-fixed user-bubble'
                      : `p-4 md:p-5 pr-10 sm:pr-16 md:pr-24 bg-tertiary-container text-on-tertiary-container border-4 border-on-tertiary-container bot-bubble font-bold shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] md:shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] ${
                          msg.pending ? 'animate-pulse' : ''
                        } ${msg.error ? 'border-error text-on-error bg-error-container' : ''}`
                  }`}
                >
                  {/* Comic Action Graphic */}
                  {msg.role !== 'user' && !msg.pending && !msg.error && (
                    <div
                      className="hidden sm:block absolute -top-6 -right-6 font-display-lg text-display-lg text-secondary-container stroke-black drop-shadow-[2px_2px_0_rgba(0,0,0,1)] rotate-12 z-20 pointer-events-none select-none"
                      style={{ WebkitTextStroke: '2px black' }}
                    >
                      {getComicWord(i)}
                    </div>
                  )}

                  {msg.role !== 'user' && (
                    <ThinkingAccordion
                      thinking={msg.thinking}
                      isThinking={msg.isThinking}
                    />
                  )}

                  {msg.role !== 'user' && !msg.pending && !msg.error && (
                    <button
                      onClick={() => togglePlaySpeech(msg)}
                      className={`absolute bottom-4 right-4 p-1.5 border-2 border-on-tertiary-container hover:scale-105 active:scale-95 transition-all flex items-center justify-center -skew-x-12 ${
                        playingMessageId === msg.id
                          ? 'bg-primary-container text-on-primary-container animate-pulse'
                          : 'bg-background text-primary-container hover:bg-primary-container hover:text-on-primary-container'
                      }`}
                      title={playingMessageId === msg.id ? "Stop Commentary" : "Play Commentary"}
                    >
                      {loadingSpeechMessageId === msg.id ? (
                        <span className="animate-spin h-4 w-4 border-2 border-current border-t-transparent rounded-full skew-x-12 animate-pulse" />
                      ) : playingMessageId === msg.id ? (
                        <div className="flex items-end gap-0.5 px-0.5 skew-x-12 h-4">
                          <span className="sound-bar bg-current w-0.5 animate-soundbar1" />
                          <span className="sound-bar bg-current w-0.5 animate-soundbar2" />
                          <span className="sound-bar bg-current w-0.5 animate-soundbar3" />
                        </div>
                      ) : (
                        <span className="material-symbols-outlined text-base font-bold skew-x-12">
                          volume_up
                        </span>
                      )}
                    </button>
                  )}

                  <p className="whitespace-pre-wrap leading-relaxed">{msg.text}</p>

                  {msg.time && (
                    <div
                      className={`text-[10px] mt-2 font-label-caps ${
                        msg.role === 'user'
                          ? 'text-outline-variant text-right'
                          : 'text-on-tertiary-container/60'
                      }`}
                    >
                      {formatTime(msg.time)}
                    </div>
                  )}
                </div>
              </div>
            ))}

            <div ref={messagesEndRef} />
          </div>

          {/* Chat Input */}
          <div className="mt-auto pt-3 md:pt-4 bg-background z-20 flex-shrink-0">
            <div className="flex border-2 border-primary-container bg-surface focus-within:border-tertiary-container transition-colors p-1 skew-x-[-6deg]">
              <input
                ref={inputRef}
                className="min-w-0 flex-1 bg-transparent border-none text-on-surface focus:ring-0 font-label-caps text-label-caps placeholder-on-surface-variant px-3 sm:px-4 skew-x-[6deg] focus:outline-none"
                placeholder={loading ? 'COMMENTATING...' : 'ENTER THE ARENA...'}
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={loading}
                autoFocus
              />
              <button
                type="button"
                className={`px-3 py-2 flex items-center justify-center skew-x-[6deg] border-l-2 border-background transition-colors ${
                  commentaryEnabled
                    ? 'bg-tertiary-container text-on-tertiary-container hover:bg-tertiary-container/80'
                    : 'bg-surface-variant text-on-surface-variant hover:bg-surface-variant/80'
                }`}
                onClick={() => setCommentaryEnabled(prev => {
                  const newVal = !prev
                  localStorage.setItem('fist_commentary_enabled', String(newVal))
                  if (!newVal && currentAudioRef.current) {
                    currentAudioRef.current.pause()
                    setPlayingMessageId(null)
                  }
                  return newVal
                })}
                title={commentaryEnabled ? "Mute Commentary" : "Enable Commentary"}
              >
                <span className="material-symbols-outlined text-lg">
                  {commentaryEnabled ? 'volume_up' : 'volume_off'}
                </span>
              </button>
              <button
                className="bg-primary-container text-on-primary-container px-4 sm:px-6 py-2 font-headline-lg-mobile text-headline-lg-mobile uppercase hover:bg-tertiary-container hover:text-on-tertiary-container transition-colors flex items-center justify-center skew-x-[6deg] -ml-2 border-l-2 border-background disabled:opacity-40 disabled:cursor-not-allowed font-bold"
                onClick={() => sendMessage()}
                disabled={!input.trim() || loading}
              >
                SEND
              </button>
            </div>
            <p className="text-center font-label-caps text-[10px] text-outline-variant mt-2">
              Powered by DeepSeek via GraphRAG · Answers stream live with full tournament context
            </p>
          </div>
        </section>

      </main>

      {/* Mobile Welcome Popup (Overlay) */}
      {showMobileWelcome && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/95 p-4 sm:p-6 overflow-y-auto">
          {/* Halftone / speedline effects inside popup */}
          <div className="absolute inset-0 pointer-events-none opacity-20 bg-speedlines" />
          <div className="absolute inset-0 pointer-events-none halftone-bg" />
          
          <div className="relative w-full max-w-md bg-surface-container-high border-4 border-primary-container p-6 skew-x-[-3deg] shadow-[8px_8px_0px_0px_rgba(0,0,0,1)] flex flex-col gap-5 z-10 my-auto">
            {/* Unskew inner content so text is readable */}
            <div className="skew-x-[3deg] flex flex-col gap-4">
              
              {/* Header Badge */}
              <div className="flex justify-between items-center border-b-2 border-outline-variant pb-3">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 bg-primary-container border-2 border-on-primary-container flex items-center justify-center -skew-x-12">
                    <span className="material-symbols-outlined text-on-primary-container font-bold skew-x-12 text-lg">
                      sports_kabaddi
                    </span>
                  </div>
                  <div className="flex flex-col">
                    <span className="font-display-lg text-lg text-primary-fixed tracking-wide uppercase italic">
                      MOBILE PORTAL
                    </span>
                    <span className="font-label-caps text-[9px] text-outline-variant uppercase">
                      Path of the Fist v1.0
                    </span>
                  </div>
                </div>
                
                {/* Compact Close X Button */}
                <button 
                  onClick={() => {
                    setShowMobileWelcome(false);
                    sessionStorage.setItem('fist_mobile_welcome_dismissed', 'true');
                  }}
                  className="w-8 h-8 flex items-center justify-center border border-error-container text-error hover:bg-error hover:text-on-error transition-colors"
                >
                  <span className="material-symbols-outlined text-sm font-bold">close</span>
                </button>
              </div>

              {/* Title & Description */}
              <div className="flex flex-col gap-1">
                <h2 className="font-display-lg text-2xl text-primary-container uppercase tracking-tight italic">
                  WELCOME TO THE ARENA
                </h2>
                <p className="text-on-surface-variant font-body-md text-xs leading-relaxed">
                  Your mobile terminal to Combo Breaker tournament data (2022 - 2026). Ask about match brackets, results, upsets, or player stats.
                </p>
              </div>

              {/* Quick-Start Cards */}
              <div className="flex flex-col gap-3 mt-1">
                <span className="font-label-caps text-[10px] text-tertiary-container uppercase tracking-wider">
                  Select a prompt to begin:
                </span>
                <div className="grid grid-cols-1 gap-2.5">
                  <button
                    onClick={() => {
                      sendMessage("What is Combo Breaker?");
                      setShowMobileWelcome(false);
                      sessionStorage.setItem('fist_mobile_welcome_dismissed', 'true');
                    }}
                    className="flex items-center justify-between p-3 bg-surface border-2 border-primary-container hover:bg-primary-container/20 text-left transition-all hover:translate-x-1"
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-lg">🎮</span>
                      <span className="font-label-caps text-xs text-on-surface">What is Combo Breaker?</span>
                    </div>
                    <span className="material-symbols-outlined text-primary-container text-sm">arrow_forward</span>
                  </button>

                  <button
                    onClick={() => {
                      sendMessage("Who are the legendary players here?");
                      setShowMobileWelcome(false);
                      sessionStorage.setItem('fist_mobile_welcome_dismissed', 'true');
                    }}
                    className="flex items-center justify-between p-3 bg-surface border-2 border-secondary-container hover:bg-secondary-container/20 text-left transition-all hover:translate-x-1"
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-lg">👑</span>
                      <span className="font-label-caps text-xs text-on-surface">Legendary Players</span>
                    </div>
                    <span className="material-symbols-outlined text-secondary-container text-sm">arrow_forward</span>
                  </button>

                  <button
                    onClick={() => {
                      sendMessage("Tell me about some hype matches or comebacks");
                      setShowMobileWelcome(false);
                      sessionStorage.setItem('fist_mobile_welcome_dismissed', 'true');
                    }}
                    className="flex items-center justify-between p-3 bg-surface border-2 border-tertiary-container hover:bg-tertiary-container/20 text-left transition-all hover:translate-x-1"
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-lg">🔥</span>
                      <span className="font-label-caps text-xs text-on-surface">Hype Matches & Comebacks</span>
                    </div>
                    <span className="material-symbols-outlined text-tertiary-container text-sm">arrow_forward</span>
                  </button>
                </div>
              </div>

              {/* Specs & Tech badges */}
              <div className="flex flex-wrap gap-1.5 mt-2 justify-center">
                <span className="bg-surface-container-low text-[9px] font-label-caps text-outline-variant px-2 py-0.5 border border-outline-variant">
                  Neo4j GraphRAG
                </span>
                <span className="bg-surface-container-low text-[9px] font-label-caps text-outline-variant px-2 py-0.5 border border-outline-variant">
                  FastAPI Streams
                </span>
                <span className="bg-surface-container-low text-[9px] font-label-caps text-outline-variant px-2 py-0.5 border border-outline-variant">
                  Touch Combat UI
                </span>
              </div>

              {/* Action / Enter Button */}
              <button
                onClick={() => {
                  setShowMobileWelcome(false);
                  sessionStorage.setItem('fist_mobile_welcome_dismissed', 'true');
                }}
                className="w-full mt-2 py-3 bg-primary-container text-on-primary-container font-headline-lg-mobile text-base uppercase font-bold hover:bg-tertiary-container hover:text-on-tertiary-container transition-colors shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] border-2 border-black flex items-center justify-center gap-2 active:scale-95"
              >
                ENTER ARENA
                <span className="material-symbols-outlined font-bold text-sm">sports_kabaddi</span>
              </button>

            </div>
          </div>
        </div>
      )}
    </div>
  )
}



function parseThinkingAndAnswer(fullText) {
  let thinking = '';
  let answer = fullText;

  const thinkingStart = '[Thinking Process]\n';
  const answerStart = '\n\n[Answer]\n';

  if (fullText.startsWith(thinkingStart)) {
    const parts = fullText.slice(thinkingStart.length).split(answerStart);
    if (parts.length > 1) {
      thinking = parts[0];
      answer = parts.slice(1).join(answerStart);
    } else {
      thinking = parts[0];
      answer = '';
    }
  }

  return { thinking, answer };
}

function ThinkingAccordion({ thinking, isThinking }) {
  const [userToggled, setUserToggled] = useState(false)
  const [isOpen, setIsOpen] = useState(true)

  if (!thinking) return null

  const handleToggle = () => {
    setUserToggled(true)
    setIsOpen(!isOpen)
  }

  // If the user hasn't interacted, follow the automatic state
  const displayedOpen = userToggled ? isOpen : isThinking

  return (
    <div className="mb-4 border-2 border-outline-variant bg-surface-container-low skew-x-[-6deg] overflow-hidden text-xs max-w-xl">
      <div className="skew-x-[6deg]">
        <button
          className="w-full flex justify-between items-center px-4 py-2 font-label-caps text-label-caps text-on-surface-variant bg-surface-container-high hover:bg-primary-container hover:text-on-primary-container transition-colors"
          onClick={handleToggle}
        >
          <span className="flex items-center gap-2">
            {isThinking ? (
              <span className="animate-spin h-3 w-3 border-2 border-primary-fixed border-t-transparent rounded-full" />
            ) : (
              <span className="material-symbols-outlined text-sm text-primary-fixed font-bold">check_circle</span>
            )}
            {isThinking ? 'THINKING PROCESS...' : 'THOUGHT PROCESS'}
          </span>
          <span className="material-symbols-outlined text-sm">
            {displayedOpen ? 'keyboard_arrow_up' : 'keyboard_arrow_down'}
          </span>
        </button>

        {displayedOpen && (
          <div className="p-4 font-mono text-[11px] text-outline-variant bg-surface-container-lowest max-h-[180px] overflow-y-auto custom-scrollbar whitespace-pre-wrap leading-relaxed select-all text-left">
            {thinking}
          </div>
        )}
      </div>
    </div>
  )
}
