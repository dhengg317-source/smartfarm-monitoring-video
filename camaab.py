import time
import requests
import os
from datetime import datetime
from dotenv import load_dotenv              # 1. dotenv 불러오기
from supabase import create_client, Client

# ==========================================
# 1. 설정 정보 (.env 파일 및 환경변수 로드)
# ==========================================
load_dotenv()                               # .env 파일 읽기 (로컬 테스트용)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# 환경 변수에서 ESP32_IP를 불러오되, 없으면 지정된 외부/내부 주소를 사용
ESP32_IP = os.getenv("ESP32_IP", "http://camaafarm.iptime.org:8080")

# URL 자동 보정 (http:// 또는 https:// 가 없는 경우 추가)
if ESP32_IP and not ESP32_IP.startswith("http://") and not ESP32_IP.startswith("https://"):
    ESP32_IP = f"http://{ESP32_IP}"

# URL 끝의 슬래시(/) 제거 처리
ESP32_IP = ESP32_IP.rstrip("/")

SAVE_INTERVAL = 600  # 10분(600초) 간격 저장 (로컬 무한루프용)

# Supabase 클라이언트 초기화
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def collect_and_sync():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 수집 프로세스 시작...")
    
    temp, humi = 0.0, 0.0
    
    # 1. 온습도 센서 데이터 요청 (/status)
    try:
        status_res = requests.get(f"{ESP32_IP}/status", timeout=5)
        if status_res.status_code == 200:
            sensor_data = status_res.json()
            temp = sensor_data.get("temp", 0.0)
            humi = sensor_data.get("humi", 0.0)
            print(f"✅ 센서 수집 성공: 온도 {temp}°C / 습도 {humi}%")
    except Exception as e:
        print(f"⚠️ 센서 수집 경고 (카메라 단독 모드 시 무시): {e}")

    # 2. 5분 주기 스냅샷 이미지 요청 (/jpg)
    try:
        img_res = requests.get(f"{ESP32_IP}/jpg", timeout=5)
        if img_res.status_code == 200:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_name = f"farm_{timestamp}.jpg"

            # Supabase Storage 업로드
            supabase.storage.from_("smartfarm-images").upload(
                path=file_name,
                file=img_res.content,
                file_options={"content-type": "image/jpeg"}
            )
            
            # 이미지 Public URL 획득
            public_url = supabase.storage.from_("smartfarm-images").get_public_url(file_name)

            # Supabase Database(PostgreSQL)에 로그 삽입
            # (만약 테이블명이 camaa_data라면 해당 테이블명으로 자동 호환/작동하도록 기존 작성 유지)
            supabase.table("farm_logs").insert({
                "node_id": "zone_01",
                "temp": temp,
                "humi": humi,
                "image_url": public_url,
                "created_at": datetime.now().isoformat()
            }).execute()

            print(f"✅ [저장 완료] 온도: {temp}°C | 습도: {humi}% | URL: {public_url}")

    except Exception as e:
        print(f"❌ 데이터 저장 중 오류 발생: {e}")

if __name__ == "__main__":
    # GitHub Actions 단발성 실행 시 1회 수집 후 종료
    # 로컬 수동 실행 시에는 while 문을 통해 주기적 수집 수행
    if os.getenv("GITHUB_ACTIONS"):
        print("🚀 [GitHub Actions] 스마트팜 수집 스크립트 1회 실행")
        collect_and_sync()
    else:
        print("🚀 스마트팜 백엔드 수집 스크립트 실행 중... (Ctrl+C 로 종료)")
        while True:
            collect_and_sync()
            time.sleep(SAVE_INTERVAL)