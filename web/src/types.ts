export type Timeframe = 'weekly' | 'monthly'
export type InsightPeriod = 'daily' | 'weekly'

export interface TechnicalIndicators {
  rsi?: number | null
  macd?: number | null
  macd_signal?: number | null
  macd_hist?: number | null
  bb_upper?: number | null
  bb_middle?: number | null
  bb_lower?: number | null
  sma_20?: number | null
  sma_50?: number | null
  ema_9?: number | null
  volume_avg?: number | null
}

export interface StockSummary {
  symbol: string
  name?: string | null
  current_price?: number | null
  change_pct?: number | null
  volume?: number | null
  market_cap?: number | null
  indicators?: TechnicalIndicators | null
  last_updated?: string | null
}

export interface ScreenerResponse {
  total: number
  stocks: StockSummary[]
}

export interface BacktestSummary {
  trades: number
  wins: number
  losses: number
  win_rate?: number | null
  avg_return_pct?: number | null
  expected_value_pct?: number | null
  avg_hold_days?: number | null
}

export interface TradePlan {
  account_size: number
  daily_profit_target: number
  capital_per_position: number
  risk_budget_usd: number
  recommended_shares: number
  position_size_usd: number
  projected_profit_usd: number
  projected_daily_profit_usd: number
  risk_amount_usd: number
  reward_risk_ratio?: number | null
  min_holding_days: number
  max_holding_days: number
}

export interface IntelligenceSignals {
  score: number
  [key: string]: string | number | boolean | null | undefined
}

export interface IntelligenceSnapshot {
  composite_score: number
  source_count: number
  fundamentals: IntelligenceSignals
  analyst: IntelligenceSignals
  ownership: IntelligenceSignals
  events: IntelligenceSignals
  sentiment: IntelligenceSignals
  options: IntelligenceSignals
  notes: string[]
}

export interface TradeSignal {
  symbol: string
  name?: string | null
  signal_type: string
  confidence: number
  strategy_score?: number | null
  entry_price?: number | null
  target_price?: number | null
  stop_loss?: number | null
  expected_return_pct?: number | null
  rationale: string[]
  timeframe: string
  generated_at: string
  trade_plan?: TradePlan | null
  backtest?: BacktestSummary | null
  intelligence?: IntelligenceSnapshot | null
}

export interface SignalsResponse {
  buy_signals: TradeSignal[]
  sell_signals: TradeSignal[]
  account_size?: number | null
  daily_profit_target?: number | null
  max_positions?: number | null
  risk_per_trade_pct?: number | null
  generated_at: string
}

export interface PortfolioHolding {
  symbol: string
  name?: string | null
  quantity: number
  avg_buy_price: number
  current_price?: number | null
  current_value?: number | null
  invested_value?: number | null
  unrealised_pnl?: number | null
  unrealised_pnl_pct?: number | null
  weight?: number | null
}

export interface PortfolioSummary {
  total_invested: number
  current_value: number
  total_pnl: number
  total_pnl_pct: number
  holdings_count: number
  holdings: PortfolioHolding[]
  last_updated: string
}

export interface GoalProgress {
  target: number
  actual: number
  progress_pct: number
}

export interface StrategyLearningState {
  weights: Record<string, number>
  learning_rate: number
  trades_evaluated: number
  last_updated: string
}

export interface PaperPosition {
  symbol: string
  side: string
  quantity: number
  entry_price: number
  current_price: number
  market_value: number
  invested_value: number
  target_price: number
  stop_loss: number
  opened_at: string
  last_marked_at: string
  days_held: number
  confidence: number
  strategy_score: number
  unrealised_pnl: number
  unrealised_pnl_pct: number
  rationale: string[]
}

export interface PaperTrade {
  symbol: string
  side: string
  quantity: number
  price: number
  executed_at: string
  reason: string
  pnl?: number | null
  pnl_pct?: number | null
  holding_days?: number | null
  confidence?: number | null
  strategy_score?: number | null
  market_regime?: string | null
}

export interface PaperPortfolioSnapshot {
  as_of_date: string
  cash_balance: number
  market_value: number
  total_equity: number
  realised_pnl: number
  unrealised_pnl: number
  total_return_pct: number
  daily_pnl: number
  weekly_pnl: number
  monthly_pnl: number
  open_positions: number
  closed_trades: number
  market_regime: string
}

export interface PaperPortfolioSummary {
  starting_cash: number
  cash_balance: number
  market_value: number
  total_equity: number
  realised_pnl: number
  unrealised_pnl: number
  total_return_pct: number
  open_positions: PaperPosition[]
  recent_trades: PaperTrade[]
  latest_snapshot?: PaperPortfolioSnapshot | null
  daily_goal: GoalProgress
  weekly_goal: GoalProgress
  monthly_goal: GoalProgress
  learning_state: StrategyLearningState
}

export interface PaperCycleResult {
  as_of_date: string
  market_regime: string
  buys_executed: PaperTrade[]
  sells_executed: PaperTrade[]
  skipped_symbols: string[]
  summary: PaperPortfolioSummary
}

export interface AutoTradingStatus {
  enabled: boolean
  is_running: boolean
  interval_minutes: number
  account_size: number
  daily_profit_target: number
  max_positions: number
  next_run_at?: string | null
  last_run_started_at?: string | null
  last_run_completed_at?: string | null
  last_cycle_date?: string | null
  last_run_outcome?: string | null
  last_error?: string | null
  total_runs: number
}

export interface MarketInsight {
  period: string
  summary: string
  top_gainers: StockSummary[]
  top_losers: StockSummary[]
  sector_performance: Record<string, number>
  key_observations: string[]
  recommended_actions: string[]
  generated_at: string
}
