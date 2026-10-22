import { createContext } from 'react'

// The latest live prices and the live symbols, for the few components deep in the tree that
// need them (the notification panel's alert form). Passing ticks down as props would make
// the memoized top bar re-render on every tick; a context re-renders only its consumers.
export const LivePricesContext = createContext({ ticks: {}, symbols: [] })
