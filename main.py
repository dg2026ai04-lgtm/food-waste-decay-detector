

from machine import I2C, Pin
from scd30 import SCD30
import time

# I2C 통신 초기화 (GP8, GP9 사용)
# *참고: SCD30은 클럭 스트레칭(Clock Stretching)을 요구하므로, I2C 통신 속도를
# 안정적인 50kHz(50000)로 설정하는 것이 좋습니다.
i2c = I2C(0, sda=Pin(8), scl=Pin(9), freq=50000)

print("SCD30 센서를 검색하고 있습니다...")

try:
    # SCD30 객체 생성 (기본 I2C 주소는 0x61입니다)
    sensor = SCD30(i2c, addr=0x61)
    print("SCD30 센서 연결 성공!")
except SCD30.NotFoundException:
    print("에러: SCD30 센서를 찾을 수 없습니다. 배선을 확인해 주세요.")
    while True:
        time.sleep(1)

# 연속 측정 시작 (매개변수로 주변 기압(mBar)을 넣어 고도 보정을 할 수도 있습니다)
sensor.start_cont_measure()
print("실시간 대기질 측정을 시작합니다...")
time.sleep(2)

while True:
    # 센서가 새로운 데이터를 측정 완료했는지 확인
    if sensor.get_status_ready():
        try:
            # CO2(ppm), 온도(°C), 습도(%) 데이터 읽기
            co2, temp, humi = sensor.read_measurement()
           
            print("-" * 50)
            print(f"💨 CO2 농도 : {co2:.1f} ppm")
            print(f"🌡️ 현재 온도 : {temp:.1f} °C")
            print(f"💧 상대 습도 : {humi:.1f} %")
           
            # 실내 환기 가이드라인 예시
            if co2 > 1000:
                print("🚨 주의: 이산화탄소 수치가 높습니다. 환기가 필요합니다!")
               
        except SCD30.CRCException:
            print("⚠️ 경고: 통신 중 데이터 패킷 CRC 오류가 발생했습니다.")
    else:
        print("데이터 대기 중...")
       
    time.sleep(2) # SCD30은 약 2초마다 새로운 데이터를 갱신합니다.
