import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import talib
from datetime import datetime

# === CONFIG ===
SYMBOL         = "Volatility 25 Index"
TIMEFRAME      = mt5.TIMEFRAME_M1
DONCHIAN_N     = 20
STO_K_PERIOD   = 14
STO_D_PERIOD   = 3
STO_SMOOTH     = 3
FVG_LOOKAHEAD  = 20  # bars within which gap must be respected

# === INIT MT5 ===
if not mt5.initialize():
    raise RuntimeError("MT5 init failed")
if not mt5.symbol_select(SYMBOL, True):
    raise RuntimeError("Symbol select failed")

# === FETCH ALL DATA ===
# Try to pull as much history as MT5 will allow in one go:
start_time = datetime(2000,1,1)
bars = mt5.copy_rates_from(SYMBOL, TIMEFRAME, start_time, 100000)
if bars is None or len(bars)==0:
    raise RuntimeError("No history returned—ensure Market History is enabled")
df = pd.DataFrame(bars)
df['time'] = pd.to_datetime(df['time'], unit='s')
df.set_index('time', inplace=True)

# === INDICATORS ===
df['donch_high'] = df['high'].rolling(DONCHIAN_N).max()
df['donch_low']  = df['low'].rolling(DONCHIAN_N).min()
k, d = talib.STOCH(df['high'], df['low'], df['close'],
                   fastk_period=STO_K_PERIOD,
                   slowk_period=STO_SMOOTH, slowk_matype=0,
                   slowd_period=STO_D_PERIOD, slowd_matype=0)
df['STO_K'], df['STO_D'] = k, d

# === STAT CONTAINER ===
stats = {
    'upper_touch':0, 'upper_success':0,
    'lower_touch':0, 'lower_success':0,
    'sto80_x':0,     'sto80_s':0,
    'sto20_x':0,     'sto20_s':0,
    'combo80_x':0,   'combo80_s':0,
    'combo20_x':0,   'combo20_s':0,
    'fvg_bull':0,    'fvg_bull_res':0,
    'fvg_bear':0,    'fvg_bear_res':0
}

# === BACKTEST LOOP ===
# start at bar  max(DONCHIAN_N,2)  and leave room for lookahead
start = max(DONCHIAN_N, 2)
end   = len(df) - FVG_LOOKAHEAD - 1

for i in range(start, end):
    close, nxt = df['close'].iat[i], df['close'].iat[i+1]
    up, lowb    = df['donch_high'].iat[i], df['donch_low'].iat[i]
    k0, d0      = df['STO_K'].iat[i], df['STO_D'].iat[i]
    k1, d1      = df['STO_K'].iat[i-1], df['STO_D'].iat[i-1]

    # 1) Donchian touches
    if close >= up:
        stats['upper_touch'] += 1
        if nxt < close: stats['upper_success'] += 1
    if close <= lowb:
        stats['lower_touch'] += 1
        if nxt > close: stats['lower_success'] += 1

    # 2) Stoch crossovers
    if k1 > d1 and k0 < d0 and k0 >= 80:
        stats['sto80_x'] += 1
        if nxt < close: stats['sto80_s'] += 1
    if k1 < d1 and k0 > d0 and k0 <= 20:
        stats['sto20_x'] += 1
        if nxt > close: stats['sto20_s'] += 1

    # 3) Combined
    if close >= up and k1 > d1 and k0 < d0 and k0 >= 80:
        stats['combo80_x'] += 1
        if nxt < close: stats['combo80_s'] += 1
    if close <= lowb and k1 < d1 and k0 > d0 and k0 <= 20:
        stats['combo20_x'] += 1
        if nxt > close: stats['combo20_s'] += 1

    # 4) Fair Value Gaps
    # Bullish FVG at i-1
    if df['low'].iat[i-1] > df['high'].iat[i-3]:
        stats['fvg_bull'] += 1
        low_gap  = df['high'].iat[i-3]
        high_gap = df['low'].iat[i-1]
        for j in range(1, FVG_LOOKAHEAD+1):
            bar = df.iloc[i-1+j]
            if bar['low'] <= high_gap and bar['high'] >= low_gap:
                stats['fvg_bull_res'] += 1
                break

    # Bearish FVG at i-1
    if df['high'].iat[i-1] < df['low'].iat[i-3]:
        stats['fvg_bear'] += 1
        high_gap = df['low'].iat[i-3]
        low_gap  = df['high'].iat[i-1]
        for j in range(1, FVG_LOOKAHEAD+1):
            bar = df.iloc[i-1+j]
            if bar['high'] >= low_gap and bar['low'] <= high_gap:
                stats['fvg_bear_res'] += 1
                break

# === PRINT RESULTS ===
def fmt(x,y): return f"{x}/{y} ({100*x/y:.2f}%)" if y>0 else "0/0 (N/A)"

print("\n=== Donchian Touch ===")
print(" Shorts@Upper:", fmt(stats['upper_success'], stats['upper_touch']))
print("  Longs@Lower:", fmt(stats['lower_success'], stats['lower_touch']))

print("\n=== Stochastic Only ===")
print(" STO80 Sells:", fmt(stats['sto80_s'], stats['sto80_x']))
print(" STO20 Buys: ", fmt(stats['sto20_s'], stats['sto20_x']))

print("\n=== Combo Band+Stoch ===")
print(" B+S80 Sells:", fmt(stats['combo80_s'], stats['combo80_x']))
print(" B+S20 Buys: ", fmt(stats['combo20_s'], stats['combo20_x']))

print("\n=== Fair Value Gaps ===")
print(" Bull FVGs found:     ", stats['fvg_bull'])
print(" Bull FVGs respected: ", fmt(stats['fvg_bull_res'], stats['fvg_bull']))
print(" Bear FVGs found:     ", stats['fvg_bear'])
print(" Bear FVGs respected: ", fmt(stats['fvg_bear_res'], stats['fvg_bear']))

mt5.shutdown()
