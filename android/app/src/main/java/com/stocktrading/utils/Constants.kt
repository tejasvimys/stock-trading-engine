package com.stocktrading.utils

object Constants {
    /**
     * Base URL is injected via BuildConfig so it can differ between debug (emulator)
     * and release (your hosted domain).
     *
     * Debug   -> http://10.0.2.2:8000/  (Android emulator loopback to host machine)
     * Release -> https://api.yourdomain.com/
     */
    const val API_CONNECT_TIMEOUT_SECONDS = 30L
    const val API_READ_TIMEOUT_SECONDS = 60L

    // Timeframe options for signals
    val TIMEFRAMES = listOf("weekly", "monthly")

    // Insight period options
    val INSIGHT_PERIODS = listOf("daily", "weekly")

    // Profit target label shown in UI
    const val PROFIT_TARGET_LABEL = "≥10% target"
}
