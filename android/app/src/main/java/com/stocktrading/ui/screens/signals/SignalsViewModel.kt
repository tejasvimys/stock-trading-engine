package com.stocktrading.ui.screens.signals

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.stocktrading.data.api.models.SignalsResponse
import com.stocktrading.data.api.models.TradeSignal
import com.stocktrading.data.repository.SignalRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class SignalsUiState(
    val isLoading: Boolean = false,
    val buySignals: List<TradeSignal> = emptyList(),
    val sellSignals: List<TradeSignal> = emptyList(),
    val generatedAt: String = "",
    val error: String? = null,
)

class SignalsViewModel : ViewModel() {

    private val repository = SignalRepository()

    private val _uiState = MutableStateFlow(SignalsUiState())
    val uiState: StateFlow<SignalsUiState> = _uiState.asStateFlow()

    private val _selectedTimeframe = MutableStateFlow("weekly")
    val selectedTimeframe: StateFlow<String> = _selectedTimeframe.asStateFlow()

    init {
        loadSignals()
    }

    fun selectTimeframe(tf: String) {
        _selectedTimeframe.value = tf
        loadSignals()
    }

    fun loadSignals() {
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isLoading = true, error = null)
            repository.getSignals(_selectedTimeframe.value).fold(
                onSuccess = { resp ->
                    _uiState.value = SignalsUiState(
                        isLoading = false,
                        buySignals = resp.buySignals,
                        sellSignals = resp.sellSignals,
                        generatedAt = resp.generatedAt,
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
}
