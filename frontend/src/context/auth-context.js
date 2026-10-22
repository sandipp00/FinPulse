import { createContext } from 'react'

// Kept apart from the provider component so that file only exports a component
// (required for fast refresh to work).
export const AuthContext = createContext(null)
