package com.stocktrading.data.repository

import com.stocktrading.data.api.RetrofitClient
import com.stocktrading.data.api.models.AddHoldingRequest
import com.stocktrading.data.api.models.PortfolioSummary

class PortfolioRepository {
    private val api = RetrofitClient.apiService

    suspend fun getPortfolio(): Result<PortfolioSummary> = runCatching {
        val response = api.getPortfolio()
        response.body() ?: error("Empty response body (code=${response.code()})")
    }

    suspend fun addHolding(symbol: String, quantity: Double, avgBuyPrice: Double): Result<String> =
        runCatching {
            val response = api.addHolding(AddHoldingRequest(symbol, quantity, avgBuyPrice))
            response.body()?.get("message") ?: "Success"
        }

    suspend fun removeHolding(symbol: String): Result<String> = runCatching {
        val response = api.removeHolding(symbol)
        response.body()?.get("message") ?: "Removed"
    }
}
