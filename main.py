# main.py - [마스터 피코용] 호기성 측정 + 메인 통합 웹서버 대시보드
from machine import Pin, SoftI2C, ADC
import utime
import network
import socket
from scd30 import SCD30

# ── 모바일 핫스팟 (2.4GHz) 정보 입력 ──────────────────
SSID = "WiFi_Name"      
PASSWORD = "WiFi_Password"

# ── 하드웨어 핀 설정 ──────────────────────────────────
led_green = Pin(16, Pin.OUT)  # D16 (초록 LED)
led_red = Pin(18, Pin.OUT)    # D18 (빨간 LED)
mq2_sensor = ADC(26)          # A0 (MQ-2 가스/에탄올 센서)

i2c = SoftI2C(sda=Pin(8, Pin.PULL_UP), scl=Pin(9, Pin.PULL_UP), freq=20000)

CO2_ACTIVE_LIMIT = 800.0     
ETHANOL_ROTTEN_LIMIT = 600.0  

scd_sensor = None
try:
    devices = i2c.scan()
    if 0x61 in devices:
        scd_sensor = SCD30(i2c, addr=0x61, pause=1500)
        utime.sleep_ms(100)
        scd_sensor.start_cont_measure()
        print(">> ✅ 마스터 SCD30 센서 가동 완료!")
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
    print(f"\n✅ 마스터 서버 가동! IP: {my_ip}")
else:
    my_ip = "127.0.0.1"
    print("\n❌ 와이파이 연결 실패")

# ── [핵심 데이터베이스] 양쪽 피코의 데이터를 모두 모아둡니다. ──
aerobic_data = {"temp": 0.0, "humid": 0.0, "co2": 0.0, "ethanol": 100.0, "temp_log": [], "co2_log": [], "ethanol_log": []}
anaerobic_data = {"temp": 0.0, "humid": 0.0, "co2": 0.0, "ethanol": 100.0, "temp_log": [], "co2_log": [], "ethanol_log": []}

MAX_LOG = 10

# ── 마스터 자신의 센서(호기성) 측정 함수 ──
def update_aerobic_sensor():
    raw_gas = mq2_sensor.read_u16()
    if raw_gas < 5000:
        ethanol_ppm = 100.0
    else:
        ethanol_ppm = 100.0 + ((raw_gas - 5000) / (65535 - 5000)) * 1900.0
        if ethanol_ppm > 2000.0: ethanol_ppm = 2000.0
            
    co2, temp, humid = aerobic_data["co2"], aerobic_data["temp"], aerobic_data["humid"]
    if scd_sensor is not None:
        try:
            if scd_sensor.get_status_ready():
                co2, temp, humid = scd_sensor.read_measurement()
        except Exception as e:
            print("센서 읽기 오류:", e)
            
    aerobic_data["temp"] = temp
    aerobic_data["humid"] = humid
    aerobic_data["co2"] = co2
    aerobic_data["ethanol"] = ethanol_ppm
    
    # 로그 추가
    aerobic_data["temp_log"].append(round(temp, 1))
    aerobic_data["co2_log"].append(round(co2, 1))
    aerobic_data["ethanol_log"].append(round(ethanol_ppm, 1))
    if len(aerobic_data["temp_log"]) > MAX_LOG:
        aerobic_data["temp_log"].pop(0)
        aerobic_data["co2_log"].pop(0)
        aerobic_data["ethanol_log"].pop(0)

    # 마스터용 LED 제어 (유기호흡 상태에 맞춤)
    if co2 > CO2_ACTIVE_LIMIT and ethanol_ppm <= ETHANOL_ROTTEN_LIMIT:
        led_green.value(1)
        led_red.value(0)
    else:
        led_green.value(0)
        led_red.value(0)

# 슬레이브로부터 전송받은 혐기성 데이터를 저장하고 로그에 추가하는 함수
def update_anaerobic_data_from_slave(temp, humid, co2, ethanol_ppm):
    anaerobic_data["temp"] = temp
    anaerobic_data["humid"] = humid
    anaerobic_data["co2"] = co2
    anaerobic_data["ethanol"] = ethanol_ppm
    
    anaerobic_data["temp_log"].append(round(temp, 1))
    anaerobic_data["co2_log"].append(round(co2, 1))
    anaerobic_data["ethanol_log"].append(round(ethanol_ppm, 1))
    if len(anaerobic_data["temp_log"]) > MAX_LOG:
        anaerobic_data["temp_log"].pop(0)
        anaerobic_data["co2_log"].pop(0)
        anaerobic_data["ethanol_log"].pop(0)

# ── SVG 그래프 생성기 ──────────────────────
def make_svg_graph(data_log, color, max_val, label):
    if len(data_log) < 2:
        return f'<div style="color:#555; font-size:0.75em; padding:10px; text-align:center;">데이터 수집 중...</div>'
    width = 250
    height = 65
    points = []
    n = len(data_log)
    for i, val in enumerate(data_log):
        x = (i / (n - 1)) * width
        y = height - (min(val, max_val) / max_val) * height
        points.append(f"{x:.0f},{y:.0f}")
    polyline = " ".join(points)
    return f'''<div style="margin-bottom:3px; color:{color}; font-size:0.7em; font-weight:bold;">{label}</div>
    <svg width="100%" height="{height}" viewBox="0 0 {width} {height}" preserveAspectRatio="none" style="background:#0a0a1a; border-radius:6px;">
        <polyline points="{polyline}" fill="none" stroke="{color}" stroke-width="2"/>
    </svg>'''

# ── 동시 비교 웹페이지 생성 ──────────────────
def make_combined_page():
    uptime = utime.ticks_ms() // 1000
    
    # 상태 판정 문구 결정
    ae_status = "♻️ 퇴비화 분해 활발" if aerobic_data["co2"] > CO2_ACTIVE_LIMIT else "💨 대기 상태"
    if aerobic_data["ethanol"] > ETHANOL_ROTTEN_LIMIT: ae_status = "🚨 산소 부족 경보!"
        
    anae_status = "🦠 무기호흡 진행 중" if anaerobic_data["ethanol"] > ETHANOL_ROTTEN_LIMIT else "💨 대기 상태"
    
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="3">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>당곡고 유기호흡 vs 무기호흡 실시간 통합 대시보드</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, 'Segoe UI', sans-serif; background: #0f0f23; color: #ccc; padding: 15px; min-height: 100vh; }}
        .header {{ text-align: center; padding: 10px 0; margin-bottom: 15px; }}
        .header h1 {{ color: #00d4ff; font-size: 1.4em; }}
        .header p {{ color: #888; font-size: 0.8em; margin-top: 3px; }}
        .container {{ display: flex; gap: 12px; max-width: 800px; margin: 0 auto; }}
        .panel {{ flex: 1; background: #1a1a3e; border-radius: 12px; padding: 12px; }}
        .panel.left {{ border: 2px solid #10B981; }}
        .panel.right {{ border: 2px solid #EF4444; }}
        .panel-title {{ font-size: 1.1em; font-weight: bold; text-align: center; margin-bottom: 10px; }}
        .status {{ color: white; border-radius: 8px; padding: 8px; text-align: center; font-size: 0.9em; font-weight: bold; margin-bottom: 10px; }}
        .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-bottom: 10px; }}
        .card {{ background: #0f0f23; border-radius: 8px; padding: 8px; text-align: center; }}
        .card .label {{ color: #888; font-size: 0.65em; }}
        .card .value {{ color: #00d4ff; font-size: 1em; font-weight: bold; }}
        .graph-section {{ margin-top: 10px; }}
        .footer {{ text-align: center; margin-top: 20px; color: #444; font-size: 0.75em; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📊 유기호흡 vs 무기호흡 동시 측정 대시보드</h1>
        <p>실시간 환경 대조 실험 모니터링 시스템 | 가동 시간 {uptime}초</p>
    </div>
    
    <div class="container">
        <!-- 1. 왼쪽 호기성 (유기호흡) 패널 -->
        <div class="panel left">
            <div class="panel-title" style="color: #10B981;">🌬️ 호기성 (유기호흡)</div>
            <div class="status" style="background: #10B981;">{ae_status}</div>
            <div class="grid">
                <div class="card"><div class="label">🌡️ 온도</div><div class="value">{aerobic_data['temp']:.1f}°C</div></div>
                <div class="card"><div class="label">💧 습도</div><div class="value">{aerobic_data['humid']:.1f}%</div></div>
                <div class="card"><div class="label">🌫️ CO₂</div><div class="value">{aerobic_data['co2']:.0f}ppm</div></div>
                <div class="card"><div class="label">🍷 에탄올</div><div class="value" style="color:#F59E0B;">{aerobic_data['ethanol']:.0f}ppm</div></div>
            </div>
            <div class="graph-section">
                {make_svg_graph(aerobic_data['co2_log'], '#00d4ff', 2000, '🌫️ CO₂ 변화')}
            </div>
            <div class="graph-section">
                {make_svg_graph(aerobic_data['ethanol_log'], '#F59E0B', 2000, '🍷 에탄올 변화')}
            </div>
        </div>

        <!-- 2. 오른쪽 혐기성 (무기호흡) 패널 -->
        <div class="panel right">
            <div class="panel-title" style="color: #EF4444;">🦠 혐기성 (무기호흡)</div>
            <div class="status" style="background: #EF4444;">{anae_status}</div>
            <div class="grid">
                <div class="card"><div class="label">🌡️ 온도</div><div class="value">{anaerobic_data['temp']:.1f}°C</div></div>
                <div class="card"><div class="label">💧 습도</div><div class="value">{anaerobic_data['humid']:.1f}%</div></div>
                <div class="card"><div class="label">🌫️ CO₂</div><div class="value">{anaerobic_data['co2']:.0f}ppm</div></div>
                <div class="card"><div class="label">🍷 에탄올</div><div class="value" style="color:#F59E0B;">{anaerobic_data['ethanol']:.0f}ppm</div></div>
            </div>
            <div class="graph-section">
                {make_svg_graph(anaerobic_data['co2_log'], '#00d4ff', 2000, '🌫️ CO₂ 변화')}
            </div>
            <div class="graph-section">
                {make_svg_graph(anaerobic_data['ethanol_log'], '#F59E0B', 2000, '🍷 에탄올 변화')}
            </div>
        </div>
    </div>
    
    <div class="footer">
        3초마다 데이터가 자동 무선 동기화됩니다.<br>
        Powered by MicroPython on Pico 2 WH | 당곡고 환경과학 프로젝트
    </div>
</body>
</html>"""

# ── 웹서버 시작 ─────────────────────────────
server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(('0.0.0.0', 80))
server.listen(5)
server.settimeout(0.5)

print()
print("=" * 55)
print(f"  👉 통합 모니터링 주소: http://{my_ip}")
print("=" * 55)

while True:
    update_aerobic_sensor()  # 마스터(호기성) 자체 센서 측정
    
    try:
        client, addr = server.accept()
        request = client.recv(1024)
        req_str = request.decode()
        
        if 'favicon' in req_str:
            client.close()
            continue
        
        # 1. 슬레이브(혐기성) 피코가 보내온 데이터 파싱 처리
        # 요청 포맷: GET /update?t=25.4&h=60.2&c=450&e=120 HTTP/1.1
        if "GET /update?" in req_str:
            try:
                query = req_str.split("GET /update?")[1].split(" ")[0]
                params = {}
                for item in query.split("&"):
                    k, v = item.split("=")
                    params[k] = float(v)
                
                # 혐기성(슬레이브) 데이터 갱신
                update_anaerobic_data_from_slave(
                    params.get("t", 0.0),
                    params.get("h", 0.0),
                    params.get("c", 0.0),
                    params.get("e", 100.0)
                )
                
                # 슬레이브에겐 가볍게 OK 응답만 줍니다.
                client.send(b"HTTP/1.1 200 OK\r\nConnection: close\r\n\r\nOK")
            except Exception as e:
                print("슬레이브 데이터 수신 오류:", e)
            client.close()
            continue
            
        # 2. 브라우저로 접속한 사용자에겐 동시 비교 화면 대시보드를 보여줍니다.
        page = make_combined_page()
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
        print(f"⚠️ 마스터 서버 오류: {e}")
        try: client.close()
        except: pass
