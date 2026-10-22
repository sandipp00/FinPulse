import PaperTrading from '../components/PaperTrading'

/** The paper-trading account: order ticket, holdings, equity curve and history. */
export default function PortfolioPage({ liveSymbols, ticks, liveStatus }) {
  return <PaperTrading symbols={liveSymbols} ticks={ticks} liveStatus={liveStatus} />
}
