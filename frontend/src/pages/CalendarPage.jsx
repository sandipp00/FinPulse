import AppLink from '../components/AppLink'
import { useEarnings } from '../hooks/useEarnings'
import { useCalendar } from '../hooks/useNews'
import { CERTAINTY_LABEL, TIMING_LABEL, byDate, formatDay, formatEps, growthVsLastYear } from '../lib/earnings'
import { assetHref } from '../lib/asset'
import { ROUTES } from '../lib/routes'
import { STATUS_LABEL, formatEventDate, formatEventTime, groupByDate, safeHref } from '../lib/news'

/** Upcoming earnings of the 30 followed US stocks (Nasdaq), soonest first. */
function EarningsCalendar() {
  const { data, error, loading } = useEarnings()
  if (loading) return <section className="panel empty-panel">Loading earnings dates…</section>
  if (error) return <section className="panel empty-panel ix-error">Earnings dates could not be loaded: {error}</section>
  const undated = data.stocks.filter((s) => !s.next)
  return (
    <section className="panel cal" aria-label="Upcoming earnings">
      <div className="cal-day">
        <h3 className="at-section-title">Company earnings: the 30 US stocks</h3>
        <p className="deriv-note">{data.notes.slice(0, 3).join(' ')}</p>
      </div>
      {byDate(data.upcoming).map(([day, reports]) => (
        <div key={day} className="cal-day">
          <h3 className="cal-date">{formatDay(day)}</h3>
          <ul>
            {reports.map((r) => (
              <li key={r.symbol} className="cal-event">
                <span className="cal-time">{r.timing ? TIMING_LABEL[r.timing] : '—'}</span>
                <span className="cal-title">
                  <strong><AppLink href={assetHref(r.symbol)} className="link-inline">{r.symbol}</AppLink> {r.name}</strong>
                  <small>
                    {r.fiscal_quarter ? `Quarter ending ${r.fiscal_quarter}` : 'Quarter not given'}
                    {r.eps_forecast != null && ` · consensus EPS ${formatEps(r.eps_forecast)}${r.analysts != null ? ` (${r.analysts} analysts)` : ''}`}
                    {growthVsLastYear(r) && ` · ${growthVsLastYear(r)}`}
                  </small>
                </span>
                <span className={`cal-status earn-${r.certainty}`}>{CERTAINTY_LABEL[r.certainty]}</span>
                <span />
              </li>
            ))}
          </ul>
        </div>
      ))}
      {undated.length > 0 && (
        <div className="cal-day">
          <p className="deriv-note">No date yet: {undated.map((s) => s.symbol).join(', ')}.</p>
        </div>
      )}
      {data.failed.length > 0 && <div className="cal-day"><p className="deriv-note ix-warn">Could not load: {data.failed.join(', ')}.</p></div>}
    </section>
  )
}

/** Company earnings, scheduled US data releases and FOMC/ECB policy meetings. No forecasts beyond the EPS consensus. */
export default function CalendarPage() {
  return (
    <div className="ix">
      <EarningsCalendar />
      <h3 className="at-section-title cal-heading">Economic releases and central-bank meetings</h3>
      <EconomicCalendar />
    </div>
  )
}

/** Scheduled US data releases and FOMC/ECB policy meetings. No forecasts are shown. */
function EconomicCalendar() {
  const { data, loading, error } = useCalendar()

  if (loading) return <section className="panel empty-panel">Loading the calendar…</section>
  if (error) return <section className="panel empty-panel ix-error">The calendar could not be loaded: {error}</section>

  const groups = groupByDate(data.events)
  return (
    <>
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
    </>
  )
}
