package com.stocktrading.ui.navigation

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.BarChart
import androidx.compose.material.icons.filled.Insights
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.PieChart
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.stocktrading.ui.screens.insights.InsightsScreen
import com.stocktrading.ui.screens.portfolio.PortfolioScreen
import com.stocktrading.ui.screens.screener.ScreenerScreen
import com.stocktrading.ui.screens.signals.SignalsScreen

sealed class Screen(val route: String, val label: String, val icon: ImageVector) {
    object Screener : Screen("screener", "Screener", Icons.Filled.BarChart)
    object Signals : Screen("signals", "Signals", Icons.Filled.Notifications)
    object Portfolio : Screen("portfolio", "Portfolio", Icons.Filled.PieChart)
    object Insights : Screen("insights", "Insights", Icons.Filled.Insights)
}

private val bottomNavItems = listOf(
    Screen.Screener,
    Screen.Signals,
    Screen.Portfolio,
    Screen.Insights,
)

@Composable
fun StockTradingNavHost() {
    val navController = rememberNavController()

    Scaffold(
        bottomBar = {
            NavigationBar {
                val navBackStackEntry by navController.currentBackStackEntryAsState()
                val currentDestination = navBackStackEntry?.destination

                bottomNavItems.forEach { screen ->
                    NavigationBarItem(
                        icon = { Icon(screen.icon, contentDescription = screen.label) },
                        label = { Text(screen.label) },
                        selected = currentDestination?.hierarchy?.any { it.route == screen.route } == true,
                        onClick = {
                            navController.navigate(screen.route) {
                                popUpTo(navController.graph.findStartDestination().id) {
                                    saveState = true
                                }
                                launchSingleTop = true
                                restoreState = true
                            }
                        },
                    )
                }
            }
        },
    ) { innerPadding ->
        NavHost(
            navController = navController,
            startDestination = Screen.Screener.route,
            contentPadding = innerPadding,
        ) {
            composable(Screen.Screener.route) { ScreenerScreen() }
            composable(Screen.Signals.route) { SignalsScreen() }
            composable(Screen.Portfolio.route) { PortfolioScreen() }
            composable(Screen.Insights.route) { InsightsScreen() }
        }
    }
}
