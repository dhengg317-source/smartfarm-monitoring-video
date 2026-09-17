import time
import requests
import os
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client, Client
import streamlit as st

# ====================================================
# 0. Streamlit 기본 페이지 설정
# ====================================================
st.set_page_config(
    page_title="건국동 스마트팜 영상 관리자",
    page_icon="🔒",
    layout="wide"
)

# ====================================================
# 1. 비밀번호 인증 함수 정의 및 실행 (로그인 대문)
# ====================================================
def check_password():
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if not st.session_state["authenticated"]:
        st.title("🔒 건국동 스마트팜 영상 관리자")

        if "ADMIN_PASSWORD" not in st.secrets:
            st.error("Secrets에 ADMIN_PASSWORD가 설정되지 않았습니다.")
            st.stop()

        pwd = st.text_input("비밀번호를 입력하세요", type="password")

        if st.button("로그인"):
            if pwd == st.secrets["ADMIN_PASSWORD"]:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("비밀번호가 올바르지 않습니다.")

        st.stop()

# 로그인 검증 실행 (비밀번호 일치 전까지 하단 코드 실행 중단)
check_password()

# ==========================================
# 2. 설정 정보 (.env 파일 및 환경변수/Secrets 로드)
# ==========================================
load_dotenv()  # .env 파일 읽기 (로컬 테스트용)

# Streamlit Secrets 또는 환경 변수에서 Supabase 설정값 로드
SUPABASE_URL = os.getenv("SUPABASE_URL") or st.secrets.get("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or st.secrets.get("SUPABASE_KEY")

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

# ==========================================
# 3. 데이터 수집 및 동기화 핵심 로직
# ==========================================
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
            supabase.table("farm_logs").insert({
                "node_id": "zone_01",
                "temp": temp,
                "humi": humi,
                "image_url": public_url,
                "created_at": datetime.now().isoformat()
            }).execute()

            print(f"✅ [저장 완료] 온도: {temp}°C | 습도: {humi}% | URL: {public_url}")
            return True, temp, humi, public_url

    except Exception as e:
        print(f"❌ 데이터 저장 중 오류 발생: {e}")
        return False, temp, humi, str(e)
    
    return False, temp, humi, "이미지 수집 실패"

# ==========================================
# 4. 로그인 성공 후 표시되는 메인 UI 화면
# ==========================================
st.title("🌿 건국동 스마트팜 영상 관리자 대시보드")
st.success("🔒 인증이 완료되었습니다.")

# 사이드바 설정 메뉴
st.sidebar.header("⚙️ 시스템 설정")
st.sidebar.text(f"연결 장치 주소:\n{ESP32_IP}")

# 실시간 수집 실행 버튼
if st.button("📸 즉시 센서 수집 및 스냅샷 저장 실행"):
    with st.spinner("ESP32-CAM 수집 및 Supabase 동기화 진행 중..."):
        success, temp, humi, result_msg = collect_and_sync()
        if success:
            st.success(f"저장 성공! 온도: {temp}°C | 습도: {humi}%")
            st.image(result_msg, caption="최근 수집된 영상 스냅샷", use_container_width=True)
        else:
            st.error(f"수집 실패 또는 오류: {result_msg}")

st.markdown("---")
st.subheader("📊 백엔드 자동 수집 프로세스 상태")

# 백엔드 스크립트 실행 제어
if __name__ == "__main__":
    if os.getenv("GITHUB_ACTIONS"):
        print("🚀 [GitHub Actions] 스마트팜 수집 스크립트 1회 실행")
        collect_and_sync()
    else:
        st.info("💡 웹 대시보드가 활성화되었습니다. 터미널 백그라운드 수집도 준비되어 있습니다.")