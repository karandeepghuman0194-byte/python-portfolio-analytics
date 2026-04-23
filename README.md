# 📊 Python Financial Analysis Portfolio

A collection of Python scripts implementing core quantitative finance concepts — from risk modelling and portfolio optimization to trading strategy backtesting.

---

## Projects

### 1. Monte Carlo Value at Risk (VaR)
**File:** `monte_carlo_var.py`

Estimates the potential loss of a multi-asset portfolio over a 5-day horizon using Monte Carlo simulation.

- Downloads 15 years of historical price data for SPY, GLD, BND, QQQ, and VTI via `yfinance`
- Computes log returns, portfolio expected return, and covariance-based standard deviation
- Runs 10,000 simulations using random z-scores drawn from a standard normal distribution
- Calculates Value at Risk (VaR) at the 99% confidence level
- Plots the distribution of simulated scenario returns with a VaR threshold line

---

### 2. Cumulative Returns Visualisation
**File:** `cumulative_returns.py`

Compares the cumulative log returns of MSFT, SPY, and QQQ over a 5-year period.

- Downloads multi-ticker OHLCV data and extracts adjusted close prices
- Computes log returns and cumulates them over time
- Plots cumulative return curves for each asset on a single chart

---

### 3. Sharpe Ratio Portfolio Optimisation
**File:** `portfolio_optimisation.py`

Finds the optimal asset allocation across 5 ETFs by maximising the Sharpe ratio using `scipy.optimize`.

- Pulls 5 years of price data for SPY, BND, GLD, QQQ, and VTI
- Annualises log returns and the covariance matrix (×252 trading days)
- Fetches the current 10-year Treasury rate from FRED as the risk-free rate
- Uses SLSQP optimisation with weight bounds (0–50% per asset) and a full-investment constraint
- Outputs optimal weights, expected annual return, volatility, and Sharpe ratio
- Visualises the optimal weights as a bar chart

---

### 4. Moving Average Crossover Strategy Backtest
**File:** `ma_crossover_backtest.py`

Backtests a classic 50-day vs. 200-day moving average crossover strategy on SPY and compares it to a buy-and-hold baseline.

- Computes log returns and both moving averages
- Generates long/flat signals: invested when 50 MA > 200 MA, flat otherwise
- Tracks cumulative returns for both the strategy and buy-and-hold starting from $1,000
- Calculates and compares annualised Sharpe ratios and maximum drawdown for each approach

---

## Setup

```bash
pip install yfinance pandas numpy scipy matplotlib fredapi
```

> The FRED API key in `portfolio_optimisation.py` is included for convenience but can be replaced with your own from [fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html).

---

## Libraries Used

| Library | Purpose |
|---|---|
| `yfinance` | Historical market data download |
| `pandas` / `numpy` | Data manipulation and numerical computing |
| `matplotlib` | Visualisation |
| `scipy` | Optimisation (SLSQP) and statistics (normal distribution) |
| `fredapi` | Fetching macroeconomic data (risk-free rate) |

---

## Concepts Covered

- Log returns and covariance matrices
- Monte Carlo simulation for VaR
- Mean-variance portfolio theory
- Sharpe ratio optimisation
- Moving average crossover signals
- Backtesting with Sharpe ratio and maximum drawdown metrics
