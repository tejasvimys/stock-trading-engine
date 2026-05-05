package com.stocktrading.ui.screens.portfolio

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.stocktrading.data.api.models.PortfolioSummary
import com.stocktrading.data.repository.PortfolioRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class PortfolioUiState(
    val isLoading: Boolean = false,
    val portfolio: PortfolioSummary? = null,
    val error: String? = null,
    val actionMessage: String? = null,
)

class PortfolioViewModel : ViewModel() {

    private val repository = PortfolioRepository()

    private val _uiState = MutableStateFlow(PortfolioUiState())
    val uiState: StateFlow<PortfolioUiState> = _uiState.asStateFlow()

    init {
        loadPortfolio()
    }

    fun loadPortfolio() {
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isLoading = true, error = null)
            repository.getPortfolio().fold(
                onSuccess = { p ->
                    _uiState.value = PortfolioUiState(isLoading = false, portfolio = p)
                },
                onFailure = { err ->
                    _uiState.value = _uiState.value.copy(
                        isLoading = false,
                        error = err.message ?: "Failed to load portfolio",
                    )
                },
            )
        }
    }

    fun addHolding(symbol: String, qty: String, price: String) {
        val quantity = qty.toDoubleOrNull() ?: return
        val avgPrice = price.toDoubleOrNull() ?: return
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isLoading = true)
            repository.addHolding(symbol.uppercase().trim(), quantity, avgPrice).fold(
                onSuccess = { msg ->
                    _uiState.value = _uiState.value.copy(actionMessage = msg)
                    loadPortfolio()
                },
                onFailure = { err ->
                    _uiState.value = _uiState.value.copy(
                        isLoading = false,
                        error = err.message,
                    )
                },
            )
        }
    }

    fun removeHolding(symbol: String) {
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isLoading = true)
            repository.removeHolding(symbol).fold(
                onSuccess = { msg ->
                    _uiState.value = _uiState.value.copy(actionMessage = msg)
                    loadPortfolio()
                },
                onFailure = { err ->
                    _uiState.value = _uiState.value.copy(isLoading = false, error = err.message)
                },
            )
        }
    }

    fun clearMessage() {
        _uiState.value = _uiState.value.copy(actionMessage = null, error = null)
    }
}
