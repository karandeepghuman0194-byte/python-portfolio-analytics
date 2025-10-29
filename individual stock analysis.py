# %%
import pandas as pd
import numpy as np
import yfinance as yf
import matplotlib.pyplot as plt

# %%
stocks = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA']
data = yf.Tickers(stocks).history(period = '2y')['Close']
data.to_excel('technology_stock_prices.xlsx')
Indices = yf.Tickers(['^NDX']).history(period = '2y')['Close']
NDX = Indices.to_excel('NASDAQ_100_Index_Prices.xlsx')

# %%
Data = pd.read_excel('C:\\Users\\karandeepghuman\\OneDrive\\Desktop\\Python\\technology_stock_prices.xlsx')
print(Data.head())

# %%
AAPL = Data[['Date', 'AAPL']].copy()
MSFT = Data[['Date', 'MSFT']].copy()
GOOGL = Data[['Date', 'GOOGL']].copy()
AMZN = Data[['Date', 'AMZN']].copy()
TSLA = Data[['Date', 'TSLA']].copy()
print(AAPL.head())

# %%
NDX = pd.read_excel("C:\\Users\\karandeepghuman\\OneDrive\\Desktop\\Python\\Independent Project\\NASDAQ_100_Index_Prices.xlsx")
print(NDX.head())

# %%
AAPL['30_day_MA'] = AAPL['AAPL'].rolling(window=30).mean()
AAPL['%Change'] = AAPL['AAPL'].pct_change()
AAPL['30_day_Volatility'] = AAPL['%Change'].rolling(window=30).std()
AAPL['Compounded_Return'] = (1 + AAPL['%Change']).cumprod() - 1
MSFT['30_day_MA'] = MSFT['MSFT'].rolling(window=30).mean()
MSFT['%Change'] = MSFT['MSFT'].pct_change()
MSFT['30_day_Volatility'] = MSFT['%Change'].rolling(window=30).std()
MSFT['Compounded_Return'] = (1 + MSFT['%Change']).cumprod() - 1
GOOGL['30_day_MA'] = GOOGL['GOOGL'].rolling(window=30).mean()
GOOGL['%Change'] = GOOGL['GOOGL'].pct_change()
GOOGL['30_day_Volatility'] = GOOGL['%Change'].rolling(window=30).std()
GOOGL['Compounded_Return'] = (1 + GOOGL['%Change']).cumprod() - 1
AMZN['30_day_MA'] = AMZN['AMZN'].rolling(window=30).mean()
AMZN['%Change'] = AMZN['AMZN'].pct_change()
AMZN['30_day_Volatility'] = AMZN['%Change'].rolling(window=30).std()
AMZN['Compounded_Return'] = (1 + AMZN['%Change']).cumprod() - 1
TSLA['30_day_MA'] = TSLA['TSLA'].rolling(window=30).mean()
TSLA['%Change'] = TSLA['TSLA'].pct_change()
TSLA['30_day_Volatility'] = TSLA['%Change'].rolling(window=30).std()
TSLA['Compounded_Return'] = (1 + TSLA['%Change']).cumprod() - 1
NDX['30_day_MA'] = NDX['^NDX'].rolling(window=30).mean()
NDX['%Change'] = NDX['^NDX'].pct_change()
NDX['30_day_Volatility'] = NDX['%Change'].rolling(window=30).std()
NDX['Compounded_Return'] = (1 + NDX['%Change']).cumprod() - 1
print(AAPL.head())

# %%
returns = pd.DataFrame({'Date': AAPL['Date'], 'AAPL': AAPL['Compounded_Return'], 'MSFT': MSFT['Compounded_Return'], 'GOOGL': GOOGL['Compounded_Return'], 'AMZN': AMZN['Compounded_Return'], 'TSLA': TSLA['Compounded_Return'], 'index': NDX['Compounded_Return']})
returns.plot(x='Date', y=['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'index'], title='Compounded Returns of Technology Stocks vs NASDAQ-100 Index', figsize=(16,10))


# %%
volatility = pd.DataFrame({'Date': AAPL['Date'], 'AAPL': AAPL['30_day_Volatility'], 'MSFT': MSFT['30_day_Volatility'], 'GOOGL': GOOGL['30_day_Volatility'], 'AMZN': AMZN['30_day_Volatility'], 'TSLA': TSLA['30_day_Volatility'], 'index': NDX['30_day_Volatility']})
volatility.plot(x='Date', y=['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'index'], title='Volatility of Technology Stocks vs NASDAQ-100 Index', figsize=(16,10))

# %%
Risk_free_Rate = 0.04 # Assuming 4% annual risk-free rate
AAPL_Sharpe_Ratio = (AAPL['%Change'].mean() * 252 - Risk_free_Rate) / (AAPL['%Change'].std() * np.sqrt(252))
print(f"AAPL Sharpe Ratio: {AAPL_Sharpe_Ratio}")
MSFT_Sharpe_Ratio = (MSFT['%Change'].mean() * 252 - Risk_free_Rate) / (MSFT['%Change'].std() * np.sqrt(252))
print(f"MSFT Sharpe Ratio: {MSFT_Sharpe_Ratio}")
GOOGL_Sharpe_Ratio = (GOOGL['%Change'].mean() * 252 - Risk_free_Rate) / (GOOGL['%Change'].std() * np.sqrt(252))
print(f"GOOGL Sharpe Ratio: {GOOGL_Sharpe_Ratio}")
AMZN_Sharpe_Ratio = (AMZN['%Change'].mean() * 252 - Risk_free_Rate) / (AMZN['%Change'].std() * np.sqrt(252))
print(f"AMZN Sharpe Ratio: {AMZN_Sharpe_Ratio}")
TSLA_Sharpe_Ratio = (TSLA['%Change'].mean() * 252 - Risk_free_Rate) / (TSLA['%Change'].std() * np.sqrt(252))
print(f"TSLA Sharpe Ratio: {TSLA_Sharpe_Ratio}")
NDX_Sharpe_Ratio = (NDX['%Change'].mean() * 252 - Risk_free_Rate) / (NDX['%Change'].std() * np.sqrt(252))
print(f"NDX Sharpe Ratio: {NDX_Sharpe_Ratio}")


# %%
AAPL['Drawdown'] = (AAPL['AAPL'] - AAPL['AAPL'].cummax()) / AAPL['AAPL'].cummax()
MSFT['Drawdown'] = (MSFT['MSFT'] - MSFT['MSFT'].cummax()) / MSFT['MSFT'].cummax()
GOOGL['Drawdown'] = (GOOGL['GOOGL'] - GOOGL['GOOGL'].cummax()) / GOOGL['GOOGL'].cummax()
AMZN['Drawdown'] = (AMZN['AMZN'] - AMZN['AMZN'].cummax()) / AMZN['AMZN'].cummax()
TSLA['Drawdown'] = (TSLA['TSLA'] - TSLA['TSLA'].cummax()) / TSLA['TSLA'].cummax()
NDX['Drawdown'] = (NDX['^NDX'] - NDX['^NDX'].cummax()) / NDX['^NDX'].cummax()

Drawdown = pd.DataFrame({'Date': AAPL['Date'], 'AAPL': AAPL['Drawdown'], 'MSFT': MSFT['Drawdown'], 'GOOGL': GOOGL['Drawdown'], 'AMZN': AMZN['Drawdown'], 'TSLA': TSLA['Drawdown'], 'index': NDX['Drawdown']})
Drawdown.plot(x='Date', y=['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'index'], title='Drawdown of Technology Stocks vs NASDAQ-100 Index', figsize=(16,10))

# %%
print(f'Apple Maximum Drawdown: {AAPL["Drawdown"].min()}')
print(f'Microsoft Maximum Drawdown: {MSFT["Drawdown"].min()}')
print(f'Google Maximum Drawdown: {GOOGL["Drawdown"].min()}')
print(f'Amazon Maximum Drawdown: {AMZN["Drawdown"].min()}')
print(f'Tesla Maximum Drawdown: {TSLA["Drawdown"].min()}')
print(f'NASDAQ-100 Maximum Drawdown: {NDX["Drawdown"].min()}')

# %%
five_stock_portfolio = pd.DataFrame({'Date': AAPL['Date'],
    'Portfolio_Return': (0.2 * AAPL['%Change'] + 0.2 * MSFT['%Change'] + 0.2 * GOOGL['%Change'] + 0.2 * AMZN['%Change'] + 0.2 * TSLA['%Change']),
    'Portfolio_rolling_Volatility': (0.2 * AAPL['30_day_Volatility'] + 0.2 * MSFT['30_day_Volatility'] + 0.2 * GOOGL['30_day_Volatility'] + 0.2 * AMZN['30_day_Volatility'] + 0.2 * TSLA['30_day_Volatility']),
    'Portfolio_drawdown': (0.2 * AAPL['Drawdown'] + 0.2 * MSFT['Drawdown'] + 0.2 * GOOGL['Drawdown'] + 0.2 * AMZN['Drawdown'] + 0.2 * TSLA['Drawdown']),
    'Portfolio_compounded_Return': (1 + (0.2 * AAPL['%Change'] + 0.2 * MSFT['%Change'] + 0.2 * GOOGL['%Change'] + 0.2 * AMZN['%Change'] + 0.2 * TSLA['%Change'])).cumprod() - 1})

# %%
portfolio_sharpe_ratio = (five_stock_portfolio['Portfolio_Return'].mean() * 252 - Risk_free_Rate) / (five_stock_portfolio['Portfolio_Return'].std() * np.sqrt(252))
print(f'Index_Sharpe_Ratio: {NDX_Sharpe_Ratio}')
print(f'Portfolio_Sharpe_Ratio: {portfolio_sharpe_ratio}')
print(f'Index_Maximum_Drawdown: {NDX["Drawdown"].min()}')
print(f'Portfolio_Maximum_Drawdown: {five_stock_portfolio["Portfolio_drawdown"].min()}')

# %%
visualize_portfolio = pd.DataFrame({'Date': five_stock_portfolio['Date'],
    'Portfolio_Compounded_Return': five_stock_portfolio['Portfolio_compounded_Return'],
    'Index_Compounded_Return': NDX['Compounded_Return']})
visualize_portfolio.plot(x='Date', y=['Portfolio_Compounded_Return', 'Index_Compounded_Return'], title='Compounded Returns: Five Stock Portfolio vs NASDAQ-100 Index', figsize=(16,10))


