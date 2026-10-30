import { ExternalLink } from 'lucide-react'
import { formatAge, parseTimestamp } from '../lib/dataStatus'
import { getAssetDetails } from '../lib/format'
import { TOPIC_LABEL, safeHref } from '../lib/news'

const publishedFormat = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'UTC',
})

/** One headline: source, age, a link to the original, its snippet and tags. */
export default function NewsItem({ item, loadedAt }) {
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
