package com.stocktrading.data.repository

import com.stocktrading.data.api.RetrofitClient
import com.stocktrading.data.api.models.SignalsResponse

class SignalRepository {
    private val api = RetrofitClient.apiService

    suspend fun getSignals(timeframe: String = "weekly"): Result<SignalsResponse> = runCatching {
        val response = api.getSignals(timeframe)
        response.body() ?: error("Empty response body (code=${response.code()})")
    }
}
