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
from datetime import datetime

# ===== TESTING CONFIG =====
TEST_MODE = True  # Set to False in production
# ==========================

# Suppress TensorFlow warnings
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'  # Suppress TensorFlow info and warnings
logging.getLogger('tensorflow').setLevel(logging.ERROR)

# === WhatsApp SETUP ===
WHATSAPP_TARGET = '"IntelliTrade"'
# Create dedicated profile directory
PROFILE_DIR = os.path.join(os.getcwd(), 'whatsapp_profile')
os.makedirs(PROFILE_DIR, exist_ok=True)  # Ensure directory exists

# Chrome options - critical fixes
CHROME_OPTIONS = [
    "--no-sandbox",                 # MUST BE FIRST! Bypass OS security model
    "--disable-dev-shm-usage",      # Overcome limited resource problems
    "--disable-gpu",                # GPU issues can cause crashes
    f"user-data-dir={PROFILE_DIR}", # Use dedicated profile
    "--window-size=1920,1080"
]
CHROMEDRIVER_PATH = "chromedriver.exe"  # In same directory as script
CHROME_BINARY_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

def setup_whatsapp():
    """Initialize Chrome with multiple fallback strategies"""
    attempts = [
        try_standard_init,
        try_headless_init
    ]
    
    for attempt in attempts:
        driver, wait = attempt()
        if driver:
            return driver, wait
    
    raise RuntimeError("All Chrome initialization attempts failed")

def try_standard_init():
    """First attempt: Standard initialization with visible browser"""
    try:
        print("Attempting standard initialization...")
        service = Service(executable_path=CHROMEDRIVER_PATH)
        options = Options()
        
        for option in CHROME_OPTIONS:
            options.add_argument(option)
            
        options.add_experimental_option("excludeSwitches", ["enable-logging"])
        
        driver = webdriver.Chrome(service=service, options=options)
        driver.get("https://web.whatsapp.com/")
        print("✅ Chrome initialized successfully with standard method")
        print("Please scan the QR code and press Enter when ready")
        input()  # Wait for user to scan QR code
        wait = WebDriverWait(driver, 120)
        
        # Verify login by checking for chat list
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div[title='Chat list']")))
        print("WhatsApp Web login successful")
        return driver, wait
    except Exception as e:
        print(f"⚠️ Standard init failed: {str(e)}")
        return None, None

def try_headless_init():
    """Second attempt: Headless mode for background operation"""
    try:
        print("Attempting headless initialization...")
        service = Service(executable_path=CHROMEDRIVER_PATH)
        options = Options()
        options.add_argument("--headless=new")
        
        # Add all non-headless options
        for option in CHROME_OPTIONS:
            if not option.startswith("--headless"):
                options.add_argument(option)
        
        driver = webdriver.Chrome(service=service, options=options)
        driver.get("https://web.whatsapp.com/")
        print("✅ Chrome initialized in headless mode")
        
        # Wait for login to complete in headless mode
        wait = WebDriverWait(driver, 120)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div[title='Chat list']")))
        print("WhatsApp Web login successful in headless mode")
        return driver, wait
    except Exception as e:
        print(f"⚠️ Headless init failed: {str(e)}")
        return None, None

# === CONFIG ===
MT5_PATH = r"C:\Program Files\MetaTrader 5 Terminal\terminal64.exe"
TIMEFRAME = mt5.TIMEFRAME_M30
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

# === INDICATORS ===
def get_macd_sig_hist(df):
    macd = df['close'].ewm(span=MACD_FAST, adjust=False).mean() - df['close'].ewm(span=MACD_SLOW, adjust=False).mean()
    sig = macd.ewm(span=MACD_SIGNAL, adjust=False).mean()
    return macd, sig, macd - sig

def get_donchian(df):
    up = df['high'].rolling(DONCHIAN_PERIOD).max()
    low = df['low'].rolling(DONCHIAN_PERIOD).min()
    return up, low

def calc_tps_sl(entry, direction):
    tps = []
    for lvl in FIB_LEVELS:
        if direction == "BUY":
            tps.append(round(entry + entry * lvl/10000, 5))  # Fixed: use percentage points correctly
        else:
            tps.append(round(entry - entry * lvl/10000, 5))
    
    # Calculate stop loss based on risk-reward ratio
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

# === TEST FUNCTIONS ===
def send_test_message(driver, wait):
    """Send a test message to verify WhatsApp is working"""
    try:
        test_msg = "📈 IntelliTrade is online and monitoring markets!"
        print("Sending test message to WhatsApp...")
        
        # Refresh to ensure we're on the main page
        driver.refresh()
        time.sleep(3)
        
        # Find target chat
        chat_css = f"span[title={WHATSAPP_TARGET}]"
        group_title = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, chat_css)))
        group_title.click()
        time.sleep(2)  # Allow chat to load
        
        # Find message input box
        input_css = "div[title='Type a message'][contenteditable='true']"
        input_box = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, input_css)))
        
        # Send test message
        input_box.send_keys(test_msg + Keys.ENTER)
        print("✅ Test message sent to WhatsApp")
        return True
    except Exception as e:
        print(f"❌ Failed to send test message: {e}")
        # Save screenshot for debugging
        driver.save_screenshot('whatsapp_error.png')
        print("Saved screenshot as 'whatsapp_error.png'")
        return False

def simulate_signal(driver, wait, tracked):
    """Simulate a trade signal for testing purposes"""
    try:
        # Use EURUSD for simulation
        sym = "EURUSD"
        direction = random.choice(["BUY", "SELL"])
        price = mt5.symbol_info_tick(sym).ask if direction == "BUY" else mt5.symbol_info_tick(sym).bid
        
        # Calculate TP/SL
        tps, sl = calc_tps_sl(price, direction)
        tid = gen_id(sym)
        msg = build_msg(sym, direction, price, tps, sl, tid)
        
        print(f"\n=== TESTING: Simulating {direction} signal for {sym} ===")
        print(f"Entry: {price}")
        print(f"TPs: {tps}")
        print(f"SL: {sl}\n")
        
        # Refresh to ensure we're on the main page
        driver.refresh()
        time.sleep(3)
        
        # Find target chat
        chat_css = f"span[title={WHATSAPP_TARGET}]"
        group_title = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, chat_css)))
        group_title.click()
        time.sleep(2)  # Allow chat to load
        
        # Find message input box
        input_css = "div[title='Type a message'][contenteditable='true']"
        input_box = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, input_css)))
        
        # Clear and send message
        input_box.clear()
        for line in msg.strip().split('\n'):
            input_box.send_keys(line)
            input_box.send_keys(Keys.SHIFT + Keys.ENTER)
        input_box.send_keys(Keys.ENTER)
        
        # Track the simulated trade
        tracked[sym] = {
            "id": tid, 
            "symbol": sym, 
            "dir": direction,
            "entry": price, 
            "tps": tps, 
            "sl": sl,
            "status": "open", 
            "hit": [],
            "simulated": True  # Mark as simulated
        }
        save_trades(tracked)
        print(f"✅ Simulated signal sent for {sym} {direction}")
        return True
    except Exception as e:
        print(f"❌ Failed to send simulated signal: {e}")
        driver.save_screenshot('simulate_error.png')
        print("Saved screenshot as 'simulate_error.png'")
        return False

# === MESSAGE SENDING HELPER ===
def send_whatsapp_message(driver, wait, message):
    """Robust method to send WhatsApp messages"""
    try:
        # Refresh to ensure we're on the main page
        driver.refresh()
        time.sleep(3)
        
        # Find target chat
        chat_css = f"span[title={WHATSAPP_TARGET}]"
        group_title = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, chat_css)))
        group_title.click()
        time.sleep(2)  # Allow chat to load
        
        # Find message input box
        input_css = "div[title='Type a message'][contenteditable='true']"
        input_box = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, input_css)))
        
        # Clear and send message
        input_box.clear()
        for line in message.strip().split('\n'):
            input_box.send_keys(line)
            input_box.send_keys(Keys.SHIFT + Keys.ENTER)
        input_box.send_keys(Keys.ENTER)
        return True
    except Exception as e:
        print(f"❌ WhatsApp send error: {e}")
        driver.save_screenshot('message_error.png')
        print("Saved screenshot as 'message_error.png'")
        return False

# === MAIN EXECUTION ===
if __name__ == "__main__":
    # Initialize MT5
    print("Initializing MT5...")
    if not mt5.initialize(path=MT5_PATH):
        print("MT5 initialization failed, retrying in 30 seconds...")
        time.sleep(30)
        if not mt5.initialize(path=MT5_PATH):
            raise RuntimeError("Failed to initialize MT5")
    
    print("MT5 initialized successfully")
    
    # Initialize WhatsApp
    print("Initializing WhatsApp...")
    driver, wait = setup_whatsapp()
    print("WhatsApp setup complete")
    
    # ===== TEST SECTION 1: Online Notification =====
    if TEST_MODE:
        # Try sending test message multiple times
        for i in range(3):
            if send_test_message(driver, wait):
                break
            print(f"Retrying test message ({i+1}/3)...")
            time.sleep(5)
    # ===============================================
    
    tracked = load_trades()
    print(f"Loaded {len(tracked)} tracked trades")
    
    # ===== TEST SECTION 2: Simulate Signal =====
    if TEST_MODE and not tracked:
        if simulate_signal(driver, wait, tracked):
            print("Sleeping 10 seconds to verify message...")
            time.sleep(10)
    # ===========================================
    
    try:
        while True:
            symbols = [s.name for s in mt5.symbols_get() if "USD" in s.name or "XAU" in s.name]
            print(f"Scanning {len(symbols)} symbols...")
            
            # ===== TEST SECTION 3: Debug Output =====
            debug_symbol = random.choice(symbols) if TEST_MODE and symbols else None
            # ========================================
            
            for sym in symbols:
                # Skip if we have an open trade for this symbol (unless simulated)
                if sym in tracked and tracked[sym].get('status') == "open" and not tracked[sym].get('simulated', False):
                    continue
                
                # Fetch rates
                rates = mt5.copy_rates_from_pos(sym, TIMEFRAME, 0, DONCHIAN_PERIOD+50)
                if rates is None or len(rates) < DONCHIAN_PERIOD+10:
                    continue
                
                # Process data
                df = pd.DataFrame(rates)
                df['time'] = pd.to_datetime(df['time'], unit='s')
                up, low = get_donchian(df)
                macd, sig, hist = get_macd_sig_hist(df)
                
                # Get last values
                last = df['close'].iloc[-1]
                prev_hist = hist.iloc[-2]
                curr_hist = hist.iloc[-1]
                prev_sig = sig.iloc[-2]
                curr_sig = sig.iloc[-1]
                
                # ===== TEST SECTION 4: Debug Output =====
                if TEST_MODE and sym == debug_symbol:
                    print(f"\n[DEBUG] {sym}:")
                    print(f"  Last: {last:.5f}, Up: {up.iloc[-2]:.5f}, Low: {low.iloc[-2]:.5f}")
                    print(f"  MACD: Prev={prev_hist:.5f}, Curr={curr_hist:.5f}, Sig={curr_sig:.5f}")
                # ========================================
                
                # Check for signal
                direction = None
                if last >= up.iloc[-2] and prev_hist > prev_sig and curr_hist < curr_sig:
                    direction = "SELL"
                    price = mt5.symbol_info_tick(sym).bid
                elif last <= low.iloc[-2] and prev_hist < prev_sig and curr_hist > curr_sig:
                    direction = "BUY"
                    price = mt5.symbol_info_tick(sym).ask
                
                # Generate and send signal if found
                if direction:
                    tps, sl = calc_tps_sl(price, direction)
                    tid = gen_id(sym)
                    msg = build_msg(sym, direction, price, tps, sl, tid)
                    print(f"Signal detected for {sym} {direction}")
                    
                    # Send WhatsApp message with retries
                    for attempt in range(3):
                        if send_whatsapp_message(driver, wait, msg):
                            # Track the trade
                            tracked[sym] = {
                                "id": tid, 
                                "symbol": sym, 
                                "dir": direction,
                                "entry": price, 
                                "tps": tps, 
                                "sl": sl,
                                "status": "open", 
                                "hit": []
                            }
                            save_trades(tracked)
                            print(f"✅ Signal sent for {sym} {direction}")
                            break
                        print(f"Retrying message send ({attempt+1}/3)...")
                        time.sleep(3)
                    else:
                        print(f"❌ Failed to send signal for {sym} after 3 attempts")
            
            # Monitor open trades
            print("Monitoring open trades...")
            for sym, tr in list(tracked.items()):
                if tr.get('status') != "open":
                    continue
                
                # Skip simulated trades in production
                if not TEST_MODE and tr.get('simulated', False):
                    continue
                
                # Get current price
                tick = mt5.symbol_info_tick(sym)
                if not tick:
                    continue
                    
                price = tick.bid if tr['dir'] == "SELL" else tick.ask
                
                # Check for TP hits
                for i, tp in enumerate(tr['tps']):
                    if tp not in tr['hit']:
                        if (tr['dir'] == "BUY" and price >= tp) or (tr['dir'] == "SELL" and price <= tp):
                            tr['hit'].append(tp)
                            print(f"✅ {sym} TP{i+1} hit @ {tp}")
                
                # Check for SL hit
                if (tr['dir'] == "BUY" and price <= tr['sl']) or (tr['dir'] == "SELL" and price >= tr['sl']):
                    tr['status'] = "closed-sl"
                    print(f"🛑 {sym} SL hit @ {tr['sl']}")
                
                # Check if all TPs are hit
                if len(tr.get('hit', [])) == len(tr['tps']):
                    tr['status'] = "closed-tp4"
                    print(f"🏁 {sym} All TPs reached")
            
            save_trades(tracked)
            cycle_time = datetime.now().strftime('%H:%M:%S')
            print(f"Cycle complete at {cycle_time}, sleeping for 30 seconds...")
            time.sleep(30)
            
    except KeyboardInterrupt:
        print("\nShutting down by user request...")
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
    finally:
        # Clean up resources
        print("Shutting down MT5...")
        mt5.shutdown()
        
        if 'driver' in locals():
            print("Closing Chrome driver...")
            driver.quit()
        
        print("Resources released. Goodbye!")