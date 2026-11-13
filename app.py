import streamlit as st

# 페이지 기본 설정
st.set_page_config(page_title="햄스터 액상과당 경고기", page_icon="🐹", layout="centered")

# 메인 제목 & 서브 제목
st.title("당신의 햄스터는 안녕하신가요? 🐹 (액상과당 경고기)")
st.caption("음료 바코드를 입력하면 당류를 분석하고, 내 몸의 변화를 햄스터로 보여드려요.")

st.divider()

# 사용자 정보 입력
st.subheader("1. 내 정보 입력")
col1, col2 = st.columns(2)
with col1:
    height = st.number_input("키 (cm)", min_value=100.0, max_value=250.0, value=170.0, step=0.1)
with col2:
    weight = st.number_input("몸무게 (kg)", min_value=20.0, max_value=300.0, value=60.0, step=0.1)

# 바코드 입력
st.subheader("2. 음료 바코드 입력")
barcode = st.text_input("바코드 숫자", placeholder="예: 8801234567890")

st.divider()

# 실행 버튼
if st.button("결과 확인하기", type="primary", use_container_width=True):
    if not barcode.strip():
        st.warning("바코드 숫자를 입력해 주세요.")
    elif not barcode.strip().isdigit():
        st.warning("바코드는 숫자만 입력해 주세요.")
    else:
        st.success(
            f"입력하신 키는 {height:g}cm, 몸무게는 {weight:g}kg입니다. "
            f"바코드 [{barcode.strip()}] 분석을 시작합니다..."
        )
