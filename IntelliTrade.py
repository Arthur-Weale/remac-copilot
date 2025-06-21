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
USE_SYMBOL_FILTER = True # Set to False to monitor all USD/XAU symbols
SYMBOL_LIST = [
    # Volatility Indices
    "Volatility 10 Index", "Volatility 25 Index", "Volatility 50 Index", 
    "Volatility 75 Index", "Volatility 100 Index",
    "Volatility 10 (1s) Index", "Volatility 25 (1s) Index", 
    "Volatility 50 (1s) Index", "Volatility 75 (1s) Index", "Volatility 100 (1s) Index",
    "Jump 10 Index", "Jump 25 Index", "Jump 50 Index", 
    "Jump 75 Index", "Jump 100 Index",
    "Step Index",
    
    # Forex
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "NZDUSD", "USDCAD",
    "EURGBP", "EURJPY", "GBPJPY", "AUDJPY", "EURAUD", "CHFJPY", "NZDJPY",
    "USDZAR", "USDTRY", "USDMXN", "USDSGD", "EURZAR", "USDSEK", "USDNOK",
    
    # Indices (common MT5 names)
    "US30", "NAS100", "USTEC", "US100", "SPX500", "US500", "GER40", "DAX",
    "UK100", "FRA40", "JPN225", "HK50", "AUS200", "STOXX50",
    
    # Commodities
    "XAUUSD", "XAGUSD", "XAU/USD", "XAG/USD", "WTI", "BRENT", "NATURALGAS"
]  # Your preferred symbols
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

# Strategy-agnostic reasons
REASONS = [
    "Strong momentum alignment detected in our analysis",
    "System shows favorable risk-reward configuration",
    "Quantitative models indicate high-probability setup",
    "Market structure supports directional bias",
    "Volatility conditions favorable for this approach",
    "Price action confirms our algorithmic triggers",
    "Timing models show optimal entry window",
    "Liquidity profile supports trade thesis",
    "System convergence on directional opportunity",
    "Algorithmic edge detected in current market conditions"
]

# Confidence levels for signals
CONFIDENCE_LEVELS = {
    1: "High Confidence",
    2: "Medium Confidence",
    3: "Very High Confidence",
    4: "Caution Advised"
}

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
    return f"{sym}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

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
            # Handle both integer and float timestamps
            timestamp = event['time']
            if isinstance(timestamp, float):
                timestamp = int(timestamp)
            event['time'] = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        
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

# === PRICE VALIDATION ===
def is_valid_price(price, symbol, last_close=None, threshold=0.05):
    """Check if price is within expected range"""
    if price <= 0:
        return False
        
    # Check against last close if available
    if last_close is not None:
        if abs(price - last_close) > last_close * threshold:
            return False
            
    return True

def validate_prices(entry, tps, sl, direction, symbol, last_close):
    """Ensure all prices make logical sense"""
    # Validate entry price
    if not is_valid_price(entry, symbol, last_close):
        return False
        
    # Validate all TPs
    for tp in tps:
        if not is_valid_price(tp, symbol, last_close):
            return False
            
    # Validate SL
    if not is_valid_price(sl, symbol, last_close):
        return False
        
    # Direction-specific validation
    if direction == "BUY":
        if any(tp <= entry for tp in tps) or sl >= entry:
            return False
    else:  # SELL
        if any(tp >= entry for tp in tps) or sl <= entry:
            return False
            
    return True

# === TRADE LOGGING ===
def log_trade_performance(symbol, direction, entry, exit_price, outcome, pips, tid, high_touch, low_touch, tp_hit_count=0):
    """Log trade performance to CSV with win/loss tracking"""
    # Validate all prices before logging
    for price in [entry, exit_price, high_touch, low_touch]:
        if not is_valid_price(price, symbol):
            print(f"⚠️ Invalid price {price} for {symbol} - skipping log")
            return
            
    filename = f"trade_performance_{symbol}.csv"
    file_exists = os.path.isfile(filename)
    
    with open(filename, 'a', newline='') as f:
        fieldnames = [
            'Timestamp', 'TradeID', 'Direction', 'Entry', 'Exit', 
            'Outcome', 'Pips', 'HighTouch', 'LowTouch', 'TPsHit',
            'TradeResult'
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        
        if not file_exists:
            writer.writeheader()
        
        # Determine trade result based on outcome and TP hits
        trade_result = "N/A"
        if outcome.startswith("TP"):
            trade_result = "WIN"
        elif outcome == "SL":
            if tp_hit_count > 0:
                trade_result = "WIN (Partial)"
            else:
                trade_result = "LOSS"
        elif outcome == "ALL_TP":
            trade_result = "WIN (Full)"
            
        writer.writerow({
            'Timestamp': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
            'TradeID': tid,
            'Direction': direction,
            'Entry': entry,
            'Exit': exit_price,
            'Outcome': outcome,
            'Pips': pips,
            'HighTouch': high_touch,
            'LowTouch': low_touch,
            'TPsHit': tp_hit_count,
            'TradeResult': trade_result
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

def get_rsi(df, period=14):
    """Calculate RSI without revealing it in messages"""
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def get_sma(df, period):
    """Calculate Simple Moving Average"""
    return df['close'].rolling(period).mean()

def calc_tps_sl(entry, direction, high_touch, low_touch):
    """Calculate realistic profit targets"""
    # 1. Calculate volatility-adjusted channel height
    channel_height = abs(high_touch - low_touch)
    
    # 2. Cap channel height at 5% of average price
    avg_price = (high_touch + low_touch) / 2
    max_allowed = avg_price * 0.05
    channel_height = min(channel_height, max_allowed)
    
    # 3. Calculate proportional targets
    tps = []
    for lvl in FIB_LEVELS:
        extension = channel_height * (lvl/100)
        if direction == "BUY":
            tp = entry + extension
        else:  # SELL
            tp = entry - extension
        tps.append(round(tp, 5))
    
    # 4. Calculate SL based on TP1 distance
    tp1_distance = abs(tps[0] - entry)
    risk_distance = tp1_distance / RR
    
    if direction == "BUY":
        sl = round(entry - risk_distance, 5)
    else:
        sl = round(entry + risk_distance, 5)
    
    return tps, sl

# === MESSAGE GENERATION ===
def generate_signal_message(sym, direction, price, tps, sl, tid, confidence_level, timeframe="M30"):
    """Generate signal message without strategy details"""
    time_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')
    confidence = CONFIDENCE_LEVELS.get(confidence_level, "High Confidence")
    
    # Strategy-agnostic commentary
    insight_comments = [
        "Strong momentum alignment detected in our analysis",
        "System shows favorable risk-reward configuration",
        "Quantitative models indicate high-probability setup",
        "Market structure supports directional bias"
    ]
    
    # Generic market observations
    market_context = [
        "Volatility conditions favorable for this approach",
        "Price action confirms our algorithmic triggers",
        "Timing models show optimal entry window",
        "Liquidity profile supports trade thesis"
    ]
    
    tp_lines = "\n".join([f"🎯 TP{i+1} → {tp}" for i, tp in enumerate(tps)])
    
    msg = f"""
📈 IntelliTrade Signal Alert ({confidence})
━━━━━━━━━━━━━━━━━━━━━━  
🔹 Asset: {sym}  
📥 Direction: {direction}  
🕒 Time: {time_str}  
⏳ Timeframe: {timeframe}  

💵 Entry: {price}  
{tp_lines}  
🛑 Stop Loss: {sl}  
🆔 Trade ID: {tid}  

━━━━━━━━━━━━━━━━━━━━━━  
📊 Execution Insight:  
{random.choice(insight_comments)}  
{random.choice(market_context)}  
━━━━━━━━━━━━━━━━━━━━━━  
🚀 _Powered by IntelliTrade Alpha Engine_
"""
    return msg

# === TRADE UPDATE MESSAGES ===
def send_trade_update(driver, wait, symbol, event_type, details, tid):
    """Send trade update notifications"""
    time_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')
    
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

def send_closure_advisory(driver, wait, symbol, entry, current_price, tid, direction):
    """Send early closure advisory"""
    pips = abs(round(current_price - entry, 5))
    profit_status = "in profit" if ((direction == "BUY" and current_price > entry) or 
                                   (direction == "SELL" and current_price < entry)) else "at risk"
    
    message = f"""
⚠️ Trade Advisory: {symbol}
━━━━━━━━━━━━━━━━━━━━━━
Price has reached key opposing level
Consider securing profits or tightening stops
🕒 Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}
🆔 Trade ID: {tid}

Entry: {entry}
Current: {current_price}
Position status: {profit_status}

💡 _Protecting gains is as important as making them_
"""
    return send_whatsapp_message(driver, wait, message)

# === SPONTANEOUS MESSAGES ===
def send_spontaneous_message(driver, wait):
    """Send various spontaneous messages"""
    now = datetime.now(timezone.utc)
    
    # Morning messages (6AM-10AM UTC)
#     if 6 <= now.hour <= 7:
#         msg = f"""
# ☀️ Good Morning Traders!
# ━━━━━━━━━━━━━━━━━━━━━━
# {random.choice([
#     "Markets are waking up - stay alert for opportunities",
#     "Fresh trading day ahead - review your watchlists",
#     "New session, new possibilities - trade with focus"
# ])}
# """
#         return send_whatsapp_message(driver, wait, msg)
    
    # Market session reminders
    sessions = [
        ("London Open", 7, "European pairs coming alive"),
        ("New York Open", 12, "Volatility surge expected"),
        ("Asian Open", 23, "Overnight positioning opportunities")
    ]
    
    for session, hour, comment in sessions:
        if now.hour == hour and now.minute < 15:
            msg = f"""
⏰ {session} Reminder
━━━━━━━━━━━━━━━━━━━━━━
{comment}
{random.choice([
    "Check your risk exposure",
    "Monitor key technical levels",
    "Prepare for potential breakouts"
])}
"""
            return send_whatsapp_message(driver, wait, msg)
    
    # Motivational messages
    if random.random() > 0.05:
        msg = f"""
💪 Trading Wisdom
━━━━━━━━━━━━━━━━━━━━━━
"{random.choice([
    "Discipline separates winners from gamblers",
    "The market rewards patience more than brilliance",
    "Risk management isn't expensive - it's priceless"
])}"
"""
        return send_whatsapp_message(driver, wait, msg)
    
    # Market status commentary
    if random.random() > 0.1:
        symbols = random.sample(SYMBOL_LIST, min(2, len(SYMBOL_LIST)))
        comments = []
        
        for sym in symbols:
            try:
                # Get market data without revealing strategy
                spread = mt5.symbol_info(sym).spread
                day_range = mt5.symbol_info(sym).point * 10000
                
                comments.append(f"{sym}: Spread {'tightening' if spread < 15 else 'widening'}")
                comments.append(f"{sym}: Daily range: {'expanding' if day_range > 70 else 'contracting'}")
            except:
                continue
        
        if comments:
            msg = f"""
📊 Market Pulse
━━━━━━━━━━━━━━━━━━━━━━
{"\n".join(comments)}
"""
            return send_whatsapp_message(driver, wait, msg)
    
    # Premium campaign (occasional)
    if random.random() > 0.95:
        msg = """
💎 IntelliTrade Premium
━━━━━━━━━━━━━━━━━━━━━━
Elevate your trading with:
• Real-time SMS trade alerts
• Advanced position management tools
• Priority market analysis

🔐 Limited slots available
👉 Learn more: intellitrade.com/premium
"""
        return send_whatsapp_message(driver, wait, msg)
    
    return False

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
        sym = "Volatility 25 Index"
        direction = random.choice(["BUY", "SELL"])
        price = mt5.symbol_info_tick(sym).ask if direction == "BUY" else mt5.symbol_info_tick(sym).bid
        
        # For simulation
        current_upper = price * 1.005
        current_lower = price * 0.995
        
        tps, sl = calc_tps_sl(price, direction, current_upper, current_lower)
        tid = gen_id(sym)
        msg = generate_signal_message(sym, direction, price, tps, sl, tid, 1)
        
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

# === CRITICAL FIXES ===
def get_mt5_time(symbol):
    """Get current time from MT5 server for a symbol"""
    try:
        tick = mt5.symbol_info_tick(symbol)
        if tick:
            return datetime.fromtimestamp(tick.time, tz=timezone.utc)
    except:
        pass
    return datetime.now(timezone.utc)  # Fallback to system time

def validate_signal(sym, direction, entry_price, tolerance=0.0005):
    """Check if signal is still valid at execution time"""
    try:
        tick = mt5.symbol_info_tick(sym)
        if not tick:
            return False
            
        if direction == "BUY":
            current_ask = tick.ask
            # Allow 0.05% tolerance for execution
            return current_ask <= entry_price * (1 + tolerance)
        else:  # SELL
            current_bid = tick.bid
            return current_bid >= entry_price * (1 - tolerance)
    except Exception as e:
        print(f"❌ Signal validation failed for {sym}: {e}")
        return False

def is_data_fresh(symbol, current_time, max_age=300):
    """Check if market data is fresh (within max_age seconds)"""
    try:
        # Get time of last tick
        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            return False
            
        # Calculate age of data
        data_age = current_time.timestamp() - tick.time
        return data_age <= max_age
    except:
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
    last_session_update = None
    
    try:
        while True:
            try:
                current_utc_time = datetime.now(timezone.utc)
                
                # Send spontaneous messages (15% chance each cycle)
                if random.random() > 0.85:
                    send_spontaneous_message(driver, wait)
                
                # Refresh news every 15 minutes
                if ENABLE_NEWS_ALERTS and (last_news_fetch is None or 
                                         (current_utc_time - last_news_fetch).seconds > 900):
                    print("Fetching news events from Finnhub...")
                    news_events = get_upcoming_news()
                    last_news_fetch = current_utc_time
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
                    
                # Filter out symbols with stale data (5 min max age)
                symbols = [s for s in symbols if is_data_fresh(s, current_utc_time)]
                print(f"Scanning {len(symbols)} symbols with fresh data...")
                
                debug_symbol = random.choice(symbols) if TEST_MODE and symbols else None
                
                for sym in symbols:
                    try:
                        # Skip if already has an open trade
                        if sym in tracked and tracked[sym].get('status') == "open" and not tracked[sym].get('simulated', False):
                            continue
                        
                        # Get market data
                        rates = mt5.copy_rates_from_pos(sym, TIMEFRAME, 0, DONCHIAN_PERIOD+50)
                        if rates is None or len(rates) < DONCHIAN_PERIOD+10:
                            continue
                        
                        df = pd.DataFrame(rates)
                        df['time'] = pd.to_datetime(df['time'], unit='s')
                        
                        # Calculate indicators
                        up, low = get_donchian(df)
                        macd, sig, hist = get_macd_sig_hist(df)
                        rsi = get_rsi(df).iloc[-1]
                        sma9 = get_sma(df, 9).iloc[-1]
                        sma21 = get_sma(df, 21).iloc[-1]
                        
                        last_close = df['close'].iloc[-1]
                        prev_close = df['close'].iloc[-2]
                        curr_hist = hist.iloc[-1]
                        prev_hist = hist.iloc[-2]
                        curr_macd = macd.iloc[-1]
                        curr_sig = sig.iloc[-1]
                        prev_macd = macd.iloc[-2]
                        prev_sig = sig.iloc[-2]
                        high_touch = df['high'].iloc[-DONCHIAN_PERIOD:].max()
                        low_touch = df['low'].iloc[-DONCHIAN_PERIOD:].min()
                        
                        if TEST_MODE and sym == debug_symbol:
                            print(f"\n[DEBUG] {sym}:")
                            print(f"  Last: {last_close:.5f}, Up: {up.iloc[-1]:.5f}, Low: {low.iloc[-1]:.5f}")
                            print(f"  MACD: {curr_macd:.5f}, Signal: {curr_sig:.5f}")
                            print(f"  RSI: {rsi:.2f}, SMA9: {sma9:.5f}, SMA21: {sma21:.5f}")
                            print(f"  High Touch: {high_touch:.5f}, Low Touch: {low_touch:.5f}")
                        
                        # Signal detection
                        signal_detected = False
                        direction = None
                        confidence = 1  # Base confidence
                        
                        # BUY Signal: Price touches lower band AND MACD bullish crossover
                        if last_close <= low.iloc[-1]:
                            # MACD bullish crossover (current MACD > current Signal AND previous MACD <= previous Signal)
                            if curr_macd > curr_sig and prev_macd <= prev_sig:
                                direction = "BUY"
                                signal_detected = True
                                
                                # Add confidence based on confirmation filters
                                if rsi < 30:  # Oversold
                                    confidence += 1
                                if sma9 > sma21:  # Bullish alignment
                                    confidence += 1
                        
                        # SELL Signal: Price touches upper band AND MACD bearish crossover
                        elif last_close >= up.iloc[-1]:
                            # MACD bearish crossover (current MACD < current Signal AND previous MACD >= previous Signal)
                            if curr_macd < curr_sig and prev_macd >= prev_sig:
                                direction = "SELL"
                                signal_detected = True
                                
                                # Add confidence based on confirmation filters
                                if rsi > 70:  # Overbought
                                    confidence += 1
                                if sma9 < sma21:  # Bearish alignment
                                    confidence += 1
                        
                        if signal_detected and direction:
                            # Get current tick price
                            if direction == "BUY":
                                price = mt5.symbol_info_tick(sym).ask
                            else:
                                price = mt5.symbol_info_tick(sym).bid
                            
                            # Price validation: non-zero and within 5% of last close
                            if not is_valid_price(price, sym, prev_close):
                                print(f"⚠️ Price validation failed for {sym} - skipping signal")
                                continue
                            
                            # Calculate TP/SL with Fibonacci levels
                            tps, sl = calc_tps_sl(price, direction, high_touch, low_touch)
                            
                            # Validate prices before sending signal
                            if not validate_prices(price, tps, sl, direction, sym, prev_close):
                                print(f"⚠️ Price validation failed for {sym} - skipping signal")
                                continue
                                
                            # Validate signal is still relevant
                            if not validate_signal(sym, direction, price):
                                print(f"⚠️ Signal no longer valid for {sym} - skipping")
                                continue
                                
                            tid = gen_id(sym)
                            msg = generate_signal_message(sym, direction, price, tps, sl, tid, confidence)
                            print(f"Signal detected for {sym} {direction} (Confidence: {CONFIDENCE_LEVELS.get(confidence, 'Medium')})")
                            
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
                    except Exception as sym_error:
                        print(f"⚠️ Error processing symbol {sym}: {sym_error}")
                
                # Trade monitoring
                print("Monitoring open trades...")
                for sym, tr in list(tracked.items()):
                    try:
                        if tr.get('status') != "open":
                            continue
                        if not TEST_MODE and tr.get('simulated', False):
                            continue
                        
                        # Safely get values with defaults
                        high_touch = tr.get('high_touch', 0)
                        low_touch = tr.get('low_touch', 0)
                        tr.setdefault('hit', [])  # Ensure hit list exists
                        tp_hit_count = len(tr['hit'])  # Track how many TPs were hit

                        tick = mt5.symbol_info_tick(sym)
                        if not tick:
                            continue
                            
                        price = tick.bid if tr['dir'] == "SELL" else tick.ask
                        
                        # Check for early closure condition (opposite band touch)
                        try:
                            rates = mt5.copy_rates_from_pos(sym, TIMEFRAME, 0, DONCHIAN_PERIOD+10)
                            if rates and len(rates) >= DONCHIAN_PERIOD:
                                df = pd.DataFrame(rates)
                                current_up = df['high'].rolling(DONCHIAN_PERIOD).max().iloc[-1]
                                current_low = df['low'].rolling(DONCHIAN_PERIOD).min().iloc[-1]
                                
                                if tr['dir'] == "BUY" and price <= current_low:
                                    if not tr.get('closure_advised', False):
                                        if send_closure_advisory(driver, wait, sym, tr['entry'], price, tr['id'], tr['dir']):
                                            tr['closure_advised'] = True
                                            print(f"⚠️ Early closure advised for {sym}")
                                
                                elif tr['dir'] == "SELL" and price >= current_up:
                                    if not tr.get('closure_advised', False):
                                        if send_closure_advisory(driver, wait, sym, tr['entry'], price, tr['id'], tr['dir']):
                                            tr['closure_advised'] = True
                                            print(f"⚠️ Early closure advised for {sym}")
                        except:
                            pass
                        
                        # Check TP hits
                        for i, tp in enumerate(tr['tps']):
                            if tp not in tr['hit']:
                                if (tr['dir'] == "BUY" and price >= tp) or (tr['dir'] == "SELL" and price <= tp):
                                    tr['hit'].append(tp)
                                    tp_hit_count += 1
                                    event = f"TP{i+1} hit @ {tp}"
                                    print(f"✅ {sym} {event}")
                                    send_trade_update(driver, wait, sym, "TP_HIT", event, tr['id'])
                                    log_trade_performance(sym, tr['dir'], tr['entry'], tp, 
                                                        f"TP{i+1}", abs(tp - tr['entry']), 
                                                        tr['id'], high_touch, low_touch, tp_hit_count)
                        
                        # Check SL hit
                        if (tr['dir'] == "BUY" and price <= tr['sl']) or (tr['dir'] == "SELL" and price >= tr['sl']):
                            tr['status'] = "closed-sl"
                            
                            # Determine outcome based on TP hits
                            if tp_hit_count > 0:
                                event = f"SL hit @ {tr['sl']} after {tp_hit_count} TP(s)"
                                outcome = "WIN (Partial)"
                            else:
                                event = f"SL hit @ {tr['sl']} without any TP"
                                outcome = "LOSS"
                                
                            print(f"🛑 {sym} {event}")
                            send_trade_update(driver, wait, sym, "SL_HIT", event, tr['id'])
                            
                            # Calculate pips with direction awareness
                            pips = abs(tr['sl'] - tr['entry'])
                            if (tr['dir'] == "BUY" and tr['sl'] < tr['entry']) or \
                               (tr['dir'] == "SELL" and tr['sl'] > tr['entry']):
                                pips = -pips
                                
                            log_trade_performance(sym, tr['dir'], tr['entry'], tr['sl'], 
                                                "SL", pips, 
                                                tr['id'], high_touch, low_touch, tp_hit_count)
                        
                        # Check all TPs hit
                        if len(tr['hit']) == len(tr['tps']):
                            tr['status'] = "closed-tp4"
                            print(f"🏁 {sym} All TPs reached")
                            send_trade_update(driver, wait, sym, "ALL_TP", "", tr['id'])
                            
                            # Calculate pips with direction awareness
                            pips = abs(tr['tps'][-1] - tr['entry'])
                            if (tr['dir'] == "BUY" and tr['tps'][-1] > tr['entry']) or \
                               (tr['dir'] == "SELL" and tr['tps'][-1] < tr['entry']):
                                pips = abs(pips)
                            else:
                                pips = -abs(pips)
                                
                            log_trade_performance(sym, tr['dir'], tr['entry'], tr['tps'][-1], 
                                                "ALL_TP", pips, 
                                                tr['id'], high_touch, low_touch, len(tr['tps']))
                    
                    except Exception as trade_error:
                        print(f"⚠️ Error processing trade {sym}: {trade_error}")
                
                save_trades(tracked)
                print(f"Cycle complete at {current_utc_time.strftime('%H:%M:%S')}, sleeping for 30 seconds...")
                time.sleep(30)
            
            except Exception as loop_error:
                print(f"⚠️ Error in main loop: {loop_error}")
                import traceback
                traceback.print_exc()
                time.sleep(30)  # Wait before continuing
            
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