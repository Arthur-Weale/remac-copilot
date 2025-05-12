import MetaTrader5 as mt5
import pandas as pd
import time
from datetime import datetime
import talib

# === CONFIGURATION ===
SYMBOL = "Volatility 25 Index"
TIMEFRAME_1M = mt5.TIMEFRAME_M1
TIMEFRAME_5M = mt5.TIMEFRAME_M5
LOT_SIZE = 0.5
MAX_POSITIONS = 5
MAGIC = 100025
DEVIATION = 20
DONCHIAN_PERIOD = 20
EMA_PERIOD = 25

# === INIT MT5 ===
if not mt5.initialize() or not mt5.symbol_select(SYMBOL, True):
    raise RuntimeError("MT5 initialization failed")
symbol_info = mt5.symbol_info(SYMBOL)
POINT = symbol_info.point if symbol_info else 0.0001

# === ENHANCED LOGGING ===
def log(msg, emoji="⏳", category="INFO"):
    colors = {
        "INFO": "\033[94m",    # Blue
        "TRADE": "\033[92m",   # Green
        "WARNING": "\033[93m", # Yellow
        "ERROR": "\033[91m"    # Red
    }
    reset = "\033[0m"
    print(f"{colors.get(category, '')}{emoji} [{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] {msg}{reset}")

# === STOP LOSS CALCULATION ===
def get_stop_loss(is_buy, entry_price, df):
    # Original wick-based logic without ATR
    wick_lows = df['low'].iloc[-4:-1]
    wick_highs = df['high'].iloc[-4:-1]
    
    if is_buy:
        low_wick = wick_lows.min()
        return low_wick if low_wick < entry_price else df['low'].iloc[-1]
    else:
        high_wick = wick_highs.max()
        return high_wick if high_wick > entry_price else df['high'].iloc[-1]

# === DATA & INDICATORS ===
def get_data(tf, count=200):
    rates = mt5.copy_rates_from_pos(SYMBOL, tf, 0, count)
    return pd.DataFrame(rates).assign(
        time=lambda x: pd.to_datetime(x['time'], unit='s')
    )

def calc_indicators(df):
    df = df.copy()
    # MACD Calculation
    df['macd'] = df['close'].ewm(span=12, adjust=False).mean() - df['close'].ewm(span=26, adjust=False).mean()
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']
    
    # Donchian Channel
    df['donchian_upper'] = df['high'].rolling(DONCHIAN_PERIOD).max()
    df['donchian_lower'] = df['low'].rolling(DONCHIAN_PERIOD).min()
    
    # EMA
    df['ema'] = df['close'].ewm(span=EMA_PERIOD, adjust=False).mean()
    
    return df

# === POSITION MANAGEMENT ===
def get_positions():
    return mt5.positions_get(symbol=SYMBOL, magic=MAGIC) or []

def count_positions():
    return len(get_positions())

def close_position(position):
    tick = mt5.symbol_info_tick(SYMBOL)
    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": position.volume,
        "type": mt5.ORDER_TYPE_SELL if position.type == 0 else mt5.ORDER_TYPE_BUY,
        "position": position.ticket,
        "price": tick.ask if position.type == 0 else tick.bid,
        "deviation": DEVIATION,
        "magic": MAGIC,
        "comment": "Band Touch Close",
    }
    
    result = mt5.order_send(req)
    if result.retcode == mt5.TRADE_RETCODE_DONE:
        log(f"Closed #{position.ticket} ({position.volume} lots)", "🎯", "TRADE")
    else:
        log(f"Close failed for #{position.ticket} (Error: {result.retcode})", "❌", "ERROR")

# === TRADE EXECUTION ===
def execute_trade(is_buy):
    if count_positions() >= MAX_POSITIONS:
        log("Max positions reached", "🚧", "WARNING")
        return
    
    price = mt5.symbol_info_tick(SYMBOL).ask if is_buy else mt5.symbol_info_tick(SYMBOL).bid
    df = get_data(TIMEFRAME_1M)
    sl = get_stop_loss(is_buy, price, df)
    
    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": LOT_SIZE,
        "type": mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL,
        "price": price,
        "sl": sl,
        "deviation": DEVIATION,
        "magic": MAGIC,
        "comment": "Initial Entry",
    }
    
    result = mt5.order_send(req)
    if result.retcode == mt5.TRADE_RETCODE_DONE:
        log(f"Opened {'BUY' if is_buy else 'SELL'} @ {price:.5f} SL: {sl:.5f}", "✅", "TRADE")
    else:
        log(f"Open failed (Error: {result.retcode})", "❌", "ERROR")

# === MAIN LOGIC ===
def run_bot():
    log("Bot Activated - Live Monitoring", "⚡", "TRADE")
    
    while True:
        start_time = time.time()
        
        # Get fresh data
        df1m = calc_indicators(get_data(TIMEFRAME_1M))
        price = df1m['close'].iloc[-1]
        upper_band = df1m['donchian_upper'].iloc[-1]
        lower_band = df1m['donchian_lower'].iloc[-1]
        macd_hist = df1m['macd_hist'].iloc[-1]

        # Log current status
        log(f"Price: {price:.5f} | Upper: {upper_band:.5f} | Lower: {lower_band:.5f} | MACD Hist: {macd_hist:.5f}", "📊")
        
        # Entry conditions
        if price >= upper_band and macd_hist < 0:
            log("Upper Band + MACD Bearish", "🔻", "TRADE")
            execute_trade(False)
        elif price <= lower_band and macd_hist > 0:
            log("Lower Band + MACD Bullish", "🔺", "TRADE")
            execute_trade(True)
        else:
            log("Waiting for valid entry signal...", "👀")

        # Close positions on opposite band touch
        for position in get_positions():
            is_buy = position.type == mt5.ORDER_TYPE_BUY
            if (is_buy and price >= upper_band) or (not is_buy and price <= lower_band):
                log(f"Band Hit - Closing #{position.ticket}", "🚪", "TRADE")
                close_position(position)

        # Maintain 1-second cycle
        cycle_time = time.time() - start_time
        if cycle_time < 1:
            time.sleep(1 - cycle_time)
        else:
            log(f"Cycle overrun: {cycle_time:.2f}s", "⏱️", "WARNING")

if __name__ == "__main__":
    run_bot()