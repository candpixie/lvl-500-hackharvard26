import { useRef, useState } from 'react'
import {
  askGrok,
  eventsFromAsk,
  focusWithMission,
  listenGrok,
  speakGrok,
  type AskContext,
  type FocusOrbit,
  type UiEvent,
} from './events.ts'

const PROMPTS = [
  { label: '1,000 sats', question: 'Where should I put 1,000 four-meter satellites?' },
  { label: '1M at 900 km', question: 'What happens if SpaceX puts a million satellites at 900 km?' },
  { label: 'Why 800 km', question: 'Why is 800 km so bad?' },
  { label: 'Near miss', question: "What's the closest near miss this week?" },
  { label: 'Over China', question: 'Where can I put a satellite over China?' },
  { label: 'Over Africa', question: 'Where can I put a satellite over Africa at 800 km?' },
]

interface AgentPanelProps {
  altitude: number
  count: number
  context: AskContext
  onFocus: (focus: FocusOrbit | null) => void
  onUiEvent: (event: UiEvent) => void
}

export default function AgentPanel({ altitude, count, context, onFocus, onUiEvent }: AgentPanelProps) {
  const [question, setQuestion] = useState(PROMPTS[0].question)
  const [answer, setAnswer] = useState('')
  const [sources, setSources] = useState<string[]>([])
  const [reasoner, setReasoner] = useState<string>('')
  const [busy, setBusy] = useState(false)
  const [listening, setListening] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [hasAudio, setHasAudio] = useState(false)
  const [focus, setFocus] = useState<FocusOrbit | null>(null)
  const playerRef = useRef<HTMLAudioElement>(null)
  const objectUrl = useRef<string | null>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)

  async function run(speak: boolean, text = question) {
    const q = text.trim()
    if (!q || busy) return
    setBusy(true)
    setError(null)
    setAnswer('Checking our catalog…')
    setSources([])
    setReasoner('')
    setFocus(null)
    onFocus(null)
    if (objectUrl.current) {
      URL.revokeObjectURL(objectUrl.current)
      objectUrl.current = null
    }
    setHasAudio(false)
    try {
      const result = await askGrok(q, context)
      setAnswer(result.answer)
      setSources(result.tool_calls.map((call) => call.name))
      setReasoner(result.reasoner ?? '')
      const nextFocus = focusWithMission(result)
      if (nextFocus) setFocus(nextFocus)
      for (const event of eventsFromAsk(result)) onUiEvent(event)

      if (speak && result.answer) {
        try {
          const blob = await speakGrok(result.answer)
          const url = URL.createObjectURL(blob)
          objectUrl.current = url
          const player = playerRef.current
          if (player) {
            player.src = url
            setHasAudio(true)
            void player.play()
          }
        } catch {
          // No XAI key / voice unavailable — answer and globe events still succeed.
        }
      }
    } catch (err) {
      setAnswer('')
      setError(err instanceof Error ? err.message : 'Ask failed')
    } finally {
      setBusy(false)
    }
  }

  async function toggleListen() {
    if (listening) {
      recorderRef.current?.stop()
      recorderRef.current = null
      setListening(false)
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const recorder = new MediaRecorder(stream)
      const chunks: BlobPart[] = []
      recorder.ondataavailable = (event) => {
        if (event.data.size) chunks.push(event.data)
      }
      recorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop())
        const blob = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' })
        setBusy(true)
        void listenGrok(blob)
          .then((text) => {
            setQuestion(text)
            return run(true, text)
          })
          .catch((err) => {
            setError(err instanceof Error ? err.message : 'STT failed')
            setBusy(false)
          })
      }
      recorderRef.current = recorder
      recorder.start()
      setListening(true)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Microphone blocked')
    }
  }

  const sourceLine =
    reasoner === 'chalk'
      ? `Chalk · ${sources.filter((name) => name !== 'ask_chalk').join(', ') || 'ask_chalk'}`
      : reasoner === 'local_fallback'
        ? `Local fallback · ${sources.join(', ')}`
        : reasoner === 'local'
          ? `Local · ${sources.join(', ')}`
          : sources.join(', ')

  return (
    <aside className="hud hud-agent">
      <div className="command-head">
        <p className="kicker">Grok</p>
        <div className="chips">
        {PROMPTS.map((item) => (
          <button
            key={item.label}
            type="button"
            className="chip"
            disabled={busy}
            onClick={() => setQuestion(item.question)}
          >
            {item.label}
          </button>
        ))}
        </div>
      </div>
      <div className="ask-row">
        <input
          className="ask-box"
          type="text"
          value={question}
          disabled={busy}
          placeholder="Ask Grok where to put it…"
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') void run(false)
          }}
        />
        <button type="button" className="ask-go" disabled={busy} onClick={() => void run(false)}>
          {busy ? 'Asking…' : 'Ask'}
        </button>
        <button type="button" className="ask-go ask-voice" disabled={busy} onClick={() => void run(true)}>
          Ask + speak
        </button>
        <button type="button" className="ask-go ask-voice" disabled={busy && !listening} onClick={() => void toggleListen()}>
          {listening ? 'Stop' : 'Talk'}
        </button>
      </div>
      {error && <p className="shell-note">{error}</p>}
      {focus &&
        Math.abs(focus.altitude_km - altitude) < 25 &&
        (focus.count == null || focus.count === count) && (
        <p className="place-here">
          <span aria-hidden="true">★</span>
          Put it here
          {focus.place ? ` · ${focus.place}` : ''} · {Math.round(focus.altitude_km)} km ·{' '}
          {Math.round(focus.inclination_deg)}°
          {focus.count != null
            ? ` · ${focus.count === 1 ? '1 sat' : `${focus.count.toLocaleString('en-US')} sats`}`
            : ''}
        </p>
      )}
      {answer && <p className="answer">{answer}</p>}
      {sources.length > 0 && (
        <p className="source" title="Tracked objects only, lower bound. CelesTrak SATCAT, GP, SOCRATES.">
          Sources: {sourceLine} · tracked objects only, lower bound
        </p>
      )}
      <audio ref={playerRef} className={hasAudio ? 'ask-audio' : 'ask-audio is-idle'} controls />
    </aside>
  )
}
