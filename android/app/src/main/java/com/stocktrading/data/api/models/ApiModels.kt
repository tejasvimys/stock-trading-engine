package com.stocktrading.data.api.models

import com.google.gson.annotations.SerializedName

// ---------------------------------------------------------------------------
// Stock / Screener
// ---------------------------------------------------------------------------

data class TechnicalIndicators(
    val rsi: Double?,
    val macd: Double?,
    @SerializedName("macd_signal") val macdSignal: Double?,
    @SerializedName("macd_hist") val macdHist: Double?,
    @SerializedName("bb_upper") val bbUpper: Double?,
    @SerializedName("bb_middle") val bbMiddle: Double?,
    @SerializedName("bb_lower") val bbLower: Double?,
    @SerializedName("sma_20") val sma20: Double?,
    @SerializedName("sma_50") val sma50: Double?,
    @SerializedName("ema_9") val ema9: Double?,
    @SerializedName("volume_avg") val volumeAvg: Double?,
)

data class StockSummary(
    val symbol: String,
    val name: String?,
    @SerializedName("current_price") val currentPrice: Double?,
    @SerializedName("change_pct") val changePct: Double?,
    val volume: Long?,
    @SerializedName("market_cap") val marketCap: Double?,
    val indicators: TechnicalIndicators?,
    @SerializedName("last_updated") val lastUpdated: String?,
)

data class ScreenerResponse(
    val total: Int,
    val stocks: List<StockSummary>,
)

// ---------------------------------------------------------------------------
// Signals
// ---------------------------------------------------------------------------

data class TradeSignal(
    val symbol: String,
    val name: String?,
    @SerializedName("signal_type") val signalType: String,
    val confidence: Double,
    @SerializedName("entry_price") val entryPrice: Double?,
    @SerializedName("target_price") val targetPrice: Double?,
    @SerializedName("stop_loss") val stopLoss: Double?,
    @SerializedName("expected_return_pct") val expectedReturnPct: Double?,
    val rationale: List<String>,
    val timeframe: String,
    @SerializedName("generated_at") val generatedAt: String,
)

data class SignalsResponse(
    @SerializedName("buy_signals") val buySignals: List<TradeSignal>,
    @SerializedName("sell_signals") val sellSignals: List<TradeSignal>,
    @SerializedName("generated_at") val generatedAt: String,
)

// ---------------------------------------------------------------------------
// Portfolio
// ---------------------------------------------------------------------------

data class PortfolioHolding(
    val symbol: String,
    val name: String?,
    val quantity: Double,
    @SerializedName("avg_buy_price") val avgBuyPrice: Double,
    @SerializedName("current_price") val currentPrice: Double?,
    @SerializedName("current_value") val currentValue: Double?,
    @SerializedName("invested_value") val investedValue: Double?,
    @SerializedName("unrealised_pnl") val unrealisedPnl: Double?,
    @SerializedName("unrealised_pnl_pct") val unrealisedPnlPct: Double?,
    val weight: Double?,
)

data class PortfolioSummary(
    @SerializedName("total_invested") val totalInvested: Double,
    @SerializedName("current_value") val currentValue: Double,
    @SerializedName("total_pnl") val totalPnl: Double,
    @SerializedName("total_pnl_pct") val totalPnlPct: Double,
    @SerializedName("holdings_count") val holdingsCount: Int,
    val holdings: List<PortfolioHolding>,
    @SerializedName("last_updated") val lastUpdated: String,
)

data class AddHoldingRequest(
    val symbol: String,
    val quantity: Double,
    @SerializedName("avg_buy_price") val avgBuyPrice: Double,
)

// ---------------------------------------------------------------------------
// Insights
// ---------------------------------------------------------------------------

data class MarketInsight(
    val period: String,
    val summary: String,
    @SerializedName("top_gainers") val topGainers: List<StockSummary>,
    @SerializedName("top_losers") val topLosers: List<StockSummary>,
    @SerializedName("sector_performance") val sectorPerformance: Map<String, Double>,
    @SerializedName("key_observations") val keyObservations: List<String>,
    @SerializedName("recommended_actions") val recommendedActions: List<String>,
    @SerializedName("generated_at") val generatedAt: String,
)
