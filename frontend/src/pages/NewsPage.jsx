import { useMemo, useState } from 'react'
import { ExternalLink } from 'lucide-react'
import { useNews } from '../hooks/useNews'
import { formatAge, parseTimestamp } from '../lib/dataStatus'
import { getAssetDetails } from '../lib/format'
import { TOPIC_LABEL, filterNews, safeHref } from '../lib/news'

const SOURCE_STATUS = {
  ok: { tone: 'ok', label: 'OK' },
  stale: { tone: 'warn', label: 'STALE' },
  unavailable: { tone: 'error', label: 'DOWN' },
  not_configured: { tone: 'muted', label: 'OFF' },
}

const publishedFormat = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'UTC',
})

function NewsItem({ item, loadedAt }) {
  const href = safeHref(item.url)
  const published = parseTimestamp(item.published_at)
  return (
    <li className="news-item">
      <div className="news-meta">
        <span className="news-source">{item.source_name}</span>
        <time dateTime={item.published_at} title={published ? `${publishedFormat.format(published)} UTC` : undefined}>
          {published ? `${formatAge(loadedAt - published.getTime())} · ${publishedFormat.format(published)} UTC` : '—'}
        </time>
        {item.stale && <span className="ix-warn">kept copy, source not answering</span>}
      </div>
      {href ? (
        <a className="news-title" href={href} target="_blank" rel="noopener noreferrer">
          {item.title} <ExternalLink size={12} aria-hidden="true" />
        </a>
      ) : (
        <span className="news-title">{item.title}</span>
      )}
      {item.summary && <p className="news-summary">{item.summary}</p>}
      <div className="news-tags">
        {item.topics.map((topic) => <span key={topic} className="news-tag">{TOPIC_LABEL[topic] ?? topic}</span>)}
        {item.instruments.map((symbol) => (
          <span key={symbol} className="news-tag news-tag-instrument" title={getAssetDetails(symbol).name}>{symbol}</span>
        ))}
      </div>
    </li>
  )
}

/** Source-linked headlines: official releases, crypto news and SEC filings, with filters. */
export default function NewsPage() {
  const { data, loading, error, loadedAt } = useNews()
  const [filters, setFilters] = useState({ topic: '', instrument: '', source: '' })
  const items = useMemo(() => (data ? filterNews(data.items, filters) : []), [data, filters])

  if (loading) return <section className="panel empty-panel">Loading news…</section>
  if (error) return <section className="panel empty-panel ix-error">News could not be loaded: {error}</section>

  const set = (key) => (event) => setFilters((current) => ({ ...current, [key]: event.target.value }))

  return (
    <div className="ix">
      <p className="macro-notice">
        {data.policy} Times are each source&apos;s own publication times, shown in UTC. Sources:{' '}
        {data.sources.map((s, i) => (
          <span key={s.id}>{i > 0 && '; '}<a href={s.homepage} target="_blank" rel="noopener noreferrer">{s.attribution}</a></span>
        ))}.
      </p>

      <section className="panel news-sources" aria-label="Sources">
        {data.sources.map((s) => {
          const state = SOURCE_STATUS[s.status] ?? SOURCE_STATUS.unavailable
          return (
            <span key={s.id} className={`status-item tone-${state.tone}`} title={s.error ?? `${s.count} items`}>
              <i />{s.name} <b>{state.label}</b>
              {s.status === 'ok' || s.status === 'stale' ? <span className="status-sub">{s.count}</span> : null}
              {s.status === 'not_configured' && <span className="status-sub">{s.error}</span>}
            </span>
          )
        })}
      </section>

      <section className="panel ix-controls" aria-label="Filters">
        <label className="ix-control">
          <span className="ix-search-label">Topic</span>
          <select className="news-select" value={filters.topic} onChange={set('topic')}>
            <option value="">All topics</option>
            {data.topics.map((t) => <option key={t} value={t}>{TOPIC_LABEL[t] ?? t}</option>)}
          </select>
        </label>
        <label className="ix-control">
          <span className="ix-search-label">Instrument</span>
          <select className="news-select" value={filters.instrument} onChange={set('instrument')}>
            <option value="">All instruments</option>
            {data.instruments.map((s) => <option key={s} value={s}>{s} · {getAssetDetails(s).name}</option>)}
          </select>
        </label>
        <label className="ix-control">
          <span className="ix-search-label">Source</span>
          <select className="news-select" value={filters.source} onChange={set('source')}>
            <option value="">All sources</option>
            {data.sources.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </label>
        <span className="news-count">{items.length} of {data.items.length} headlines</span>
      </section>

      {items.length === 0 ? (
        <section className="panel empty-panel">No headlines match these filters.</section>
      ) : (
        <ul className="panel news-list">
          {items.map((item) => <NewsItem key={item.id} item={item} loadedAt={loadedAt} />)}
        </ul>
      )}
    </div>
  )
}
