from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
import MetaTrader5 as mt5
import pandas as pd
import json
import random
import time
import os
import logging
import pyperclip
import win32clipboard
import csv
import requests
from datetime import datetime, timedelta, timezone

# ===== TESTING CONFIG =====
TEST_MODE = False  # Set to False in production
# ==========================

# ===== ASSET FILTER CONFIG =====
USE_SYMBOL_FILTER = False  # Set to False to monitor all USD/XAU symbols
SYMBOL_LIST = ["Volatility 10 Index",
    "Volatility 25 Index",
    "Volatility 50 Index",
    "Volatility 75 Index",
    "Volatility 100 Index",
    "Volatility 10 (1s) Index",
    "Volatility 25 (1s) Index",
    "Volatility 50 (1s) Index",
    "Volatility 75 (1s) Index",
    "Volatility 100 (1s) Index",
    "Jump 10 Index",
    "Jump 25 Index",
    "Jump 50 Index",
    "Jump 75 Index",
    "Jump 100 Index",
    "Step Index"]  # Your preferred symbols
# ===============================

# ===== NEWS FILTER CONFIG =====
ENABLE_NEWS_ALERTS = True  # Set to True to receive news notifications
NEWS_ALERT_BUFFER = 30  # Minutes before news to send alert
FINNHUB_API_KEY = "d172u5pr01qkv5je79sgd172u5pr01qkv5je79t0"
# ==============================

# Suppress TensorFlow warnings
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
logging.getLogger('tensorflow').setLevel(logging.ERROR)

# === WhatsApp SETUP ===
WHATSAPP_TARGET = '"IntelliTrade"'
PROFILE_DIR = os.path.join(os.getcwd(), 'whatsapp_profile')
os.makedirs(PROFILE_DIR, exist_ok=True)

# Chrome options
CHROME_OPTIONS = [
    f"user-data-dir={PROFILE_DIR}",
    "--profile-directory=Default",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--window-size=1920,1080",
    "--disable-blink-features=AutomationControlled",
    f"user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
]
CHROMEDRIVER_PATH = "chromedriver.exe"

def setup_whatsapp():
    """Initialize Chrome with persistent session handling"""
    try:
        print("Initializing Chrome with persistent profile...")
        service = Service(executable_path=CHROMEDRIVER_PATH)
        options = Options()
        
        for option in CHROME_OPTIONS:
            options.add_argument(option)
            
        options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
        options.add_experimental_option('useAutomationExtension', False)
        
        driver = webdriver.Chrome(service=service, options=options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        print("Loading WhatsApp Web...")
        driver.get("https://web.whatsapp.com/")
        print("✅ Chrome initialized successfully")
        
        # Visual feedback
        print("\n" + "="*50)
        print("WAITING FOR WHATSAPP LOGIN - PLEASE CHECK BROWSER")
        print("="*50)
        print("1. If you see QR code, please scan it")
        print("2. If you're already logged in, do nothing")
        print("3. The script will automatically proceed after login")
        print("="*50 + "\n")
        
        # Wait for login state
        start_time = time.time()
        timeout = 240
        logged_in = False
        
        while time.time() - start_time < timeout:
            try:
                print(f"Current URL: {driver.current_url}")
                print(f"Page title: {driver.title}")
                
                # Login detection logic
                logged_in_selectors = [
                    ("div[data-testid='chat-list']", "chat list"),
                    ("div[title='Type a message']", "message input"),
                    ("div[data-testid='conversation-panel']", "conversation panel"),
                    ("div[aria-label='Message list']", "message list"),
                    ("header[data-testid='conversation-header']", "conversation header"),
                    ("div[role='grid']", "message grid")
                ]
                
                for selector, description in logged_in_selectors:
                    if len(driver.find_elements(By.CSS_SELECTOR, selector)) > 0:
                        print(f"✅ Detected {description} - logged in")
                        logged_in = True
                        break
                
                if logged_in:
                    break
                    
                # QR code detection
                qr_selectors = [
                    ("canvas[aria-label='Scan me!']", "QR code canvas"),
                    ("div[data-ref]", "QR code container"),
                    ("canvas[data-ref]", "QR code data-ref"),
                    ("div[data-testid='qrcode']", "QR code testid")
                ]
                
                for selector, description in qr_selectors:
                    if len(driver.find_elements(By.CSS_SELECTOR, selector)) > 0:
                        print(f"⚠️ Detected {description} - please scan to login")
                        scan_start = time.time()
                        while time.time() - scan_start < 180:
                            for login_selector, desc in logged_in_selectors:
                                if len(driver.find_elements(By.CSS_SELECTOR, login_selector)) > 0:
                                    print(f"✅ Login detected after QR scan ({desc})")
                                    logged_in = True
                                    break
                            if logged_in:
                                break
                            print("Waiting for QR scan to complete...")
                            time.sleep(5)
                        break
                
                if logged_in:
                    break
                    
                # Loading states
                loading_selectors = [
                    "div[data-testid='loading-screen']",
                    "div[aria-label='Loading...']",
                    "div[class*='loading']",
                    "div[class*='spinner']"
                ]
                
                for selector in loading_selectors:
                    if len(driver.find_elements(By.CSS_SELECTOR, selector)) > 0:
                        print("⏳ WhatsApp is loading...")
                        time.sleep(5)
                        continue
                
                # Error handling
                error_selectors = [
                    "div[class*='error']",
                    "div[class*='exception']",
                    "div[class*='problem']",
                    "div[class*='refresh']"
                ]
                
                for selector in error_selectors:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        print(f"⚠️ Error detected: {elements[0].text[:100]}")
                        print("Attempting to refresh page...")
                        driver.refresh()
                        time.sleep(5)
                        break
                
                # Unrecognized state
                print("⚠️ Unrecognized screen state - saving screenshot")
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                screenshot_name = f'whatsapp_unknown_{timestamp}.png'
                driver.save_screenshot(screenshot_name)
                print(f"Saved screenshot as '{screenshot_name}'")
                time.sleep(5)
                
            except Exception as e:
                print(f"⚠️ Detection error: {str(e)}")
                time.sleep(5)
            
        if not logged_in:
            driver.save_screenshot('whatsapp_timeout.png')
            print("❌ WhatsApp login detection timed out after 4 minutes")
            raise RuntimeError("WhatsApp login detection timed out")
        
        wait = WebDriverWait(driver, 30)
        print("✅ WhatsApp login successful")
        return driver, wait
            
    except Exception as e:
        print(f"⚠️ Chrome initialization failed: {str(e)}")
        raise RuntimeError("Chrome initialization failed")            


# === CONFIG ===
MT5_PATH = r"C:\Program Files\MetaTrader 5 Terminal\terminal64.exe"
TIMEFRAME = mt5.TIMEFRAME_M1
DONCHIAN_PERIOD = 20
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
FIB_LEVELS = [100, 161.8, 261.8, 423.6]
RR = 3
TRACK_FILE = "intellitrade_trades.json"

REASONS = [
    "Reactive zone interaction aligned with macro flow indicator.",
    "Price-action trigger supported by momentum divergence resolution.",
    "Structural inflection respected with oscillator confirmation.",
    "Dynamic range boundary interaction with trend alignment.",
    "Volatility compression followed by directional momentum shift.",
    "Liquidity zone engagement validated by momentum oscillator.",
    "Trend filter confirmation at key market structure pivot.",
    "Momentum oscillator crossover at critical price threshold.",
    "Price structure test coupled with internal momentum validation.",
    "Algorithmic trigger from volatility cluster and flow alignment."
]

# === TRACKING ===
def load_trades():
    try:
        with open(TRACK_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_trades(trades):
    with open(TRACK_FILE, 'w') as f:
        json.dump(trades, f, indent=4)

def gen_id(sym): 
    return f"{sym}_{datetime.now().strftime('%Y%m%d%H%M%S')}"

# === NEWS ALERTS ===
def get_upcoming_news():
    """Fetch upcoming high-impact news events from Finnhub"""
    try:
        # Get current time range (now to +1 day)
        now = datetime.now(timezone.utc)
        start_date = now.strftime('%Y-%m-%d')
        end_date = (now + timedelta(days=1)).strftime('%Y-%m-%d')
        
        # Fetch economic calendar
        url = f"https://finnhub.io/api/v1/calendar/economic?from={start_date}&to={end_date}&token={FINNHUB_API_KEY}"
        response = requests.get(url, timeout=10)
        
        if response.status_code != 200:
            print(f"❌ News API error: {response.status_code}")
            return []
            
        events = response.json().get('economicCalendar', [])
        
        # Filter for high-impact events
        high_impact_events = [
            event for event in events 
            if event.get('impact') == 'high' and event.get('time') is not None
        ]
        
        # Convert timestamps to datetime objects
        for event in high_impact_events:
            event['time'] = datetime.fromtimestamp(event['time'], tz= timezone.utc)
        
        return high_impact_events
    
    except Exception as e:
        print(f"❌ Failed to fetch news: {e}")
        return []

def send_news_alert(driver, wait, event):
    """Send news alert notification via WhatsApp"""
    try:
        # Format the news event
        event_time = event['time'].strftime('%Y-%m-%d %H:%M UTC')
        message = f"""
🚨 Economic News Alert
━━━━━━━━━━━━━━━━━━━━━━
📅 Event: {event['event']}
⏰ Time: {event_time}
🌐 Country: {event['country']}
💱 Currency: {event['currency']}
📊 Impact: High
━━━━━━━━━━━━━━━━━━━━━━
ℹ️ {event.get('description', 'No description available')}
━━━━━━━━━━━━━━━━━━━━━━
💡 _Monitor market volatility_
"""
        return send_whatsapp_message(driver, wait, message)
    except Exception as e:
        print(f"❌ Failed to send news alert: {e}")
        return False

# === TRADE LOGGING ===
def log_trade_performance(symbol, direction, entry, exit_price, outcome, pips, tid, high_touch, low_touch):
    """Log trade performance to CSV"""
    filename = f"trade_performance_{symbol}.csv"
    file_exists = os.path.isfile(filename)
    
    with open(filename, 'a', newline='') as f:
        fieldnames = [
            'Timestamp', 'TradeID', 'Direction', 'Entry', 'Exit', 
            'Outcome', 'Pips', 'HighTouch', 'LowTouch'
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        
        if not file_exists:
            writer.writeheader()
        
        writer.writerow({
            'Timestamp': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
            'TradeID': tid,
            'Direction': direction,
            'Entry': entry,
            'Exit': exit_price,
            'Outcome': outcome,
            'Pips': pips,
            'HighTouch': high_touch,
            'LowTouch': low_touch
        })

# === INDICATORS ===
def get_macd_sig_hist(df):
    macd = df['close'].ewm(span=MACD_FAST, adjust=False).mean() - df['close'].ewm(span=MACD_SLOW, adjust=False).mean()
    sig = macd.ewm(span=MACD_SIGNAL, adjust=False).mean()
    return macd, sig, macd - sig

def get_donchian(df):
    up = df['high'].rolling(DONCHIAN_PERIOD).max()
    low = df['low'].rolling(DONCHIAN_PERIOD).min()
    return up, low

def calc_tps_sl(entry, direction, high_touch, low_touch):
    """
    Calculate Fibonacci profit targets based on actual Donchian band touches
    
    For BUY:
    - Start: Previous high that touched upper band (high_touch)
    - Profit targets: Extensions ABOVE start point
    
    For SELL:
    - Start: Previous low that touched lower band (low_touch)
    - Profit targets: Extensions BELOW start point
    """
    channel_height = abs(high_touch - low_touch)
    
    tps = []
    for lvl in FIB_LEVELS:
        if direction == "BUY":
            # Extensions ABOVE high_touch
            tp = high_touch + channel_height * (lvl/100)
        else:  # SELL
            # Extensions BELOW low_touch
            tp = low_touch - channel_height * (lvl/100)
        tps.append(round(tp, 5))
    
    # Risk management
    risk_distance = abs(tps[0] - entry)
    if direction == "BUY":
        sl = round(entry - risk_distance * RR, 5)
    else:
        sl = round(entry + risk_distance * RR, 5)
    
    return tps, sl

def build_msg(sym, dir, entry, tps, sl, tid, timeframe="M30"):
    time_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    tp_lines = "\n".join([f"🎯 TP{i+1} → {tp}" for i, tp in enumerate(tps)])
    return f"""
📈 IntelliTrade Signal Alert  
━━━━━━━━━━━━━━━━━━━━━━  
🔹 Asset: {sym}  
📥 Direction: {dir}  
🕒 Time: {time_str}  
⏳ Timeframe: {timeframe}  

💵 Entry: {entry}  
{tp_lines}  
🛑 Stop Loss: {sl}  
🆔 Trade ID: {tid}  

━━━━━━━━━━━━━━━━━━━━━━  
📊 Execution Insight:  
{random.choice(REASONS)}  
━━━━━━━━━━━━━━━━━━━━━━  
🚀 _Powered by IntelliTrade Alpha Engine_
"""

# === TRADE UPDATE MESSAGES ===
def send_trade_update(driver, wait, symbol, event_type, details, tid):
    """Send trade update notifications"""
    time_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    
    if event_type == "TP_HIT":
        message = f"""
📊 Trade Update: {symbol}
⏰ Time: {time_str}
✅ {details}
🆔 Trade ID: {tid}
"""
    elif event_type == "SL_HIT":
        message = f"""
📊 Trade Update: {symbol}
⏰ Time: {time_str}
🛑 {details}
🆔 Trade ID: {tid}
"""
    elif event_type == "ALL_TP":
        message = f"""
📊 Trade Update: {symbol}
⏰ Time: {time_str}
🏁 All Profit Targets Reached!
🆔 Trade ID: {tid}
"""
    else:
        return False
    
    return send_whatsapp_message(driver, wait, message)

# === TEST FUNCTIONS ===
def send_test_message(driver, wait):
    try:
        test_msg = "📈 IntelliTrade is online and monitoring markets!"
        print("Sending test message to WhatsApp...")
        return send_whatsapp_message(driver, wait, test_msg)
    except Exception as e:
        print(f"❌ Failed to send test message: {e}")
        return False
    
def simulate_signal(driver, wait, tracked):
    try:
        sym = "EURUSD"
        direction = random.choice(["BUY", "SELL"])
        price = mt5.symbol_info_tick(sym).ask if direction == "BUY" else mt5.symbol_info_tick(sym).bid
        
        # For simulation
        current_upper = price * 1.005
        current_lower = price * 0.995
        
        tps, sl = calc_tps_sl(price, direction, current_upper, current_lower)
        tid = gen_id(sym)
        msg = build_msg(sym, direction, price, tps, sl, tid)
        
        print(f"\n=== TESTING: Simulating {direction} signal for {sym} ===")
        print(f"Entry: {price}")
        print(f"TPs: {tps}")
        print(f"SL: {sl}\n")
        
        if send_whatsapp_message(driver, wait, msg):
            tracked[sym] = {
                "id": tid, 
                "symbol": sym, 
                "dir": direction,
                "entry": price, 
                "tps": tps, 
                "sl": sl,
                "status": "open", 
                "hit": [],
                "simulated": True,
                "high_touch": current_upper,
                "low_touch": current_lower
            }
            save_trades(tracked)
            print(f"✅ Simulated signal sent for {sym} {direction}")
            return True
        return False
    except Exception as e:
        print(f"❌ Failed to send simulated signal: {e}")
        return False
    
# === MESSAGE SENDING ===
def send_whatsapp_message(driver, wait, message):
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            print(f"\nAttempt {attempt+1}/{max_attempts} to send message")
            
            chat_css = f"span[title={WHATSAPP_TARGET}]"
            group_title = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, chat_css)))
            group_title.click()
            print("✅ Found and clicked target chat")
            time.sleep(1)
            
            input_selectors = [
                "div[contenteditable='true'][title='Type a message']",
                "div[contenteditable='true'][data-tab='10']",
                "footer div[contenteditable='true']"
            ]
            
            input_box = None
            for selector in input_selectors:
                try:
                    input_box = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
                    print(f"✅ Found input with selector: {selector}")
                    break
                except:
                    continue
            
            if not input_box:
                raise RuntimeError("Could not find message input box")
            
            input_box.clear()
            print("Cleared input box")
            
            try:
                pyperclip.copy(message)
            except:
                win32clipboard.OpenClipboard()
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(message)
                win32clipboard.CloseClipboard()
            
            print("📋 Copied message to clipboard")
            input_box.send_keys(Keys.CONTROL, 'v')
            print("📋 Pasted message from clipboard")
            time.sleep(1)
            input_box.send_keys(Keys.ENTER)
            print("✅ Message sent successfully")
            return True
            
        except Exception as e:
            print(f"❌ Message send attempt {attempt+1} failed: {str(e)}")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_name = f'message_error_{timestamp}.png'
            driver.save_screenshot(screenshot_name)
            print(f"Saved screenshot as '{screenshot_name}'")
            driver.refresh()
            time.sleep(5)
    
    print(f"❌ Failed to send message after {max_attempts} attempts")
    return False

# === MAIN EXECUTION ===
if __name__ == "__main__":
    print("Initializing MT5...")
    if not mt5.initialize(path=MT5_PATH):
        print("MT5 initialization failed, retrying in 30 seconds...")
        time.sleep(30)
        if not mt5.initialize(path=MT5_PATH):
            raise RuntimeError("Failed to initialize MT5")
    print("MT5 initialized successfully")
    
    print("Initializing WhatsApp...")
    driver, wait = setup_whatsapp()
    print("WhatsApp setup complete")
    
    if TEST_MODE:
        for i in range(3):
            if send_test_message(driver, wait):
                break
            print(f"Retrying test message ({i+1}/3)...")
            time.sleep(5)
    
    tracked = load_trades()
    print(f"Loaded {len(tracked)} tracked trades")
    
    if TEST_MODE and not tracked:
        if simulate_signal(driver, wait, tracked):
            print("Sleeping 10 seconds to verify message...")
            time.sleep(10)
    
    # Cache for news events and alerts
    last_news_fetch = None
    news_events = []
    alerted_events = set()  # Track events we've already alerted about
    
    try:
        while True:
            # Refresh news every 15 minutes
            if ENABLE_NEWS_ALERTS and (last_news_fetch is None or 
                                     (datetime.now() - last_news_fetch).seconds > 900):
                print("Fetching news events from Finnhub...")
                news_events = get_upcoming_news()
                last_news_fetch = datetime.now()
                print(f"Found {len(news_events)} upcoming high-impact news events")
            
            # Send news alerts if enabled
            if ENABLE_NEWS_ALERTS:
                now = datetime.now(timezone.utc)
                for event in news_events:
                    event_id = f"{event['event']}_{event['time'].timestamp()}"
                    
                    # Skip if already alerted
                    if event_id in alerted_events:
                        continue
                        
                    # Check if event is within alert window
                    alert_time = event['time'] - timedelta(minutes=NEWS_ALERT_BUFFER)
                    if now >= alert_time:
                        print(f"⚠️ High-impact news event upcoming: {event['event']}")
                        if send_news_alert(driver, wait, event):
                            print(f"✅ News alert sent for: {event['event']}")
                            alerted_events.add(event_id)
            
            # Get all available symbols
            all_symbols = [s.name for s in mt5.symbols_get()]
            
            # Apply symbol filter
            if USE_SYMBOL_FILTER:
                symbols = [s for s in SYMBOL_LIST if s in all_symbols]
            else:
                symbols = [s for s in all_symbols if "USD" in s or "XAU" in s]
                
            print(f"Scanning {len(symbols)} symbols...")
            
            debug_symbol = random.choice(symbols) if TEST_MODE and symbols else None
            
            for sym in symbols:
                if sym in tracked and tracked[sym].get('status') == "open" and not tracked[sym].get('simulated', False):
                    continue
                
                rates = mt5.copy_rates_from_pos(sym, TIMEFRAME, 0, DONCHIAN_PERIOD+50)
                if rates is None or len(rates) < DONCHIAN_PERIOD+10:
                    continue
                
                df = pd.DataFrame(rates)
                df['time'] = pd.to_datetime(df['time'], unit='s')
                up, low = get_donchian(df)
                macd, sig, hist = get_macd_sig_hist(df)
                
                last = df['close'].iloc[-1]
                curr_hist = hist.iloc[-1]
                high_touch = df['high'].iloc[-DONCHIAN_PERIOD:].max()
                low_touch = df['low'].iloc[-DONCHIAN_PERIOD:].min()
                
                if TEST_MODE and sym == debug_symbol:
                    print(f"\n[DEBUG] {sym}:")
                    print(f"  Last: {last:.5f}, Up: {up.iloc[-1]:.5f}, Low: {low.iloc[-1]:.5f}")
                    print(f"  MACD Histogram: {curr_hist:.5f}")
                    print(f"  High Touch: {high_touch:.5f}, Low Touch: {low_touch:.5f}")
                
                # Signal detection
                direction = None
                if last >= up.iloc[-1] and curr_hist < 0:
                    direction = "SELL"
                    price = mt5.symbol_info_tick(sym).bid
                elif last <= low.iloc[-1] and curr_hist > 0:
                    direction = "BUY"
                    price = mt5.symbol_info_tick(sym).ask
                
                if direction:
                    tps, sl = calc_tps_sl(price, direction, high_touch, low_touch)
                    tid = gen_id(sym)
                    msg = build_msg(sym, direction, price, tps, sl, tid)
                    print(f"Signal detected for {sym} {direction}")
                    
                    for attempt in range(3):
                        if send_whatsapp_message(driver, wait, msg):
                            tracked[sym] = {
                                "id": tid, 
                                "symbol": sym, 
                                "dir": direction,
                                "entry": price, 
                                "tps": tps, 
                                "sl": sl,
                                "status": "open", 
                                "hit": [],
                                "high_touch": high_touch,
                                "low_touch": low_touch
                            }
                            save_trades(tracked)
                            print(f"✅ Signal sent for {sym} {direction}")
                            break
                        print(f"Retrying message send ({attempt+1}/3)...")
                        time.sleep(3)
                    else:
                        print(f"❌ Failed to send signal for {sym} after 3 attempts")
            
            # Trade monitoring
            print("Monitoring open trades...")
            for sym, tr in list(tracked.items()):
                if tr.get('status') != "open":
                    continue
                if not TEST_MODE and tr.get('simulated', False):
                    continue
                
                tick = mt5.symbol_info_tick(sym)
                if not tick:
                    continue
                    
                price = tick.bid if tr['dir'] == "SELL" else tick.ask
                
                # Check TP hits
                for i, tp in enumerate(tr['tps']):
                    if tp not in tr['hit']:
                        if (tr['dir'] == "BUY" and price >= tp) or (tr['dir'] == "SELL" and price <= tp):
                            tr['hit'].append(tp)
                            event = f"TP{i+1} hit @ {tp}"
                            print(f"✅ {sym} {event}")
                            send_trade_update(driver, wait, sym, "TP_HIT", event, tr['id'])
                            log_trade_performance(sym, tr['dir'], tr['entry'], tp, 
                                                f"TP{i+1}", abs(tp - tr['entry']), 
                                                tr['id'], tr['high_touch'], tr['low_touch'])
                
                # Check SL hit
                if (tr['dir'] == "BUY" and price <= tr['sl']) or (tr['dir'] == "SELL" and price >= tr['sl']):
                    tr['status'] = "closed-sl"
                    event = f"SL hit @ {tr['sl']}"
                    print(f"🛑 {sym} {event}")
                    send_trade_update(driver, wait, sym, "SL_HIT", event, tr['id'])
                    log_trade_performance(sym, tr['dir'], tr['entry'], tr['sl'], 
                                         "SL", -abs(tr['sl'] - tr['entry']), 
                                         tr['id'], tr['high_touch'], tr['low_touch'])
                
                # Check all TPs hit
                if len(tr.get('hit', [])) == len(tr['tps']):
                    tr['status'] = "closed-tp4"
                    print(f"🏁 {sym} All TPs reached")
                    send_trade_update(driver, wait, sym, "ALL_TP", "", tr['id'])
                    log_trade_performance(sym, tr['dir'], tr['entry'], tr['tps'][-1], 
                                         "ALL_TP", abs(tr['tps'][-1] - tr['entry']), 
                                         tr['id'], tr['high_touch'], tr['low_touch'])
            
            save_trades(tracked)
            print(f"Cycle complete at {datetime.now().strftime('%H:%M:%S')}, sleeping for 30 seconds...")
            time.sleep(30)
            
    except KeyboardInterrupt:
        print("\nShutting down by user request...")
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
    finally:
        print("Shutting down MT5...")
        mt5.shutdown()
        
        if 'driver' in locals():
            print("Closing Chrome driver...")
            driver.quit()
        
        print("Resources released. Goodbye!")