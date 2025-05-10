import MetaTrader5 as mt5
import pandas as pd
import time
from datetime import datetime
import talib

# === CONFIGURATION ===
SYMBOL = "Volatility 25 Index"
TIMEFRAME_1M = mt5.TIMEFRAME_M1
TIMEFRAME_5M = mt5.TIMEFRAME_M5
LOT_SIZE = 0.5       # per trade
MAX_POSITIONS = 5
MAGIC = 100025
DEVIATION = 20
DONCHIAN_PERIOD = 20
EMA_PERIOD = 25
ATR_PERIOD = 14
ATR_MULTIPLIER = 1.0  # buffer multiplier

# === INIT MT5 ===
symbol_info = mt5.initialize() and mt5.symbol_select(SYMBOL, True)
if not symbol_info:
    raise RuntimeError("MT5 initialization or symbol selection failed")
symbol_info = mt5.symbol_info(SYMBOL)
POINT = symbol_info.point if symbol_info and symbol_info.point else 0.0001

# === LOGGING ===
def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

# === DATA FETCH ===
def get_data(tf, count=200):
    rates = mt5.copy_rates_from_pos(SYMBOL, tf, 0, count)
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df

# === INDICATORS ===
def calc_macd_hist(df):
    macd = df['close'].ewm(span=12).mean() - df['close'].ewm(span=26).mean()
    signal = macd.ewm(span=9).mean()
    return macd - signal

def get_velocity(hist):
    return hist.diff()

def is_negative_peak_velocity(vel, hist):
    return hist.iloc[-2] < 0 and vel.iloc[-2] < 0 and vel.iloc[-1] > 0

def calc_sar(df):
    return pd.Series(
        talib.SAR(df['high'].values, df['low'].values, acceleration=0.02, maximum=0.2),
        index=df.index
    )

def calc_donchian(df, period):
    upper = df['high'].rolling(period).max()
    lower = df['low'].rolling(period).min()
    middle = (upper + lower) / 2
    return upper, middle, lower

def calc_ema(df, period):
    return df['close'].ewm(span=period).mean()

def calc_atr(df, period):
    return talib.ATR(
        df['high'].values, df['low'].values, df['close'].values,
        period
    )

# === PEAK/TROUGH DETECTION ===
def is_valid_positive_peak(hist):
    if len(hist) < 6: return False
    b2, b1, b0 = hist.iloc[-3], hist.iloc[-2], hist.iloc[-1]
    return (
        (b2 < b1 < b0)
        and ((b0 - b1) < (b1 - b2))
        and (b0 > hist.iloc[-6:-1].mean() * 1.1)
    )

def is_valid_positive_trough(hist):
    if len(hist) < 6: return False
    b2, b1, b0 = hist.iloc[-3], hist.iloc[-2], hist.iloc[-1]
    return (
        (b2 > b1 > b0)
        and ((b1 - b0) < (b2 - b1))
        and (b0 < hist.iloc[-6:-1].mean() * 0.9)
    )

# === STOP LOSS ===
def get_stop_loss(is_buy, entry_price, df):
    # Compute ATR for buffer
    atr = calc_atr(df, ATR_PERIOD)[-1] * ATR_MULTIPLIER
    # Prior three wicks
    wick_lows = df['low'].iloc[-4:-1]
    wick_highs = df['high'].iloc[-4:-1]
    if is_buy:
        low_wick = wick_lows.min()
        if low_wick < entry_price:
            return low_wick - atr
        # fallback to entry-bar low
        entry_low = df['low'].iloc[-1]
        return entry_low - atr
    else:
        high_wick = wick_highs.max()
        if high_wick > entry_price:
            return high_wick + atr
        entry_high = df['high'].iloc[-1]
        return entry_high + atr

# === POSITION MANAGEMENT ===
def count_positions():
    pos = mt5.positions_get(symbol=SYMBOL, magic=MAGIC)
    return len(pos) if pos else 0

def close_trade(ticket, is_buy):
    ct = mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY
    price = mt5.symbol_info_tick(SYMBOL).bid if is_buy else mt5.symbol_info_tick(SYMBOL).ask
    vol = mt5.positions_get(ticket=ticket)[0].volume
    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": vol,
        "type": ct,
        "position": ticket,
        "price": price,
        "deviation": DEVIATION,
        "magic": MAGIC,
        "comment": "🚪 Auto close",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_FOK
    }
    log(f"🚪 Closing position #{ticket} at {price}")
    r = mt5.order_send(req)
    if r is None:
        log(f"❌ Close order returned None: {mt5.last_error()}")
    elif r.retcode == mt5.TRADE_RETCODE_DONE:
        log(f"✅ Closed position #{ticket}")
    else:
        log(f"❌ Failed to close position #{ticket}, retcode={r.retcode}")

# === OPEN TRADES ===
def open_trade(is_buy, sl=None):
    log(f"🛒 Attempting to open {'BUY' if is_buy else 'SELL'} trade. Positions={count_positions()}")
    if count_positions() >= MAX_POSITIONS:
        log(f"⚠️ Max positions reached ({MAX_POSITIONS}), skipping entry.")
        return
    entry_price = mt5.symbol_info_tick(SYMBOL).ask if is_buy else mt5.symbol_info_tick(SYMBOL).bid
    if sl is None:
        sl = get_stop_loss(is_buy, entry_price, df1)
    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": LOT_SIZE,
        "type": mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL,
        "price": entry_price,
        "sl": sl,
        "deviation": DEVIATION,
        "magic": MAGIC,
        "comment": "🛒 Entry",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_FOK
    }
    log(f"📝 Order Request: {req}")
    r = mt5.order_send(req)
    if r is None:
        log(f"❌ Entry order returned None: {mt5.last_error()}")
    elif r.retcode == mt5.TRADE_RETCODE_DONE:
        log(f"🟢 Opened {'BUY' if is_buy else 'SELL'} @ {entry_price:.5f} SL={sl:.5f}")
    else:
        log(f"❌ Failed to open trade, retcode={r.retcode}, comment={r.comment}")

# === MAIN LOOP ===
def run_bot():
    global df1
    log("🚀 Bot started with Donchian, MACD, SAR, EMA filters.")
    while True:
        df1 = get_data(TIMEFRAME_1M)
        hist1 = calc_macd_hist(df1)
        vel1 = get_velocity(hist1)
        sar1 = calc_sar(df1).iloc[-1]
        price1 = df1['close'].iloc[-1]
        ema1 = calc_ema(df1, EMA_PERIOD).iloc[-1]
        up1, mid1, low1 = calc_donchian(df1, DONCHIAN_PERIOD)
        upper1, middle1, lower1 = up1.iloc[-1], mid1.iloc[-1], low1.iloc[-1]

        df5 = get_data(TIMEFRAME_5M)
        hist5 = calc_macd_hist(df5)
        htf_bull = hist5.iloc[-1] > 0
        htf_bear = hist5.iloc[-1] < 0

        if is_valid_positive_peak(hist1) and price1 >= upper1:
            log("🔻 Signal: MACD peak + upper Donchian (sell setup)")
            open_trade(False)
        elif (is_valid_positive_trough(hist1) or is_negative_peak_velocity(vel1, hist1)) and price1 <= lower1:
            log("🔺 Signal: MACD trough/vel peak + lower Donchian (buy setup)")
            open_trade(True)
        else:
            log("⏳ No new entry signals.")

        for p in mt5.positions_get(symbol=SYMBOL) or []:
            is_buy = (p.type == mt5.ORDER_TYPE_BUY)
            if is_buy and price1 >= upper1:
                log(f"🔔 Buy #{p.ticket} hit upper band.")
                if not (htf_bear and price1 > ema1 and sar1 < price1):
                    close_trade(p.ticket, True)
                else:
                    log(f"🏄 Holding buy #{p.ticket} to ride uptrend.")
            elif not is_buy and price1 <= lower1:
                log(f"🔔 Sell #{p.ticket} hit lower band.")
                if not (htf_bear and price1 < ema1 and sar1 > price1):
                    close_trade(p.ticket, False)
                else:
                    log(f"🏄 Holding sell #{p.ticket} to ride downtrend.")

        time.sleep(5)

if __name__ == "__main__":
    run_bot()
