from machine import Pin, SoftI2C, ADC
import utime
import network
import socket
from scd30 import SCD30
from neopixel import NeoPixel

# ── 모바일 핫스팟 (2.4GHz) 정보 입력 ──────────────────
SSID = "WiFi_Name"      
PASSWORD = "WiFi_Password"

# ── WS2813 네오픽셀 LED 설정 (D16 = GP16) ──────────────
NEOPIXEL_PIN = 16
NUM_LEDS = 10
WS2813_TIMING = (280, 515, 515, 745)
np = NeoPixel(Pin(NEOPIXEL_PIN), NUM_LEDS, timing=WS2813_TIMING)
LED_BRIGHTNESS = 0.3

# ── 기타 하드웨어 핀 설정 ──────────────────────────────
mq2_sensor = ADC(26)

i2c = SoftI2C(sda=Pin(8, Pin.PULL_UP), scl=Pin(9, Pin.PULL_UP), freq=20000)

CO2_ACTIVE_LIMIT = 800.0      
ETHANOL_WARN_LIMIT = 500.0    

# ── WS2813 네오픽셀 제어 함수들 ──────────────────────
def set_all_leds(r, g, b):
    r = int(r * LED_BRIGHTNESS)
    g = int(g * LED_BRIGHTNESS)
    b = int(b * LED_BRIGHTNESS)
    for i in range(NUM_LEDS):
        np[i] = (r, g, b)
    np.write()

def wheel(pos):
    if pos < 85:
        return (255 - pos * 3, pos * 3, 0)
    elif pos < 170:
        pos -= 85
        return (0, 255 - pos * 3, pos * 3)
    else:
        pos -= 170
        return (pos * 3, 0, 255 - pos * 3)

rainbow_pos = 0

def rainbow_cycle():
    global rainbow_pos
    for i in range(NUM_LEDS):
        color = wheel((i * 256 // NUM_LEDS + rainbow_pos) & 255)
        r = int(color[0] * LED_BRIGHTNESS)
        g = int(color[1] * LED_BRIGHTNESS)
        b = int(color[2] * LED_BRIGHTNESS)
        np[i] = (r, g, b)
    np.write()
    rainbow_pos = (rainbow_pos + 8) & 255

def update_leds(respiration, is_connected, blink):
    if not is_connected:
        rainbow_cycle()
    elif respiration == "ANAEROBIC":
        if blink:
            set_all_leds(255, 0, 0)
        else:
            set_all_leds(0, 0, 0)
    elif respiration == "AEROBIC":
        set_all_leds(0, 255, 0)
    else:
        set_all_leds(0, 80, 255)

# ── 부팅 시 LED 무지개 테스트 ──
print(">> 🌈 LED 테스트 중...")
for _ in range(30):
    rainbow_cycle()
    utime.sleep_ms(30)

scd_sensor = None
try:
    devices = i2c.scan()
    if 0x61 in devices:
        scd_sensor = SCD30(i2c, addr=0x61, pause=1500)
        utime.sleep_ms(100)
        scd_sensor.start_cont_measure()
        print(">> ✅ SCD30 센서 가동 완료!")
except Exception as e:
    print(">> ❌ 센서 에러:", e)

# ── 와이파이 연결 ──────────────────────────
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect(SSID, PASSWORD)
print("와이파이 연결 중...")
max_wait = 15
while max_wait > 0:
    if wlan.isconnected():
        break
    max_wait -= 1
    print(".", end="")
    rainbow_cycle()
    utime.sleep(1)

if wlan.isconnected():
    my_ip = wlan.ifconfig()[0]
    print(f"\n✅ 연결 성공! 접속 주소: http://{my_ip}")
    set_all_leds(0, 80, 255)
else:
    my_ip = "127.0.0.1"
    print("\n❌ 와이파이 연결 실패")

# ── 측정값 및 시간축 데이터 저장 ──
data = {"temp": 0.0, "humid": 0.0, "co2": 0.0, "ethanol": 100.0,
        "co2_log": [], "ethanol_log": [], "time_log": [], "respiration": "WAITING"}

# ── 측정 시간 관리 변수 ──
MAX_POINTS = 30
total_minutes = 0
is_measuring = False
just_started = False
start_time = 0
save_interval = 10
last_save_time = 0
blink_state = False

# ── 센서 측정 + 호흡 판별 ──
def update_sensor_data():
    global blink_state, is_measuring, last_save_time, just_started
    raw_gas = mq2_sensor.read_u16()
    if raw_gas < 5000:
        ethanol_ppm = 100.0
    else:
        ethanol_ppm = 100.0 + ((raw_gas - 5000) / (65535 - 5000)) * 1900.0
        if ethanol_ppm > 2000.0:
            ethanol_ppm = 2000.0
    
    co2, temp, humid = data["co2"], data["temp"], data["humid"]
    if scd_sensor is not None:
        try:
            if scd_sensor.get_status_ready():
                co2, temp, humid = scd_sensor.read_measurement()
        except Exception as e:
            print("센서 읽기 오류:", e)
    
    data["temp"] = temp
    data["humid"] = humid
    data["co2"] = co2
    data["ethanol"] = ethanol_ppm
    
    is_decomposing = co2 > CO2_ACTIVE_LIMIT
    has_ethanol = ethanol_ppm > ETHANOL_WARN_LIMIT
    blink_state = not blink_state
    
    if is_decomposing and has_ethanol:
        data["respiration"] = "ANAEROBIC"
    elif is_decomposing and not has_ethanol:
        data["respiration"] = "AEROBIC"
    else:
        data["respiration"] = "WAITING"
    
    update_leds(data["respiration"], wlan.isconnected(), blink_state)
    
    if is_measuring:
        now = utime.ticks_ms()
        elapsed_sec = utime.ticks_diff(now, start_time) // 1000
        
        if just_started or (utime.ticks_diff(now, last_save_time) >= save_interval * 1000):
            just_started = False
            last_save_time = now
            elapsed_min = elapsed_sec / 60
            data["co2_log"].append(round(co2, 1))
            data["ethanol_log"].append(round(ethanol_ppm, 1))
            data["time_log"].append(round(elapsed_min, 1))
            print(f"[기록] {elapsed_min:.1f}분 | CO2:{co2:.0f} 에탄올:{ethanol_ppm:.0f}")
        
        if elapsed_sec >= total_minutes * 60:
            is_measuring = False
            print(f">> ⏰ {total_minutes}분 측정 완료!")
    
    print(f"CO2:{co2:.0f} 에탄올:{ethanol_ppm:.0f}ppm → {data['respiration']}")

# ── 시간축 SVG 그래프 (직전 값 비교로 상승/하강 정확 판별!) ──
def make_time_graph(value_log, time_log, color, max_val, label, unit):
    if len(value_log) < 2:
        return f'<div style="color:#999; font-size:0.85em; padding:20px; text-align:center;">⏳ 잠시만 기다려 주세요 (두 번째 데이터 수집 후 그래프가 나타납니다)</div>'
    
    width = 320
    height = 120
    margin_x = 10
    margin_top = 15
    margin_bottom = 15
    
    data_min = min(value_log)
    data_max = max(value_log)
    
    value_range = data_max - data_min
    if value_range < 20:
        center = (data_max + data_min) / 2
        data_min = center - 15
        data_max = center + 15
        value_range = data_max - data_min
    
    y_min = data_min - value_range * 0.2
    y_max = data_max + value_range * 0.2
    y_range = y_max - y_min
    if y_range == 0:
        y_range = 1
    
    graph_h = height - margin_top - margin_bottom
    graph_w = width - 2 * margin_x
    max_time = time_log[-1] if time_log[-1] > 0 else 1
    
    points = []
    circles = ""
    for i, val in enumerate(value_log):
        x = margin_x + (time_log[i] / max_time) * graph_w
        y = margin_top + graph_h - ((val - y_min) / y_range) * graph_h
        y = max(margin_top, min(y, margin_top + graph_h))
        points.append(f"{x:.1f},{y:.1f}")
        circles += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="{color}"/>'
    
    polyline = " ".join(points)
    
    first_x = margin_x
    last_x = margin_x + graph_w
    bottom_y = margin_top + graph_h
    fill_points = f"{first_x:.1f},{bottom_y:.1f} " + polyline + f" {last_x:.1f},{bottom_y:.1f}"
    
    grid_lines = ""
    y_labels = ""
    for ratio in [0, 0.5, 1.0]:
        gy = margin_top + graph_h * ratio
        grid_lines += f'<line x1="{margin_x}" y1="{gy:.1f}" x2="{last_x:.1f}" y2="{gy:.1f}" stroke="#e8e8e8" stroke-width="1"/>'
        label_val = y_max - (y_max - y_min) * ratio
        y_labels += f'<text x="{margin_x + 2}" y="{gy - 2:.1f}" font-size="8" fill="#aaa">{label_val:.0f}</text>'
    
    start_val = value_log[0]
    end_val = value_log[-1]
    prev_val = value_log[-2]
    recent_change = end_val - prev_val
    
    if recent_change > 1:
        change_text = f'<span style="color:#e53935; font-weight:bold;">▲ 상승 중 ({end_val:.0f}{unit})</span>'
    elif recent_change < -1:
        change_text = f'<span style="color:#1e88e5; font-weight:bold;">▼ 하강 중 ({end_val:.0f}{unit})</span>'
    else:
        change_text = f'<span style="color:#888; font-weight:bold;">― 유지 ({end_val:.0f}{unit})</span>'
    
    return f'''<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:5px;">
        <span style="color:{color}; font-size:0.9em; font-weight:bold;">{label}</span>
        <span style="font-size:0.8em;">{change_text}</span>
    </div>
    <svg width="100%" height="{height}" viewBox="0 0 {width} {height}" style="background:#fafafa; border-radius:8px; border:1px solid #e0e0e0;">
        {grid_lines}
        <polygon points="{fill_points}" fill="{color}" opacity="0.12"/>
        <polyline points="{polyline}" fill="none" stroke="{color}" stroke-width="3"/>
        {circles}
        {y_labels}
    </svg>
    <div style="display:flex; justify-content:space-between; color:#888; font-size:0.7em; margin-top:3px;">
        <span>⏱️ 0분 (시작: {start_val:.0f}{unit})</span>
        <span>{max_time:.1f}분 (현재: {end_val:.0f}{unit})</span>
    </div>'''
    # ── 측정 시간 입력 페이지 ──
def make_setup_page():
    return """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>측정 시간 설정</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, 'Segoe UI', sans-serif; background: linear-gradient(135deg, #e3f2fd, #bbdefb); color: #333; padding: 20px; min-height: 100vh; display: flex; flex-direction: column; justify-content: center; align-items: center; }
        .setup-box { background: white; border-radius: 20px; padding: 40px; max-width: 450px; width: 100%; box-shadow: 0 8px 25px rgba(0,0,0,0.1); text-align: center; }
        .food-emoji { font-size: 4em; margin-bottom: 15px; }
        h1 { color: #1976d2; font-size: 1.6em; margin-bottom: 10px; }
        p { color: #777; font-size: 0.9em; margin-bottom: 25px; }
        .time-btns { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 20px; }
        .time-btn { background: #e3f2fd; color: #1976d2; border: 2px solid #90caf9; border-radius: 12px; padding: 18px; text-decoration: none; font-size: 1.1em; font-weight: bold; transition: all 0.2s; }
        .time-btn:active { background: #1976d2; color: white; }
        .custom-form { margin-top: 20px; padding-top: 20px; border-top: 1px solid #eee; }
        .custom-form input { width: 100px; padding: 12px; border: 2px solid #90caf9; border-radius: 10px; font-size: 1.1em; text-align: center; }
        .custom-form button { background: #1976d2; color: white; border: none; border-radius: 10px; padding: 12px 25px; font-size: 1em; font-weight: bold; margin-left: 8px; cursor: pointer; }
    </style>
</head>
<body>
    <div class="setup-box">
        <div class="food-emoji">🍎🥬🍌</div>
        <h1>🔬 측정 시간 설정</h1>
        <p>미생물 호흡 측정을 몇 분 동안 진행할까요?</p>
        <div class="time-btns">
            <a href="/start?min=5" class="time-btn">⏱️ 5분</a>
            <a href="/start?min=10" class="time-btn">⏱️ 10분</a>
            <a href="/start?min=30" class="time-btn">⏱️ 30분</a>
            <a href="/start?min=60" class="time-btn">⏱️ 60분</a>
        </div>
        <div class="custom-form">
            <form action="/start" method="get">
                <input type="number" name="min" placeholder="직접 입력" min="1" max="600" required>
                <button type="submit">측정 시작 ▶</button>
            </form>
            <p style="margin-top:10px; font-size:0.75em;">단위: 분 (1~600분 입력 가능)</p>
        </div>
    </div>
</body>
</html>"""

# ── 측정 진행 및 대시보드 화면 ──
def make_measure_page():
    uptime = utime.ticks_ms() // 1000
    resp = data["respiration"]
    
    if is_measuring:
        elapsed = utime.ticks_diff(utime.ticks_ms(), start_time) // 1000
        elapsed_min = elapsed / 60
        remain_min = max(0.0, total_minutes - elapsed_min)
        progress = min(100, (elapsed / (total_minutes * 60)) * 100)
        time_info = f"⏱️ {elapsed_min:.1f}분 경과 / 총 {total_minutes}분 (남은 시간: {remain_min:.1f}분)"
        measuring_badge = "🟢 측정 중"
    else:
        progress = 100
        time_info = f"✅ {total_minutes}분 측정 완료!"
        measuring_badge = "⏹️ 측정 종료"
    
    # ★ 상태별 귀여운 캐릭터 일러스트 (SVG로 직접 그림!) ★
    if resp == "ANAEROBIC":
        verdict = "🚨 무기호흡 감지! (부패 진행)"
        bg_gradient = "linear-gradient(135deg, #ffcccc, #ff9999)"
        verdict_bg = "#ff5252"
        accent = "#d32f2f"
        led_info = "🔴 빨간 LED 깜빡임 (경보!)"
        top_visual = '''<div class="top-illust rotten-top">
            <svg viewBox="0 0 120 100" width="90" height="75">
                <ellipse cx="60" cy="60" rx="35" ry="33" fill="#8d9440"/>
                <ellipse cx="48" cy="55" rx="8" ry="10" fill="#5d6428" opacity="0.6"/>
                <ellipse cx="72" cy="68" rx="6" ry="7" fill="#5d6428" opacity="0.6"/>
                <circle cx="50" cy="52" r="5" fill="white"/>
                <circle cx="70" cy="52" r="5" fill="white"/>
                <circle cx="50" cy="54" r="2.5" fill="#333"/>
                <circle cx="70" cy="54" r="2.5" fill="#333"/>
                <path d="M50 72 Q60 65 70 72" stroke="#444" stroke-width="2.5" fill="none"/>
                <path d="M40 45 Q43 42 46 45" stroke="#5d6428" stroke-width="2" fill="none"/>
                <ellipse cx="42" cy="62" rx="3" ry="4" fill="#7ec8e3" opacity="0.7"/>
                <path d="M60 28 Q58 20 62 22" stroke="#6b4423" stroke-width="3" fill="none"/>
                <text x="92" y="35" font-size="14">🪰</text>
                <text x="18" y="40" font-size="12">💨</text>
            </svg>
            <div class="illust-text">부패 중...</div>
        </div>'''
        scene = """
        <div class="scene rotten">
            <div class="rot-emoji">🍎</div>
            <div class="gas g1">🤢</div>
            <div class="gas g2">💨</div>
            <div class="gas g3">☠️</div>
            <div class="fly fly1">🪰</div>
            <div class="fly fly2">🪰</div>
            <div class="fly fly3">🪰</div>
        </div>"""
    elif resp == "AEROBIC":
        verdict = "♻️ 유기호흡 진행 중 (정상 퇴비화)"
        bg_gradient = "linear-gradient(135deg, #e8f5e9, #a5d6a7)"
        verdict_bg = "#4caf50"
        accent = "#2e7d32"
        led_info = "🟢 초록 LED 점등 (정상)"
        top_visual = '''<div class="top-illust fresh-top">
            <svg viewBox="0 0 120 100" width="90" height="75">
                <ellipse cx="60" cy="60" rx="35" ry="33" fill="#a5d66f"/>
                <circle cx="49" cy="55" r="6" fill="white"/>
                <circle cx="71" cy="55" r="6" fill="white"/>
                <circle cx="50" cy="56" r="3" fill="#333"/>
                <circle cx="72" cy="56" r="3" fill="#333"/>
                <circle cx="51" cy="55" r="1" fill="white"/>
                <circle cx="73" cy="55" r="1" fill="white"/>
                <path d="M48 68 Q60 78 72 68" stroke="#333" stroke-width="2.5" fill="none"/>
                <circle cx="42" cy="64" r="4" fill="#ff9eb0" opacity="0.6"/>
                <circle cx="78" cy="64" r="4" fill="#ff9eb0" opacity="0.6"/>
                <path d="M55 28 Q53 18 58 22 Q60 16 62 22 Q67 18 65 28" fill="#4caf50"/>
                <text x="92" y="35" font-size="14">✨</text>
                <text x="15" y="40" font-size="14">🌟</text>
            </svg>
            <div class="illust-text">건강하게 분해 중!</div>
        </div>'''
        scene = """
        <div class="scene fresh">
            <div class="pile">🍂🪵🍂</div>
            <div class="sprout s1">🌱</div>
            <div class="sprout s2">🌿</div>
            <div class="sprout s3">🌱</div>
            <div class="sparkle sp1">✨</div>
            <div class="sparkle sp2">🌟</div>
            <div class="sparkle sp3">✨</div>
        </div>"""
    else:
        verdict = "💨 분해 대기 상태"
        bg_gradient = "linear-gradient(135deg, #f5f5f5, #e0e0e0)"
        verdict_bg = "#9e9e9e"
        accent = "#616161"
        led_info = "🔵 파란 LED (대기 중)"
        top_visual = '''<div class="top-illust">
            <svg viewBox="0 0 120 100" width="90" height="75">
                <ellipse cx="60" cy="60" rx="35" ry="33" fill="#bdbdbd"/>
                <circle cx="49" cy="55" r="5" fill="white"/>
                <circle cx="71" cy="55" r="5" fill="white"/>
                <circle cx="50" cy="55" r="2.5" fill="#333"/>
                <circle cx="72" cy="55" r="2.5" fill="#333"/>
                <line x1="48" y1="70" x2="72" y2="70" stroke="#333" stroke-width="2.5"/>
                <text x="90" y="35" font-size="14">💤</text>
            </svg>
            <div class="illust-text">측정 대기 중...</div>
        </div>'''
        scene = """
        <div class="scene waiting">
            <div class="wait-emoji">🍱</div>
            <div class="wait-text">측정 대기 중...</div>
        </div>"""

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="3">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>측정 진행 중</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, 'Segoe UI', sans-serif; background: {bg_gradient}; color: #333; padding: 20px; min-height: 100vh; transition: background 0.8s ease; }}
        
        /* 상단 귀여운 캐릭터 일러스트 */
        .top-illust {{ width: 100%; max-width: 550px; min-height: 130px; margin: 0 auto 12px; display: flex; flex-direction: column; align-items: center; justify-content: center; border-radius: 16px; box-shadow: 0 4px 15px rgba(0,0,0,0.15); background: white; padding: 12px; }}
        .illust-text {{ font-weight: bold; font-size: 0.95em; margin-top: 4px; color: #555; }}
        .fresh-top {{ background: linear-gradient(135deg, #e8f5e9, #a5d6a7); }}
        .fresh-top .illust-text {{ color: #2e7d32; }}
        .rotten-top {{ background: linear-gradient(135deg, #d7ccc8, #a1887f); animation: rotten-shake 0.6s infinite; }}
        .rotten-top .illust-text {{ color: #5d4037; }}
        @keyframes rotten-shake {{ 0%,100% {{ transform: rotate(-1deg); }} 50% {{ transform: rotate(1deg); }} }}
        
        .header {{ text-align: center; padding: 5px 0; margin-bottom: 12px; }}
        .header h1 {{ color: {accent}; font-size: 1.5em; margin-bottom: 5px; }}
        
        .scene {{ position: relative; width: 100%; max-width: 550px; height: 140px; margin: 0 auto 14px; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.1); }}
        .scene.fresh {{ background: linear-gradient(180deg, #c8e6c9, #81c784); }}
        .scene.rotten {{ background: linear-gradient(180deg, #8d6e63, #5d4037); }}
        .scene.waiting {{ background: linear-gradient(180deg, #eeeeee, #bdbdbd); display: flex; flex-direction: column; align-items: center; justify-content: center; }}
        
        .pile {{ position: absolute; bottom: 5px; left: 50%; transform: translateX(-50%); font-size: 2.5em; }}
        .sprout {{ position: absolute; bottom: 25px; font-size: 1.8em; animation: grow 2s ease-in-out infinite; }}
        .s1 {{ left: 30%; animation-delay: 0s; }}
        .s2 {{ left: 50%; animation-delay: 0.5s; }}
        .s3 {{ left: 65%; animation-delay: 1s; }}
        @keyframes grow {{ 0%,100% {{ transform: translateY(0) scale(1); }} 50% {{ transform: translateY(-8px) scale(1.15); }} }}
        .sparkle {{ position: absolute; font-size: 1.3em; animation: twinkle 1.5s ease-in-out infinite; }}
        .sp1 {{ top: 20px; left: 20%; animation-delay: 0s; }}
        .sp2 {{ top: 30px; left: 60%; animation-delay: 0.5s; }}
        .sp3 {{ top: 15px; left: 80%; animation-delay: 1s; }}
        @keyframes twinkle {{ 0%,100% {{ opacity: 0.2; transform: scale(0.8); }} 50% {{ opacity: 1; transform: scale(1.3); }} }}
        
        .rot-emoji {{ position: absolute; bottom: 10px; left: 50%; transform: translateX(-50%); font-size: 3em; animation: shake 0.5s infinite; }}
        @keyframes shake {{ 0%,100% {{ transform: translateX(-50%) rotate(-3deg); }} 50% {{ transform: translateX(-50%) rotate(3deg); }} }}
        .gas {{ position: absolute; font-size: 1.6em; animation: rise 3s ease-in infinite; opacity: 0; }}
        .g1 {{ left: 35%; animation-delay: 0s; }}
        .g2 {{ left: 55%; animation-delay: 1s; }}
        .g3 {{ left: 45%; animation-delay: 2s; }}
        @keyframes rise {{ 0% {{ bottom: 40px; opacity: 0; }} 30% {{ opacity: 0.9; }} 100% {{ bottom: 120px; opacity: 0; }} }}
        
        .fly {{ position: absolute; font-size: 1.4em; }}
        .fly1 {{ animation: buzz1 4s linear infinite; }}
        .fly2 {{ animation: buzz2 5s linear infinite; }}
        .fly3 {{ animation: buzz3 3.5s linear infinite; }}
        @keyframes buzz1 {{ 0% {{ left: 10%; top: 20px; }} 25% {{ left: 70%; top: 60px; }} 50% {{ left: 40%; top: 10px; }} 75% {{ left: 80%; top: 80px; }} 100% {{ left: 10%; top: 20px; }} }}
        @keyframes buzz2 {{ 0% {{ left: 80%; top: 70px; }} 25% {{ left: 20%; top: 30px; }} 50% {{ left: 60%; top: 90px; }} 75% {{ left: 30%; top: 50px; }} 100% {{ left: 80%; top: 70px; }} }}
        @keyframes buzz3 {{ 0% {{ left: 50%; top: 50px; }} 33% {{ left: 15%; top: 80px; }} 66% {{ left: 85%; top: 20px; }} 100% {{ left: 50%; top: 50px; }} }}
        
        .wait-emoji {{ font-size: 3em; }}
        .wait-text {{ color: #757575; font-weight: bold; margin-top: 8px; }}
        
        .time-bar {{ background: white; border-radius: 14px; padding: 15px; max-width: 550px; margin: 10px auto; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }}
        .time-info {{ color: {accent}; font-size: 0.95em; font-weight: bold; text-align: center; margin-bottom: 10px; }}
        .progress-bg {{ background: #e0e0e0; border-radius: 10px; height: 14px; overflow: hidden; }}
        .progress-fill {{ background: {verdict_bg}; height: 100%; width: {progress:.0f}%; border-radius: 10px; transition: width 0.5s; }}
        .verdict {{ background: {verdict_bg}; color: white; border-radius: 16px; padding: 18px; text-align: center; max-width: 550px; margin: 12px auto; box-shadow: 0 6px 18px rgba(0,0,0,0.15); }}
        .verdict .title {{ font-size: 1.3em; font-weight: bold; }}
        .led-badge {{ background: white; border-radius: 12px; padding: 12px; max-width: 550px; margin: 10px auto; text-align: center; box-shadow: 0 4px 12px rgba(0,0,0,0.08); color: {accent}; font-weight: bold; font-size: 0.9em; }}
        .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; max-width: 550px; margin: 12px auto; }}
        .card {{ background: white; border-radius: 14px; padding: 16px; text-align: center; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }}
        .card.ethanol {{ border: 2px solid #ff9800; }}
        .card .icon {{ font-size: 1.6em; margin-bottom: 6px; }}
        .card .label {{ color: #888; font-size: 0.75em; margin-bottom: 4px; }}
        .card .value {{ color: {accent}; font-size: 1.4em; font-weight: bold; }}
        .card.ethanol .value {{ color: #ff9800; }}
        .graph-box {{ background: white; border-radius: 14px; padding: 18px; max-width: 550px; margin: 12px auto; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }}
        .new-btn {{ display: block; text-align: center; background: {accent}; color: white; text-decoration: none; padding: 14px; border-radius: 12px; max-width: 550px; margin: 15px auto; font-weight: bold; }}
        .footer {{ text-align: center; margin-top: 20px; color: #888; font-size: 0.8em; }}
    </style>
</head>
<body>
    {top_visual}
    
    <div class="header">
        <h1>🔬 미생물 호흡 측정 중</h1>
    </div>
    
    {scene}
    
    <div class="time-bar">
        <div class="time-info">{time_info}</div>
        <div class="progress-bg"><div class="progress-fill"></div></div>
    </div>
    
    <div class="verdict">
        <div class="title">{verdict}</div>
    </div>
    
    <div class="led-badge">💡 현재 LED 상태: {led_info}</div>
    
    <div class="grid">
        <div class="card"><div class="icon">🌫️</div><div class="label">CO₂ 농도</div><div class="value">{data['co2']:.0f} ppm</div></div>
        <div class="card ethanol"><div class="icon">🍷</div><div class="label">에탄올</div><div class="value">{data['ethanol']:.0f} ppm</div></div>
        <div class="card"><div class="icon">🌡️</div><div class="label">온도</div><div class="value">{data['temp']:.1f}°C</div></div>
        <div class="card"><div class="icon">💧</div><div class="label">습도</div><div class="value">{data['humid']:.1f}%</div></div>
    </div>
    
    <div class="graph-box">
        {make_time_graph(data['co2_log'], data['time_log'], '#2196f3', 2000, '🌫️ CO₂ 농도 변화 (시간축)', 'ppm')}
    </div>
    <div class="graph-box">
        {make_time_graph(data['ethanol_log'], data['time_log'], '#ff9800', 2000, '🍷 에탄올 변화 (시간축)', 'ppm')}
    </div>
    
    <a href="/" class="new-btn">🔄 새로운 측정 시작하기</a>
    
    <div class="footer">
        {measuring_badge} | 데이터 저장 간격: {save_interval}초<br>
        Powered by MicroPython on Pico 2 WH | 당곡고 환경과학 프로젝트
    </div>
</body>
</html>"""

# ── 웹서버 시작 ─────────────────────────────
server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(('0.0.0.0', 80))
server.listen(2)
server.settimeout(1.0)

print()
print("=" * 45)
print(f"  👉 접속 주소: http://{my_ip}")
print("=" * 45)

while True:
    update_sensor_data()
    
    try:
        client, addr = server.accept()
        request = client.recv(1024)
        req_str = request.decode()
        if 'favicon' in req_str:
            client.close()
            continue
        
        if 'GET /start?min=' in req_str:
            try:
                min_str = req_str.split('min=')[1].split(' ')[0].split('&')[0]
                total_minutes = int(min_str)
                save_interval = max(2, (total_minutes * 60) // MAX_POINTS)
                
                data["co2_log"] = []
                data["ethanol_log"] = []
                data["time_log"] = []
                
                is_measuring = True
                just_started = True
                start_time = utime.ticks_ms()
                last_save_time = utime.ticks_ms()
                
                print(f">> ▶ {total_minutes}분 측정 시작! (저장 간격: {save_interval}초)")
                
                header = "HTTP/1.1 303 See Other\r\n"
                header += "Location: /measure\r\n"
                header += "Connection: close\r\n\r\n"
                client.sendall(header.encode())
                client.close()
                continue
            except Exception as e:
                print("측정 시작 오류:", e)
                page = make_setup_page()
                
        elif 'GET /measure' in req_str:
            page = make_measure_page()
            
        elif 'GET / ' in req_str or 'GET /index' in req_str:
            is_measuring = False
            page = make_setup_page()
        else:
            page = make_measure_page()
        
        page_bytes = page.encode('utf-8')
        header = "HTTP/1.1 200 OK\r\n"
        header += "Content-Type: text/html; charset=utf-8\r\n"
        header += "Content-Length: " + str(len(page_bytes)) + "\r\n"
        header += "Cache-Control: no-store, no-cache, must-revalidate, max-age=0\r\n"
        header += "Connection: close\r\n\r\n"
        client.sendall(header.encode())
        for i in range(0, len(page_bytes), 256):
            client.sendall(page_bytes[i:i+256])
        client.close()
        
    except OSError:
        pass
    except Exception as e:
        print(f"⚠️ 서버 오류: {e}")
        try:
            client.close()
        except:
            pass
