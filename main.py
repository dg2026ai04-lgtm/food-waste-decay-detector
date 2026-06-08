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
        .food-img { width: 100%; height: 150px; object-fit: cover; border-radius: 14px; margin-bottom: 20px; }
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
        <img class="food-img" src="https://images.unsplash.com/photo-1542838132-92c53300491e?w=500&q=80" alt="음식물">
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
    
    # ★ 상태별 비주얼 연출 (음식 사진 + 애니메이션) ★
    if resp == "ANAEROBIC":
        verdict = "🚨 무기호흡 감지! (부패 진행)"
        bg_gradient = "linear-gradient(135deg, #ffcccc, #ff9999)"
        verdict_bg = "#ff5252"
        accent = "#d32f2f"
        led_info = "🔴 빨간 LED 깜빡임 (경보!)"
        food_img = "https://images.unsplash.com/photo-1605493725784-56b1b2c8b48f?w=500&q=80"
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
        food_img = "https://images.unsplash.com/photo-1591857177580-dc82b9ac4e1e?w=500&q=80"
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
        food_img = "https://images.unsplash.com/photo-1542838132-92c53300491e?w=500&q=80"
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
        .top-img {{ width: 100%; max-width: 550px; height: 160px; object-fit: cover; border-radius: 16px; margin: 0 auto 12px; display: block; box-shadow: 0 4px 15px rgba(0,0,0,0.2); }}
        .header {{ text-align: center; padding: 5px 0; margin-bottom: 12px; }}
        .header h1 {{ color: {accent}; font-size: 1.5em; margin-bottom: 5px; }}
        
        /* 애니메이션 무대 */
        .scene {{ position: relative; width: 100%; max-width: 550px; height: 140px; margin: 0 auto 14px; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.1); }}
        .scene.fresh {{ background: linear-gradient(180deg, #c8e6c9, #81c784); }}
        .scene.rotten {{ background: linear-gradient(180deg, #8d6e63, #5d4037); }}
        .scene.waiting {{ background: linear-gradient(180deg, #eeeeee, #bdbdbd); display: flex; flex-direction: column; align-items: center; justify-content: center; }}
        
        /* 유기호흡: 새싹과 반짝이 */
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
        
        /* 무기호흡: 독가스와 파리 */
        .rot-emoji {{ position: absolute; bottom: 10px; left: 50%; transform: translateX(-50%); font-size: 3em; animation: shake 0.5s infinite; }}
        @keyframes shake {{ 0%,100% {{ transform: translateX(-50%) rotate(-3deg); }} 50% {{ transform: translateX(-50%) rotate(3deg); }} }}
        .gas {{ position: absolute; font-size: 1.6em; animation: rise 3s ease-in infinite; opacity: 0; }}
        .g1 {{ left: 35%; animation-delay: 0s; }}
        .g2 {{ left: 55%; animation-delay: 1s; }}
        .g3 {{ left: 45%; animation-delay: 2s; }}
        @keyframes rise {{ 0% {{ bottom: 40px; opacity: 0; }} 30% {{ opacity: 0.9; }} 100% {{ bottom: 120px; opacity: 0; }} }}
        
        /* 파리 3마리 지그재그 비행 */
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
    <img class="top-img" src="{food_img}" alt="음식물 상태">
    
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
        
        # ★ 측정 시작 요청 처리 (리다이렉트 기법으로 무한 리셋 방지!) ★
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
                client.sendall(header.encode())   # ★ sendall 사용!
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
        client.sendall(header.encode())           # ★ sendall 사용!
        # ★ 긴 데이터를 끊김 없이 256바이트씩 확실하게 전송! ★
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
