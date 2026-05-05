package com.stocktrading.ui.screens.signals

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowDownward
import androidx.compose.material.icons.filled.ArrowUpward
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.stocktrading.data.api.models.TradeSignal
import com.stocktrading.ui.theme.GainGreen
import com.stocktrading.ui.theme.LossRed
import com.stocktrading.ui.theme.NeutralGrey
import com.stocktrading.utils.Constants

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SignalsScreen(viewModel: SignalsViewModel = viewModel()) {
    val uiState by viewModel.uiState.collectAsState()
    val timeframe by viewModel.selectedTimeframe.collectAsState()

    Column(modifier = Modifier.fillMaxSize()) {
        TopAppBar(
            title = { Text("Trade Signals") },
            actions = {
                IconButton(onClick = { viewModel.loadSignals() }) {
                    Icon(Icons.Filled.Refresh, contentDescription = "Refresh")
                }
            },
        )

        // Timeframe tabs
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 4.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Constants.TIMEFRAMES.forEach { tf ->
                FilterChip(
                    selected = timeframe == tf,
                    onClick = { viewModel.selectTimeframe(tf) },
                    label = { Text(tf.replaceFirstChar { it.uppercase() }) },
                )
            }
        }

        when {
            uiState.isLoading -> {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        CircularProgressIndicator()
                        Spacer(Modifier.height(8.dp))
                        Text("Generating signals…")
                    }
                }
            }
            uiState.error != null -> {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.padding(24.dp)) {
                        Text("⚠ ${uiState.error}", color = LossRed)
                        Spacer(Modifier.height(12.dp))
                        Button(onClick = { viewModel.loadSignals() }) { Text("Retry") }
                    }
                }
            }
            else -> {
                LazyColumn(contentPadding = PaddingValues(bottom = 80.dp)) {
                    if (uiState.buySignals.isNotEmpty()) {
                        item {
                            SectionHeader(
                                title = "BUY Signals (${uiState.buySignals.size})",
                                color = GainGreen,
                            )
                        }
                        items(uiState.buySignals, key = { it.symbol + "BUY" }) {
                            SignalCard(signal = it)
                        }
                    }
                    if (uiState.sellSignals.isNotEmpty()) {
                        item {
                            SectionHeader(
                                title = "SELL Signals (${uiState.sellSignals.size})",
                                color = LossRed,
                            )
                        }
                        items(uiState.sellSignals, key = { it.symbol + "SELL" }) {
                            SignalCard(signal = it)
                        }
                    }
                    if (uiState.buySignals.isEmpty() && uiState.sellSignals.isEmpty()) {
                        item {
                            Box(
                                modifier = Modifier.fillParentMaxSize(),
                                contentAlignment = Alignment.Center,
                            ) {
                                Text(
                                    "No strong signals at this time.\nTry again later.",
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = NeutralGrey,
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun SectionHeader(title: String, color: androidx.compose.ui.graphics.Color) {
    Text(
        text = title,
        fontWeight = FontWeight.Bold,
        fontSize = 15.sp,
        color = color,
        modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
    )
}

@Composable
private fun SignalCard(signal: TradeSignal) {
    val isBuy = signal.signalType == "BUY"
    val accentColor = if (isBuy) GainGreen else LossRed

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
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Icon(
                        if (isBuy) Icons.Filled.ArrowUpward else Icons.Filled.ArrowDownward,
                        contentDescription = signal.signalType,
                        tint = accentColor,
                    )
                    Column {
                        Text(signal.symbol, fontWeight = FontWeight.Bold, fontSize = 16.sp)
                        signal.name?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = NeutralGrey) }
                    }
                }
                Column(horizontalAlignment = Alignment.End) {
                    AssistChip(
                        onClick = {},
                        label = { Text(signal.signalType, color = accentColor, fontWeight = FontWeight.Bold) },
                    )
                    Text(
                        "Confidence: ${"%.0f".format(signal.confidence * 100)}%",
                        style = MaterialTheme.typography.labelSmall,
                        color = NeutralGrey,
                    )
                }
            }

            Spacer(Modifier.height(8.dp))
            HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
            Spacer(Modifier.height(8.dp))

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                PriceLabel("Entry", signal.entryPrice)
                PriceLabel("Target", signal.targetPrice, GainGreen)
                PriceLabel("Stop Loss", signal.stopLoss, LossRed)
                signal.expectedReturnPct?.let {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text("Expected", style = MaterialTheme.typography.labelSmall, color = NeutralGrey)
                        Text(
                            "%+.1f%%".format(it),
                            fontWeight = FontWeight.Bold,
                            color = if (it >= 0) GainGreen else LossRed,
                        )
                    }
                }
            }

            if (signal.rationale.isNotEmpty()) {
                Spacer(Modifier.height(8.dp))
                Text("Why?", fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.labelMedium)
                signal.rationale.forEach { reason ->
                    Text("• $reason", style = MaterialTheme.typography.bodySmall, color = NeutralGrey)
                }
            }
        }
    }
}

@Composable
private fun PriceLabel(label: String, price: Double?, color: androidx.compose.ui.graphics.Color = androidx.compose.ui.graphics.Color.Unspecified) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(label, style = MaterialTheme.typography.labelSmall, color = NeutralGrey)
        Text(
            price?.let { "₹%.2f".format(it) } ?: "—",
            fontWeight = FontWeight.SemiBold,
            color = color,
        )
    }
}
