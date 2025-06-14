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
import win32clipboard  # For Windows clipboard access
from datetime import datetime

# ===== TESTING CONFIG =====
TEST_MODE = False  # Set to False in production
# ==========================

# Suppress TensorFlow warnings
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'  # Suppress TensorFlow info and warnings
logging.getLogger('tensorflow').setLevel(logging.ERROR)

# === WhatsApp SETUP ===
WHATSAPP_TARGET = '"IntelliTrade"'
# Create dedicated profile directory
PROFILE_DIR = os.path.join(os.getcwd(), 'whatsapp_profile')
os.makedirs(PROFILE_DIR, exist_ok=True)  # Ensure directory exists

# Chrome options with persistent profile
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
    """Initialize Chrome with persistent session handling and robust detection"""
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
        
        # Visual feedback for user
        print("\n==================================================")
        print("WAITING FOR WHATSAPP LOGIN - PLEASE CHECK BROWSER")
        print("==================================================")
        print("1. If you see QR code, please scan it")
        print("2. If you're already logged in, do nothing")
        print("3. The script will automatically proceed after login")
        print("==================================================\n")
        
        # Wait for either login state or QR code with extended timeout
        start_time = time.time()
        timeout = 240  # 4 minutes
        logged_in = False
        
        while time.time() - start_time < timeout:
            try:
                # Debug: print current URL and page title
                print(f"Current URL: {driver.current_url}")
                print(f"Page title: {driver.title}")
                
                # Check if we're logged in by multiple methods
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
                    
                # Check for QR code with multiple selectors
                qr_selectors = [
                    ("canvas[aria-label='Scan me!']", "QR code canvas"),
                    ("div[data-ref]", "QR code container"),
                    ("canvas[data-ref]", "QR code data-ref"),
                    ("div[data-testid='qrcode']", "QR code testid")
                ]
                
                for selector, description in qr_selectors:
                    if len(driver.find_elements(By.CSS_SELECTOR, selector)) > 0:
                        print(f"⚠️ Detected {description} - please scan to login")
                        
                        # Wait for login to complete after scanning
                        scan_start = time.time()
                        while time.time() - scan_start < 180:  # 3 minutes to scan
                            # Check if we're now logged in
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
                    
                # Check for loading spinner
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
                
                # Check for error messages
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
                        # Suggest refresh
                        print("Attempting to refresh page...")
                        driver.refresh()
                        time.sleep(5)
                        break
                
                # No recognizable elements found
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
            # Save screenshot for debugging
            driver.save_screenshot('whatsapp_timeout.png')
            print("❌ WhatsApp login detection timed out after 4 minutes")
            print("Saved screenshot as 'whatsapp_timeout.png'")
            raise RuntimeError("WhatsApp login detection timed out")
        
        # Create WebDriverWait instance
        wait = WebDriverWait(driver, 30)
        print("✅ WhatsApp login successful")
        return driver, wait
            
    except Exception as e:
        print(f"⚠️ Chrome initialization failed: {str(e)}")
        raise RuntimeError("Chrome initialization failed")            


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
        return send_whatsapp_message(driver, wait, test_msg)
    except Exception as e:
        print(f"❌ Failed to send test message: {e}")
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
        
        # Send using our robust message sender
        if send_whatsapp_message(driver, wait, msg):
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
        return False
    except Exception as e:
        print(f"❌ Failed to send simulated signal: {e}")
        return False
    
# Update the message sending function
def send_whatsapp_message(driver, wait, message):
    """Robust method to send WhatsApp messages using clipboard"""
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            print(f"\nAttempt {attempt+1}/{max_attempts} to send message")
            
            # Find target chat
            chat_css = f"span[title={WHATSAPP_TARGET}]"
            group_title = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, chat_css)))
            group_title.click()
            print("✅ Found and clicked target chat")
            time.sleep(1)  # Allow chat to load
            
            # Find message input box
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
            
            # Clear input
            input_box.clear()
            print("Cleared input box")
            
            # Copy message to clipboard
            try:
                pyperclip.copy(message)
            except:
                # Fallback for Windows
                win32clipboard.OpenClipboard()
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(message)
                win32clipboard.CloseClipboard()
            
            print("📋 Copied message to clipboard")
            
            # Paste from clipboard
            input_box.send_keys(Keys.CONTROL, 'v')
            print("📋 Pasted message from clipboard")
            time.sleep(1)  # Allow paste to complete
            
            # Send the message
            input_box.send_keys(Keys.ENTER)
            print("✅ Message sent successfully")
            return True
            
        except Exception as e:
            print(f"❌ Message send attempt {attempt+1} failed: {str(e)}")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_name = f'message_error_{timestamp}.png'
            driver.save_screenshot(screenshot_name)
            print(f"Saved screenshot as '{screenshot_name}'")
            
            # Refresh page before retrying
            driver.refresh()
            time.sleep(5)
    
    print(f"❌ Failed to send message after {max_attempts} attempts")
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