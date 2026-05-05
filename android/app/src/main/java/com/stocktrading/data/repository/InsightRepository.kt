package com.stocktrading.data.repository

import com.stocktrading.data.api.RetrofitClient
import com.stocktrading.data.api.models.MarketInsight

class InsightRepository {
    private val api = RetrofitClient.apiService

    suspend fun getInsights(period: String = "daily"): Result<MarketInsight> = runCatching {
        val response = api.getInsights(period)
        response.body() ?: error("Empty response body (code=${response.code()})")
    }
}
