import type {
  AutoTradingStatus,
  InsightPeriod,
  MarketInsight,
  PaperCycleResult,
  PaperPortfolioSnapshot,
  PaperPortfolioSummary,
  PaperTrade,
  PortfolioSummary,
  ScreenerResponse,
  SignalsResponse,
  Timeframe,
} from './types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      Accept: 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  })

  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `Request failed: ${response.status}`)
  }

  return response.json() as Promise<T>
}

export function getSignals(timeframe: Timeframe): Promise<SignalsResponse> {
  return request<SignalsResponse>(`/signals?timeframe=${timeframe}`)
}

export function getScreener(): Promise<ScreenerResponse> {
  return request<ScreenerResponse>('/stocks/screen?sort_by=change_pct&sort_order=desc&limit=20')
}

export function getPortfolio(): Promise<PortfolioSummary> {
  return request<PortfolioSummary>('/portfolio')
}

export function getPaperSummary(): Promise<PaperPortfolioSummary> {
  return request<PaperPortfolioSummary>('/paper/summary')
}

export function getPaperTrades(): Promise<PaperTrade[]> {
  return request<PaperTrade[]>('/paper/trades?limit=20')
}

export function getPaperSnapshots(): Promise<PaperPortfolioSnapshot[]> {
  return request<PaperPortfolioSnapshot[]>('/paper/snapshots?limit=30')
}

export function getInsights(period: InsightPeriod): Promise<MarketInsight> {
  return request<MarketInsight>(`/insights?period=${period}`)
}

export function runPaperCycle(): Promise<PaperCycleResult> {
  return request<PaperCycleResult>('/paper/run-cycle', { method: 'POST' })
}

export function replayPaperTrading(days = 30, reset = false): Promise<{ days_replayed: number }> {
  return request<{ days_replayed: number }>(`/paper/replay?days=${days}&reset=${reset}`, {
    method: 'POST',
  })
}

export function getAutoTradingStatus(): Promise<AutoTradingStatus> {
  return request<AutoTradingStatus>('/paper/auto/status')
}

export function startAutoTrading(intervalMinutes = 15, runImmediately = true): Promise<AutoTradingStatus> {
  return request<AutoTradingStatus>(
    `/paper/auto/start?interval_minutes=${intervalMinutes}&run_immediately=${runImmediately}`,
    { method: 'POST' },
  )
}

export function stopAutoTrading(): Promise<AutoTradingStatus> {
  return request<AutoTradingStatus>('/paper/auto/stop', { method: 'POST' })
}
