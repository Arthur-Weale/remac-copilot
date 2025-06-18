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
import numpy as np
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
SMA_PERIOD_SHORT = 9
SMA_PERIOD_LONG = 21
RSI_PERIOD = 14
FIB_LEVELS = [100, 161.8, 261.8, 423.6]
RR = 3
TRACK_FILE = "intellitrade_trades.json"
DAILY_SUMMARY_FILE = "daily_trading_summary.txt"
TRADE_PERFORMANCE_DIR = "trade_performance_data"

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
class TradePerformance:
    def __init__(self):
        # Create directory for trade performance data
        os.makedirs(TRADE_PERFORMANCE_DIR, exist_ok=True)
        
        # Initialize daily summary
        self.today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        self.trade_count = 0
        self.wins = 0
        self.losses = 0
        self.total_pips = 0
        self.max_win = 0
        self.max_loss = 0
        self.tp_hits = 0
        self.sl_hits = 0
        self.win_streak = 0
        self.loss_streak = 0
        self.current_win_streak = 0
        self.current_loss_streak = 0
        
    def log_trade(self, trade_data):
        """Log detailed trade performance to CSV"""
        # Validate all prices before logging
        for price in [trade_data['Entry'], trade_data['Exit']]:
            if not is_valid_price(price, trade_data['Symbol']):
                print(f"⚠️ Invalid price {price} for {trade_data['Symbol']} - skipping log")
                return
                
        filename = os.path.join(TRADE_PERFORMANCE_DIR, f"trade_performance_{self.today}.csv")
        file_exists = os.path.isfile(filename)
        
        with open(filename, 'a', newline='', encoding='utf-8') as f:
            fieldnames = [
                'Timestamp', 'TradeID', 'Symbol', 'Direction', 'Entry', 'Exit', 
                'Outcome', 'Pips', 'DonchianUpper', 'DonchianLower',
                'MACD_Main', 'MACD_Signal', 'MACD_Hist', 
                'RSI', 'RSI_Status', 'SMA_9', 'SMA_21', 'SMA_Alignment'
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            
            if not file_exists:
                writer.writeheader()
            
            writer.writerow(trade_data)
        
        # Update daily summary stats
        self.trade_count += 1
        pips = trade_data['Pips']
        
        if trade_data['Outcome'] != "SL":
            self.wins += 1
            self.total_pips += pips
            self.current_win_streak += 1
            self.current_loss_streak = 0
            if pips > self.max_win:
                self.max_win = pips
            if trade_data['Outcome'].startswith("TP"):
                self.tp_hits += 1
        else:
            self.losses += 1
            self.total_pips += pips  # pips is negative for losses
            self.current_loss_streak += 1
            self.current_win_streak = 0
            if pips < self.max_loss:
                self.max_loss = pips
            self.sl_hits += 1
        
        if self.current_win_streak > self.win_streak:
            self.win_streak = self.current_win_streak
        if self.current_loss_streak > self.loss_streak:
            self.loss_streak = self.current_loss_streak
            
        # Update daily summary file
        self.update_daily_summary()
    
    def update_daily_summary(self):
        """Update daily summary file with current statistics"""
        win_rate = (self.wins / self.trade_count * 100) if self.trade_count > 0 else 0
        profit_factor = (self.wins / self.losses) if self.losses > 0 else float('inf')
        avg_win = (self.total_pips / self.wins) if self.wins > 0 else 0
        avg_loss = (abs(self.total_pips) / self.losses) if self.losses > 0 else 0
        
        summary = f"""
=== DAILY TRADING SUMMARY ===
Date: {self.today}
Timestamp: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}
Total Trades: {self.trade_count}
Wins: {self.wins} ({win_rate:.2f}%)
Losses: {self.losses}
Profit Factor: {profit_factor:.2f}
Total Pips: {self.total_pips:.2f}
Avg Pips/Trade: {self.total_pips/self.trade_count:.2f if self.trade_count > 0 else 0}
Max Win: {self.max_win:.2f} pips
Max Loss: {self.max_loss:.2f} pips
TPs Hit: {self.tp_hits}
SLs Hit: {self.sl_hits}
Current Win Streak: {self.current_win_streak}
Current Loss Streak: {self.current_loss_streak}
Longest Win Streak: {self.win_streak}
Longest Loss Streak: {self.loss_streak}
Avg Win: {avg_win:.2f} pips
Avg Loss: {avg_loss:.2f} pips
"""
        
        with open(DAILY_SUMMARY_FILE, 'w') as f:
            f.write(summary)
        print(f"✅ Updated daily summary at {DAILY_SUMMARY_FILE}")

# === INDICATORS ===
def get_donchian(df):
    up = df['high'].rolling(DONCHIAN_PERIOD).max()
    low = df['low'].rolling(DONCHIAN_PERIOD).min()
    return up, low

def get_macd(df):
    macd_line = df['close'].ewm(span=MACD_FAST, adjust=False).mean() - df['close'].ewm(span=MACD_SLOW, adjust=False).mean()
    signal_line = macd_line.ewm(span=MACD_SIGNAL, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

def get_rsi(df, period=RSI_PERIOD):
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    
    avg_gain = gain.ewm(alpha=1/period).mean()
    avg_loss = loss.ewm(alpha=1/period).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def get_sma(df, period):
    return df['close'].rolling(period).mean()

def calc_tps_sl(entry, direction, donchian_upper, donchian_lower):
    """Calculate profit targets based on Donchian channel height"""
    channel_height = abs(donchian_upper - donchian_lower)
    avg_price = (donchian_upper + donchian_lower) / 2
    max_allowed = avg_price * 0.05
    channel_height = min(channel_height, max_allowed)
    
    tps = []
    for lvl in FIB_LEVELS:
        extension = channel_height * (lvl/100)
        if direction == "BUY":
            tp = entry + extension
        else:  # SELL
            tp = entry - extension
        tps.append(round(tp, 5))
    
    tp1_distance = abs(tps[0] - entry)
    risk_distance = tp1_distance / RR
    
    if direction == "BUY":
        sl = round(entry - risk_distance, 5)
    else:
        sl = round(entry + risk_distance, 5)
    
    return tps, sl

# === MESSAGE GENERATION ===
def generate_signal_message(sym, direction, price, tps, sl, tid, indicators):
    """Generate signal message with strategy details"""
    time_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')
    
    # Generate TP lines with the exact format in the example
    tp_lines = "\n".join([
        f"🎯 TP1 → {tps[0]}",
        f"🎯 TP2 → {tps[1]}",
        f"🎯 TP3 → {tps[2]}",
        f"🎯 TP4 → {tps[3]}"  
    ])
    
    # Select two random execution insights
    insight_lines = "\n".join(random.sample(REASONS, 2))
    
    return f"""
📈 IntelliTrade Signal Alert (High Confidence)
━━━━━━━━━━━━━━━━━━━━━━  
🔹 Asset: {sym}  
📥 Direction: {direction}  
🕒 Time: {time_str}  
⏳ Timeframe: M30  

💵 Entry: {price}  
{tp_lines}  
🛑 Stop Loss: {sl}  
🆔 Trade ID: {tid}  

━━━━━━━━━━━━━━━━━━━━━━  
📊 Execution Insight:  
{insight_lines}  
━━━━━━━━━━━━━━━━━━━━━━  
🚀 _Powered by IntelliTrade Alpha Engine_
"""

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

def send_closure_advisory(driver, wait, symbol, entry, current_price, tid, direction, reason):
    """Send early closure advisory"""
    pips = abs(round(current_price - entry, 5))
    profit_status = "in profit" if ((direction == "BUY" and current_price > entry) or 
                                   (direction == "SELL" and current_price < entry)) else "at risk"
    
    message = f"""
⚠️ Trade Advisory: {symbol}
━━━━━━━━━━━━━━━━━━━━━━
{reason}
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
    if 6 <= now.hour <= 10:
        msg = f"""
☀️ Good Morning Traders!
━━━━━━━━━━━━━━━━━━━━━━
{random.choice([
    "Markets are waking up - stay alert for opportunities",
    "Fresh trading day ahead - review your watchlists",
    "New session, new possibilities - trade with focus"
])}
"""
        return send_whatsapp_message(driver, wait, msg)
    
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
    if random.random() > 0.85:
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
    if random.random() > 0.9:
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
    
def simulate_signal(driver, wait, tracked, analytics):
    try:
        sym = "Volatility 25 Index"
        direction = random.choice(["BUY", "SELL"])
        price = mt5.symbol_info_tick(sym).ask if direction == "BUY" else mt5.symbol_info_tick(sym).bid
        
        # For simulation
        current_upper = price * 1.005
        current_lower = price * 0.995
        
        tps, sl = calc_tps_sl(price, direction, current_upper, current_lower)
        tid = gen_id(sym)
        
        # Create simulated indicators
        indicators = {
            'donchian_upper': current_upper,
            'donchian_lower': current_lower,
            'macd_main': random.uniform(-0.5, 0.5),
            'macd_signal': random.uniform(-0.5, 0.5),
            'macd_hist': random.uniform(-0.5, 0.5),
            'rsi': random.uniform(30, 70),
            'sma_9': price * random.uniform(0.99, 1.01),
            'sma_21': price * random.uniform(0.99, 1.01)
        }
        
        msg = generate_signal_message(sym, direction, price, tps, sl, tid, indicators)
        
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
                "indicators": indicators,
                "closure_advised": False
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

def is_data_fresh(symbol, current_time, max_age=120):
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
    
    # Initialize trade performance tracker
    analytics = TradePerformance()
    
    if TEST_MODE:
        for i in range(3):
            if send_test_message(driver, wait):
                break
            print(f"Retrying test message ({i+1}/3)...")
            time.sleep(5)
    
    tracked = load_trades()
    print(f"Loaded {len(tracked)} tracked trades")
    
    if TEST_MODE and not tracked:
        if simulate_signal(driver, wait, tracked, analytics):
            print("Sleeping 10 seconds to verify message...")
            time.sleep(10)
    
    # Cache for news events and alerts
    last_news_fetch = None
    news_events = []
    alerted_events = set()  # Track events we've already alerted about
    last_session_update = None
    
    # Track last signal times per symbol
    last_signal_times = {}
    
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
                    
                # Filter out symbols with stale data
                symbols = [s for s in symbols if is_data_fresh(s, current_utc_time)]
                print(f"Scanning {len(symbols)} symbols with fresh data...")
                
                debug_symbol = random.choice(symbols) if TEST_MODE and symbols else None
                
                for sym in symbols:
                    try:
                        # Skip if we've recently sent a signal for this symbol
                        if sym in last_signal_times:
                            time_since_last = (current_utc_time - last_signal_times[sym]).total_seconds()
                            if time_since_last < 300:  # 5 minutes cooldown
                                continue
                        
                        # Skip if already has an open trade
                        if sym in tracked and tracked[sym].get('status') == "open" and not tracked[sym].get('simulated', False):
                            continue
                        
                        rates = mt5.copy_rates_from_pos(sym, TIMEFRAME, 0, DONCHIAN_PERIOD+50)
                        if rates is None or len(rates) < DONCHIAN_PERIOD+10:
                            continue
                        
                        df = pd.DataFrame(rates)
                        df['time'] = pd.to_datetime(df['time'], unit='s')
                        
                        # Calculate indicators
                        donchian_upper, donchian_lower = get_donchian(df)
                        macd_line, signal_line, histogram = get_macd(df)
                        rsi = get_rsi(df)
                        sma_9 = get_sma(df, SMA_PERIOD_SHORT)
                        sma_21 = get_sma(df, SMA_PERIOD_LONG)
                        
                        # Get current values
                        current_close = df['close'].iloc[-1]
                        current_upper = donchian_upper.iloc[-1]
                        current_lower = donchian_lower.iloc[-1]
                        current_hist = histogram.iloc[-1]
                        current_signal = signal_line.iloc[-1]
                        current_rsi = rsi.iloc[-1]
                        current_sma_9 = sma_9.iloc[-1]
                        current_sma_21 = sma_21.iloc[-1]
                        
                        # Determine SMA alignment
                        sma_alignment = "Bullish" if current_sma_9 > current_sma_21 else "Bearish"
                        
                        # Determine RSI status
                        rsi_status = "Neutral"
                        if current_rsi >= 70:
                            rsi_status = "Overbought"
                        elif current_rsi <= 30:
                            rsi_status = "Oversold"
                        
                        if TEST_MODE and sym == debug_symbol:
                            print(f"\n[DEBUG] {sym}:")
                            print(f"  Close: {current_close:.5f}, Upper: {current_upper:.5f}, Lower: {current_lower:.5f}")
                            print(f"  MACD Histogram: {current_hist:.5f}, Signal: {current_signal:.5f}")
                            print(f"  RSI: {current_rsi:.2f} ({rsi_status})")
                            print(f"  SMA 9: {current_sma_9:.5f}, SMA 21: {current_sma_21:.5f} ({sma_alignment})")
                        
                        # Signal detection - YOUR EXACT STRATEGY
                        direction = None
                        
                        # SELL signal: Price touches upper band AND MACD histogram is below signal line
                        if current_close >= current_upper and current_hist < current_signal:
                            direction = "SELL"
                            price = mt5.symbol_info_tick(sym).bid
                        
                        # BUY signal: Price touches lower band AND MACD histogram is above signal line
                        elif current_close <= current_lower and current_hist > current_signal:
                            direction = "BUY"
                            price = mt5.symbol_info_tick(sym).ask
                        
                        if direction:
                            # Skip if price validation fails
                            if not is_valid_price(price, sym):
                                print(f"⚠️ Invalid price for {sym} - skipping")
                                continue
                            
                            # Calculate TP/SL
                            tps, sl = calc_tps_sl(price, direction, current_upper, current_lower)
                            
                            # Validate prices before sending signal
                            if not validate_prices(price, tps, sl, direction, sym, current_close):
                                print(f"⚠️ Price validation failed for {sym} - skipping signal")
                                continue
                                
                            # Validate signal is still relevant
                            if not validate_signal(sym, direction, price):
                                print(f"⚠️ Signal no longer valid for {sym} - skipping")
                                continue
                                
                            tid = gen_id(sym)
                            
                            # Prepare indicator data for message and logging
                            indicators = {
                                'donchian_upper': current_upper,
                                'donchian_lower': current_lower,
                                'macd_main': macd_line.iloc[-1],
                                'macd_signal': current_signal,
                                'macd_hist': current_hist,
                                'rsi': current_rsi,
                                'rsi_status': rsi_status,
                                'sma_9': current_sma_9,
                                'sma_21': current_sma_21,
                                'sma_alignment': sma_alignment
                            }
                            
                            msg = generate_signal_message(sym, direction, price, tps, sl, tid, indicators)
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
                                        "indicators": indicators,
                                        "closure_advised": False,
                                        "simulated": False
                                    }
                                    save_trades(tracked)
                                    last_signal_times[sym] = current_utc_time
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
                        
                        tick = mt5.symbol_info_tick(sym)
                        if not tick:
                            continue
                            
                        price = tick.bid if tr['dir'] == "SELL" else tick.ask
                        
                        # Check for early closure conditions
                        closure_reason = None
                        
                        # 1. Opposite Donchian band touch
                        try:
                            rates = mt5.copy_rates_from_pos(sym, TIMEFRAME, 0, DONCHIAN_PERIOD+10)
                            if rates and len(rates) >= DONCHIAN_PERIOD:
                                df = pd.DataFrame(rates)
                                donchian_upper, donchian_lower = get_donchian(df)
                                current_upper = donchian_upper.iloc[-1]
                                current_lower = donchian_lower.iloc[-1]
                                
                                if tr['dir'] == "BUY" and price <= current_lower:
                                    closure_reason = "Price touched opposite (lower) Donchian band"
                                elif tr['dir'] == "SELL" and price >= current_upper:
                                    closure_reason = "Price touched opposite (upper) Donchian band"
                        except Exception as e:
                            print(f"⚠️ Error checking Donchian for {sym}: {e}")
                        
                        # 2. MACD crossover
                        if not closure_reason:
                            try:
                                rates = mt5.copy_rates_from_pos(sym, TIMEFRAME, 0, 3)
                                if rates and len(rates) >= 2:
                                    df = pd.DataFrame(rates)
                                    _, signal_line, histogram = get_macd(df)
                                    current_hist = histogram.iloc[-1]
                                    current_signal = signal_line.iloc[-1]
                                    prev_hist = histogram.iloc[-2]
                                    prev_signal = signal_line.iloc[-2]
                                    
                                    # Check for crossover
                                    if tr['dir'] == "BUY":
                                        if prev_hist > prev_signal and current_hist < current_signal:
                                            closure_reason = "MACD histogram crossed below signal line"
                                    else:  # SELL
                                        if prev_hist < prev_signal and current_hist > current_signal:
                                            closure_reason = "MACD histogram crossed above signal line"
                            except Exception as e:
                                print(f"⚠️ Error checking MACD for {sym}: {e}")
                        
                        # Send advisory if closure condition met
                        if closure_reason and not tr.get('closure_advised', False):
                            if send_closure_advisory(driver, wait, sym, tr['entry'], price, tr['id'], tr['dir'], closure_reason):
                                print(f"⚠️ Closure advisory sent for {sym}: {closure_reason}")
                                tr['closure_advised'] = True
                                tracked[sym] = tr
                                save_trades(tracked)
                        
                        # Check TP hits
                        for i, tp in enumerate(tr['tps']):
                            if tp not in tr['hit']:
                                if (tr['dir'] == "BUY" and price >= tp) or (tr['dir'] == "SELL" and price <= tp):
                                    tr['hit'].append(tp)
                                    event = f"TP{i+1} hit @ {tp}"
                                    print(f"✅ {sym} {event}")
                                    send_trade_update(driver, wait, sym, "TP_HIT", event, tr['id'])
                                    
                                    # Log performance
                                    trade_data = {
                                        'Timestamp': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
                                        'TradeID': tr['id'],
                                        'Symbol': sym,
                                        'Direction': tr['dir'],
                                        'Entry': tr['entry'],
                                        'Exit': tp,
                                        'Outcome': f"TP{i+1}",
                                        'Pips': abs(tp - tr['entry']),
                                        'DonchianUpper': tr['indicators']['donchian_upper'],
                                        'DonchianLower': tr['indicators']['donchian_lower'],
                                        'MACD_Main': tr['indicators']['macd_main'],
                                        'MACD_Signal': tr['indicators']['macd_signal'],
                                        'MACD_Hist': tr['indicators']['macd_hist'],
                                        'RSI': tr['indicators']['rsi'],
                                        'RSI_Status': tr['indicators']['rsi_status'],
                                        'SMA_9': tr['indicators']['sma_9'],
                                        'SMA_21': tr['indicators']['sma_21'],
                                        'SMA_Alignment': tr['indicators']['sma_alignment']
                                    }
                                    analytics.log_trade(trade_data)
                                    
                                    # Close trade if all TPs hit
                                    if len(tr['hit']) == len(tr['tps']):
                                        tr['status'] = "closed"
                                        print(f"🏁 {sym} All TPs reached")
                                        send_trade_update(driver, wait, sym, "ALL_TP", "", tr['id'])
                                        tracked[sym] = tr
                                        save_trades(tracked)
                
                        # Check SL hit
                        if (tr['dir'] == "BUY" and price <= tr['sl']) or (tr['dir'] == "SELL" and price >= tr['sl']):
                            tr['status'] = "closed"
                            
                            # Determine SL outcome based on TP hits
                            if len(tr['hit']) > 0:
                                outcome = "SL after TP (Win)"
                                event = f"SL hit after TP @ {tr['sl']} (Win)"
                            else:
                                outcome = "SL without TP (Loss)"
                                event = f"SL hit without any TP @ {tr['sl']} (Loss)"
                            
                            print(f"🛑 {sym} {event}")
                            send_trade_update(driver, wait, sym, "SL_HIT", event, tr['id'])
                            tracked[sym] = tr
                            save_trades(tracked)
                            
                            # Log performance
                            trade_data = {
                                'Timestamp': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
                                'TradeID': tr['id'],
                                'Symbol': sym,
                                'Direction': tr['dir'],
                                'Entry': tr['entry'],
                                'Exit': tr['sl'],
                                'Outcome': outcome,
                                'Pips': -abs(tr['sl'] - tr['entry']),
                                'DonchianUpper': tr['indicators']['donchian_upper'],
                                'DonchianLower': tr['indicators']['donchian_lower'],
                                'MACD_Main': tr['indicators']['macd_main'],
                                'MACD_Signal': tr['indicators']['macd_signal'],
                                'MACD_Hist': tr['indicators']['macd_hist'],
                                'RSI': tr['indicators']['rsi'],
                                'RSI_Status': tr['indicators']['rsi_status'],
                                'SMA_9': tr['indicators']['sma_9'],
                                'SMA_21': tr['indicators']['sma_21'],
                                'SMA_Alignment': tr['indicators']['sma_alignment']
                            }
                            analytics.log_trade(trade_data)
                    
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