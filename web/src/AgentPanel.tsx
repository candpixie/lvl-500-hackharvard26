import { useRef, useState } from 'react'
import { askGrok, imagineGrok, listenGrok, speakGrok, type FocusOrbit } from './events.ts'

const PROMPTS = [
  { label: '1,000 sats', question: 'Where should I put 1,000 four-meter satellites?' },
  { label: '1M at 900 km', question: 'What happens if SpaceX puts a million satellites at 900 km?' },
  { label: 'Why 800 km', question: 'Why is 800 km so bad?' },
  { label: 'Near miss', question: "What's the closest near miss this week?" },
]

interface AgentPanelProps {
  onFocus: (focus: FocusOrbit) => void
}

export default function AgentPanel({ onFocus }: AgentPanelProps) {
  const [question, setQuestion] = useState(PROMPTS[0].question)
  const [answer, setAnswer] = useState('')
  const [sources, setSources] = useState<string[]>([])
  const [reasoner, setReasoner] = useState<string>('')
  const [busy, setBusy] = useState(false)
  const [listening, setListening] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [hasAudio, setHasAudio] = useState(false)
  const [image, setImage] = useState<{ src: string; label: string } | null>(null)
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
    setImage(null)
    if (objectUrl.current) {
      URL.revokeObjectURL(objectUrl.current)
      objectUrl.current = null
    }
    setHasAudio(false)
    try {
      const result = await askGrok(q)
      setAnswer(result.answer)
      setSources(result.tool_calls.map((call) => call.name))
      setReasoner(result.reasoner ?? '')
      if (result.focus) onFocus(result.focus)
      void imagineGrok(
        result.focus
          ? `Low Earth orbit shell at ${Math.round(result.focus.altitude_km)} km, inclination ${Math.round(result.focus.inclination_deg)} degrees`
          : "Low Earth orbit with satellites and amber debris around Earth",
      )
        .then((art) => {
          const src = art.url ?? (art.b64_json ? `data:image/png;base64,${art.b64_json}` : '')
          if (src) setImage({ src, label: art.label })
        })
        .catch(() => {})
      if (speak && result.answer) {
        const blob = await speakGrok(result.answer)
        const url = URL.createObjectURL(blob)
        objectUrl.current = url
        const player = playerRef.current
        if (player) {
          player.src = url
          setHasAudio(true)
          void player.play()
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

  const sourceLine = reasoner === 'chalk'
    ? `Chalk · ${sources.filter((name) => name !== 'ask_chalk').join(', ') || 'ask_chalk'}`
    : reasoner === 'local_fallback'
      ? `Local fallback · ${sources.join(', ')}`
      : sources.join(', ')

  return (
    <aside className="hud hud-agent">
      <p className="kicker">Grok</p>
      <h1>Where should it go?</h1>
      <p className="dek">Speak or type. Chalk reasons on our catalog. The globe flies to that shell.</p>
      <div className="chips">
        {PROMPTS.map((item) => (
          <button key={item.label} type="button" className="chip" disabled={busy} onClick={() => setQuestion(item.question)}>
            {item.label}
          </button>
        ))}
      </div>
      <textarea
        className="ask-box"
        value={question}
        disabled={busy}
        onChange={(event) => setQuestion(event.target.value)}
        rows={3}
      />
      <div className="ask-row">
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
      {answer && <p className="answer">{answer}</p>}
      {sources.length > 0 && (
        <p className="source" title="Tracked objects only, lower bound. CelesTrak SATCAT, GP, SOCRATES.">
          Sources: {sourceLine} · tracked objects only, lower bound
        </p>
      )}
      {image && (
        <figure className="imagine">
          <img src={image.src} alt={image.label} />
          <figcaption>{image.label}</figcaption>
        </figure>
      )}
      <audio ref={playerRef} className={hasAudio ? 'ask-audio' : 'ask-audio is-idle'} controls />
    </aside>
  )
}
