import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime
import talib

# === CONFIGURATION ===
SYMBOL = "Volatility 25 Index"
TIMEFRAME = mt5.TIMEFRAME_M1
DONCHIAN_PERIOD = 20
ADX_PERIOD = 14
OUTPUT_CSV = "adx_di_analysis.csv"
OUTPUT_TXT = "adx_di_analysis.txt"

# === INIT MT5 ===
if not mt5.initialize():
    raise RuntimeError("MT5 initialization failed")
if not mt5.symbol_select(SYMBOL, True):
    raise RuntimeError(f"Failed to select symbol {SYMBOL}")

# === FETCH DATA ===
bars = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, 10000)
df = pd.DataFrame(bars)
df['time'] = pd.to_datetime(df['time'], unit='s')

# === INDICATORS ===
df['donch_high'] = df['high'].rolling(DONCHIAN_PERIOD).max()
df['donch_low'] = df['low'].rolling(DONCHIAN_PERIOD).min()
high = df['high'].values
low = df['low'].values
close = df['close'].values

di_plus = talib.PLUS_DI(high, low, close, timeperiod=ADX_PERIOD)
di_minus = talib.MINUS_DI(high, low, close, timeperiod=ADX_PERIOD)
adx = talib.ADX(high, low, close, timeperiod=ADX_PERIOD)

df['DI+'] = di_plus
df['DI-'] = di_minus
df['ADX'] = adx

# === EVENT DETECTION ===
events = []
for i in range(DONCHIAN_PERIOD, len(df)):
    row = df.iloc[i]
    if row['close'] <= row['donch_low']:
        events.append({'time': row['time'], 'type': 'buy_touch', 'DI+': row['DI+'], 'DI-': row['DI-'], 'ADX': row['ADX']})
    elif row['close'] >= row['donch_high']:
        events.append({'time': row['time'], 'type': 'sell_touch', 'DI+': row['DI+'], 'DI-': row['DI-'], 'ADX': row['ADX']})

events_df = pd.DataFrame(events)

# === PAIRING FOR DURATION ===
# For each buy_touch, find next sell_touch; and vice versa
ride_stats = {'buy_touch': [], 'sell_touch': []}
for idx, ev in events_df.iterrows():
    t0 = ev['time']
    tp = events_df.iloc[idx+1:]
    # find opposite type
    if ev['type'] == 'buy_touch':
        nxt = tp[tp['type']=='sell_touch']
    else:
        nxt = tp[tp['type']=='buy_touch']
    if not nxt.empty:
        t1 = nxt.iloc[0]['time']
        ride_stats[ev['type']].append((t1 - t0).total_seconds()/60)

# === SUMMARY STATS ===
stats = {}
for evt_type in ['buy_touch', 'sell_touch']:
    sub = events_df[events_df['type'] == evt_type]
    total = len(sub)
    di_cond = sub[sub['DI+'] > sub['DI-']] if evt_type=='buy_touch' else sub[sub['DI-'] > sub['DI+']]
    strong = di_cond[di_cond['ADX'] >= 25]
    weak = di_cond[di_cond['ADX'] < 25]
    durations = ride_stats[evt_type]
    stats[evt_type] = {
        'total_touches': total,
        'strong_count': len(strong),
        'strong_pct': len(strong)/total*100 if total else np.nan,
        'weak_count': len(weak),
        'weak_pct': len(weak)/total*100 if total else np.nan,
        'avg_ride_min': np.mean(durations) if durations else np.nan,
        'max_ride_min': np.max(durations) if durations else np.nan
    }

# === OUTPUT ===
events_df.to_csv(OUTPUT_CSV, index=False)
with open(OUTPUT_TXT, 'w') as f:
    f.write(events_df.to_string(index=False))

# Print summary
for evt, v in stats.items():
    print(f"\nEvent: {evt}")
    print(f"  Total touches: {v['total_touches']}")
    print(f"  Strong (ADX>=25 & DI): {v['strong_count']} ({v['strong_pct']:.2f}%)")
    print(f"  Weak   (ADX<25 & DI):  {v['weak_count']} ({v['weak_pct']:.2f}%)")
    print(f"  Avg ride duration: {v['avg_ride_min']:.2f} min")
    print(f"  Max ride duration: {v['max_ride_min']:.2f} min")
