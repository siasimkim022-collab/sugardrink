import streamlit as st
import requests
from PIL import Image, ImageOps
from pyzbar.pyzbar import decode

# API 키는 코드에 직접 쓰지 말고 Streamlit Secrets에 저장 (아래 설명 참고)
API_KEY = st.secrets["API_KEY"]


def read_barcode(image_file):
    """사진에서 바코드 숫자를 읽어 리스트로 반환"""
    img = Image.open(image_file).convert("L")  # 흑백 변환
    results = decode(img)
    if not results:
        # 인식 실패 시 대비를 높이고 2배 확대해서 재시도
        img = ImageOps.autocontrast(img)
        img = img.resize((img.width * 1.5, img.height * 1.5))
        results = decode(img)
    return [r.data.decode("utf-8") for r in results]


def lookup_product(barcode):
    """공공데이터 API 호출 - 이 부분을 기존 코드로 교체하세요"""
    # 예시: 식품안전나라 바코드연계제품정보(C005)를 쓰는 경우
    url = f"http://openapi.foodsafetykorea.go.kr/api/{API_KEY}/C005/json/1/5/BAR_CD={barcode}"
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    return r.json()


st.title("바코드 제품 조회")

photo = st.camera_input("바코드를 화면에 가깝고 선명하게 맞춰 촬영하세요")
barcode = None

if photo:
    codes = read_barcode(photo)
    if codes:
        barcode = codes[0]
        st.success(f"인식된 바코드: {barcode}")
    else:
        st.warning("바코드를 인식하지 못했어요. 더 가까이, 밝은 곳에서 다시 찍어보세요.")

manual = st.text_input("인식이 안 되면 직접 입력")
if manual.strip():
    barcode = manual.strip()

if barcode:
    with st.spinner("조회 중..."):
        try:
            data = lookup_product(barcode)
            st.json(data)  # 기존에 결과를 보여주던 코드로 교체
        except Exception as e:
            st.error(f"API 조회 실패: {e}")
