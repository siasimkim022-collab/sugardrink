import streamlit as st
import requests
from PIL import Image, ImageOps

try:
  from pyzbar.pyzbar import decode

  SCAN_OK = True
except Exception:
  SCAN_OK = False

# 페이지 설정
st.set_page_config(
    page_title="액상과당 타임머신 시뮬레이터", page_icon="🥤", layout="centered"
)

# API 키 설정 (Streamlit Secrets 활용)
API_KEY = st.secrets["API_KEY"]

st.title("액상과당 타임머신 시뮬레이터 🥤")
st.write(
    "내 체형을 먼저 확인하고, 음료를 마셨을 때의 미래 체형 변화를"
    " 시뮬레이션해보세요!"
)
st.write("---")

# 1. 사용자 기본 정보 입력 (성별, 나이, 키, 몸무게)
col1, col2 = st.columns(2)
with col1:
  gender = st.radio("성별을 선택하세요", ["남자", "여자"])
with col2:
  age = st.number_input(
      "나이를 입력하세요", min_value=10, max_value=100, value=22
  )

col3, col4 = st.columns(2)
with col3:
  height = st.number_input(
      "키(cm)를 입력하세요", min_value=100.0, max_value=250.0, value=174.0
  )
with col4:
  weight = st.number_input(
      "몸무게(kg)를 입력하세요", min_value=30.0, max_value=200.0, value=65.0
  )


# 초기 BMI 계산 및 5단계 매핑 함수
def get_bmi_step(bmi):
  if bmi < 18.5:
    return 1  # Slim
  elif 18.5 <= bmi < 23:
    return 2  # Average
  elif 23 <= bmi < 25:
    return 3  # Chubby
  elif 25 <= bmi < 30:
    return 4  # Overweight
  else:
    return 5  # Obese


# 초기 BMI 및 캐릭터 단계 계산
initial_height_m = height / 100.0
initial_bmi = weight / (initial_height_m**2)
initial_step = get_bmi_step(initial_bmi)

# 성별에 따른 이미지 파일명 접두사 설정 (띄어쓰기 및 파일명 일치)
prefix = "boy" if gender == "남자" else "girl"

st.subheader(f"📊 나의 현재 체형 진단 (BMI: {initial_bmi:.1f})")

# 초기 캐릭터 이미지 출력
initial_image_path = f"step {initial_step} {prefix}.png"
try:
  initial_img = Image.open(initial_image_path)
  st.image(
      initial_img,
      caption=f"현재 상태 (Step {initial_step})",
      use_container_width=True,
  )
except Exception:
  st.warning(f"이미지 파일을 찾지 못했습니다: {initial_image_path}")

st.write("---")

# 2. 바코드 카메라 인식 또는 직접 입력
st.subheader("📷 음료 바코드 및 제품 확인")
barcode = ""

if SCAN_OK:
  photo = st.camera_input("바코드를 가까이, 선명하게 비춰 촬영하세요")
  if photo:
    img = Image.open(photo).convert("L")
    results = decode(img)
    if not results:
      img = ImageOps.autocontrast(img)
      img = img.resize((img.width * 2, img.height * 2))
      results = decode(img)
    if results:
      barcode = results[0].data.decode("utf-8")
      st.success(f"인식된 바코드: {barcode}")
    else:
      st.warning("인식하지 못했어요. 다시 찍거나 아래에 직접 입력해 주세요.")
else:
  st.info("바코드 스캔 기능을 불러오지 못해 직접 입력만 가능합니다.")

manual = st.text_input("또는 바코드 번호 직접 입력", placeholder="바코드 숫자를 입력하세요")
if manual.strip():
  barcode = manual.strip()


# 제품 조회 함수 (식품안전나라 API)
def lookup_product(bc):
  url = (
      f"http://openapi.foodsafetykorea.go.kr/api/{API_KEY}/C005/json/1/5/BAR_CD={bc}"
  )
  r = requests.get(url, timeout=10)
  r.raise_for_status()
  data = r.json().get("C005", {})
  rows = data.get("row", [])
  if not rows:
    return None
  return rows[0].get("PRDLST_NM", "제품명 없음")


prod_name = None
if barcode.strip():
  try:
    prod_name = lookup_product(barcode.strip())
  except Exception as e:
    st.error(f"API 조회 중 오류가 발생했습니다: {e}")

  if prod_name:
    st.info(f"✨ 인식된 제품명: **{prod_name}**")
  else:
    st.warning(
        "등록되지 않은 바코드이거나 정보를 찾지 못했습니다. 아래에서 당류를"
        " 직접 입력해 주세요."
    )

# 3. 당류 섭취량 및 기간 설정에 따른 시뮬레이션
st.subheader("🍬 당류 섭취량 및 기간 설정")
sugar = st.number_input(
    "음료 영양성분표의 당류(g)를 입력하세요 (1회 제공량 기준)",
    min_value=0.0,
    max_value=200.0,
    value=20.0,
)
servings = st.slider("하루에 몇 번 마시나요?", 1, 5, 1)
months = st.slider("몇 개월 뒤를 볼까요?", 1, 12, 3)

# 당류 1g = 4kcal, 체중 1kg ≈ 7,700kcal 가정
extra_kcal = sugar * 4 * servings * 30 * months
simulated_weight = weight + extra_kcal / 7700
simulated_bmi = simulated_weight / (initial_height_m**2)
simulated_step = get_bmi_step(simulated_bmi)

st.subheader(
    f"🔮 {months}개월 뒤 예상 체형 (예상 체중: {simulated_weight:.1f}kg, BMI:"
    f" {simulated_bmi:.1f})"
)
st.caption("섭취 열량만 늘고 다른 조건은 같다고 가정한 단순 계산입니다.")

sim_image_path = f"step {simulated_step} {prefix}.png"
try:
  st.image(
      Image.open(sim_image_path),
      caption=f"{months}개월 뒤 변화된 모습 (Step {simulated_step})",
      use_container_width=True,
  )
except Exception:
  st.warning(f"이미지 파일을 찾지 못했습니다: {sim_image_path}")

if simulated_step > initial_step:
  st.error("⚠️ 이 습관이 이어지면 체형 단계가 올라갈 수 있습니다!")
else:
  st.success("🎉 현재 체형 단계를 안전하게 유지할 수 있는 수준입니다.")
