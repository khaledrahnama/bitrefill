#!/usr/bin/env python3
"""
Automated demo video recorder for Value Router.
Run:  python3 make_video.py
Produces: demo_final.mp4

Requirements: pip3 install pyautogui   (already installed)
              ffmpeg (already installed)
              Flask app running on port 5050
"""

import subprocess, threading, time, os, sys, math

# ── Paths ──────────────────────────────────────────────────────────────────────
DIR          = os.path.dirname(os.path.abspath(__file__))
VOX          = os.path.join(DIR, "voiceover")
SCREEN_RAW   = os.path.join(DIR, "screen_raw.mp4")
AUDIO_CONCAT = os.path.join(DIR, "voiceover_full.aiff")
FINAL        = os.path.join(DIR, "demo_final.mp4")
APP_URL      = "http://localhost:5050"
DEMO_URL     = "http://localhost:5050/demo"
W, H         = 1512, 982   # screen resolution

# ── Browser control via osascript ─────────────────────────────────────────────

def activate_chrome():
    subprocess.run(["osascript", "-e",
        'tell application "Google Chrome" to activate'], capture_output=True)
    time.sleep(0.4)

def nav(url):
    script = f'''tell application "Google Chrome"
        set URL of front window's active tab to "{url}"
    end tell'''
    subprocess.run(["osascript", "-e", script], capture_output=True)
    time.sleep(2.5)

def js(code):
    """Execute JS in Chrome's active tab."""
    escaped = code.replace('\\', '\\\\').replace('"', '\\"').replace('\n', ' ')
    script = f'''tell application "Google Chrome"
        execute front window's active tab javascript "{escaped}"
    end tell'''
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return r.stdout.strip()

# ── Mouse control via pyautogui ───────────────────────────────────────────────

import pyautogui
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0

def move(x, y, dur=0.6):
    pyautogui.moveTo(x, y, duration=dur, tween=pyautogui.easeInOutQuad)

def scroll_down(amount=3):
    pyautogui.scroll(-amount, x=W//2, y=H//2)
    time.sleep(0.15)

# ── Audio ─────────────────────────────────────────────────────────────────────

def play_bg(fname):
    """Play audio file in background, return Popen."""
    return subprocess.Popen(["afplay", os.path.join(VOX, fname)])

def wait(proc):
    proc.wait()

# ── ffmpeg recording ──────────────────────────────────────────────────────────

def start_recording():
    cmd = [
        "ffmpeg", "-y",
        "-f", "avfoundation",
        "-framerate", "30",
        "-capture_cursor", "1",
        "-i", "1",            # Capture screen 0 (video only)
        "-vcodec", "libx264",
        "-preset", "ultrafast",
        "-crf", "20",
        "-pix_fmt", "yuv420p",
        SCREEN_RAW,
    ]
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(2.5)   # Wait for ffmpeg to initialize
    return proc

def stop_recording(proc):
    try:
        proc.stdin.write(b'q\n')
        proc.stdin.flush()
    except Exception:
        proc.terminate()
    proc.wait(timeout=10)

def concat_audio():
    """Concatenate all segment .aiff files into one."""
    files = sorted(
        f for f in os.listdir(VOX)
        if f.endswith(".aiff") and not f.startswith("FULL")
    )
    list_file = os.path.join(DIR, "_concat_list.txt")
    with open(list_file, "w") as f:
        for fname in files:
            f.write(f"file '{os.path.join(VOX, fname)}'\n")
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", list_file,
        "-c", "copy",
        AUDIO_CONCAT,
    ], check=True, capture_output=True)
    os.remove(list_file)

def merge():
    """Mux video + audio into final MP4."""
    subprocess.run([
        "ffmpeg", "-y",
        "-i", SCREEN_RAW,
        "-i", AUDIO_CONCAT,
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        FINAL,
    ], check=True)

# ── Segment actions ───────────────────────────────────────────────────────────

def seg_00_intro():
    activate_chrome()
    nav(APP_URL)
    move(W//2, 320, dur=1.2)
    p = play_bg("00_intro.aiff")
    move(W//2 + 60, 280, dur=2.5)
    move(W//2, 340, dur=2.0)
    wait(p)

def seg_01_problem():
    p = play_bg("01_problem.aiff")
    move(W//2, 240, dur=2.0)
    move(W//2 - 80, 380, dur=3.0)
    move(W//2 + 40, 320, dur=3.5)
    move(W//2, 300, dur=2.0)
    wait(p)

def seg_02_landing():
    p = play_bg("02_landing.aiff")
    for _ in range(6):
        scroll_down(2)
        time.sleep(0.4)
    move(W//2, H//2, dur=1.0)
    wait(p)

def seg_03_app_open():
    nav(DEMO_URL)
    p = play_bg("03_app_open.aiff")
    move(220, 130, dur=1.2)   # Value Router tab area
    time.sleep(1.2)
    move(680, 130, dur=1.5)   # Shop & Pay tab area
    time.sleep(1.0)
    move(220, 130, dur=1.0)   # Back to Value Router
    wait(p)

def seg_04_single_intent():
    # Make sure Single mode is selected and test mode on
    js("""
        (function(){
            var tabs = document.querySelectorAll('.tab-btn, button');
            for(var t of tabs){if(t.innerText.includes('Single')||t.innerText.includes('🌍')){t.click();break;}}
        })()
    """)
    time.sleep(0.5)
    # Fill intent textarea
    js("""
        (function(){
            var ta = document.querySelector('textarea');
            if(!ta) return;
            var nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value').set;
            nativeInputValueSetter.call(ta,'Send $10 to my brother in Lagos');
            ta.dispatchEvent(new Event('input',{bubbles:true}));
        })()
    """)
    time.sleep(0.4)
    # Enable test mode
    js("""
        (function(){
            var labels = document.querySelectorAll('label');
            for(var l of labels){if(l.innerText.toLowerCase().includes('test')){var cb=l.querySelector('input[type=checkbox]');if(cb&&!cb.checked)cb.click();break;}}
            var inputs = document.querySelectorAll('input[type=checkbox]');
            for(var inp of inputs){if(!inp.checked)inp.click();}
        })()
    """)
    time.sleep(0.4)
    p = play_bg("04_single_intent.aiff")
    move(W//2, 380, dur=1.0)
    time.sleep(2.5)
    # Click Run Agent
    js("""
        (function(){
            var btns = document.querySelectorAll('button');
            for(var b of btns){if(b.innerText.includes('Run')||b.innerText.includes('Agent')){b.click();break;}}
        })()
    """)
    move(W//2, 450, dur=2.0)
    wait(p)

def seg_05_single_result():
    p = play_bg("05_single_result.aiff")
    time.sleep(2.0)
    for _ in range(4):
        scroll_down(3)
        time.sleep(0.8)
    move(W//2, 520, dur=1.5)
    wait(p)

def seg_06_team_intro():
    # Click Team toggle
    js("""
        (function(){
            var btns = document.querySelectorAll('button, .mode-btn');
            for(var b of btns){if(b.innerText.includes('Team')||b.innerText.includes('👥')){b.click();break;}}
        })()
    """)
    time.sleep(0.8)
    # Scroll back to top
    js("window.scrollTo(0,0)")
    p = play_bg("06_team_intro.aiff")
    move(W//2, 200, dur=1.2)
    move(W//2 - 60, 260, dur=2.0)
    move(W//2 + 60, 220, dur=2.0)
    wait(p)

def seg_07_team_reasoning():
    js("""
        (function(){
            var ta = document.querySelector('textarea');
            if(!ta) return;
            var setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value').set;
            setter.call(ta,'Send $10 each to Alice in Lagos, Bob in Manila, and Carlos in Mexico City');
            ta.dispatchEvent(new Event('input',{bubbles:true}));
        })()
    """)
    time.sleep(0.5)
    p = play_bg("07_team_reasoning.aiff")
    # Click Run
    js("""
        (function(){
            var btns = document.querySelectorAll('button');
            for(var b of btns){if(b.innerText.includes('Run')||b.innerText.includes('Agent')){b.click();break;}}
        })()
    """)
    time.sleep(3.0)
    move(W//2, 420, dur=2.0)
    for _ in range(3):
        scroll_down(2)
        time.sleep(1.2)
    wait(p)

def seg_08_team_result():
    p = play_bg("08_team_result.aiff")
    for _ in range(3):
        scroll_down(2)
        time.sleep(0.6)
    move(W//2, 500, dur=1.5)
    wait(p)

def seg_09_shop_intro():
    # Click Shop & Pay tab
    js("""
        (function(){
            var btns = document.querySelectorAll('button, .tab-btn');
            for(var b of btns){if(b.innerText.includes('Shop')||b.innerText.includes('🛒')){b.click();break;}}
        })()
    """)
    time.sleep(0.8)
    js("window.scrollTo(0,0)")
    p = play_bg("09_shop_intro.aiff")
    move(W * 3//4, 220, dur=1.5)
    move(W * 3//4, 280, dur=2.0)
    wait(p)

def seg_10_shop_search():
    js("""
        (function(){
            var inp = document.querySelector('#shopQuery') ||
                      document.querySelector('input[placeholder]') ||
                      document.querySelector('.shop-input input') ||
                      Array.from(document.querySelectorAll('input')).find(i=>i.type==='text'||i.type==='search');
            if(!inp) return;
            var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
            setter.call(inp,'cheapest screen protector for iPhone 14 on Amazon');
            inp.dispatchEvent(new Event('input',{bubbles:true}));
        })()
    """)
    time.sleep(0.5)
    p = play_bg("10_shop_search.aiff")
    # Click search button
    js("""
        (function(){
            var btns = document.querySelectorAll('button');
            for(var b of btns){
                if(b.innerText.includes('Search')||b.innerText.includes('Find')){b.click();break;}
            }
        })()
    """)
    move(W * 3//4, 360, dur=2.0)
    move(W * 3//4 + 40, 420, dur=3.0)
    wait(p)

def seg_11_shop_result():
    p = play_bg("11_shop_result.aiff")
    time.sleep(2.5)
    for _ in range(3):
        scroll_down(2)
        time.sleep(0.6)
    move(W * 3//4, 420, dur=1.5)
    move(W * 3//4 - 30, 460, dur=1.5)
    wait(p)

def seg_12_shop_purchase():
    # Click Confirm / Buy button
    js("""
        (function(){
            var btns = document.querySelectorAll('button');
            for(var b of btns){
                if(b.innerText.includes('Confirm')||b.innerText.includes('Buy')||b.innerText.includes('confirm')){
                    b.click();break;
                }
            }
        })()
    """)
    p = play_bg("12_shop_purchase.aiff")
    time.sleep(3.0)
    for _ in range(4):
        scroll_down(2)
        time.sleep(0.8)
    move(W * 3//4, 500, dur=1.5)
    wait(p)

def seg_13_innovation():
    p = play_bg("13_innovation.aiff")
    time.sleep(1.5)
    # Switch to Value Router tab
    js("""
        (function(){
            var btns = document.querySelectorAll('button, .tab-btn');
            for(var b of btns){if(b.innerText.includes('Value')||b.innerText.includes('Router')||b.innerText.includes('🌍')){b.click();break;}}
        })()
    """)
    move(W//2, 280, dur=1.5)
    time.sleep(4.0)
    # Switch to Shop & Pay
    js("""
        (function(){
            var btns = document.querySelectorAll('button, .tab-btn');
            for(var b of btns){if(b.innerText.includes('Shop')||b.innerText.includes('🛒')){b.click();break;}}
        })()
    """)
    move(W * 3//4, 280, dur=1.5)
    time.sleep(3.0)
    wait(p)

def seg_14_close():
    p = play_bg("14_close.aiff")
    time.sleep(2.0)
    nav(APP_URL)   # Back to landing page
    move(W//2, 300, dur=2.0)
    move(W//2, H//2, dur=3.0)
    wait(p)
    time.sleep(1.0)

# ── Main ───────────────────────────────────────────────────────────────────────

SEGMENTS = [
    (seg_00_intro,       "00_intro       — Landing page hero"),
    (seg_01_problem,     "01_problem     — Problem statement"),
    (seg_02_landing,     "02_landing     — Scroll landing"),
    (seg_03_app_open,    "03_app_open    — Open demo app"),
    (seg_04_single_intent, "04_single    — Type Lagos intent, Run Agent"),
    (seg_05_single_result, "05_result    — Show routing + invoice"),
    (seg_06_team_intro,  "06_team_intro  — Switch to Team mode"),
    (seg_07_team_reasoning, "07_team_reasoning — Run 3-recipient plan"),
    (seg_08_team_result, "08_team_result — Show team invoice"),
    (seg_09_shop_intro,  "09_shop_intro  — Switch to Shop & Pay"),
    (seg_10_shop_search, "10_shop_search — Search Amazon product"),
    (seg_11_shop_result, "11_shop_result — Show product + price + link"),
    (seg_12_shop_purchase, "12_purchase  — Confirm & buy gift card"),
    (seg_13_innovation,  "13_innovation  — Innovation recap"),
    (seg_14_close,       "14_close       — Closing + GitHub"),
]

if __name__ == "__main__":
    print("\n╔══════════════════════════════════════════╗")
    print("║   Value Router — Demo Video Recorder     ║")
    print("╚══════════════════════════════════════════╝\n")

    # Pre-flight checks
    if not os.path.isdir(VOX) or not os.listdir(VOX):
        print("ERROR: Run python3 voiceover.py first to generate audio segments.")
        sys.exit(1)

    try:
        import pyautogui
    except ImportError:
        print("ERROR: pip3 install pyautogui")
        sys.exit(1)

    print("Opening Chrome to landing page...")
    subprocess.run(["open", "-a", "Google Chrome", APP_URL])
    time.sleep(3)

    # Full-screen Chrome for clean recording
    subprocess.run(["osascript", "-e", """
        tell application "Google Chrome"
            activate
            set bounds of front window to {0, 0, 1512, 982}
        end tell
    """], capture_output=True)
    time.sleep(1)

    print("Starting screen recording (ffmpeg)...")
    recorder = start_recording()
    print("  Recording started.\n")

    for i, (fn, label) in enumerate(SEGMENTS):
        print(f"  [{i+1:02d}/{len(SEGMENTS)}] {label}")
        try:
            fn()
        except Exception as e:
            print(f"         ⚠ segment error: {e} — continuing")
        time.sleep(0.8)  # Natural pause between segments

    print("\nStopping screen recording...")
    stop_recording(recorder)
    print("  Saved:", SCREEN_RAW)

    print("\nConcatenating audio segments...")
    concat_audio()
    print("  Saved:", AUDIO_CONCAT)

    print("\nMerging video + audio...")
    merge()

    size_mb = os.path.getsize(FINAL) / 1_000_000
    print(f"\n✓ Done!  {FINAL}  ({size_mb:.1f} MB)")
    print("\nNext steps:")
    print("  1. Watch demo_final.mp4 to review")
    print("  2. Upload to YouTube (unlisted)")
    print("  3. Update YOUR_DEMO_LINK in index.html and README.md")
    print("  4. Submit to hackathon\n")

    # Open the video
    subprocess.run(["open", FINAL])
