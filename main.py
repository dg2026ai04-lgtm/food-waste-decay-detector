# main.py - 에탄올+CO₂ 종합 분석으로 호흡 종류 자동 판별 + LED 경고 시스템
from machine import Pin, SoftI2C, ADC
import utime
import network
import socket
from scd30 import SCD30

# ── 모바일 핫스팟 (2.4GHz) 정보 입력 ──────────────────
SSID = "WiFi_Name"      
PASSWORD = "WiFi_Password"

# ── 하드웨어 핀 설정 ──────────────────────────────────
led_green = Pin(16, Pin.OUT)  # D16 (초록 LED: 유기호흡=정상)
led_red = Pin(18, Pin.OUT)    # D18 (빨간 LED: 무기호흡=경고)
mq2_sensor = ADC(26)          # A0 (에탄올 센서)

i2c = SoftI2C(sda=Pin(8, Pin.PULL_UP), scl=Pin(9, Pin.PULL_UP), freq=20000)

# ── 판별 기준값 (실험하며 조정 가능) ──────────────────
CO2_ACTIVE_LIMIT = 800.0      # 이 값 이상이면 "분해 활동 중"으로 판단
ETHANOL_WARN_LIMIT = 500.0    # 이 값 이상이면 "에탄올 발생=무기호흡"으로 판단

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

# ── 측정값 및 그래프용 로그 ──
data = {"temp": 0.0, "humid": 0.0, "co2": 0.0, "ethanol": 100.0,
        "co2_log": [], "ethanol_log": [], "respiration": "WAITING"}
MAX_LOG = 15

# ── 센서 측정 + 호흡 종류 판별 알고리즘 ──
def update_sensor_data():
    raw_gas = mq2_sensor.read_u16()
    # 에탄올 농도 변환 (100~2000 ppm)
    if raw_gas < 5000:
        ethanol_ppm = 100.0
    else:
        ethanol_ppm = 100.0 + ((raw_gas - 5000) / (65535 - 5000)) * 1900.0
        if ethanol_ppm > 2000.0: ethanol_ppm = 2000.0
    
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
    
    # 그래프 로그 갱신
    data["co2_log"].append(round(co2, 1))
    data["ethanol_log"].append(round(ethanol_ppm, 1))
    if len(data["co2_log"]) > MAX_LOG:
        data["co2_log"].pop(0)
        data["ethanol_log"].pop(0)
    
    # ★★★ 핵심: 에탄올 + CO₂ 종합 분석으로 호흡 종류 판별 ★★★
    is_decomposing = co2 > CO2_ACTIVE_LIMIT      # CO₂로 분해 활동 여부 확인 (SCD30 활용!)
    has_ethanol = ethanol_ppm > ETHANOL_WARN_LIMIT  # 에탄올 발생 여부 확인 (MQ-2 활용!)
    
    if is_decomposing and has_ethanol:
        # CO₂도 높고 에탄올도 높음 → 무기호흡(혐기성 발효)!
        data["respiration"] = "ANAEROBIC"
        led_green.value(0)
        led_red.value(1)   # 🚨 빨간 LED 경고 점등!
    elif is_decomposing and not has_ethanol:
        # CO₂는 높은데 에탄올은 낮음 → 유기호흡(호기성)! 정상
        data["respiration"] = "AEROBIC"
        led_green.value(1)  # ✅ 초록 LED 점등
        led_red.value(0)
    else:
        # 둘 다 낮음 → 아직 분해 활동 미미
        data["respiration"] = "WAITING"
        led_green.value(0)
        led_red.value(0)
    
    print(f"CO2:{co2:.0f} 에탄올:{ethanol_ppm:.0f}ppm → 판정:{data['respiration']}")

# ── SVG 그래프 ──
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

# ── 페이지 생성 ──
def make_page():
    uptime = utime.ticks_ms() // 1000
    resp = data["respiration"]
    
    # 호흡 종류 판정에 따른 화면 표시
    if resp == "ANAEROBIC":
        verdict = "🚨 무기호흡 감지! (부패 진행)"
        verdict_color = "#EF4444"
        verdict_desc = "에탄올이 검출되었습니다! 산소가 부족하여 혐기성 발효(부패)가 일어나고 있습니다."
    elif resp == "AEROBIC":
        verdict = "♻️ 유기호흡 진행 중 (정상 퇴비화)"
        verdict_color = "#10B981"
        verdict_desc = "CO₂는 발생하지만 에탄올이 없습니다! 산소가 충분한 건강한 호기성 분해 상태입니다."
    else:
        verdict = "💨 분해 대기 상태"
        verdict_color = "#64748B"
        verdict_desc = "아직 미생물의 분해 활동이 활발하지 않습니다. 측정을 계속 진행해주세요."

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="3">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>호흡 종류 자동 판별 시스템</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, 'Segoe UI', sans-serif; background: #0f0f23; color: #ccc; padding: 20px; min-height: 100vh; }}
        .header {{ text-align: center; padding: 15px 0; margin-bottom: 15px; }}
        .header h1 {{ color: #00d4ff; font-size: 1.5em; margin-bottom: 5px; }}
        .header p {{ color: #888; font-size: 0.85em; }}
        .verdict {{ background: {verdict_color}; color: white; border-radius: 14px; padding: 20px; text-align: center; max-width: 550px; margin: 15px auto; box-shadow: 0 4px 15px rgba(0,0,0,0.4); }}
        .verdict .title {{ font-size: 1.4em; font-weight: bold; margin-bottom: 8px; }}
        .verdict .desc {{ font-size: 0.85em; opacity: 0.95; line-height: 1.4; }}
        .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; max-width: 550px; margin: 15px auto; }}
        .card {{ background: #1a1a3e; border-radius: 12px; padding: 18px; text-align: center; border: 1px solid #2a2a5e; }}
        .card.ethanol {{ border: 2px solid #F59E0B; }}
        .card .icon {{ font-size: 1.8em; margin-bottom: 8px; }}
        .card .label {{ color: #888; font-size: 0.8em; margin-bottom: 4px; }}
        .card .value {{ color: #00d4ff; font-size: 1.4em; font-weight: bold; }}
        .graph-box {{ background: #1a1a3e; border-radius: 12px; padding: 18px; max-width: 550px; margin: 12px auto; border: 1px solid #2a2a5e; }}
        .footer {{ text-align: center; margin-top: 25px; color: #444; font-size: 0.8em; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🔬 미생물 호흡 종류 자동 판별기</h1>
        <p>에탄올 + CO₂ 종합 분석 시스템 | 가동 {uptime}초</p>
    </div>
    
    <!-- ★ 호흡 종류 자동 판정 결과 배너 ★ -->
    <div class="verdict">
        <div class="title">{verdict}</div>
        <div class="desc">{verdict_desc}</div>
    </div>
    
    <div class="grid">
        <div class="card"><div class="icon">🌫️</div><div class="label">CO₂ 농도 (분해 지표)</div><div class="value">{data['co2']:.0f} ppm</div></div>
        <div class="card ethanol"><div class="icon">🍷</div><div class="label" style="color:#F59E0B; font-weight:bold;">에탄올 (호흡 판별 핵심!)</div><div class="value" style="color:#F59E0B;">{data['ethanol']:.0f} ppm</div></div>
        <div class="card"><div class="icon">🌡️</div><div class="label">내부 온도</div><div class="value">{data['temp']:.1f} °C</div></div>
        <div class="card"><div class="icon">💧</div><div class="label">내부 습도</div><div class="value">{data['humid']:.1f} %</div></div>
    </div>
    
    <div class="graph-box">
        {make_svg_graph(data['co2_log'], '#00d4ff', 2000, '🌫️ CO₂ 농도 변화 (유기·무기호흡 공통 증가)')}
    </div>
    <div class="graph-box">
        {make_svg_graph(data['ethanol_log'], '#F59E0B', 2000, '🍷 에탄올 변화 (무기호흡일 때만 증가!)')}
    </div>
    
    <div class="footer">
        💡 판별 원리: CO₂↑ & 에탄올↑ = 무기호흡 / CO₂↑ & 에탄올≈0 = 유기호흡<br>
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
print(f"  👉 호흡 판별 시스템 주소: http://{my_ip}")
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
        try: client.close()
        except: pass
