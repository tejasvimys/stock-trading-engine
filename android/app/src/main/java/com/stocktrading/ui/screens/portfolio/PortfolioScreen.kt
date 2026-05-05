package com.stocktrading.ui.screens.portfolio

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Refresh
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
import com.stocktrading.data.api.models.PortfolioHolding
import com.stocktrading.ui.theme.GainGreen
import com.stocktrading.ui.theme.LossRed
import com.stocktrading.ui.theme.NeutralGrey

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PortfolioScreen(viewModel: PortfolioViewModel = viewModel()) {
    val uiState by viewModel.uiState.collectAsState()
    var showAddDialog by remember { mutableStateOf(false) }

    // Snackbar
    val snackbarHostState = remember { SnackbarHostState() }
    LaunchedEffect(uiState.actionMessage) {
        uiState.actionMessage?.let {
            snackbarHostState.showSnackbar(it)
            viewModel.clearMessage()
        }
    }
    LaunchedEffect(uiState.error) {
        uiState.error?.let {
            snackbarHostState.showSnackbar("Error: $it")
            viewModel.clearMessage()
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Portfolio") },
                actions = {
                    IconButton(onClick = { viewModel.loadPortfolio() }) {
                        Icon(Icons.Filled.Refresh, "Refresh")
                    }
                },
            )
        },
        floatingActionButton = {
            FloatingActionButton(onClick = { showAddDialog = true }) {
                Icon(Icons.Filled.Add, "Add holding")
            }
        },
        snackbarHost = { SnackbarHost(snackbarHostState) },
    ) { padding ->
        when {
            uiState.isLoading -> {
                Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator()
                }
            }
            uiState.portfolio == null -> {
                Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                    Text("No portfolio data available.", color = NeutralGrey)
                }
            }
            else -> {
                val portfolio = uiState.portfolio!!
                LazyColumn(
                    modifier = Modifier.fillMaxSize().padding(padding),
                    contentPadding = PaddingValues(bottom = 80.dp),
                ) {
                    item { PortfolioSummaryCard(portfolio) }
                    if (portfolio.holdings.isEmpty()) {
                        item {
                            Box(
                                modifier = Modifier.fillParentMaxWidth().padding(32.dp),
                                contentAlignment = Alignment.Center,
                            ) {
                                Text("No holdings yet.\nTap + to add your first stock.", color = NeutralGrey)
                            }
                        }
                    } else {
                        item {
                            Text(
                                "Holdings",
                                fontWeight = FontWeight.Bold,
                                modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
                            )
                        }
                        items(portfolio.holdings, key = { it.symbol }) { holding ->
                            HoldingCard(holding = holding, onRemove = { viewModel.removeHolding(it) })
                        }
                    }
                }
            }
        }
    }

    if (showAddDialog) {
        AddHoldingDialog(
            onDismiss = { showAddDialog = false },
            onAdd = { symbol, qty, price ->
                viewModel.addHolding(symbol, qty, price)
                showAddDialog = false
            },
        )
    }
}

@Composable
private fun PortfolioSummaryCard(portfolio: com.stocktrading.data.api.models.PortfolioSummary) {
    val pnlColor = if (portfolio.totalPnl >= 0) GainGreen else LossRed

    Card(
        modifier = Modifier
            .fillMaxWidth()
            .padding(12.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer),
        elevation = CardDefaults.cardElevation(4.dp),
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text("Portfolio Summary", fontWeight = FontWeight.Bold, fontSize = 18.sp)
            Spacer(Modifier.height(12.dp))
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                SummaryItem("Invested", "₹%.0f".format(portfolio.totalInvested))
                SummaryItem("Current Value", "₹%.0f".format(portfolio.currentValue))
                SummaryItem(
                    "P&L",
                    "%+.1f%%".format(portfolio.totalPnlPct),
                    pnlColor,
                )
            }
            Spacer(Modifier.height(4.dp))
            Text(
                "Total P&L: ₹%.0f".format(portfolio.totalPnl),
                color = pnlColor,
                fontWeight = FontWeight.SemiBold,
            )
        }
    }
}

@Composable
private fun SummaryItem(label: String, value: String, color: Color = Color.Unspecified) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(label, style = MaterialTheme.typography.labelSmall, color = NeutralGrey)
        Text(value, fontWeight = FontWeight.Bold, color = color)
    }
}

@Composable
private fun HoldingCard(holding: PortfolioHolding, onRemove: (String) -> Unit) {
    val pnlPct = holding.unrealisedPnlPct ?: 0.0
    val pnlColor = if (pnlPct >= 0) GainGreen else LossRed

    Card(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 4.dp),
        elevation = CardDefaults.cardElevation(2.dp),
    ) {
        Row(
            modifier = Modifier.padding(12.dp).fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(holding.symbol, fontWeight = FontWeight.Bold, fontSize = 15.sp)
                holding.name?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = NeutralGrey) }
                Text("Qty: ${holding.quantity} @ ₹%.2f".format(holding.avgBuyPrice), style = MaterialTheme.typography.labelSmall)
                holding.weight?.let {
                    Text("Weight: %.1f%%".format(it), style = MaterialTheme.typography.labelSmall, color = NeutralGrey)
                }
            }
            Column(horizontalAlignment = Alignment.End) {
                Text(holding.currentPrice?.let { "₹%.2f".format(it) } ?: "—", fontWeight = FontWeight.Bold)
                Text(
                    "%+.2f%%".format(pnlPct),
                    color = pnlColor,
                    fontWeight = FontWeight.SemiBold,
                )
                holding.unrealisedPnl?.let {
                    Text("₹%+.0f".format(it), color = pnlColor, style = MaterialTheme.typography.labelSmall)
                }
                IconButton(
                    onClick = { onRemove(holding.symbol) },
                    modifier = Modifier.size(32.dp),
                ) {
                    Icon(Icons.Filled.Delete, "Remove", tint = LossRed, modifier = Modifier.size(18.dp))
                }
            }
        }
    }
}

@Composable
private fun AddHoldingDialog(onDismiss: () -> Unit, onAdd: (String, String, String) -> Unit) {
    var symbol by remember { mutableStateOf("") }
    var quantity by remember { mutableStateOf("") }
    var price by remember { mutableStateOf("") }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Add Holding") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(
                    value = symbol,
                    onValueChange = { symbol = it.uppercase() },
                    label = { Text("Symbol (e.g. RELIANCE.NS)") },
                    singleLine = true,
                )
                OutlinedTextField(
                    value = quantity,
                    onValueChange = { quantity = it },
                    label = { Text("Quantity") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    singleLine = true,
                )
                OutlinedTextField(
                    value = price,
                    onValueChange = { price = it },
                    label = { Text("Avg Buy Price (₹)") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    singleLine = true,
                )
            }
        },
        confirmButton = {
            Button(
                onClick = { if (symbol.isNotBlank() && quantity.isNotBlank() && price.isNotBlank()) onAdd(symbol, quantity, price) },
            ) { Text("Add") }
        },
        dismissButton = {
            OutlinedButton(onClick = onDismiss) { Text("Cancel") }
        },
    )
}
