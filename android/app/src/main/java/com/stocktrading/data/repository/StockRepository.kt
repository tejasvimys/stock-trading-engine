package com.stocktrading.data.repository

import com.stocktrading.data.api.RetrofitClient
import com.stocktrading.data.api.models.ScreenerResponse

class StockRepository {
    private val api = RetrofitClient.apiService

    suspend fun screenStocks(
        rsiMin: Double? = null,
        rsiMax: Double? = null,
        macdSignal: String? = null,
        bbPosition: String? = null,
        minVolume: Int? = null,
        sortBy: String = "symbol",
        sortOrder: String = "asc",
        limit: Int = 50,
    ): Result<ScreenerResponse> = runCatching {
        val response = api.screenStocks(
            rsiMin = rsiMin,
            rsiMax = rsiMax,
            macdSignal = macdSignal,
            bbPosition = bbPosition,
            minVolume = minVolume,
            sortBy = sortBy,
            sortOrder = sortOrder,
            limit = limit,
        )
        response.body() ?: error("Empty response body (code=${response.code()})")
    }
}
