import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  getAutoTradingStatus,
  getInsights,
  getPaperSnapshots,
  getPaperSummary,
  getPaperTrades,
  getPortfolio,
  getScreener,
  getSignals,
  replayPaperTrading,
  runPaperCycle,
  startAutoTrading,
  stopAutoTrading,
} from './api'
import './App.css'
import type {
  AutoTradingStatus,
  InsightPeriod,
  MarketInsight,
  PaperPortfolioSnapshot,
  PaperPortfolioSummary,
  PaperTrade,
  PortfolioSummary,
  ScreenerResponse,
  SignalsResponse,
  Timeframe,
  TradeSignal,
} from './types'

type TabKey = 'overview' | 'signals' | 'paper' | 'screener' | 'portfolio' | 'insights'

const tabs: Array<{ key: TabKey; label: string }> = [
  { key: 'overview', label: 'Overview' },
  { key: 'signals', label: 'Signals' },
  { key: 'paper', label: 'Paper Trading' },
  { key: 'screener', label: 'Screener' },
  { key: 'portfolio', label: 'Portfolio' },
  { key: 'insights', label: 'Insights' },
]

function formatCurrency(value?: number | null): string {
  if (value === undefined || value === null || Number.isNaN(value)) {
    return '—'
  }
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 2,
  }).format(value)
}

function formatPercent(value?: number | null): string {
  if (value === undefined || value === null || Number.isNaN(value)) {
    return '—'
  }
  return `${value.toFixed(2)}%`
}

function formatDate(value?: string | null): string {
  if (!value) return '—'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString()
}

function describeAutoOutcome(status?: AutoTradingStatus | null): string {
  if (!status?.enabled) {
    return 'Automatic paper trading is off.'
  }
  if (status.is_running) {
    return 'A cycle is running now.'
  }
  if (status.last_error) {
    return 'Last cycle could not fetch enough market data.'
  }
  if (status.last_run_outcome) {
    return `Last cycle: ${status.last_run_outcome}`
  }
  return 'Waiting for the first automatic cycle.'
}

function Sparkline({ snapshots }: { snapshots: PaperPortfolioSnapshot[] }) {
  if (snapshots.length < 2) {
    return <div className="empty-inline">Need more paper-trading snapshots to draw the equity curve.</div>
  }

  const values = snapshots
    .slice()
    .reverse()
    .map((item) => item.total_equity)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const range = max - min || 1
  const width = 520
  const height = 140
  const points = values
    .map((value, index) => {
      const x = (index / (values.length - 1)) * width
      const y = height - ((value - min) / range) * height
      return `${x},${y}`
    })
    .join(' ')

  return (
    <div className="sparkline-card">
      <div className="section-heading">
        <h3>Paper equity curve</h3>
        <span>{snapshots.length} snapshots</span>
      </div>
      <svg className="sparkline" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
        <polyline fill="none" stroke="currentColor" strokeWidth="3" points={points} />
      </svg>
      <div className="sparkline-range">
        <span>{formatCurrency(min)}</span>
        <span>{formatCurrency(max)}</span>
      </div>
    </div>
  )
}

function SignalTable({ title, signals }: { title: string; signals: TradeSignal[] }) {
  return (
    <section className="panel">
      <div className="section-heading">
        <h3>{title}</h3>
        <span>{signals.length} ideas</span>
      </div>
      {signals.length === 0 ? (
        <div className="empty-state">No signals returned for this view.</div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Confidence</th>
                <th>Entry</th>
                <th>Target</th>
                <th>Projected/day</th>
                <th>Backtest EV</th>
              </tr>
            </thead>
            <tbody>
              {signals.slice(0, 10).map((signal) => (
                <tr key={`${title}-${signal.symbol}`}>
                  <td>
                    <strong>{signal.symbol}</strong>
                    <div className="muted">{signal.name ?? '—'}</div>
                  </td>
                  <td>{formatPercent(signal.confidence * 100)}</td>
                  <td>{formatCurrency(signal.entry_price)}</td>
                  <td>{formatCurrency(signal.target_price)}</td>
                  <td>{formatCurrency(signal.trade_plan?.projected_daily_profit_usd)}</td>
                  <td>{formatPercent(signal.backtest?.expected_value_pct)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

function App() {
  const [activeTab, setActiveTab] = useState<TabKey>('overview')
  const [signalsTimeframe, setSignalsTimeframe] = useState<Timeframe>('weekly')
  const [insightPeriod, setInsightPeriod] = useState<InsightPeriod>('daily')
  const [signals, setSignals] = useState<SignalsResponse | null>(null)
  const [screener, setScreener] = useState<ScreenerResponse | null>(null)
  const [portfolio, setPortfolio] = useState<PortfolioSummary | null>(null)
  const [paperSummary, setPaperSummary] = useState<PaperPortfolioSummary | null>(null)
  const [paperTrades, setPaperTrades] = useState<PaperTrade[]>([])
  const [paperSnapshots, setPaperSnapshots] = useState<PaperPortfolioSnapshot[]>([])
  const [autoTradingStatus, setAutoTradingStatus] = useState<AutoTradingStatus | null>(null)
  const [insights, setInsights] = useState<MarketInsight | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actionStatus, setActionStatus] = useState<string | null>(null)

  const refreshAll = useCallback(async () => {
    setLoading(true)
    setError(null)
    const results = await Promise.allSettled([
      getSignals(signalsTimeframe),
      getScreener(),
      getPortfolio(),
      getPaperSummary(),
      getPaperTrades(),
      getPaperSnapshots(),
      getAutoTradingStatus(),
      getInsights(insightPeriod),
    ])

    const failures = results
      .filter((result): result is PromiseRejectedResult => result.status === 'rejected')
      .map((result) => result.reason instanceof Error ? result.reason.message : String(result.reason))

    if (results[0].status === 'fulfilled') setSignals(results[0].value)
    if (results[1].status === 'fulfilled') setScreener(results[1].value)
    if (results[2].status === 'fulfilled') setPortfolio(results[2].value)
    if (results[3].status === 'fulfilled') setPaperSummary(results[3].value)
    if (results[4].status === 'fulfilled') setPaperTrades(results[4].value)
    if (results[5].status === 'fulfilled') setPaperSnapshots(results[5].value)
    if (results[6].status === 'fulfilled') setAutoTradingStatus(results[6].value)
    if (results[7].status === 'fulfilled') setInsights(results[7].value)

    if (failures.length > 0) {
      setError(failures[0])
    }
    setLoading(false)
  }, [insightPeriod, signalsTimeframe])

  useEffect(() => {
    void refreshAll()
  }, [refreshAll])

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      void refreshAll()
    }, 30_000)

    const handleVisibilityRefresh = () => {
      if (document.visibilityState === 'visible') {
        void refreshAll()
      }
    }

    window.addEventListener('focus', handleVisibilityRefresh)
    document.addEventListener('visibilitychange', handleVisibilityRefresh)

    return () => {
      window.clearInterval(intervalId)
      window.removeEventListener('focus', handleVisibilityRefresh)
      document.removeEventListener('visibilitychange', handleVisibilityRefresh)
    }
  }, [refreshAll])

  const buySignals = signals?.buy_signals ?? []
  const sellSignals = signals?.sell_signals ?? []
  const topSignal = buySignals[0]
  const latestSnapshot = paperSummary?.latest_snapshot
  const displayPaperTrades = paperTrades.length ? paperTrades : (paperSummary?.recent_trades ?? [])

  const providerReadiness = useMemo(() => {
    const count = topSignal?.intelligence?.source_count ?? 0
    if (count >= 3) return 'Provider-enriched'
    if (count >= 1) return 'Partially enriched'
    return 'Technical-only fallback'
  }, [topSignal])

  async function handleRunPaperCycle() {
    setActionStatus('Running paper cycle...')
    try {
      await runPaperCycle()
      setActionStatus('Paper cycle completed.')
      await refreshAll()
    } catch (err) {
      setActionStatus(err instanceof Error ? err.message : 'Failed to run paper cycle.')
    }
  }

  async function handleReplay() {
    setActionStatus('Replaying 30 market days...')
    try {
      await replayPaperTrading(30, false)
      setActionStatus('Replay completed.')
      await refreshAll()
    } catch (err) {
      setActionStatus(err instanceof Error ? err.message : 'Replay failed.')
    }
  }

  async function handleStartAutoTrading() {
    setActionStatus('Starting automatic paper trading...')
    try {
      const status = await startAutoTrading()
      setAutoTradingStatus(status)
      setActionStatus('Automatic paper trading is on.')
      await refreshAll()
    } catch (err) {
      setActionStatus(err instanceof Error ? err.message : 'Failed to start automatic paper trading.')
    }
  }

  async function handleStopAutoTrading() {
    setActionStatus('Stopping automatic paper trading...')
    try {
      const status = await stopAutoTrading()
      setAutoTradingStatus(status)
      setActionStatus('Automatic paper trading is off.')
      await refreshAll()
    } catch (err) {
      setActionStatus(err instanceof Error ? err.message : 'Failed to stop automatic paper trading.')
    }
  }

  return (
    <div className="app-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">Local web operator console</p>
          <h1>Stock Trading Engine</h1>
          <p className="hero-copy">
            Test the FastAPI backend, multi-source signal fusion, and paper-trading loop here first,
            then mirror the same flows in Android.
          </p>
        </div>
        <div className="hero-actions">
          <button type="button" onClick={() => void refreshAll()}>Refresh data</button>
          <button type="button" className="secondary" onClick={() => void handleRunPaperCycle()}>
            Run paper cycle
          </button>
          <button type="button" className="secondary" onClick={() => void handleReplay()}>
            Replay 30 days
          </button>
        </div>
      </header>

      <section className="top-stats">
        <article className="stat-card">
          <span>Top BUY idea</span>
          <strong>{topSignal?.symbol ?? '—'}</strong>
          <small>{formatCurrency(topSignal?.trade_plan?.projected_daily_profit_usd)} / day</small>
        </article>
        <article className="stat-card">
          <span>Paper equity</span>
          <strong>{formatCurrency(paperSummary?.total_equity)}</strong>
          <small>{formatPercent(paperSummary?.total_return_pct)}</small>
        </article>
        <article className="stat-card">
          <span>Today vs goal</span>
          <strong>{formatCurrency(paperSummary?.daily_goal?.actual)}</strong>
          <small>{formatPercent(paperSummary?.daily_goal?.progress_pct)}</small>
        </article>
        <article className="stat-card">
          <span>Signal readiness</span>
          <strong>{providerReadiness}</strong>
          <small>{topSignal?.intelligence?.source_count ?? 0} sources on top idea</small>
        </article>
        <article className="stat-card">
          <span>Auto paper mode</span>
          <strong>{autoTradingStatus?.enabled ? 'Active' : 'Manual'}</strong>
          <small>{describeAutoOutcome(autoTradingStatus)}</small>
        </article>
      </section>

      <nav className="tab-bar" aria-label="Primary">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            type="button"
            className={tab.key === activeTab ? 'tab active' : 'tab'}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {error ? <div className="banner error">{error}</div> : null}
      {actionStatus ? <div className="banner">{actionStatus}</div> : null}
      {loading ? <div className="loading">Loading backend data...</div> : null}

      {!loading && (
        <main className="content">
          {activeTab === 'overview' && (
            <div className="grid two-col">
              <section className="panel">
                <div className="section-heading">
                  <h3>Signals snapshot</h3>
                  <div className="inline-controls">
                    <label>
                      Timeframe
                      <select value={signalsTimeframe} onChange={(e) => setSignalsTimeframe(e.target.value as Timeframe)}>
                        <option value="weekly">Weekly</option>
                        <option value="monthly">Monthly</option>
                      </select>
                    </label>
                  </div>
                </div>
                <div className="mini-grid">
                  <div className="mini-card">
                    <span>BUY signals</span>
                    <strong>{buySignals.length}</strong>
                  </div>
                  <div className="mini-card">
                    <span>SELL signals</span>
                    <strong>{sellSignals.length}</strong>
                  </div>
                  <div className="mini-card">
                    <span>Paper open positions</span>
                    <strong>{paperSummary?.open_positions?.length ?? 0}</strong>
                  </div>
                  <div className="mini-card">
                    <span>Closed trades</span>
                    <strong>{latestSnapshot?.closed_trades ?? 0}</strong>
                  </div>
                </div>
                <SignalTable title="Top BUY signals" signals={buySignals} />
              </section>
              <div className="stack">
                <Sparkline snapshots={paperSnapshots} />
                <section className="panel">
                  <div className="section-heading">
                    <h3>Learning state</h3>
                    <span>{paperSummary?.learning_state?.trades_evaluated ?? 0} trades evaluated</span>
                  </div>
                  <div className="weights-list">
                    {paperSummary
                      ? Object.entries(paperSummary.learning_state.weights).map(([key, value]) => (
                          <div key={key} className="weight-row">
                            <span>{key.replaceAll('_', ' ')}</span>
                            <strong>{formatPercent(value * 100)}</strong>
                          </div>
                        ))
                      : <div className="empty-state">No learning data yet.</div>}
                  </div>
                </section>
              </div>
            </div>
          )}

          {activeTab === 'signals' && (
            <div className="stack">
              <section className="panel">
                <div className="section-heading">
                  <h3>Signal controls</h3>
                  <label>
                    Timeframe
                    <select value={signalsTimeframe} onChange={(e) => setSignalsTimeframe(e.target.value as Timeframe)}>
                      <option value="weekly">Weekly</option>
                      <option value="monthly">Monthly</option>
                    </select>
                  </label>
                </div>
              </section>
              <SignalTable title="BUY signals" signals={buySignals} />
              <SignalTable title="SELL signals" signals={sellSignals} />
            </div>
          )}

          {activeTab === 'paper' && (
            <div className="stack">
              <section className="panel">
                <div className="section-heading">
                  <h3>Automatic paper trading</h3>
                  <span>{autoTradingStatus?.enabled ? 'running on schedule' : 'manual only'}</span>
                </div>
                <div className="mini-grid">
                  <div className="mini-card">
                    <span>Status</span>
                    <strong>{autoTradingStatus?.is_running ? 'Running now' : autoTradingStatus?.enabled ? 'Enabled' : 'Stopped'}</strong>
                    <small>Every {autoTradingStatus?.interval_minutes ?? 15} min</small>
                  </div>
                  <div className="mini-card">
                    <span>Next cycle</span>
                    <strong>{formatDate(autoTradingStatus?.next_run_at)}</strong>
                    <small>Last cycle {formatDate(autoTradingStatus?.last_cycle_date)}</small>
                  </div>
                  <div className="mini-card">
                    <span>Total auto runs</span>
                    <strong>{autoTradingStatus?.total_runs ?? 0}</strong>
                    <small>{describeAutoOutcome(autoTradingStatus)}</small>
                  </div>
                </div>
                <div className="action-row">
                  <button type="button" onClick={() => void handleStartAutoTrading()}>
                    Start auto trading
                  </button>
                  <button type="button" className="secondary" onClick={() => void handleStopAutoTrading()}>
                    Stop auto trading
                  </button>
                </div>
                {autoTradingStatus?.last_error ? (
                  <div className="inline-error">Last scheduler error: {autoTradingStatus.last_error}</div>
                ) : null}
              </section>

              <section className="panel">
                <div className="section-heading">
                  <h3>Paper portfolio summary</h3>
                  <span>{latestSnapshot?.market_regime ?? '—'}</span>
                </div>
                <div className="mini-grid">
                  <div className="mini-card">
                    <span>Cash</span>
                    <strong>{formatCurrency(paperSummary?.cash_balance)}</strong>
                  </div>
                  <div className="mini-card">
                    <span>Market value</span>
                    <strong>{formatCurrency(paperSummary?.market_value)}</strong>
                  </div>
                  <div className="mini-card">
                    <span>Daily goal</span>
                    <strong>{formatCurrency(paperSummary?.daily_goal?.actual)}</strong>
                    <small>Target {formatCurrency(paperSummary?.daily_goal?.target)}</small>
                  </div>
                  <div className="mini-card">
                    <span>Weekly goal</span>
                    <strong>{formatCurrency(paperSummary?.weekly_goal?.actual)}</strong>
                    <small>Target {formatCurrency(paperSummary?.weekly_goal?.target)}</small>
                  </div>
                </div>
              </section>

              <Sparkline snapshots={paperSnapshots} />

              <section className="panel">
                <div className="section-heading">
                  <h3>Open positions</h3>
                  <span>{paperSummary?.open_positions?.length ?? 0} open</span>
                </div>
                {paperSummary?.open_positions?.length ? (
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Side</th>
                          <th>Symbol</th>
                          <th>Held</th>
                          <th>Entry</th>
                          <th>Current</th>
                          <th>PnL</th>
                        </tr>
                      </thead>
                      <tbody>
                        {paperSummary.open_positions.map((position) => (
                          <tr key={position.symbol}>
                            <td>{position.side}</td>
                            <td>{position.symbol}</td>
                            <td>{position.days_held}d</td>
                            <td>{formatCurrency(position.entry_price)}</td>
                            <td>{formatCurrency(position.current_price)}</td>
                            <td>{formatCurrency(position.unrealised_pnl)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="empty-state">No open paper positions yet.</div>
                )}
              </section>

              <section className="panel">
                <div className="section-heading">
                  <h3>Recent paper trades</h3>
                  <span>{displayPaperTrades.length} shown</span>
                </div>
                {displayPaperTrades.length ? (
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Side</th>
                          <th>Symbol</th>
                          <th>Price</th>
                          <th>PnL</th>
                          <th>Reason</th>
                          <th>Executed</th>
                        </tr>
                      </thead>
                      <tbody>
                        {displayPaperTrades.map((trade, index) => (
                          <tr key={`${trade.symbol}-${trade.side}-${index}`}>
                            <td>{trade.side}</td>
                            <td>{trade.symbol}</td>
                            <td>{formatCurrency(trade.price)}</td>
                            <td>{formatCurrency(trade.pnl)}</td>
                            <td>{trade.reason}</td>
                            <td>{formatDate(trade.executed_at)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="empty-state">No paper trades recorded yet.</div>
                )}
              </section>
            </div>
          )}

          {activeTab === 'screener' && (
            <section className="panel">
              <div className="section-heading">
                <h3>Top screener results</h3>
                <span>{screener?.total ?? 0} matches</span>
              </div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Symbol</th>
                      <th>Price</th>
                      <th>Change %</th>
                      <th>RSI</th>
                      <th>Volume</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(screener?.stocks ?? []).map((stock) => (
                      <tr key={stock.symbol}>
                        <td>
                          <strong>{stock.symbol}</strong>
                          <div className="muted">{stock.name ?? '—'}</div>
                        </td>
                        <td>{formatCurrency(stock.current_price)}</td>
                        <td>{formatPercent(stock.change_pct)}</td>
                        <td>{stock.indicators?.rsi?.toFixed(1) ?? '—'}</td>
                        <td>{stock.volume?.toLocaleString() ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {activeTab === 'portfolio' && (
            <section className="panel">
              <div className="section-heading">
                <h3>Portfolio</h3>
                <span>{portfolio?.holdings_count ?? 0} holdings</span>
              </div>
              <div className="mini-grid">
                <div className="mini-card">
                  <span>Invested</span>
                  <strong>{formatCurrency(portfolio?.total_invested)}</strong>
                </div>
                <div className="mini-card">
                  <span>Current</span>
                  <strong>{formatCurrency(portfolio?.current_value)}</strong>
                </div>
                <div className="mini-card">
                  <span>Total PnL</span>
                  <strong>{formatCurrency(portfolio?.total_pnl)}</strong>
                </div>
                <div className="mini-card">
                  <span>PnL %</span>
                  <strong>{formatPercent(portfolio?.total_pnl_pct)}</strong>
                </div>
              </div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Symbol</th>
                      <th>Qty</th>
                      <th>Avg buy</th>
                      <th>Current</th>
                      <th>PnL</th>
                      <th>Weight</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(portfolio?.holdings ?? []).map((holding) => (
                      <tr key={holding.symbol}>
                        <td>{holding.symbol}</td>
                        <td>{holding.quantity}</td>
                        <td>{formatCurrency(holding.avg_buy_price)}</td>
                        <td>{formatCurrency(holding.current_price)}</td>
                        <td>{formatCurrency(holding.unrealised_pnl)}</td>
                        <td>{formatPercent(holding.weight)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {activeTab === 'insights' && (
            <div className="stack">
              <section className="panel">
                <div className="section-heading">
                  <h3>Market insights</h3>
                  <label>
                    Period
                    <select value={insightPeriod} onChange={(e) => setInsightPeriod(e.target.value as InsightPeriod)}>
                      <option value="daily">Daily</option>
                      <option value="weekly">Weekly</option>
                    </select>
                  </label>
                </div>
                <p className="insight-summary">{insights?.summary ?? 'No insights available.'}</p>
              </section>

              <div className="grid two-col">
                <section className="panel">
                  <div className="section-heading">
                    <h3>Observations</h3>
                    <span>{insights?.key_observations?.length ?? 0}</span>
                  </div>
                  <ul className="bullet-list">
                    {(insights?.key_observations ?? []).map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </section>
                <section className="panel">
                  <div className="section-heading">
                    <h3>Recommended actions</h3>
                    <span>{insights?.recommended_actions?.length ?? 0}</span>
                  </div>
                  <ul className="bullet-list">
                    {(insights?.recommended_actions ?? []).map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </section>
              </div>
            </div>
          )}
        </main>
      )}
    </div>
  )
}

export default App
