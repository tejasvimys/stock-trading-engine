package com.stocktrading.ui.screens.insights

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.stocktrading.data.api.models.MarketInsight
import com.stocktrading.data.repository.InsightRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class InsightsUiState(
    val isLoading: Boolean = false,
    val insight: MarketInsight? = null,
    val error: String? = null,
)

class InsightsViewModel : ViewModel() {

    private val repository = InsightRepository()

    private val _uiState = MutableStateFlow(InsightsUiState())
    val uiState: StateFlow<InsightsUiState> = _uiState.asStateFlow()

    private val _selectedPeriod = MutableStateFlow("daily")
    val selectedPeriod: StateFlow<String> = _selectedPeriod.asStateFlow()

    init {
        loadInsights()
    }

    fun selectPeriod(period: String) {
        _selectedPeriod.value = period
        loadInsights()
    }

    fun loadInsights() {
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isLoading = true, error = null)
            repository.getInsights(_selectedPeriod.value).fold(
                onSuccess = { insight ->
                    _uiState.value = InsightsUiState(isLoading = false, insight = insight)
                },
                onFailure = { err ->
                    _uiState.value = _uiState.value.copy(
                        isLoading = false,
                        error = err.message ?: "Failed to load insights",
                    )
                },
            )
        }
    }
}
