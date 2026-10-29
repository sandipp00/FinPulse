import { useEffect, useState } from 'react'
import { Send } from 'lucide-react'
import { askAssistant, getAssistantStatus } from '../api/finpulse'
import { safeHref } from '../lib/news'

const KIND_LABEL = { data: 'DATA', calculated: 'CALC', unavailable: 'N/A' }

function Kind({ kind }) {
  return <span className={`as-kind as-kind-${kind}`}>{KIND_LABEL[kind] ?? kind}</span>
}

function Sources({ sources }) {
  if (!sources.length) return null
  return (
    <section className="panel as-sources" aria-label="Sources">
      <h3>Sources</h3>
      <ol>
        {sources.map((s) => {
          const href = safeHref(s.url)
          return (
            <li key={s.id}>
              <b>[{s.id}]</b>{' '}
              {href ? <a href={href} target="_blank" rel="noopener noreferrer" className="link-inline">{s.name}</a> : s.name}
              <small>
                {[s.provider, s.as_of && `as of ${String(s.as_of).slice(0, 16).replace('T', ' ')}`, s.status, s.detail]
                  .filter(Boolean).join(' · ')}
              </small>
            </li>
          )
        })}
      </ol>
    </section>
  )
}

function Section({ section }) {
  return (
    <section className="panel as-section" aria-label={section.title}>
      <h3>{section.title} {section.source_ids?.length > 0 && <small>[{section.source_ids.join('][')}]</small>}</h3>
      {section.error ? (
        <p className="ix-warn">{section.error}</p>
      ) : (
        <dl className="as-facts">
          {section.facts.map((fact) => (
            <div key={`${fact.label}-${fact.value}`}>
              <dt>{fact.label}</dt>
              <dd className="num">{String(fact.value)} <Kind kind={fact.kind} /></dd>
            </div>
          ))}
        </dl>
      )}
      {section.notes.map((note) => <p key={note} className="ix-footnote">{note}</p>)}
    </section>
  )
}

/** Ask questions about FinPulse's own data: rule-based (always on) or a local AI model (optional). */
export default function AssistantPage() {
  const [status, setStatus] = useState(null)
  const [question, setQuestion] = useState('')
  const [mode, setMode] = useState('rules')
  const [state, setState] = useState({ loading: false, error: '', answer: null })

  useEffect(() => {
    let cancelled = false
    getAssistantStatus()
      .then((data) => { if (!cancelled) setStatus(data) })
      .catch(() => { if (!cancelled) setStatus({ rules: { available: true }, local: { available: false, error: 'Status unavailable.' }, examples: [] }) })
    return () => { cancelled = true }
  }, [])

  const ask = async (text) => {
    const q = (text ?? question).trim()
    if (q.length < 2 || state.loading) return
    setQuestion(q)
    setState({ loading: true, error: '', answer: null })
    try {
      setState({ loading: false, error: '', answer: await askAssistant(q, mode) })
    } catch (err) {
      setState({ loading: false, error: err.message || 'The assistant could not answer.', answer: null })
    }
  }

  const local = status?.local
  const answer = state.answer

  return (
    <div className="ix">
      <p className="macro-notice">
        Answers come only from FinPulse&apos;s own data and calculations, with every source listed. Nothing is traded or changed.
        {mode === 'rules'
          ? ' Rule-based mode: no AI, it reports figures and never interprets or predicts.'
          : ' Local AI mode: a model running on this computer writes the answer; numbers it did not get from the data are flagged.'}
        {' '}Not investment advice.
      </p>

      <section className="panel as-ask" aria-label="Ask a question">
        <div className="range-control" role="group" aria-label="Assistant mode">
          <button onClick={() => setMode('rules')} className={mode === 'rules' ? 'range-active' : ''} aria-pressed={mode === 'rules'}>Rule-based</button>
          <button
            onClick={() => setMode('local')}
            className={mode === 'local' ? 'range-active' : ''}
            aria-pressed={mode === 'local'}
            disabled={!local?.available}
            title={local?.available ? `Local model: ${local.model}` : local?.error ?? 'Checking…'}
          >
            Local AI{local?.available ? ` · ${local.model}` : ''}
          </button>
        </div>
        {local && !local.available && <p className="ix-footnote">Local AI is off: {local.error}</p>}
        <form className="as-form" onSubmit={(event) => { event.preventDefault(); ask() }}>
          <input
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="e.g. Compare Bitcoin with the S&P 500"
            maxLength={300}
            aria-label="Question"
          />
          <button type="submit" disabled={state.loading || question.trim().length < 2} className="as-submit">
            <Send size={14} /> {state.loading ? (mode === 'local' ? 'Thinking (can take a minute)…' : 'Working…') : 'Ask'}
          </button>
        </form>
        <div className="as-examples">
          {(status?.examples ?? []).map((example) => (
            <button key={example} onClick={() => ask(example)} className="news-tag">{example}</button>
          ))}
        </div>
      </section>

      {state.error && <section className="panel empty-panel ix-error">{state.error}</section>}

      {answer && (
        <>
          <section className="panel as-answer" aria-label="Answer">
            {answer.understood && <p className="ix-footnote">Understood as: {answer.understood}</p>}
            {answer.mode === 'local' && answer.available === false && <p className="ix-warn">{answer.error}</p>}
            {answer.mode === 'local' && answer.answer && (
              <>
                <p className="as-text">{answer.answer}</p>
                {answer.unverified.length > 0 ? (
                  <p className="as-unverified">
                    ⚠ Not found in the data: {answer.unverified.join(', ')}. Treat these numbers as unreliable and check the tables below.
                  </p>
                ) : (
                  <p className="ix-footnote">Every number in this answer was found in the data below.</p>
                )}
              </>
            )}
            <ul className="as-summary">
              {answer.summary.map((line) => <li key={line.text}><Kind kind={line.kind} /> {line.text}</li>)}
            </ul>
          </section>
          {answer.sections.map((section) => <Section key={`${section.tool}-${JSON.stringify(section.args)}`} section={section} />)}
          <Sources sources={answer.sources} />
        </>
      )}
    </div>
  )
}
