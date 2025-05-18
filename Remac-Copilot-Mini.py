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
ATR_PERIOD = 14
ATR_MULTIPLIER = 1.0      # buffer multiplier for trailing
STOCH_K = 14
STOCH_D = 3
LOG_INTERVAL = 5          # seconds between status summaries

# === TRAILING STATE ===
floor_sl = {}             # locked SL floors by ticket
tailing_active = set()    # tickets with activated trailing

# === INITIALIZE COLORS & LOGGER ===
colorama_init(autoreset=True)
logger = logging.getLogger("MT5Bot")
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter(
    f"{Fore.CYAN}[%(asctime)s]{Style.RESET_ALL} %(levelname)s: {Fore.YELLOW}%(message)s{Style.RESET_ALL}",
    datefmt="%Y-%m-%d %H:%M:%S"
))
logger.handlers = [handler]

# === INITIALIZE MT5 ===
if not mt5.initialize() or not mt5.symbol_select(SYMBOL, True):
    logger.critical("MT5 init or symbol selection failed")
    raise RuntimeError("MT5 initialization failed")
sym_info = mt5.symbol_info(SYMBOL)
POINT = sym_info.point if sym_info else 0.0001
MIN_SL = getattr(sym_info, 'trade_tick_size', POINT)

# === HELPERS ===
def send_with_sl_retry(req, is_buy, price):
    """
    Attempts order_send. If retcode 10016 (invalid SL), increments SL by 10*POINT until success.
    """
    # initial SL from req
    sl = req.get('sl', price)
    while True:
        r = mt5.order_send(req)
        if r and r.retcode == mt5.TRADE_RETCODE_DONE:
            return r
        # check for invalid SL error code 10016
        rc = getattr(r, 'retcode', None)
        if rc == 10016:
            # increment SL by 10 points
            increment = POINT * 10
            sl = sl - increment if is_buy else sl + increment
            req['sl'] = sl
            logger.warning(f"Invalid SL (10016). Adjusting SL to {sl:.5f} and retrying...")
            continue
        # other failures
        logger.error(f"Order failed (retcode={rc}). No further retry.")
        return r

# Alias for backwards compat
send_with_sl_fallback = send_with_sl_retry

# === DATA & INDICATORS ===
def get_data(tf, count=200):
    df = pd.DataFrame(mt5.copy_rates_from_pos(SYMBOL, tf, 0, count))
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df

def calc_macd_hist(df):
    macd = df['close'].ewm(span=12).mean() - df['close'].ewm(span=26).mean()
    return macd - macd.ewm(span=9).mean()

def calc_donchian(df, p):
    up = df['high'].rolling(p).max(); lo = df['low'].rolling(p).min()
    mid = (up + lo)/2
    return up, mid, lo

def calc_stoch(df):
    k,d = talib.STOCH(df['high'], df['low'], df['close'],
                     fastk_period=STOCH_K, slowk_period=STOCH_D, slowk_matype=0,
                     slowd_period=STOCH_D, slowd_matype=0)
    return pd.Series(k,index=df.index), pd.Series(d,index=df.index)

def get_atr_sl(is_buy, entry_price, df):
    atr = talib.ATR(df['high'], df['low'], df['close'], ATR_PERIOD).iloc[-1]*ATR_MULTIPLIER
    base = df['low'][-4:-1].min() if is_buy else df['high'][-4:-1].max()
    sl = (base - atr) if is_buy else (base + atr)
    return sl

def entry_phase(macd, k, d, price, up, lo):
    phase=0
    if price<=lo or price>=up: phase+=1
    if (macd.iloc[-2]>0 and macd.iloc[-1]<macd.iloc[-2]) or \
       (macd.iloc[-2]<0 and macd.iloc[-1]>macd.iloc[-2]): phase+=1
    if k.iloc[-2]<d.iloc[-2]<k.iloc[-1] and k.iloc[-1]<=30: phase+=1
    if k.iloc[-2]>d.iloc[-2]>k.iloc[-1] and k.iloc[-1]>=80: phase+=1
    return phase

# === EXECUTION ===
def execute_phase_trade(is_buy, phase, df1):
    cnt={1:3,2:5,3:10}.get(phase,0)
    if not cnt: return
    logger.info(f"Phase{phase} {'BUY' if is_buy else 'SELL'}: opening {cnt} positions")
    tick=mt5.symbol_info_tick(SYMBOL)
    price=tick.ask if is_buy else tick.bid
    for _ in range(cnt):
        req={
            "action":mt5.TRADE_ACTION_DEAL,
            "symbol":SYMBOL,
            "volume":LOT_SIZE,
            "type":mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL,
            "price":price,
            "sl":price,
            "deviation":DEVIATION,
            "magic":MAGIC,
            "comment":f"Entry phase{phase}",
            "type_time":mt5.ORDER_TIME_GTC,
            "type_filling":mt5.ORDER_FILLING_FOK
        }
        r=send_with_sl_retry(req,is_buy,price)
        if r and r.retcode==mt5.TRADE_RETCODE_DONE:
            floor_sl[r.order]=price
            logger.info(f"Opened #{r.order} @ {price:.5f} floorSL={price:.5f}")

# === MANAGEMENT ===
def close_position(pos):
    ct=mt5.ORDER_TYPE_SELL if pos.type==mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
    price=mt5.symbol_info_tick(SYMBOL).bid if pos.type==mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(SYMBOL).ask
    req={
        "action":mt5.TRADE_ACTION_DEAL,
        "symbol":SYMBOL,
        "volume":pos.volume,
        "type":ct,
        "position":pos.ticket,
        "price":price,
        "deviation":DEVIATION,
        "magic":MAGIC,
        "comment":"Auto close",
        "type_time":mt5.ORDER_TIME_GTC,
        "type_filling":mt5.ORDER_FILLING_FOK
    }
    r=mt5.order_send(req)
    if r and r.retcode==mt5.TRADE_RETCODE_DONE:
        floor_sl.pop(pos.ticket,None); tailing_active.discard(pos.ticket)
        logger.info(f"Closed #{pos.ticket} @ {price:.5f}")


def modify_sl(pos,new_sl):
    if new_sl==pos.sl: return
    req={"action":mt5.TRADE_ACTION_SLTP,"position":pos.ticket,"sl":new_sl,"magic":MAGIC}
    r=send_with_sl_retry(req,pos.type==mt5.ORDER_TYPE_BUY,new_sl)
    if r and r.retcode==mt5.TRADE_RETCODE_DONE:
        logger.info(f"SL modified for #{pos.ticket} to {new_sl:.5f}")

# closes 75%, leaves ~25% (floor-trailing) on upper/lower band
# that remaining continues TSL
def manage_trades(df1,up,mid,lo):
    pos=mt5.positions_get(symbol=SYMBOL) or []
    if not pos: return
    price=mt5.symbol_info_tick(SYMBOL).ask
    if price>=up or price<=lo:
        to_close=round(len(pos)*0.75)
        logger.info(f"Closing {to_close}/{len(pos)} on band touch")
        for p in pos[:to_close]: close_position(p)
        return
    if lo<price<up and abs(price-mid)<=POINT/2:
        for p in pos:
            if p.ticket not in tailing_active:
                floor=floor_sl.get(p.ticket,p.price_open)
                sl=floor+ (POINT if p.type==mt5.ORDER_TYPE_BUY else -POINT)
                modify_sl(p,sl); floor_sl[p.ticket]=sl; tailing_active.add(p.ticket)
                logger.info(f"Floor set #{p.ticket} at {sl:.5f}")
    for p in pos:
        if p.ticket in tailing_active:
            raw=get_atr_sl(p.type==mt5.ORDER_TYPE_BUY,p.price_open,df1)
            floor=floor_sl.get(p.ticket,p.price_open)
            new_sl=max(raw,floor) if p.type==mt5.ORDER_TYPE_BUY else min(raw,floor)
            modify_sl(p,new_sl)

# === STATUS ===
def report_status(act,pos):
    logger.info(f"Last: {act} | Open:{len(pos)}/{MAX_POSITIONS} | {datetime.now():%H:%M:%S}")

# === MAIN ===
def run_bot():
    logger.info("Starting bot...")
    last_rep=time.time(); last_act="None"
    while True:
        df1=get_data(TIMEFRAME_1M);macd=calc_macd_hist(df1)
        k,d=calc_stoch(df1);up,mid,lo=calc_donchian(df1,DONCHIAN_PERIOD)
        pr=df1['close'].iat[-1]
        ph=entry_phase(macd,k,d,pr,up.iat[-1],lo.iat[-1])
        if not mt5.positions_total() and ph>0:
            ib=pr<=lo.iat[-1]; is_=pr>=up.iat[-1]
            if ib or is_: execute_phase_trade(ib,ph,df1); last_act=f"Phase{ph} {'B' if ib else 'S'}"
        manage_trades(df1,up.iat[-1],mid.iat[-1],lo.iat[-1])
        if mt5.positions_total(): last_act=last_act or "Manage"
        if time.time()-last_rep>=LOG_INTERVAL:
            report_status(last_act,mt5.positions_get(symbol=SYMBOL) or [])
            last_rep=time.time()
        time.sleep(1)

if __name__ == '__main__': run_bot()
