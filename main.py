# main.py - Pico 2 WH & Grove Shield 최적화 IoT 웹서버 코드
from machine import Pin, SoftI2C, ADC
import utime
import network
import socket
from scd30 import SCD30  # 우리가 저장한 scd30.py 호출 [1]

# ── [중요] 모바일 핫스팟 (2.4GHz) 정보 입력 ──────────────────
SSID = "senWiFi_Free_sky"      
PASSWORD = "sudo25sky@"

# ── 하드웨어 및 캐리어 보드 핀 설정 ──────────────────────────────────
# 1. LED 설정: D16(초록 LED), D18(빨간 LED)에 대응
led_green = Pin(16, Pin.OUT)  # D16 핀 (내부 GP16)
led_red = Pin(18, Pin.OUT)    # D18 핀 (내부 GP18)

# 2. MQ-2 가스 센서: A0에 대응
mq2_sensor = ADC(26)          # A0 핀 (내부 GP26 / ADC0)

# 3. SCD30 센서: I2C0에 대응
# 클록 스트레칭을 정밀 제어하기 위해 소프트웨어 I2C 사용 (GP8/SDA, GP9/SCL)
i2c = SoftI2C(
    sda=Pin(8, Pin.PULL_UP), 
    scl=Pin(9, Pin.PULL_UP), 
    freq=20000
)

# 판별 알고리즘 임계값 설정
CO2_COMPOST_LIMIT = 800.0  
GAS_ROTTEN_LIMIT = 22000    

scd_sensor = None
try:
    print(">> I2C 버스 스캔 가동 중 (I2C0 포트 / GP8, GP9)...")
    devices = i2c.scan()
    print(">> 감지된 16진수 I2C 주소들:", [hex(d) for d in devices])
    
    if 0x61 in devices:
        # 제공해주신 정밀 클래스로 연결 가동
        scd_sensor = SCD30(i2c, addr=0x61, pause=1500)
        utime.sleep_ms(100)
        scd_sensor.start_cont_measure()  # SCD30 측정 시작 명령 송출
        print(">> ✅ 정밀 SCD30 센서 가동 및 수립 완료!")
    else:
        print(">> ⚠️ 여전히 SCD30 센서가 감지되지 않습니다. I2C0 자리에 확실히 꽂았는지 확인해 주세요.")
except SCD30.NotFoundException:
    print(">> ⚠️ 예외 발생: SCD30 장치를 발견하지 못했습니다.")
except Exception as e:
    print(">> ❌ 초기화 중 에러 발생:", e)

# ── 와이파이 연결 프로세스 (모바일 핫스팟 연결 확인) ──────────────────
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect(SSID, PASSWORD)

print("와이파이에 연결하는 중입니다...")
max_wait = 15
while max_wait > 0:
    if wlan.isconnected():
        break
    max_wait -= 1
    print(".", end="")
    utime.sleep(1)

if wlan.isconnected():
    my_ip = wlan.ifconfig()[0]
    print("\n✅ 와이파이 연결 성공!")
    print(f"IP 주소: {my_ip}")
else:
    my_ip = "127.0.0.1"
    print("\n❌ 와이파이 연결 실패. 핫스팟 이름과 비번, 그리고 2.4GHz 설정인지 확인해 주세요.")

# ── HTML 페이지 동적 생성 함수 ──────────────────────
def make_page(temp, humid, co2, gas_val, status, rssi, uptime):
    if status == "ROTTEN":
        status_text = "🚨 부패 및 악취 발생!"
        status_color = "#EF4444"
    elif status == "COMPOSTING":
        status_text = "♻️ 친환경 퇴비화 진행 중"
        status_color = "#10B981"
    else:
        status_text = "💨 초기 분해 대기 상태"
        status_color = "#64748B"

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="3">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>당곡고 스마트 에코 모니터</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, 'Segoe UI', sans-serif;
            background: #0f0f23;
            color: #ccc;
            padding: 20px;
            min-height: 100vh;
        }}
        .header {{ text-align: center; padding: 20px 0; }}
        .header h1 {{ color: #00d4ff; font-size: 1.6em; margin-bottom: 5px; }}
        .header p {{ color: #888; font-size: 0.9em; }}
        .status-banner {{
            background: {status_color};
            color: white;
            border-radius: 12px;
            padding: 15px;
            text-align: center;
            font-size: 1.3em;
            font-weight: bold;
            max-width: 500px;
            margin: 10px auto;
            box-shadow: 0 4px 10px rgba(0,0,0,0.3);
        }}
        .grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
            max-width: 500px;
            margin: 15px auto;
        }}
        .card {{
            background: #1a1a3e;
            border-radius: 12px;
            padding: 18px;
            text-align: center;
            border: 1px solid #2a2a5e;
        }}
        .card.wide {{ grid-column: span 2; }}
        .card .icon {{ font-size: 1.8em; margin-bottom: 8px; }}
        .card .label {{ color: #888; font-size: 0.8em; margin-bottom: 4px; }}
        .card .value {{ color: #00d4ff; font-size: 1.4em; font-weight: bold; }}
        .footer {{ text-align: center; margin-top: 30px; color: #444; font-size: 0.8em; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🌱 에코 밀폐 용기 모니터 🌱</h1>
        <p>친환경 퇴비화 vs 부패 판별기 (Pico 2 WH)</p>
    </div>

    <div class="status-banner">
        {status_text}
    </div>

    <div class="grid">
        <div class="card">
            <div class="icon">🌡️</div>
            <div class="label">내부 온도</div>
            <div class="value">{temp:.1f} °C</div>
        </div>
        <div class="card">
            <div class="icon">💧</div>
            <div class="label">내부 습도</div>
            <div class="value">{humid:.1f} %</div>
        </div>
        <div class="card">
            <div class="icon">🌫️</div>
            <div class="label">CO2 농도</div>
            <div class="value">{co2:.1f} ppm</div>
        </div>
        <div class="card">
            <div class="icon">💨</div>
            <div class="label">악취 가스 수치</div>
            <div class="value">{gas_val}</div>
        </div>
        <div class="card">
            <div class="icon">📶</div>
            <div class="label">Wi-Fi 신호</div>
            <div class="value">{rssi} dBm</div>
        </div>
        <div class="card">
            <div class="icon">⏱️</div>
            <div class="label">가동 시간</div>
            <div class="value">{uptime}초</div>
        </div>
        <div class="card wide">
            <div class="label" style="color: #64748B;">이 페이지는 3초마다 자동으로 갱신됩니다.</div>
        </div>
    </div>

    <div class="footer">
        Powered by MicroPython on Pico 2 WH | 당곡고 환경과학 프로젝트
    </div>
</body>
</html>"""

# ── 웹서버 시작 ─────────────────────────────
server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(('0.0.0.0', 80))
server.listen(2)

print()
print("=" * 45)
print(f"  ✅ 웹서버 구동 완료! 접속 주소:")
print(f"  👉 http://{my_ip}")
print("=" * 45)

while True:
    try:
        client, addr = server.accept()
        request = client.recv(1024)

        req_str = request.decode()
        if 'favicon' in req_str:
            client.close()
            continue

        print(f"💻 기기 접속: {addr[0]}")
        
        # 1. MQ-2 아날로그 가스 수집
        gas_val = mq2_sensor.read_u16()
        
        # 2. SCD30 데이터 수집 (안전 예외 처리 적용)
        co2, temp, humid = 0.0, 0.0, 0.0
        
        if scd_sensor is not None:
            try:
                # 제공해주신 라이브러리의 감지 상태 판별 및 읽기 메서드 실행
                if scd_sensor.get_status_ready():
                    co2, temp, humid = scd_sensor.read_measurement()
            except Exception as read_err:
                print("SCD30 데이터 수신 실패:", read_err)
                
        # 3. 환경 판단 알고리즘
        status_str = "STANDBY"
        if gas_val > GAS_ROTTEN_LIMIT:
            status_str = "ROTTEN"
            led_green.value(0)
            led_red.value(1)
        elif co2 > CO2_COMPOST_LIMIT and gas_val <= GAS_ROTTEN_LIMIT:
            status_str = "COMPOSTING"
            led_green.value(1)
            led_red.value(0)
        else:
            status_str = "STANDBY"
            led_green.value(0)
            led_red.value(0)
            
        rssi = wlan.status('rssi') if wlan.isconnected() else 0
        uptime = utime.ticks_ms() // 1000

        # 동적 HTML 전송
        page = make_page(temp, humid, co2, gas_val, status_str, rssi, uptime)
        client.send(b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nConnection: close\r\n\r\n")
        client.send(page.encode('utf-8'))
        client.close()

    except Exception as e:
        print(f"⚠️ 서버 내부 오류: {e}")
        try:
            client.close()
        except:
            pass
