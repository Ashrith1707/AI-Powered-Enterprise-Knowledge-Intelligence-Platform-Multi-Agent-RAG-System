import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

export function Markdown({ children }) {
  return (
    <div className="md">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{children}</ReactMarkdown>
    </div>
  )
}

/**
 * Streaming-like reveal of an ALREADY-COMPLETE answer (the backend is a
 * single non-streaming POST — this is presentation only, never fake tokens).
 */
export function TypewriterMarkdown({ text, animate, onDone }) {
  const [visible, setVisible] = useState(animate ? 0 : text.length)

  useEffect(() => {
    if (!animate) { setVisible(text.length); return }
    setVisible(0)
    const step = Math.max(2, Math.round(text.length / 220)) // ~2s total
    const timer = setInterval(() => {
      setVisible((v) => {
        if (v >= text.length) { clearInterval(timer); onDone?.(); return v }
        return v + step
      })
    }, 12)
    return () => clearInterval(timer)
  }, [text, animate]) // eslint-disable-line react-hooks/exhaustive-deps

  return <Markdown>{text.slice(0, visible)}</Markdown>
}
