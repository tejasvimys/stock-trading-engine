package com.stocktrading.ui.screens.insights

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.TrendingDown
import androidx.compose.material.icons.filled.TrendingUp
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.stocktrading.data.api.models.MarketInsight
import com.stocktrading.data.api.models.StockSummary
import com.stocktrading.ui.theme.GainGreen
import com.stocktrading.ui.theme.LossRed
import com.stocktrading.ui.theme.NeutralGrey
import com.stocktrading.utils.Constants

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun InsightsScreen(viewModel: InsightsViewModel = viewModel()) {
    val uiState by viewModel.uiState.collectAsState()
    val period by viewModel.selectedPeriod.collectAsState()

    Column(modifier = Modifier.fillMaxSize()) {
        TopAppBar(
            title = { Text("Market Insights") },
            actions = {
                IconButton(onClick = { viewModel.loadInsights() }) {
                    Icon(Icons.Filled.Refresh, "Refresh")
                }
            },
        )

        // Period selector
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 4.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Constants.INSIGHT_PERIODS.forEach { p ->
                FilterChip(
                    selected = period == p,
                    onClick = { viewModel.selectPeriod(p) },
                    label = { Text(p.replaceFirstChar { it.uppercase() }) },
                )
            }
        }

        when {
            uiState.isLoading -> {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        CircularProgressIndicator()
                        Spacer(Modifier.height(8.dp))
                        Text("Analysing markets…")
                    }
                }
            }
            uiState.error != null -> {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.padding(24.dp)) {
                        Text("⚠ ${uiState.error}", color = LossRed)
                        Spacer(Modifier.height(12.dp))
                        Button(onClick = { viewModel.loadInsights() }) { Text("Retry") }
                    }
                }
            }
            uiState.insight != null -> {
                InsightsContent(insight = uiState.insight!!)
            }
        }
    }
}

@Composable
private fun InsightsContent(insight: MarketInsight) {
    LazyColumn(contentPadding = PaddingValues(bottom = 80.dp)) {
        // Summary card
        item {
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(12.dp),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer),
                elevation = CardDefaults.cardElevation(4.dp),
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        "${insight.period.replaceFirstChar { it.uppercase() }} Summary",
                        fontWeight = FontWeight.Bold,
                        fontSize = 18.sp,
                    )
                    Spacer(Modifier.height(8.dp))
                    Text(insight.summary, style = MaterialTheme.typography.bodyMedium)
                }
            }
        }

        // Sector performance
        if (insight.sectorPerformance.isNotEmpty()) {
            item {
                SectionTitle("Sector Performance")
                SectorPerformanceTable(insight.sectorPerformance)
            }
        }

        // Top gainers
        if (insight.topGainers.isNotEmpty()) {
            item { SectionTitle("Top Gainers") }
            items(insight.topGainers) { stock ->
                MiniStockRow(stock = stock, isGainer = true)
            }
        }

        // Top losers
        if (insight.topLosers.isNotEmpty()) {
            item { SectionTitle("Top Losers") }
            items(insight.topLosers) { stock ->
                MiniStockRow(stock = stock, isGainer = false)
            }
        }

        // Key observations
        if (insight.keyObservations.isNotEmpty()) {
            item {
                SectionTitle("Key Observations")
                Column(modifier = Modifier.padding(horizontal = 16.dp)) {
                    insight.keyObservations.forEach { obs ->
                        Row(
                            modifier = Modifier.padding(vertical = 3.dp),
                            verticalAlignment = Alignment.Top,
                        ) {
                            Icon(
                                Icons.Filled.Info,
                                contentDescription = null,
                                tint = MaterialTheme.colorScheme.primary,
                                modifier = Modifier.size(16.dp).padding(top = 2.dp),
                            )
                            Spacer(Modifier.width(6.dp))
                            Text(obs, style = MaterialTheme.typography.bodySmall)
                        }
                    }
                }
            }
        }

        // Recommended actions
        if (insight.recommendedActions.isNotEmpty()) {
            item {
                SectionTitle("Recommended Actions")
                Column(modifier = Modifier.padding(horizontal = 16.dp)) {
                    insight.recommendedActions.forEach { action ->
                        Row(
                            modifier = Modifier.padding(vertical = 3.dp),
                            verticalAlignment = Alignment.Top,
                        ) {
                            Icon(
                                Icons.Filled.CheckCircle,
                                contentDescription = null,
                                tint = GainGreen,
                                modifier = Modifier.size(16.dp).padding(top = 2.dp),
                            )
                            Spacer(Modifier.width(6.dp))
                            Text(action, style = MaterialTheme.typography.bodySmall)
                        }
                    }
                }
                Spacer(Modifier.height(8.dp))
            }
        }
    }
}

@Composable
private fun SectionTitle(title: String) {
    Text(
        text = title,
        fontWeight = FontWeight.Bold,
        fontSize = 15.sp,
        modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
    )
}

@Composable
private fun MiniStockRow(stock: StockSummary, isGainer: Boolean) {
    val color = if (isGainer) GainGreen else LossRed
    val icon = if (isGainer) Icons.Filled.TrendingUp else Icons.Filled.TrendingDown

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 3.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Icon(icon, contentDescription = null, tint = color, modifier = Modifier.size(16.dp))
            Column {
                Text(stock.symbol, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
                stock.name?.let { Text(it, style = MaterialTheme.typography.labelSmall, color = NeutralGrey) }
            }
        }
        Text(
            text = stock.changePct?.let { "%+.2f%%".format(it) } ?: "—",
            color = color,
            fontWeight = FontWeight.Bold,
        )
    }
}

@Composable
private fun SectorPerformanceTable(sectors: Map<String, Double>) {
    Column(modifier = Modifier.padding(horizontal = 16.dp)) {
        sectors.entries.sortedByDescending { it.value }.forEach { (sector, perf) ->
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 3.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(sector, style = MaterialTheme.typography.bodySmall)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    val color = if (perf >= 0) GainGreen else LossRed
                    val barFraction = (kotlin.math.abs(perf) / 5f).coerceIn(0.05f, 1f)
                    Box(
                        modifier = Modifier
                            .height(8.dp)
                            .width((80 * barFraction).dp)
                            .background(color, shape = MaterialTheme.shapes.small),
                    )
                    Spacer(Modifier.width(8.dp))
                    Text("%+.2f%%".format(perf), color = color, fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
                }
            }
        }
    }
}
