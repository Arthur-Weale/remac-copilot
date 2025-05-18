import MetaTrader5 as mt5
import pandas as pd
import time
from datetime import datetime
import talib

# === CONFIGURATION ===
SYMBOL = "Volatility 25 Index"
TIMEFRAME_1M = mt5.TIMEFRAME_M1
TIMEFRAME_5M = mt5.TIMEFRAME_M5
LOT_SIZE = 0.5            # per position
MAX_POSITIONS = 10        # max concurrent positions
MAGIC = 100025
DEVIATION = 20
DONCHIAN_PERIOD = 20
EMA_PERIOD = 25
ATR_PERIOD = 14
ATR_MULTIPLIER = 1.0      # buffer multiplier
STOCH_K = 14
STOCH_D = 3

# === INITIALIZE MT5 ===
if not mt5.initialize() or not mt5.symbol_select(SYMBOL, True):
    raise RuntimeError("MT5 init or symbol selection failed")
sym_info = mt5.symbol_info(SYMBOL)
POINT = sym_info.point if sym_info else 0.0001

# === LOGGING ===
def log(msg):
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}")

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

def calc_donchian(df, period):
    up = df['high'].rolling(period).max()
    mid = (up + df['low'].rolling(period).min()) / 2
    low = df['low'].rolling(period).min()
    return up, mid, low

def calc_ema(df, period):
    return df['close'].ewm(span=period).mean()

def calc_atr(df, period):
    return talib.ATR(df['high'].values, df['low'].values, df['close'].values, period)

def calc_stoch(df):
    k, d = talib.STOCH(df['high'].values, df['low'].values, df['close'].values,
                       fastk_period=STOCH_K, slowk_period=STOCH_D, slowk_matype=0,
                       slowd_period=STOCH_D, slowd_matype=0)
    return pd.Series(k, index=df.index), pd.Series(d, index=df.index)

# === ENTRY PHASE LOGIC ===
def entry_phase(macd_hist, stoch_k, stoch_d, price, upper, lower):
    phase = 0
    # Donchian touch gives 1 point
    if price <= lower or price >= upper:
        phase += 1
    # MACD peak/trough
    if (macd_hist.iloc[-2] > 0 and macd_hist.iloc[-1] < macd_hist.iloc[-2]) or \
       (macd_hist.iloc[-2] < 0 and macd_hist.iloc[-1] > macd_hist.iloc[-2]):
        phase += 1
    # Stochastic crossover in extreme zones
    if stoch_k.iloc[-2] < stoch_d.iloc[-2] and stoch_k.iloc[-1] > stoch_d.iloc[-1]:
        # bullish crossover
        if stoch_k.iloc[-1] <= 30:
            phase += 1
        # bearish crossover
    elif stoch_k.iloc[-2] > stoch_d.iloc[-2] and stoch_k.iloc[-1] < stoch_d.iloc[-1]:
        if stoch_k.iloc[-1] >= 80:
            phase += 1
    return phase

# === STOP LOSS UTILS ===
def get_atr_sl(is_buy, entry_price, df):
    atr = calc_atr(df, ATR_PERIOD)[-1] * ATR_MULTIPLIER
    recent = df.iloc[-4:-1]
    if is_buy:
        base = recent['low'].min() if recent['low'].min() < entry_price else df['low'].iloc[-1]
        return base - atr
    else:
        base = recent['high'].max() if recent['high'].max() > entry_price else df['high'].iloc[-1]
        return base + atr

# === TRADE EXECUTION ===
def execute_phase_trade(is_buy, phase, df1):
    if phase == 0:
        return
    # determine how many positions
    count = {1: 3, 2: 5, 3: 10}.get(phase, 0)
    log(f"Phase {phase} signal: executing {count} positions.")
    tick = mt5.symbol_info_tick(SYMBOL)
    price = tick.ask if is_buy else tick.bid
    sl = get_atr_sl(is_buy, price, df1)
    for _ in range(count):
        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": SYMBOL,
            "volume": LOT_SIZE,
            "type": mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL,
            "price": price,
            "sl": sl,
            "deviation": DEVIATION,
            "magic": MAGIC,
            "comment": f"Entry phase{phase}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_FOK
        }
        r = mt5.order_send(req)
        if r and r.retcode == mt5.TRADE_RETCODE_DONE:
            log(f"Opened {'BUY' if is_buy else 'SELL'} #{r.order} @ {price:.5f} SL={sl:.5f}")
        else:
            log(f"Failed entry: {r}")

# === TRADE MANAGEMENT ===
def manage_trades(df1, upper, mid, lower):
    positions = mt5.positions_get(symbol=SYMBOL) or []
    if not positions:
        return
    tick = mt5.symbol_info_tick(SYMBOL)
    price = tick.ask
    # Close 75% on band touch
    if positions and price >= upper:
        to_close = int(round(len(positions) * 0.75))
        for p in positions[:to_close]: close_position(p)
    elif positions and price <= lower:
        to_close = int(round(len(positions) * 0.75))
        for p in positions[:to_close]: close_position(p)
    # Move SL to break-even on middle band
    if positions and lower < price < upper:
        for p in positions:
            new_sl = p.price_open if p.type == mt5.ORDER_TYPE_BUY else p.price_open
            modify_sl(p, new_sl)
    # Trailing SL for remaining positions
    for p in mt5.positions_get(symbol=SYMBOL) or []:
        new_sl = get_atr_sl(p.type == mt5.ORDER_TYPE_BUY, p.price_open, df1)
        modify_sl(p, new_sl)


def close_position(pos):
    close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
    price = mt5.symbol_info_tick(SYMBOL).bid if pos.type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(SYMBOL).ask
    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": pos.volume,
        "type": close_type,
        "position": pos.ticket,
        "price": price,
        "deviation": DEVIATION,
        "magic": MAGIC,
        "comment": "Auto close",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_FOK
    }
    r = mt5.order_send(req)
    if r and r.retcode == mt5.TRADE_RETCODE_DONE:
        log(f"Closed #{pos.ticket} @ {price}")
    else:
        log(f"Close failed: {r}")


def modify_sl(pos, new_sl):
    if new_sl == pos.sl:
        return
    req = {
        "action": mt5.TRADE_ACTION_SLTP,
        "position": pos.ticket,
        "sl": new_sl,
        "price": pos.price_open,
        "magic": MAGIC,
    }
    r = mt5.order_send(req)
    if r and r.retcode == mt5.TRADE_RETCODE_DONE:
        log(f"Modified SL for #{pos.ticket} to {new_sl:.5f}")
    else:
        log(f"SL modify failed: {r}")

# === MAIN LOOP ===
def run_bot():
    log("Bot started: phased entries, stochastic+MACD+Donchian.")
    while True:
        df1 = get_data(TIMEFRAME_1M)
        df5 = get_data(TIMEFRAME_5M)
        macd_hist = calc_macd_hist(df1)
        stoch_k, stoch_d = calc_stoch(df1)
        up1, mid1, low1 = calc_donchian(df1, DONCHIAN_PERIOD)
        price = df1['close'].iloc[-1]

        # Only new entries if no open positions
        if not mt5.positions_total():
            phase = entry_phase(macd_hist, stoch_k, stoch_d, price,
                                up1.iloc[-1], low1.iloc[-1])
            # determine buy or sell
            is_buy = phase > 0 and price <= low1.iloc[-1]
            is_sell = phase > 0 and price >= up1.iloc[-1]
            if phase and (is_buy or is_sell):
                execute_phase_trade(is_buy, phase, df1)
        # manage existing trades
        manage_trades(df1, up1.iloc[-1], mid1.iloc[-1], low1.iloc[-1])
        time.sleep(5)

if __name__ == "__main__":
    run_bot()
