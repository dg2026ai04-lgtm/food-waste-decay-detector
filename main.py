# main.py - 호기성 vs 혐기성 좌우 비교 + 실시간 그래프 버전
from machine import Pin, SoftI2C, ADC
import utime
import network
import socket
from scd30 import SCD30

# ── 모바일 핫스팟 (2.4GHz) 정보 입력 ──────────────────
SSID = "WiFi_Name"      
PASSWORD = "WiFi_Password"

# ── 하드웨어 핀 설정 ──────────────────────────────────
led_green = Pin(16, Pin.OUT)  # D16
led_red = Pin(18, Pin.OUT)    # D18
mq2_sensor = ADC(26)          # A0

i2c = SoftI2C(sda=Pin(8, Pin.PULL_UP), scl=Pin(9, Pin.PULL_UP), freq=20000)

# ── 판별 임계값 ──────────────────
CO2_ACTIVE_LIMIT = 800.0     
GAS_ROTTEN_LIMIT = 20000     

scd_sensor = None
try:
    devices = i2c.scan()
    print(">> 감지된 주소:", [hex(d) for d in devices])
    if 0x61 in devices:
        scd_sensor = SCD30(i2c, addr=0x61, pause=1500)
        utime.sleep_ms(100)
        scd_sensor.start_cont_measure()
        print(">> ✅ SCD30 센서 가동 완료!")
except Exception as e:
    print(">> ❌ 센서 초기화 에러:", e)

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
    print(f"\n✅ 연결 성공! IP: {my_ip}")
else:
    my_ip = "127.0.0.1"
    print("\n❌ 와이파이 연결 실패")

# ── 호기성/혐기성 각각의 최신값 + 그래프용 기록 저장 ──
# 최근 10개의 측정값을 저장하여 그래프로 그립니다.
aerobic_data = {"temp": 0.0, "humid": 0.0, "co2": 0.0, "gas": 0,
                "temp_log": [], "co2_log": [], "gas_log": []}
anaerobic_data = {"temp": 0.0, "humid": 0.0, "co2": 0.0, "gas": 0,
                  "temp_log": [], "co2_log": [], "gas_log": []}

MAX_LOG = 10  # 그래프에 표시할 최대 데이터 개수

# 현재 어느 쪽을 측정 중인지 ("aerobic" 또는 "anaerobic" 또는 None)
current_target = None

# ── 센서 측정 및 기록 함수 ──
def update_sensor_data(target):
    gas_val = mq2_sensor.read_u16()
    
    data = aerobic_data if target == "aerobic" else anaerobic_data
    co2, temp, humid = data["co2"], data["temp"], data["humid"]
    
    if scd_sensor is not None:
        try:
            if scd_sensor.get_status_ready():
                co2, temp, humid = scd_sensor.read_measurement()
        except Exception as e:
            print("센서 읽기 오류:", e)
    
    # 최신값 갱신
    data["temp"] = temp
    data["humid"] = humid
    data["co2"] = co2
    data["gas"] = gas_val
    
    # 그래프용 로그에 추가 (최대 개수 유지)
    data["temp_log"].append(round(temp, 1))
    data["co2_log"].append(round(co2, 1))
    data["gas_log"].append(gas_val)
    if len(data["temp_log"]) > MAX_LOG:
        data["temp_log"].pop(0)
        data["co2_log"].pop(0)
        data["gas_log"].pop(0)
    
    # LED 제어 (악취 가스 기준)
    if gas_val > GAS_ROTTEN_LIMIT:
        led_green.value(0)
        led_red.value(1)
    elif co2 > CO2_ACTIVE_LIMIT:
        led_green.value(1)
        led_red.value(0)
    else:
        led_green.value(0)
        led_red.value(0)
    
    print(f"[{target}] 온도:{temp:.1f} 습도:{humid:.1f} CO2:{co2:.1f} 가스:{gas_val}")

# ── 그래프(SVG)를 그려주는 함수 ──
def make_svg_graph(data_log, color, max_val, label):
    if len(data_log) < 2:
        return f'<div style="color:#555; font-size:0.75em; padding:10px;">데이터 수집 중...</div>'
    
    width = 200
    height = 60
    points = []
    n = len(data_log)
    for i, val in enumerate(data_log):
        x = (i / (n - 1)) * width
        # 값이 0~max_val 범위라고 가정하고 높이 계산 (위아래 뒤집기)
        y = height - (min(val, max_val) / max_val) * height
        points.append(f"{x:.0f},{y:.0f}")
    
    polyline = " ".join(points)
    return f'''<svg width="100%" height="{height}" viewBox="0 0 {width} {height}" preserveAspectRatio="none" style="background:#0a0a1a; border-radius:6px;">
        <polyline points="{polyline}" fill="none" stroke="{color}" stroke-width="2"/>
    </svg>
    <div style="color:{color}; font-size:0.7em; text-align:center;">{label}</div>'''

# ── 한쪽(호기성 또는 혐기성) 패널 HTML 생성 ──
def make_panel(target, data, is_active):
    if target == "aerobic":
        title = "🌬️ 호기성 (유기호흡)"
        sub = "산소 O₂ 있음 · 퇴비화"
        accent = "#10B981"
    else:
        title = "🦠 혐기성 (무기호흡)"
        sub = "산소 O₂ 없음 · 부패"
        accent = "#EF4444"
    
    # 현재 측정 중인 패널 표시
    active_badge = '<span style="background:#00d4ff; color:#000; padding:2px 8px; border-radius:10px; font-size:0.65em; margin-left:5px;">측정중</span>' if is_active else ''
    
    # 측정 시작 버튼
    btn_label = "■ 측정 정지" if is_active else "▶ 이쪽 측정 시작"
    btn_action = "/stop" if is_active else f"/start_{target}"
    btn_color = "#64748B" if is_active else accent

    return f'''<div style="flex:1; background:#1a1a3e; border-radius:12px; padding:12px; border:2px solid {accent if is_active else '#2a2a5e'};">
        <div style="text-align:center; margin-bottom:10px;">
            <div style="color:{accent}; font-size:1.1em; font-weight:bold;">{title}{active_badge}</div>
            <div style="color:#888; font-size:0.7em;">{sub}</div>
        </div>
        
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:6px; margin-bottom:10px;">
            <div style="background:#0f0f23; border-radius:8px; padding:8px; text-align:center;">
                <div style="color:#888; font-size:0.65em;">🌡️ 온도</div>
                <div style="color:#00d4ff; font-size:1em; font-weight:bold;">{data['temp']:.1f}°C</div>
            </div>
            <div style="background:#0f0f23; border-radius:8px; padding:8px; text-align:center;">
                <div style="color:#888; font-size:0.65em;">💧 습도</div>
                <div style="color:#00d4ff; font-size:1em; font-weight:bold;">{data['humid']:.1f}%</div>
            </div>
            <div style="background:#0f0f23; border-radius:8px; padding:8px; text-align:center;">
                <div style="color:#888; font-size:0.65em;">🌫️ CO₂</div>
                <div style="color:#00d4ff; font-size:1em; font-weight:bold;">{data['co2']:.0f}</div>
            </div>
            <div style="background:#0f0f23; border-radius:8px; padding:8px; text-align:center;">
                <div style="color:#888; font-size:0.65em;">💨 가스</div>
                <div style="color:#00d4ff; font-size:1em; font-weight:bold;">{data['gas']}</div>
            </div>
        </div>
        
        <div style="margin-bottom:8px;">
            {make_svg_graph(data['co2_log'], '#00d4ff', 2000, 'CO₂ 변화 그래프')}
        </div>
        <div style="margin-bottom:10px;">
            {make_svg_graph(data['gas_log'], '#F59E0B', 40000, '악취 가스 변화 그래프')}
        </div>
        
        <a href="{btn_action}" style="display:block; text-align:center; background:{btn_color}; color:white; text-decoration:none; padding:10px; border-radius:8px; font-size:0.85em; font-weight:bold;">{btn_label}</a>
    </div>'''

# ── 메인 비교 페이지 생성 ──────────────────
def make_compare_page():
    rssi = wlan.status('rssi') if wlan.isconnected() else 0
    uptime = utime.ticks_ms() // 1000
    
    left_panel = make_panel("aerobic", aerobic_data, current_target == "aerobic")
    right_panel = make_panel("anaerobic", anaerobic_data, current_target == "anaerobic")

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="3">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>호기성 vs 혐기성 비교</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, 'Segoe UI', sans-serif; background: #0f0f23; color: #ccc; padding: 12px; min-height: 100vh; }}
        .header {{ text-align: center; padding: 10px 0; }}
        .header h1 {{ color: #00d4ff; font-size: 1.3em; margin-bottom: 4px; }}
        .header p {{ color: #888; font-size: 0.8em; }}
        .compare-box {{ display: flex; gap: 10px; max-width: 700px; margin: 15px auto; }}
        .footer {{ text-align: center; margin-top: 15px; color: #555; font-size: 0.75em; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>⚖️ 호기성 vs 혐기성 실시간 비교</h1>
        <p>당곡고 친환경 퇴비화 판별 시스템 | 가동 {uptime}초 | 📶 {rssi}dBm</p>
    </div>
    <div class="compare-box">
        {left_panel}
        {right_panel}
    </div>
    <div class="footer">
        측정할 쪽의 '측정 시작' 버튼을 누르세요. 3초마다 자동 갱신됩니다.<br>
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
print(f"  ✅ 웹서버 구동 완료! 접속 주소: http://{my_ip}")
print("=" * 45)

while True:
    # 측정 대상이 정해져 있으면 계속 그쪽 센서값 갱신
    if current_target is not None:
        update_sensor_data(current_target)
    
    try:
        client, addr = server.accept()
        request = client.recv(1024)
        req_str = request.decode()
        
        if 'favicon' in req_str:
            client.close()
            continue
        
        # ★ 버튼 요청 처리 ★
        if 'GET /start_aerobic' in req_str:
            current_target = "aerobic"
        elif 'GET /start_anaerobic' in req_str:
            current_target = "anaerobic"
        elif 'GET /stop' in req_str:
            current_target = None
            led_green.value(0)
            led_red.value(0)
        
        # 항상 비교 페이지를 보여줌
        page = make_compare_page()
        
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
