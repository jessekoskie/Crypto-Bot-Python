import time
from binance.client import Client
import pandas as pd
import logging
import threading

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Binance API keys (replace with your actual API keys)
API_KEY = 'fnGInvArAH6MgE018Ewjz6y8uUvlXJ1vNfGrWY4HKZWdx61mfeA7ZpBRu1sdgYRM'
API_SECRET = 'CUNMaiCFv9NKskbiUsiOHZj5BGQoR9bZNLO5mmwjFkwccQoRXsj6o9QZcWa4YnVz'

# Initialize Binance client
client = Client(API_KEY, API_SECRET)

# Function to fetch the PEPE balance
def get_pepe_balance():
    try:
        balance_info = client.get_asset_balance(asset='PEPE')
        return float(balance_info['free']) if balance_info else 0.0
    except Exception as e:
        logging.error(f"Error fetching PEPE balance: {e}")
        return 0.0

# Function to fetch candlestick data with rate limit handling
def fetch_data(symbol, interval, limit=100):
    while True:
        try:
            candlesticks = client.get_klines(symbol=symbol, interval=interval, limit=limit)
            df = pd.DataFrame(candlesticks, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time',
                                                     'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume',
                                                     'taker_buy_quote_asset_volume', 'ignore'])
            df['close'] = pd.to_numeric(df['close'])
            return df
        except Exception as e:
            logging.error(f"Error fetching data: {e}")
            if "Too many requests" in str(e):
                logging.warning("Rate limit exceeded. Sleeping for 30 seconds.")
                time.sleep(30)
            else:
                break

# Calculate Exponential Moving Averages (EMAs) and RSI
def calculate_indicators(df, short_ema=2, long_ema=5):
    df['EMA_short'] = df['close'].ewm(span=short_ema).mean()
    df['EMA_long'] = df['close'].ewm(span=long_ema).mean()

    # RSI Calculation with protection against division by zero
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=5).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=5).mean()
    rs = gain / (loss + 1e-10)  # Add small value to avoid division by zero
    df['RSI'] = 100 - (100 / (1 + rs))

    # Buy/sell signals based on EMA and RSI (faster signals)
    df['buy_signal'] = (df['EMA_short'] > df['EMA_long']) & (df['RSI'] < 55)  # Relaxed RSI condition
    df['sell_signal'] = (df['EMA_short'] < df['EMA_long']) & (df['RSI'] > 45)  # Relaxed RSI condition

    return df

# Function to fetch trading rules and get minimum trade size
def get_trade_filters(symbol):
    try:
        exchange_info = client.get_symbol_info(symbol)
        min_qty = 0.0
        step_size = 0.0
        min_notional = 0.0

        for filter in exchange_info['filters']:
            if filter['filterType'] == 'LOT_SIZE':
                min_qty = float(filter['minQty'])
                step_size = float(filter['stepSize'])
            elif filter['filterType'] == 'MIN_NOTIONAL':
                min_notional = float(filter['minNotional'])

        return min_qty, step_size, min_notional
    except Exception as e:
        logging.error(f"Error fetching trade filters for {symbol}: {e}")
        return 0.0, 0.0, 0.0

# Retry mechanism for fetching real-time price
def fetch_real_time_price(symbol):
    while True:
        try:
            ticker = client.get_symbol_ticker(symbol=symbol)
            return float(ticker['price'])  # Returns the latest price
        except Exception as e:
            logging.error(f"Error fetching real-time price for {symbol}: {e}")
            time.sleep(5)  # Retry in 5 seconds

# Function to get USDT balance
def get_usdt_balance():
    try:
        balance_info = client.get_asset_balance(asset='USDT')
        return float(balance_info['free']) if balance_info else 0.0
    except Exception as e:
        logging.error(f"Error fetching USDT balance: {e}")
        return 0.0

# Function to place orders with retry mechanism and precision handling
def place_order(symbol, side, quantity):
    min_qty, step_size, min_notional = get_trade_filters(symbol)
    price = fetch_real_time_price(symbol)

    if price is None:
        logging.error("Failed to fetch price, cannot place order.")
        return

    # Ensure the notional value of the trade exceeds the minimum notional
    notional_value = quantity * price
    if notional_value < min_notional:
        logging.error(f"Order notional value {notional_value:.2f} is below the minimum of {min_notional:.2f}.")
        return

    # Ensure quantity respects the minimum trade size
    if quantity < min_qty:
        logging.error(f"Order quantity {quantity} is below the minimum trade size of {min_qty}.")
        return

    # Adjust quantity to nearest step size
    quantity = (quantity // step_size) * step_size
    quantity = round(quantity, 6)  # Adjust precision to 6 decimal places

    try:
        order = client.create_order(
            symbol=symbol,
            side=side,
            type=Client.ORDER_TYPE_MARKET,
            quantity=quantity  # Use rounded quantity
        )
        logging.info(f"{side} order placed: {order}")
    except Exception as e:
        logging.error(f"Error placing order: {e}")
        if "Too many requests" in str(e):
            logging.warning("Rate limit exceeded while placing order. Sleeping for 30 seconds.")
            time.sleep(30)  # Retry after waiting
            place_order(symbol, side, quantity)

# Aggressive bot loop
def aggressive_bot_loop(risk_percentage=0.35):  # Increased risk percentage
    symbol = 'PEPEUSDT'

    def trade_logic():
        try:
            while True:
                # Fetch real-time price
                real_time_price = fetch_real_time_price(symbol)
                if real_time_price is not None:
                    logging.info(f"Real-time price of {symbol}: {real_time_price}")

                    # Fetch candlestick data and calculate indicators
                    df = fetch_data(symbol, Client.KLINE_INTERVAL_1MINUTE)
                    if df is not None and not df.empty:
                        df = calculate_indicators(df)

                        # Get USDT and PEPE balances
                        usdt_balance = get_usdt_balance()
                        pepe_balance = get_pepe_balance()

                        # Calculate PEPE quantity to buy based on higher risk percentage of USDT balance
                        pepe_quantity_to_buy = (usdt_balance * risk_percentage) / real_time_price

                        # Log current balances and trading quantity
                        logging.info(f"Current USDT balance: {usdt_balance:.2f} USDT")
                        logging.info(f"Current PEPE balance: {pepe_balance:.2f} PEPE")
                        logging.info(f"Calculated PEPE quantity to buy: {pepe_quantity_to_buy:.2f} PEPE")

                        # Check for buy signals (USDT available, no PEPE)
                        if df.iloc[-1]['buy_signal']:
                            if usdt_balance >= 0.5:  # Lowered USDT threshold
                                logging.info(f"Buy signal detected at {df.iloc[-1]['timestamp']}")
                                place_order(symbol, 'BUY', pepe_quantity_to_buy)
                            else:
                                logging.warning(f"Not enough USDT to place buy order. Current USDT balance: {usdt_balance:.2f}")

                        # Check for sell signals (PEPE available)
                        elif df.iloc[-1]['sell_signal']:
                            if pepe_balance >= 0.05:  # Lowered PEPE threshold
                                logging.info(f"Sell signal detected at {df.iloc[-1]['timestamp']}")
                                place_order(symbol, 'SELL', pepe_balance)
                            else:
                                logging.warning(f"Not enough PEPE to place sell order. Current PEPE balance: {pepe_balance:.2f}")

                        else:
                            logging.info("No buy or sell signal detected.")

                # Sleep for reduced frequency: check every 5 seconds
                time.sleep(5)

        except KeyboardInterrupt:
            logging.info("Bot stopped by user.")
        except Exception as e:
            logging.error(f"An error occurred: {e}")

    # Start aggressive trading logic
    trade_thread = threading.Thread(target=trade_logic)
    trade_thread.start()

# Start aggressive bot
aggressive_bot_loop()
