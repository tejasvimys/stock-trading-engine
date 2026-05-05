package com.stocktrading.ui.screens.screener

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.FilterList
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.TrendingDown
import androidx.compose.material.icons.filled.TrendingUp
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.stocktrading.data.api.models.StockSummary
import com.stocktrading.ui.theme.GainGreen
import com.stocktrading.ui.theme.LossRed
import com.stocktrading.ui.theme.NeutralGrey

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ScreenerScreen(viewModel: ScreenerViewModel = viewModel()) {
    val uiState by viewModel.uiState.collectAsState()
    val filters by viewModel.filters.collectAsState()
    var showFilters by remember { mutableStateOf(false) }

    Column(modifier = Modifier.fillMaxSize()) {
        TopAppBar(
            title = { Text("Stock Screener") },
            actions = {
                IconButton(onClick = { showFilters = !showFilters }) {
                    Icon(Icons.Filled.FilterList, contentDescription = "Filters")
                }
                IconButton(onClick = { viewModel.applyFilters() }) {
                    Icon(Icons.Filled.Refresh, contentDescription = "Refresh")
                }
            },
        )

        if (showFilters) {
            FilterPanel(
                filters = filters,
                onFiltersChanged = { viewModel.updateFilters { it } },
                onApply = { viewModel.applyFilters(); showFilters = false },
                onClear = { viewModel.clearFilters(); showFilters = false },
                viewModel = viewModel,
            )
        }

        when {
            uiState.isLoading -> {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        CircularProgressIndicator()
                        Spacer(modifier = Modifier.height(8.dp))
                        Text("Fetching market data…", style = MaterialTheme.typography.bodyMedium)
                    }
                }
            }
            uiState.error != null -> {
                ErrorView(message = uiState.error!!, onRetry = { viewModel.applyFilters() })
            }
            else -> {
                Text(
                    text = "${uiState.total} stocks found",
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.secondary,
                )
                LazyColumn(contentPadding = PaddingValues(bottom = 80.dp)) {
                    items(uiState.stocks, key = { it.symbol }) { stock ->
                        StockCard(stock = stock)
                    }
                }
            }
        }
    }
}

@Composable
private fun FilterPanel(
    filters: ScreenerFilters,
    onFiltersChanged: (ScreenerFilters.() -> ScreenerFilters) -> Unit,
    onApply: () -> Unit,
    onClear: () -> Unit,
    viewModel: ScreenerViewModel,
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .padding(12.dp),
        elevation = CardDefaults.cardElevation(4.dp),
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Text("Filters", fontWeight = FontWeight.Bold, fontSize = 16.sp)
            Spacer(modifier = Modifier.height(8.dp))

            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(
                    value = filters.rsiMin,
                    onValueChange = { viewModel.updateFilters { copy(rsiMin = it) } },
                    label = { Text("RSI Min") },
                    modifier = Modifier.weight(1f),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    singleLine = true,
                )
                OutlinedTextField(
                    value = filters.rsiMax,
                    onValueChange = { viewModel.updateFilters { copy(rsiMax = it) } },
                    label = { Text("RSI Max") },
                    modifier = Modifier.weight(1f),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    singleLine = true,
                )
            }

            Spacer(modifier = Modifier.height(8.dp))

            Text("MACD Signal", style = MaterialTheme.typography.labelMedium)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf(null to "Any", "bullish" to "Bullish", "bearish" to "Bearish").forEach { (value, label) ->
                    FilterChip(
                        selected = filters.macdSignal == value,
                        onClick = { viewModel.updateFilters { copy(macdSignal = value) } },
                        label = { Text(label) },
                    )
                }
            }

            Spacer(modifier = Modifier.height(8.dp))

            Text("Bollinger Band Position", style = MaterialTheme.typography.labelMedium)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf(null to "Any", "below_lower" to "Below Lower", "above_upper" to "Above Upper").forEach { (value, label) ->
                    FilterChip(
                        selected = filters.bbPosition == value,
                        onClick = { viewModel.updateFilters { copy(bbPosition = value) } },
                        label = { Text(label) },
                    )
                }
            }

            Spacer(modifier = Modifier.height(8.dp))

            OutlinedTextField(
                value = filters.minVolume,
                onValueChange = { viewModel.updateFilters { copy(minVolume = it) } },
                label = { Text("Min Volume") },
                modifier = Modifier.fillMaxWidth(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                singleLine = true,
            )

            Spacer(modifier = Modifier.height(12.dp))

            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = onClear, modifier = Modifier.weight(1f)) { Text("Clear") }
                Button(onClick = onApply, modifier = Modifier.weight(1f)) { Text("Apply Filters") }
            }
        }
    }
}

@Composable
private fun StockCard(stock: StockSummary) {
    val changePct = stock.changePct ?: 0.0
    val changeColor = when {
        changePct > 0 -> GainGreen
        changePct < 0 -> LossRed
        else -> NeutralGrey
    }

    Card(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 4.dp),
        elevation = CardDefaults.cardElevation(2.dp),
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column {
                    Text(stock.symbol, fontWeight = FontWeight.Bold, fontSize = 16.sp)
                    if (!stock.name.isNullOrBlank()) {
                        Text(stock.name, style = MaterialTheme.typography.bodySmall, color = NeutralGrey)
                    }
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text(
                        text = stock.currentPrice?.let { "₹%.2f".format(it) } ?: "—",
                        fontWeight = FontWeight.Bold,
                        fontSize = 16.sp,
                    )
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(
                            if (changePct >= 0) Icons.Filled.TrendingUp else Icons.Filled.TrendingDown,
                            contentDescription = null,
                            tint = changeColor,
                            modifier = Modifier.size(14.dp),
                        )
                        Text(
                            text = "%+.2f%%".format(changePct),
                            color = changeColor,
                            fontSize = 13.sp,
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(8.dp))

            val ind = stock.indicators
            if (ind != null) {
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    ind.rsi?.let { IndicatorBadge("RSI", "%.1f".format(it), rsiColor(it)) }
                    val macdDir = if ((ind.macd ?: 0.0) > (ind.macdSignal ?: 0.0)) "▲ Bullish" else "▼ Bearish"
                    val macdColor = if ((ind.macd ?: 0.0) > (ind.macdSignal ?: 0.0)) GainGreen else LossRed
                    IndicatorBadge("MACD", macdDir, macdColor)
                    val price = stock.currentPrice ?: 0.0
                    val bbLow = ind.bbLower ?: 0.0
                    val bbHigh = ind.bbUpper ?: Double.MAX_VALUE
                    val bbPos = when {
                        price <= bbLow -> "↓ Low"
                        price >= bbHigh -> "↑ High"
                        else -> "— Mid"
                    }
                    IndicatorBadge("BB", bbPos, NeutralGrey)
                }
            }
        }
    }
}

@Composable
private fun IndicatorBadge(label: String, value: String, color: Color) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(label, style = MaterialTheme.typography.labelSmall, color = NeutralGrey)
        Text(value, style = MaterialTheme.typography.labelMedium, color = color, fontWeight = FontWeight.SemiBold)
    }
}

private fun rsiColor(rsi: Double): Color = when {
    rsi < 30 -> GainGreen
    rsi > 70 -> LossRed
    else -> NeutralGrey
}

@Composable
private fun ErrorView(message: String, onRetry: () -> Unit) {
    Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.padding(24.dp)) {
            Text("⚠ Error", fontWeight = FontWeight.Bold)
            Spacer(modifier = Modifier.height(8.dp))
            Text(message, color = LossRed, style = MaterialTheme.typography.bodySmall)
            Spacer(modifier = Modifier.height(16.dp))
            Button(onClick = onRetry) { Text("Retry") }
        }
    }
}
