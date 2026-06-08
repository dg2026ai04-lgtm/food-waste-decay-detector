from machine import Pin, SoftI2C, ADC
import utime
import network
import socket
from scd30 import SCD30

# ── 모바일 핫스팟 (2.4GHz) 정보 입력 ──────────────────
SSID = "WiFi_Name"      
PASSWORD = "WiFi_Password"

# ── 하드웨어 핀 설정 ──────────────────────────────────
led_green = Pin(16, Pin.OUT)
led_red = Pin(18, Pin.OUT)
mq2_sensor = ADC(26)

i2c = SoftI2C(sda=Pin(8, Pin.PULL_UP), scl=Pin(9, Pin.PULL_UP), freq=20000)

CO2_ACTIVE_LIMIT = 800.0      
ETHANOL_WARN_LIMIT = 500.0    

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
    utime.sleep(1)

if wlan.isconnected():
    my_ip = wlan.ifconfig()[0]
    print(f"\n✅ 연결 성공! 접속 주소: http://{my_ip}")
else:
    my_ip = "127.0.0.1"
    print("\n❌ 와이파이 연결 실패")

# ── 측정값 및 시간축 데이터 저장 ──
data = {"temp": 0.0, "humid": 0.0, "co2": 0.0, "ethanol": 100.0,
        "co2_log": [], "ethanol_log": [], "time_log": [], "respiration": "WAITING"}

# ── 측정 시간 관리 변수 ──
MAX_POINTS = 30          # 그래프에 표시할 최대 데이터 개수
total_minutes = 0        # 사용자가 설정한 총 측정 시간(분)
is_measuring = False     # 측정 중인지 여부
start_time = 0           # 측정 시작 시각(ms)
save_interval = 10       # 데이터 저장 간격(초) - 자동 계산됨
last_save_time = 0       # 마지막 저장 시각
blink_state = False

# ── 센서 측정 + 호흡 판별 ──
def update_sensor_data():
    global blink_state, is_measuring, last_save_time
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
    
    # 호흡 판별
    is_decomposing = co2 > CO2_ACTIVE_LIMIT
    has_ethanol = ethanol_ppm > ETHANOL_WARN_LIMIT
    blink_state = not blink_state
    
    if is_decomposing and has_ethanol:
        data["respiration"] = "ANAEROBIC"
        led_green.value(0)
        led_red.value(1 if blink_state else 0)
    elif is_decomposing and not has_ethanol:
        data["respiration"] = "AEROBIC"
        led_green.value(1)
        led_red.value(0)
    else:
        data["respiration"] = "WAITING"
        led_green.value(1 if blink_state else 0)
        led_red.value(0)
    
    # ★ 측정 중일 때만 시간축 데이터 저장 ★
    if is_measuring:
        now = utime.ticks_ms()
        elapsed_sec = utime.ticks_diff(now, start_time) // 1000  # 경과 시간(초)
        
        # 설정한 저장 간격마다 데이터 기록
        if utime.ticks_diff(now, last_save_time) >= save_interval * 1000:
            last_save_time = now
            elapsed_min = elapsed_sec / 60  # 경과 시간(분)
            data["co2_log"].append(round(co2, 1))
            data["ethanol_log"].append(round(ethanol_ppm, 1))
            data["time_log"].append(round(elapsed_min, 1))
            print(f"[기록] {elapsed_min:.1f}분 | CO2:{co2:.0f} 에탄올:{ethanol_ppm:.0f}")
        
        # 설정 시간이 다 되면 측정 자동 종료
        if elapsed_sec >= total_minutes * 60:
            is_measuring = False
            led_green.value(0)
            led_red.value(0)
            print(f">> ⏰ {total_minutes}분 측정 완료!")
    
    print(f"CO2:{co2:.0f} 에탄올:{ethanol_ppm:.0f}ppm → {data['respiration']}")

# ── 시간축 SVG 그래프 (X축에 시간 표시!) ──
def make_time_graph(value_log, time_log, color, max_val, label, unit):
    if len(value_log) < 2:
        return f'<div style="color:#999; font-size:0.85em; padding:20px; text-align:center;">⏳ 측정을 시작하면 그래프가 그려집니다</div>'
    
    width = 320
    height = 100
    margin = 5
    points = []
    n = len(value_log)
    max_time = time_log[-1] if time_log[-1] > 0 else 1
    
    for i, val in enumerate(value_log):
        # X축: 시간 비율, Y축: 값 비율
        x = margin + (time_log[i] / max_time) * (width - 2*margin)
        y = height - margin - (min(val, max_val) / max_val) * (height - 2*margin)
        points.append(f"{x:.0f},{y:.0f}")
    
    polyline = " ".join(points)
    # 시작값과 끝값 표시
    start_val = value_log[0]
    end_val = value_log[-1]
    
    return f'''<div style="margin-bottom:5px; color:{color}; font-size:0.9em; font-weight:bold;">{label}</div>
    <svg width="100%" height="{height}" viewBox="0 0 {width} {height}" style="background:#f8f9fa; border-radius:8px; border:1px solid #e0e0e0;">
        <polyline points="{polyline}" fill="none" stroke="{color}" stroke-width="2.5"/>
    </svg>
    <div style="display:flex; justify-content:space-between; color:#888; font-size:0.7em; margin-top:3px;">
        <span>0분 (시작: {start_val:.0f}{unit})</span>
        <span>{max_time:.1f}분 (현재: {end_val:.0f}{unit})</span>
    </div>'''

# ── 측정 시간 입력 페이지 (시작 화면) ──
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

# ── 측정 진행 화면 ──
def make_measure_page():
    uptime = utime.ticks_ms() // 1000
    resp = data["respiration"]
    
    # 경과 시간 및 남은 시간 계산
    if is_measuring:
        elapsed = utime.ticks_diff(utime.ticks_ms(), start_time) // 1000
        elapsed_min = elapsed / 60
        remain_min = total_minutes - elapsed_min
        progress = min(100, (elapsed / (total_minutes * 60)) * 100)
        time_info = f"⏱️ {elapsed_min:.1f}분 경과 / 총 {total_minutes}분 (남은 시간: {remain_min:.1f}분)"
        measuring_badge = "🟢 측정 중"
    else:
        progress = 100
        time_info = f"✅ {total_minutes}분 측정 완료!"
        measuring_badge = "⏹️ 측정 종료"
    
    # 상태별 배경색
    if resp == "ANAEROBIC":
        verdict = "🚨 무기호흡 감지! (부패)"
        bg_gradient = "linear-gradient(135deg, #ffe5e5, #ffcccc)"
        verdict_bg = "#ff5252"
        accent = "#d32f2f"
    elif resp == "AEROBIC":
        verdict = "♻️ 유기호흡 진행 중 (정상)"
        bg_gradient = "linear-gradient(135deg, #e8f5e9, #c8e6c9)"
        verdict_bg = "#4caf50"
        accent = "#2e7d32"
    else:
        verdict = "💨 분해 대기 상태"
        bg_gradient = "linear-gradient(135deg, #f5f5f5, #e0e0e0)"
        verdict_bg = "#9e9e9e"
        accent = "#616161"

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
        .header {{ text-align: center; padding: 10px 0; margin-bottom: 12px; }}
        .header h1 {{ color: {accent}; font-size: 1.5em; margin-bottom: 5px; }}
        .time-bar {{ background: white; border-radius: 14px; padding: 15px; max-width: 550px; margin: 10px auto; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }}
        .time-info {{ color: {accent}; font-size: 0.95em; font-weight: bold; text-align: center; margin-bottom: 10px; }}
        .progress-bg {{ background: #e0e0e0; border-radius: 10px; height: 14px; overflow: hidden; }}
        .progress-fill {{ background: {verdict_bg}; height: 100%; width: {progress:.0f}%; border-radius: 10px; transition: width 0.5s; }}
        .verdict {{ background: {verdict_bg}; color: white; border-radius: 16px; padding: 18px; text-align: center; max-width: 550px; margin: 12px auto; box-shadow: 0 6px 18px rgba(0,0,0,0.15); }}
        .verdict .title {{ font-size: 1.3em; font-weight: bold; }}
        .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; max-width: 550px; margin: 12px auto; }}
        .card {{ background: white; border-radius: 14px; padding: 16px; text-align: center; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }}
        .card.ethanol {{ border: 2px solid #ff9800; }}
        .card .icon {{ font-size: 1.6em; margin-bottom: 6px; }}
        .card .label {{ color: #888; font-size: 0.75em; margin-bottom: 4px; }}
        .card .value {{ color: {accent}; font-size: 1.4em; font-weight: bold; }}
        .card.ethanol .value {{ color: #ff9800; }}
        .graph-box {{ background: white; border-radius: 14px; padding: 18px; max-width: 550px; margin: 12px auto; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }}
        .new-btn {{ display: block; text-align: center; background: {accent}; color: white; text-decoration: none; padding: 14px; border-radius: 12px; max-width: 550px; margin: 15px auto; font-weight: bold; }}
        .footer {{ text-align: center; margin-top: 20px; color: #aaa; font-size: 0.8em; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🔬 미생물 호흡 측정 중</h1>
    </div>
    
    <div class="time-bar">
        <div class="time-info">{time_info}</div>
        <div class="progress-bg"><div class="progress-fill"></div></div>
    </div>
    
    <div class="verdict">
        <div class="title">{verdict}</div>
    </div>
    
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
        
        # ★ 측정 시작 요청 처리 ★
        if 'GET /start?min=' in req_str:
            try:
                # URL에서 측정 시간(분) 추출
                min_str = req_str.split('min=')[1].split(' ')[0].split('&')[0]
                total_minutes = int(min_str)
                
                # 측정 시간에 따라 저장 간격 자동 계산 (최대 30개 점)
                save_interval = max(2, (total_minutes * 60) // MAX_POINTS)
                
                # 측정 초기화 및 시작
                data["co2_log"] = []
                data["ethanol_log"] = []
                data["time_log"] = []
                is_measuring = True
                start_time = utime.ticks_ms()
                last_save_time = utime.ticks_ms()
                print(f">> ▶ {total_minutes}분 측정 시작! (저장 간격: {save_interval}초)")
                page = make_measure_page()
            except Exception as e:
                print("측정 시작 오류:", e)
                page = make_setup_page()
        elif 'GET /' in req_str and 'GET /start' not in req_str:
            # 홈(설정 화면)으로 가면 측정 중지
            if req_str.split(' ')[1] == '/':
                is_measuring = False
                page = make_setup_page()
            else:
                page = make_measure_page()
        else:
            page = make_measure_page()
        
        header = "HTTP/1.1 200 OK\r\n"
        header += "Content-Type: text/html; charset=utf-8\r\n"
        header += "Cache-Control: no-store, no-cache, must-revalidate, max-age=0\r\n"
        header += "Connection: close\r\n\r\n"
        client.send(header.encode())
        client.send(page.encode('utf-8'))
        client.close()
        
    except OSError:
        pass
    except Exception as e:
        print(f"⚠️ 서버 오류: {e}")
        try:
            client.close()
        except:
            pass
