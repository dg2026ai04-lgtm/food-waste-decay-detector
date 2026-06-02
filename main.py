# main.py - 모드 설정형 단일 측정 + 그래프 버전
from machine import Pin, SoftI2C, ADC
import utime
import network
import socket
from scd30 import SCD30

# ★★★★★ 여기만 바꾸세요! ★★★★★
# 호기성(유기호흡) 측정용 피코 → "aerobic"
# 혐기성(무기호흡) 측정용 피코 → "anaerobic"
MODE = "aerobic"   
# ★★★★★★★★★★★★★★★★★★★★★★

# ── 모바일 핫스팟 (2.4GHz) 정보 입력 ──────────────────
SSID = "WiFi_Name"      
PASSWORD = "WiFi_Password"

# ── 하드웨어 핀 설정 ──────────────────────────────────
led_green = Pin(16, Pin.OUT)  # D16
led_red = Pin(18, Pin.OUT)    # D18
mq2_sensor = ADC(26)          # A0

i2c = SoftI2C(sda=Pin(8, Pin.PULL_UP), scl=Pin(9, Pin.PULL_UP), freq=20000)

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
    print(f"\n✅ 연결 성공! 접속 주소: http://{my_ip}")
else:
    my_ip = "127.0.0.1"
    print("\n❌ 와이파이 연결 실패")

# ── 측정값 및 그래프용 로그 저장 ──
data = {"temp": 0.0, "humid": 0.0, "co2": 0.0, "gas": 0,
        "temp_log": [], "co2_log": [], "gas_log": []}
MAX_LOG = 15  # 그래프에 표시할 데이터 개수

# ── 센서 측정 함수 ──
def update_sensor_data():
    gas_val = mq2_sensor.read_u16()
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
    data["gas"] = gas_val
    
    # 그래프 로그 갱신
    data["temp_log"].append(round(temp, 1))
    data["co2_log"].append(round(co2, 1))
    data["gas_log"].append(gas_val)
    if len(data["temp_log"]) > MAX_LOG:
        data["temp_log"].pop(0)
        data["co2_log"].pop(0)
        data["gas_log"].pop(0)
    
    # LED 제어
    if gas_val > GAS_ROTTEN_LIMIT:
        led_green.value(0)
        led_red.value(1)
    elif co2 > CO2_ACTIVE_LIMIT:
        led_green.value(1)
        led_red.value(0)
    else:
        led_green.value(0)
        led_red.value(0)
    
    print(f"[{MODE}] 온도:{temp:.1f} 습도:{humid:.1f} CO2:{co2:.1f} 가스:{gas_val}")

# ── SVG 그래프 생성 함수 ──
def make_svg_graph(data_log, color, max_val, label):
    if len(data_log) < 2:
        return f'<div style="color:#555; font-size:0.8em; padding:15px; text-align:center;">데이터 수집 중...</div>'
    
    width = 300
    height = 80
    points = []
    n = len(data_log)
    for i, val in enumerate(data_log):
        x = (i / (n - 1)) * width
        y = height - (min(val, max_val) / max_val) * height
        points.append(f"{x:.0f},{y:.0f}")
    
    polyline = " ".join(points)
    return f'''<div style="margin-bottom:5px; color:{color}; font-size:0.8em; font-weight:bold;">{label}</div>
    <svg width="100%" height="{height}" viewBox="0 0 {width} {height}" preserveAspectRatio="none" style="background:#0a0a1a; border-radius:8px;">
        <polyline points="{polyline}" fill="none" stroke="{color}" stroke-width="2"/>
    </svg>'''

# ── 페이지 생성 함수 ──
def make_page():
    rssi = wlan.status('rssi') if wlan.isconnected() else 0
    uptime = utime.ticks_ms() // 1000
    
    # 모드별 디자인 설정
    if MODE == "aerobic":
        title = "🌬️ 호기성 호흡 (유기호흡)"
        sub = "산소(O₂) 있는 환경 · 친환경 퇴비화 측정"
        accent = "#10B981"
        if data["gas"] > GAS_ROTTEN_LIMIT:
            status_text, status_color = "⚠️ 이상! 악취 발생", "#EF4444"
        elif data["co2"] > CO2_ACTIVE_LIMIT:
            status_text, status_color = "♻️ 정상! 퇴비화 활발", "#10B981"
        else:
            status_text, status_color = "💨 분해 대기 상태", "#64748B"
    else:
        title = "🦠 혐기성 호흡 (무기호흡)"
        sub = "산소(O₂) 없는 환경 · 부패/악취 측정"
        accent = "#EF4444"
        if data["gas"] > GAS_ROTTEN_LIMIT:
            status_text, status_color = "🚨 부패 진행! 악취 발생", "#EF4444"
        elif data["co2"] > CO2_ACTIVE_LIMIT:
            status_text, status_color = "🔄 혐기성 분해 진행 중", "#F59E0B"
        else:
            status_text, status_color = "💨 분해 대기 상태", "#64748B"

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="3">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, 'Segoe UI', sans-serif; background: #0f0f23; color: #ccc; padding: 20px; min-height: 100vh; }}
        .header {{ text-align: center; padding: 15px 0; border-bottom: 3px solid {accent}; margin-bottom: 20px; }}
        .header h1 {{ color: {accent}; font-size: 1.6em; margin-bottom: 5px; }}
        .header p {{ color: #888; font-size: 0.9em; }}
        .status-banner {{ background: {status_color}; color: white; border-radius: 12px; padding: 15px; text-align: center; font-size: 1.3em; font-weight: bold; max-width: 550px; margin: 10px auto; box-shadow: 0 4px 10px rgba(0,0,0,0.3); }}
        .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; max-width: 550px; margin: 15px auto; }}
        .card {{ background: #1a1a3e; border-radius: 12px; padding: 18px; text-align: center; border: 1px solid #2a2a5e; }}
        .card .icon {{ font-size: 1.8em; margin-bottom: 8px; }}
        .card .label {{ color: #888; font-size: 0.8em; margin-bottom: 4px; }}
        .card .value {{ color: #00d4ff; font-size: 1.4em; font-weight: bold; }}
        .graph-box {{ background: #1a1a3e; border-radius: 12px; padding: 18px; max-width: 550px; margin: 12px auto; border: 1px solid #2a2a5e; }}
        .footer {{ text-align: center; margin-top: 25px; color: #444; font-size: 0.8em; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{title}</h1>
        <p>{sub}</p>
    </div>
    
    <div class="status-banner">{status_text}</div>
    
    <div class="grid">
        <div class="card"><div class="icon">🌡️</div><div class="label">내부 온도</div><div class="value">{data['temp']:.1f} °C</div></div>
        <div class="card"><div class="icon">💧</div><div class="label">내부 습도</div><div class="value">{data['humid']:.1f} %</div></div>
        <div class="card"><div class="icon">🌫️</div><div class="label">CO₂ 농도</div><div class="value">{data['co2']:.1f} ppm</div></div>
        <div class="card"><div class="icon">💨</div><div class="label">악취 가스</div><div class="value">{data['gas']}</div></div>
    </div>
    
    <div class="graph-box">
        {make_svg_graph(data['co2_log'], '#00d4ff', 2000, '📈 CO₂ 농도 변화 추이')}
    </div>
    <div class="graph-box">
        {make_svg_graph(data['gas_log'], '#F59E0B', 40000, '📈 악취 가스 변화 추이')}
    </div>
    <div class="graph-box">
        {make_svg_graph(data['temp_log'], '#10B981', 50, '📈 온도 변화 추이')}
    </div>
    
    <div class="footer">
        가동 시간 {uptime}초 | Wi-Fi 신호 {rssi}dBm<br>
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
print(f"  ✅ [{MODE}] 모드 웹서버 구동! 접속: http://{my_ip}")
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
        
        page = make_page()
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
