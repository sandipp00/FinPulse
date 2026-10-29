import { useId, useMemo, useRef, useState } from 'react'
import { Search } from 'lucide-react'
import { searchInstruments } from '../lib/explorer'
import { getAssetDetails } from '../lib/format'

const CLASS_LABEL = { crypto: 'Crypto', stock: 'Stock', index: 'Index' }

/**
 * A searchable instrument picker (ARIA combobox): type to filter, arrow keys to
 * move, Enter to choose, Escape to close. `disabledReason(item)` can grey out
 * options with a reason (e.g. "no hourly data").
 */
export default function InstrumentSearch({ label, instruments, value, onChange, disabledReason, allowNone = false }) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const inputRef = useRef(null)
  const listId = useId()

  const matches = useMemo(() => searchInstruments(instruments, query), [instruments, query])
  const options = allowNone ? [null, ...matches] : matches
  const selected = instruments.find((item) => item.symbol === value)

  const choose = (item) => {
    if (item && disabledReason?.(item)) return
    onChange(item ? item.symbol : '')
    setQuery('')
    setOpen(false)
    inputRef.current?.blur()
  }

  const onKeyDown = (event) => {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      if (!open) {
        setOpen(true)
        return
      }
      const step = event.key === 'ArrowDown' ? 1 : -1
      setActive((index) => (index + step + options.length) % Math.max(options.length, 1))
    } else if (event.key === 'Enter') {
      if (open && options.length > 0) {
        event.preventDefault()
        choose(options[Math.min(active, options.length - 1)])
      }
    } else if (event.key === 'Escape') {
      if (query) setQuery('')
      else {
        setOpen(false)
        event.currentTarget.blur()
      }
    }
  }

  const display = selected ? `${selected.symbol} · ${getAssetDetails(selected.symbol).name}` : (allowNone ? 'None' : '')

  return (
    <div className="ix-search">
      <span className="ix-search-label">{label}</span>
      <div className={`ix-search-box ${open ? 'ix-search-open' : ''}`}>
        <Search size={14} aria-hidden="true" />
        <input
          ref={inputRef}
          role="combobox"
          aria-label={label}
          aria-expanded={open}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={open && options.length ? `${listId}-${active}` : undefined}
          value={open ? query : display}
          placeholder={open ? 'Symbol or name…' : undefined}
          onFocus={() => {
            setOpen(true)
            setActive(0)
          }}
          onBlur={() => setOpen(false)}
          onChange={(event) => {
            setQuery(event.target.value)
            setActive(0)
          }}
          onKeyDown={onKeyDown}
        />
      </div>

      {open && (
        <ul className="ix-options" role="listbox" id={listId}>
          {options.length === 0 && <li className="ix-option-empty">No supported instrument matches “{query}”.</li>}
          {options.map((item, index) => {
            const reason = item ? disabledReason?.(item) : null
            return (
              <li
                key={item?.symbol ?? 'none'}
                id={`${listId}-${index}`}
                role="option"
                aria-selected={(item?.symbol ?? '') === (value ?? '')}
                aria-disabled={reason ? true : undefined}
                className={`ix-option ${index === active ? 'ix-option-active' : ''} ${reason ? 'ix-option-disabled' : ''}`}
                // mousedown, not click: a click would blur the input (closing the list) first.
                onMouseDown={(event) => {
                  event.preventDefault()
                  choose(item)
                }}
                onMouseEnter={() => setActive(index)}
              >
                {item ? (
                  <>
                    <strong>{item.symbol}</strong>
                    <span>{getAssetDetails(item.symbol).name}</span>
                    <small>{reason ?? `${CLASS_LABEL[item.asset_class]} · ${item.live ? 'live + history' : 'stored daily'}`}</small>
                  </>
                ) : (
                  <span>No comparison</span>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
