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

# 1. 첫 화면: 사용자 기본 정보 입력 (성별, 나이, 키, 몸무게)
st.subheader("👤 기본 정보를 입력해주세요")
col1, col2 = st.columns(2)
with col1:
  gender = st.radio("성별을 선택하세요", ["남자", "여자"])
with col2:
  age = st.number_input(
      "나이를 입력하세요", min_value=10, max_value=100, value=25
  )

col3, col4 = st.columns(2)
with col3:
  height = st.number_input(
      "키(cm)를 입력하세요", min_value=100.0, max_value=250.0, value=175.0
  )
with col4:
  weight = st.number_input(
      "몸무게(kg)를 입력하세요", min_value=30.0, max_value=200.0, value=65.0
  )

# 단계 분리: 시작하기 버튼 전에는 아래 내용 숨김
if "started" not in st.session_state:
  st.session_state.started = False

st.write("")
if not st.session_state.started:
  if st.button("확인하고 시작하기 ▶", use_container_width=True):
    st.session_state.started = True
    st.rerun()
  st.stop()


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


initial_height_m = height / 100.0
initial_bmi = weight / (initial_height_m**2)
initial_step = get_bmi_step(initial_bmi)
prefix = "boy" if gender == "남자" else "girl"

st.write("---")
st.subheader(f"📊 나의 현재 체형 진단 (BMI: {initial_bmi:.1f})")

initial_image_path = f"step {initial_step} {prefix}.png"
try:
  initial_img = Image.open(initial_image_path)
  # [수정] 이미지가 너무 커지지 않도록 width를 제한 (예: 250픽셀)
  st.image(
      initial_img,
      caption=f"현재 상태 (Step {initial_step})",
      width=250,
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


# C005(제품명) + I2790(영양성분) 조회 함수
def get_product_and_sugar(bc):
  prod_name, sugar_val = None, None
  debug = {}

  try:
    url = f"http://openapi.foodsafetykorea.go.kr/api/{API_KEY}/C005/json/1/1/BAR_CD={bc}"
    data = requests.get(url, timeout=5).json()
    debug["C005"] = data
    rows = data.get("C005", {}).get("row", [])
    if rows:
      prod_name = rows[0].get("PRDLST_NM")
  except Exception as e:
    debug["C005_error"] = str(e)

  try:
    url = f"http://openapi.foodsafetykorea.go.kr/api/{API_KEY}/I2790/json/1/1/BAR_CD={bc}"
    data = requests.get(url, timeout=5).json()
    debug["I2790"] = data
    rows = data.get("I2790", {}).get("row", [])
    if rows:
      try:
        sugar_val = float(rows[0].get("NUTR_CONT5"))
      except (TypeError, ValueError):
        sugar_val = None
  except Exception as e:
    debug["I2790_error"] = str(e)

  return prod_name, sugar_val, debug


auto_sugar = 20.0
prod_name, found_sugar, debug_info = None, None, {}

if barcode.strip():
  with st.spinner("식품 데이터베이스에서 조회 중..."):
    prod_name, found_sugar, debug_info = get_product_and_sugar(barcode.strip())

  if prod_name:
    st.info(f"✨ 제품명: **{prod_name}**")
  else:
    st.warning("제품명을 찾지 못했어요.")

  if found_sugar is not None:
    auto_sugar = found_sugar
    st.success(
        f"DB에서 찾은 당류: **{found_sugar}g** (기준량은 제품마다 다를 수"
        " 있어요)"
    )
  else:
    st.warning(
        "당류를 자동으로 찾지 못했어요. 아래에 영양성분표를 보고 직접 입력해"
        " 주세요."
    )

  with st.expander("🔧 API 응답 확인 (개발용)"):
    st.json(debug_info)

# 3. 당류 섭취량 및 기간 설정에 따른 시뮬레이션
st.write("---")
st.subheader("🍬 당류 섭취량 및 기간 설정")
sugar = st.number_input(
    "음료 영양성분표의 당류(g)를 입력하세요 (1회 제공량 기준)",
    min_value=0.0,
    max_value=200.0,
    value=float(auto_sugar),
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
  # [수정] 미래 체형 이미지도 너무 커지지 않도록 width를 250으로 제한
  st.image(
      Image.open(sim_image_path),
      caption=f"{months}개월 뒤 변화된 모습 (Step {simulated_step})",
      width=250,
  )
except Exception:
  st.warning(f"이미지 파일을 찾지 못했습니다: {sim_image_path}")

if simulated_step > initial_step:
  st.error("⚠️ 이 습관이 이어지면 체형 단계가 올라갈 수 있습니다!")
else:
  st.success("🎉 현재 체형 단계를 안전하게 유지할 수 있는 수준입니다.")
