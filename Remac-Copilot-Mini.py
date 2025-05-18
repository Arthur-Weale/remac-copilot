import MetaTrader5 as mt5
import pandas as pd
import time
from datetime import datetime
import talib
import logging
from colorama import Fore, Style, init as colorama_init

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
LOG_INTERVAL = 5          # seconds between status summaries

# === INITIALIZE COLORS ===
colorama_init(autoreset=True)

# === SETUP LOGGER ===
logger = logging.getLogger("MT5Bot")
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
formatter = logging.Formatter(
    f"{Fore.CYAN}[%(asctime)s]{Style.RESET_ALL} %(levelname)s: {Fore.YELLOW}%(message)s{Style.RESET_ALL}",
    datefmt="%Y-%m-%d %H:%M:%S"
)
handler.setFormatter(formatter)
logger.handlers = [handler]

# === INITIALIZE MT5 ===
if not mt5.initialize() or not mt5.symbol_select(SYMBOL, True):
    logger.critical("MT5 init or symbol selection failed")
    raise RuntimeError("MT5 initialization failed")
sym_info = mt5.symbol_info(SYMBOL)
POINT = sym_info.point if sym_info else 0.0001

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
    upper = df['high'].rolling(period).max()
    lower = df['low'].rolling(period).min()
    middle = (upper + lower) / 2
    return upper, middle, lower


def calc_stoch(df):
    k, d = talib.STOCH(
        df['high'].values, df['low'].values, df['close'].values,
        fastk_period=STOCH_K, slowk_period=STOCH_D, slowk_matype=0,
        slowd_period=STOCH_D, slowd_matype=0
    )
    return pd.Series(k, index=df.index), pd.Series(d, index=df.index)

# === ENTRY PHASE LOGIC ===

def entry_phase(macd_hist, stoch_k, stoch_d, price, upper, lower):
    phase = 0
    if price <= lower or price >= upper:
        phase += 1
    if (macd_hist.iloc[-2] > 0 and macd_hist.iloc[-1] < macd_hist.iloc[-2]) or \
       (macd_hist.iloc[-2] < 0 and macd_hist.iloc[-1] > macd_hist.iloc[-2]):
        phase += 1
    if stoch_k.iloc[-2] < stoch_d.iloc[-2] and stoch_k.iloc[-1] > stoch_d.iloc[-1] and stoch_k.iloc[-1] <= 30:
        phase += 1
    if stoch_k.iloc[-2] > stoch_d.iloc[-2] and stoch_k.iloc[-1] < stoch_d.iloc[-1] and stoch_k.iloc[-1] >= 80:
        phase += 1
    return phase

# === STOP LOSS CALCULATION ===

def get_atr_sl(is_buy, entry_price, df):
    atr = talib.ATR(df['high'].values, df['low'].values, df['close'].values, ATR_PERIOD)[-1] * ATR_MULTIPLIER
    recent = df.iloc[-4:-1]
    if is_buy:
        base = recent['low'].min() if recent['low'].min() < entry_price else df['low'].iloc[-1]
        return base - atr
    base = recent['high'].max() if recent['high'].max() > entry_price else df['high'].iloc[-1]
    return base + atr

# === TRADE EXECUTION ===

def execute_phase_trade(is_buy, phase, df1):
    count = {1: 3, 2: 5, 3: 10}.get(phase, 0)
    if count == 0:
        return
    logger.info(f"Phase {phase} {'BUY' if is_buy else 'SELL'}: opening {count} positions.")
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
            logger.info(f"Opened {'BUY' if is_buy else 'SELL'} #{r.order} @ {price:.5f} SL={sl:.5f}")
        else:
            logger.error(f"Entry failed: {r}")

# === TRADE MANAGEMENT ===

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
        logger.info(f"Closed #{pos.ticket} @ {price:.5f}")
    else:
        logger.error(f"Close failed: {r}")


def modify_sl(pos, new_sl):
    if new_sl == pos.sl:
        return
    req = {
        "action": mt5.TRADE_ACTION_SLTP,
        "position": pos.ticket,
        "sl": new_sl,
        "magic": MAGIC
    }
    r = mt5.order_send(req)
    if r and r.retcode == mt5.TRADE_RETCODE_DONE:
        logger.info(f"Modified SL for #{pos.ticket} to {new_sl:.5f}")
    else:
        logger.error(f"SL modify failed: {r}")


def manage_trades(df1, upper, mid, lower):
    positions = mt5.positions_get(symbol=SYMBOL) or []
    if not positions:
        return
    tick = mt5.symbol_info_tick(SYMBOL)
    price = tick.ask

    if price >= upper or price <= lower:
        to_close = int(round(len(positions) * 0.75))
        logger.info(f"Band touch: closing {to_close} of {len(positions)} positions.")
        for pos in positions[:to_close]:
            close_position(pos)

    if lower < price < upper:
        logger.info("Middle band touched: moving SLs to break-even.")
        for pos in positions:
            modify_sl(pos, pos.price_open)

    positions = mt5.positions_get(symbol=SYMBOL) or []
    for pos in positions:
        new_sl = get_atr_sl(pos.type == mt5.ORDER_TYPE_BUY, pos.price_open, df1)
        modify_sl(pos, new_sl)

# === STATUS REPORT ===

def report_status(last_action, positions):
    status = (
        f"Last action: {last_action} | "
        f"Open positions: {len(positions)}/{MAX_POSITIONS} | "
        f"Time: {datetime.now():%H:%M:%S}"
    )
    logger.info(status)

# === MAIN LOOP ===

def run_bot():
    logger.info("Bot started: phased entries with debug logging.")
    last_report = time.time()
    last_action = "None"

    while True:
        df1 = get_data(TIMEFRAME_1M)
        macd_hist = calc_macd_hist(df1)
        stoch_k, stoch_d = calc_stoch(df1)
        up, mid, low = calc_donchian(df1, DONCHIAN_PERIOD)
        price = df1['close'].iloc[-1]

        # Debug: log phase evaluation
        phase = entry_phase(macd_hist, stoch_k, stoch_d, price, up.iloc[-1], low.iloc[-1])
        logger.debug(f"Phase calc -> phase={phase}, price={price:.5f}, lower={low.iloc[-1]:.5f}, upper={up.iloc[-1]:.5f}")

        if not mt5.positions_total():
            if phase > 0:
                is_buy = price <= low.iloc[-1]
                is_sell = price >= up.iloc[-1]
                if is_buy or is_sell:
                    execute_phase_trade(is_buy, phase, df1)
                    last_action = f"Entered phase {phase} {'BUY' if is_buy else 'SELL'}"
                else:
                    logger.debug("Phase criteria met but price not touching Donchian band for direction.")

        manage_trades(df1, up.iloc[-1], mid.iloc[-1], low.iloc[-1])
        if mt5.positions_total():
            last_action = last_action or "Managing trades"

        if time.time() - last_report >= LOG_INTERVAL:
            report_status(last_action, mt5.positions_get(symbol=SYMBOL) or [])
            last_report = time.time()

        time.sleep(1)

if __name__ == "__main__":
    run_bot()
