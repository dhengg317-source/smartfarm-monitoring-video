import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import plotly.express as px
from supabase import create_client, Client

# 웹 페이지 레이아웃 설정
st.set_page_config(page_title="스마트팜 통합 관제 센터", layout="wide", page_icon="🌱")

# ==========================================
# 1. 설정 정보 (본인 환경에 맞게 수정)
# ==========================================
# secrets.toml 사용을 권장하며, 직접 적을 경우 아래 문자열 교체
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

# ESP32 IP (같은 Wi-Fi 공유기 내 테스트 시 사용)
ESP32_IP = "http://192.168.0.23"

@st.cache_resource
def init_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

try:
    supabase = init_supabase()
except Exception as e:
    st.error(f"Supabase 연결 실패: {e}")
    st.stop()

st.title("🌱 스마트팜 ESP32-CAM 통합 모니터링 시스템")
st.markdown("---")

# 상단: 실시간 라이브 동영상 스트림
st.subheader("📹 실시간 구역 영상 (0.3초 고속 프레임)")

# 안정화된 JS 300ms 스트리밍
live_stream_html = f"""
<div style="text-align: center; background-color: #1a1a1a; padding: 10px; border-radius: 12px;">
    <img id="live_frame" src="{ESP32_IP}/jpg" style="width: 100%; max-width: 680px; border-radius: 8px; border: 2px solid #00E676;" 
         onerror="this.onerror=null; this.alt='영상 스트림 연결 불가 (ESP32 IP 확인 필요)';" />
</div>
<script>
    const imgElement = document.getElementById('live_frame');
    function refreshFrame() {{
        const newImg = new Image();
        newImg.onload = function() {{
            imgElement.src = this.src;
        }};
        newImg.src = "{ESP32_IP}/jpg?t=" + new Date().getTime();
    }}
    setInterval(refreshFrame, 300); // 0.3초 주기 갱신
</script>
"""
components.html(live_stream_html, height=480)

st.markdown("---")

# 하단: Supabase DB 누적 기록 및 과거 스냅샷 이력
st.subheader("📊 과거 환경 기록 및 스냅샷 이력")

# Supabase 데이터 불러오기 함수
def load_data():
    try:
        res = supabase.table("farm_logs").select("*").order("created_at", desc=True).limit(50).execute()
        if res.data:
            df = pd.DataFrame(res.data)
            df['created_at'] = pd.to_datetime(df['created_at'])
            return df
    except Exception as e:
        st.warning(f"데이터 로드 중 오류 발생: {e}")
    return pd.DataFrame()

df = load_data()

if not df.empty:
    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown("##### 📈 최근 온습도 변화 추이 (5분 단위 적재)")
        # Plotly 차트 시각화
        fig = px.line(df, x='created_at', y=['temp', 'humi'], 
                      labels={'value': '수치', 'created_at': '시간', 'variable': '구분'},
                      title="온도(°C) 및 습도(%) 트렌드",
                      markers=True)
        fig.update_layout(height=350)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.markdown("##### 🖼️ 최신 저장 스냅샷")
        latest_record = df.iloc[0]
        
        image_url = latest_record.get('image_url', '')
        
        # 시간 표시 안전 처리
        created_at_val = latest_record.get('created_at', '')
        if hasattr(created_at_val, 'strftime'):
            time_str = created_at_val.strftime('%Y-%m-%d %H:%M:%S')
        else:
            time_str = str(created_at_val)[:19] # 문자열일 경우 앞 19자리만 잘라냄
        
        # 이미지 표시 (예외 처리 추가)
        if image_url and str(image_url).startswith('http'):
            try:
                st.image(image_url, caption=f"저장시간: {time_str}", use_container_width=True)
            except Exception as e:
                st.warning("⚠️ 이미지를 로드할 수 없습니다.")
        else:
            st.warning("📷 저장된 이미지 링크가 없습니다.")

        st.metric(label="최근 측정 온도", value=f"{latest_record.get('temp', 0.0)} °C")
        st.metric(label="최근 측정 습도", value=f"{latest_record.get('humi', 0.0)} %")

    # 과거 로그 데이터표 출력
    with st.expander("📋 상세 데이터 로그 확인"):
        # 필요한 컬럼만 추출 (없는 경우 대비 안전 처리)
        cols_to_show = [c for c in ['created_at', 'node_id', 'temp', 'humi', 'image_url'] if c in df.columns]
        st.dataframe(df[cols_to_show], use_container_width=True)
else:
    st.info("💡 아직 Supabase에 누적된 데이터가 없습니다. 수집 스크립트(`camaab.py`)를 실행하여 첫 데이터 적재를 진행하세요.")

# 대시보드 새로고침 버튼
if st.button("🔄 대시보드 데이터 새로고침"):
    st.rerun()