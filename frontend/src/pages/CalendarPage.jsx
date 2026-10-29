import AppLink from '../components/AppLink'
import { useCalendar } from '../hooks/useNews'
import { ROUTES } from '../lib/routes'
import { STATUS_LABEL, formatEventDate, formatEventTime, groupByDate, safeHref } from '../lib/news'

/** Scheduled US data releases and FOMC/ECB policy meetings. No forecasts are shown. */
export default function CalendarPage() {
  const { data, loading, error } = useCalendar()

  if (loading) return <section className="panel empty-panel">Loading the calendar…</section>
  if (error) return <section className="panel empty-panel ix-error">The calendar could not be loaded: {error}</section>

  const groups = groupByDate(data.events)
  return (
    <div className="ix">
      <p className="macro-notice">
        Release dates from FRED&apos;s release calendar; BEA release times from BEA&apos;s schedule. BLS releases show the
        date only. FOMC and ECB meetings are copied from the central banks&apos; calendars (checked {data.meetings_checked}).{' '}
        {data.consensus_note} Released values are on the <AppLink href={ROUTES.macro} className="link-inline">Macro</AppLink> page.
      </p>
      {data.notes.map((note) => <p key={note} className="macro-notice ix-warn">{note}</p>)}

      {groups.length === 0 ? (
        <section className="panel empty-panel">No events between {data.from} and {data.to}.</section>
      ) : (
        <section className="panel cal" aria-label={`Events from ${data.from} to ${data.to}`}>
          {groups.map(([day, events]) => (
            <div key={day} className={`cal-day cal-${events[0].status}`}>
              <h3 className="cal-date">{formatEventDate(day)}</h3>
              <ul>
                {events.map((event) => {
                  const href = safeHref(event.source_url)
                  const time = formatEventTime(event.time_utc)
                  return (
                    <li key={`${event.title}-${event.date}`} className="cal-event">
                      <span className="cal-time num">{time ?? '—'}</span>
                      <span className="cal-title">
                        <strong>{event.title}</strong>
                        <small>
                          {event.agency}{event.detail ? ` · ${event.detail}` : ''}
                          {event.series.length > 0 && ` · ${event.series.join(', ')}`}
                        </small>
                        {event.note && <small className="ix-warn">{event.note}</small>}
                      </span>
                      <span className={`cal-status cal-status-${event.status}`}>
                        {event.tentative ? 'Tentative' : STATUS_LABEL[event.status]}
                      </span>
                      {href ? <a href={href} target="_blank" rel="noopener noreferrer" className="link-inline">Source</a> : <span />}
                    </li>
                  )
                })}
              </ul>
            </div>
          ))}
        </section>
      )}
    </div>
  )
}
