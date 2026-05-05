package com.stocktrading

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.stocktrading.ui.navigation.StockTradingNavHost
import com.stocktrading.ui.theme.StockTradingTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            StockTradingTheme {
                StockTradingNavHost()
            }
        }
    }
}
