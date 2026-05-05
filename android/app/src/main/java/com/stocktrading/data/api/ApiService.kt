package com.stocktrading.data.api

import com.stocktrading.data.api.models.*
import retrofit2.Response
import retrofit2.http.*

interface ApiService {

    // ----- Stocks / Screener -----
    @GET("stocks/screen")
    suspend fun screenStocks(
        @Query("rsi_min") rsiMin: Double? = null,
        @Query("rsi_max") rsiMax: Double? = null,
        @Query("macd_signal") macdSignal: String? = null,
        @Query("bb_position") bbPosition: String? = null,
        @Query("min_volume") minVolume: Int? = null,
        @Query("sort_by") sortBy: String = "symbol",
        @Query("sort_order") sortOrder: String = "asc",
        @Query("limit") limit: Int = 50,
    ): Response<ScreenerResponse>

    // ----- Signals -----
    @GET("signals")
    suspend fun getSignals(
        @Query("timeframe") timeframe: String = "weekly",
    ): Response<SignalsResponse>

    // ----- Portfolio -----
    @GET("portfolio")
    suspend fun getPortfolio(): Response<PortfolioSummary>

    @POST("portfolio/holdings")
    suspend fun addHolding(@Body request: AddHoldingRequest): Response<Map<String, String>>

    @DELETE("portfolio/holdings/{symbol}")
    suspend fun removeHolding(@Path("symbol") symbol: String): Response<Map<String, String>>

    // ----- Insights -----
    @GET("insights")
    suspend fun getInsights(
        @Query("period") period: String = "daily",
    ): Response<MarketInsight>

    // ----- Health -----
    @GET("health")
    suspend fun health(): Response<Map<String, String>>
}
