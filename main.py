from machine import Pin, SoftI2C, ADC
import utime
import network
import socket
from scd30 import SCD30
from neopixel import NeoPixel

# ── 모바일 핫스팟 (2.4GHz) 정보 입력 ──────────────────
# ★ 아래 두 줄을 본인 핫스팟 정보로 수정하세요! (따옴표는 남겨두기)
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

# ── 시간축 SVG 그래프 (작은 변화도 잘 보이는 안정 버전) ──
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
    change = end_val - start_val
    
    if change > 0:
        change_text = f'<span style="color:#e53935; font-weight:bold;">▲ {abs(change):.0f}{unit} 상승</span>'
    elif change < 0:
        change_text = f'<span style="color:#1e88e5; font-weight:bold;">▼ {abs(change):.0f}{unit} 하강</span>'
    else:
        change_text = f'<span style="color:#888;">― 변화 없음</span>'
    
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
    
