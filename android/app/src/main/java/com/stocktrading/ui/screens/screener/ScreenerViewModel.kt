package com.stocktrading.ui.screens.screener

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.stocktrading.data.api.models.StockSummary
import com.stocktrading.data.repository.StockRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class ScreenerUiState(
    val isLoading: Boolean = false,
    val stocks: List<StockSummary> = emptyList(),
    val error: String? = null,
    val total: Int = 0,
)

data class ScreenerFilters(
    val rsiMin: String = "",
    val rsiMax: String = "",
    val macdSignal: String? = null,   // null | "bullish" | "bearish"
    val bbPosition: String? = null,   // null | "below_lower" | "above_upper" | "middle"
    val minVolume: String = "",
    val sortBy: String = "symbol",
    val sortOrder: String = "asc",
)

class ScreenerViewModel : ViewModel() {

    private val repository = StockRepository()

    private val _uiState = MutableStateFlow(ScreenerUiState())
    val uiState: StateFlow<ScreenerUiState> = _uiState.asStateFlow()

    private val _filters = MutableStateFlow(ScreenerFilters())
    val filters: StateFlow<ScreenerFilters> = _filters.asStateFlow()

    init {
        applyFilters()
    }

    fun updateFilters(update: ScreenerFilters.() -> ScreenerFilters) {
        _filters.value = _filters.value.update()
    }

    fun applyFilters() {
        val f = _filters.value
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isLoading = true, error = null)
            val result = repository.screenStocks(
                rsiMin = f.rsiMin.toDoubleOrNull(),
                rsiMax = f.rsiMax.toDoubleOrNull(),
                macdSignal = f.macdSignal,
                bbPosition = f.bbPosition,
                minVolume = f.minVolume.toIntOrNull(),
                sortBy = f.sortBy,
                sortOrder = f.sortOrder,
            )
            result.fold(
                onSuccess = { resp ->
                    _uiState.value = ScreenerUiState(
                        isLoading = false,
                        stocks = resp.stocks,
                        total = resp.total,
                    )
                },
                onFailure = { err ->
                    _uiState.value = _uiState.value.copy(
                        isLoading = false,
                        error = err.message ?: "Unknown error",
                    )
                },
            )
        }
    }

    fun clearFilters() {
        _filters.value = ScreenerFilters()
        applyFilters()
    }
}
