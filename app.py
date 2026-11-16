import re
from PIL import Image, ImageOps
import requests
import streamlit as st

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

# 국내 주요 시판 음료 참고용 대표 당류 데이터 (100ml당 당류 g 기준)
KOREAN_DRINK_SUGAR_100ML = {
    "트레비": 0.0,
    "씨그램": 0.0,
    "하늘보리": 0.0,
    "옥수수수염차": 0.0,
    "헛개수": 0.0,
    "코카콜라": 10.8,
    "펩시콜라": 11.0,
    "칠성사이다": 10.8,
    "스프라이트": 10.0,
    "환타": 10.4,
    "밀키스": 10.0,
    "포카리스웨트": 6.0,
    "게토레이": 6.0,
    "파워에이드": 5.8,
    "토레타": 4.4,
    "데미소다": 9.6,
    "웰치스": 11.8,
    "마운틴듀": 12.4,
    "닥터페퍼": 10.4,
    "봉봉": 10.1,
    "코코팜": 10.0,
    "갈아만든배": 10.1,
    "바나나맛우유": 11.3,
    "초코에몽": 11.1,
    "레쓰비": 8.0,
    "칸타타": 6.5,
    "조지아": 6.8,
    "비락식혜": 9.2,
    "핫식스": 9.6,
    "몬스터에너지": 11.0,
    "레드불": 10.8,
    "비타500": 10.0,
    "박카스": 12.0,
    "야쿠르트": 13.8,
    "쿨피스": 8.8,
    "립톤": 7.6,
    "실론티": 7.5,
    "데자와": 7.5,
    "이프로": 5.8,
}


def find_local_sugar_100ml(prod_name):
  if not prod_name:
    return None
  norm_name = re.sub(r"[^가-힣a-zA-Z0-9]", "", prod_name).lower()

  # 제로/무설탕/블랙 제품은 일반 설탕 음료보다 먼저 판별
  if any(w in norm_name for w in ["제로", "zero", "무설탕", "무당", "블랙"]):
    return 0.0

  for key in sorted(KOREAN_DRINK_SUGAR_100ML.keys(), key=len, reverse=True):
    if key in norm_name:
      return KOREAN_DRINK_SUGAR_100ML[key]
  return None


def lookup_nutrition_100ml(bc):
  prod_name = None
  sugar_100ml = None
  source_type = None  # "db" 또는 "ref"

  # 1단계: 식품안전나라 C005로 한국 제품명 조회 (2018년 이전 등록 제품 중심)
  try:
    url_c005 = f"http://openapi.foodsafetykorea.go.kr/api/{API_KEY}/C005/json/1/5/BAR_CD={bc}"
    data_c005 = requests.get(url_c005, timeout=5).json()
    rows_c005 = data_c005.get("C005", {}).get("row", [])
    if rows_c005:
      prod_name = rows_c005[0].get("PRDLST_NM")
  except Exception:
    pass

  # 2단계: Open Food Facts API로 100ml 기준 당류 직접 조회
  try:
    url_off = f"https://world.openfoodfacts.org/api/v2/product/{bc}.json"
    headers = {"User-Agent": "SugarDrinkSimulator/1.0"}
    data_off = requests.get(url_off, headers=headers, timeout=5).json()
    if data_off.get("status") == 1:
      product = data_off.get("product", {})
      if not prod_name:
        prod_name = product.get("product_name_ko") or product.get(
            "product_name"
        )
      nutriments = product.get("nutriments", {})
      if nutriments.get("sugars_100g") is not None:
        sugar_100ml = round(float(nutriments["sugars_100g"]), 1)
        source_type = "db"
  except Exception:
    pass

  # 3단계: 국내 대표 음료 100ml당 참고용 대표값 매칭
  if sugar_100ml is None and prod_name:
    ref_val = find_local_sugar_100ml(prod_name)
    if ref_val is not None:
      sugar_100ml = ref_val
      source_type = "ref"

  return prod_name, sugar_100ml, source_type


default_sugar_100ml = 10.0
input_key = "sugar100_default"

if barcode.strip():
  bc_clean = barcode.strip()
  with st.spinner("제품 정보를 조회하는 중..."):
    prod_name, found_100ml, source_type = lookup_nutrition_100ml(bc_clean)

  if prod_name:
    st.info(f"✨ 제품명: **{prod_name}**")
  else:
    st.warning(
        "바코드 DB에서 제품명을 찾지 못했어요 (2018년 이후 신제품이거나 미등록"
        " 바코드일 수 있습니다). 아래에 직접 입력해 주세요."
    )

  if found_100ml is not None:
    default_sugar_100ml = found_100ml
    input_key = f"sugar100_{bc_clean}"
    if source_type == "db":
      st.success(
          "✅ Open Food Facts(사용자 등록 데이터) 100ml당 당류:"
          f" **{found_100ml}g**"
      )
    else:
      st.info(
          f"💡 100ml당 당류(참고용 대표값): **{found_100ml}g** (라벨과 다르면"
          " 아래에서 수정하세요)"
      )
  else:
    input_key = f"sugar100_{bc_clean}_none"
    st.warning(
        "당류 정보가 등록되지 않은 음료입니다. 영양성분표를 보고 100ml당 당류를"
        " 입력해 주세요."
    )

# 3. 100ml당 당류 및 마시는 양(ml) 기반 시뮬레이션
st.write("---")
st.subheader("🍬 당류 섭취량 및 기간 설정")

sugar_per_100ml = st.number_input(
    "100ml당 당류(g)를 입력하세요 (총 당류 ÷ 총 내용량 × 100)",
    min_value=0.0,
    max_value=100.0,
    value=float(default_sugar_100ml),
    step=0.1,
    key=input_key,
)

vol_choice = st.radio(
    "한 번에 마시는 양(ml)을 선택하세요",
    ["250ml (작은 캔)", "355ml (큰 캔)", "500ml (페트병)", "직접 입력"],
    horizontal=True,
)

if vol_choice == "250ml (작은 캔)":
  volume_ml = 250
elif vol_choice == "355ml (큰 캔)":
  volume_ml = 355
elif vol_choice == "500ml (페트병)":
  volume_ml = 500
else:
  volume_ml = st.number_input(
      "마시는 양(ml)을 직접 입력하세요",
      min_value=10,
      max_value=3000,
      value=300,
      step=10,
  )

once_sugar = round(sugar_per_100ml * volume_ml / 100.0, 1)
st.info(
    f"🥤 1회 섭취 당류: **{once_sugar}g** (100ml당 {sugar_per_100ml:.1f}g ×"
    f" {volume_ml}ml)"
)

servings = st.slider("하루에 몇 번 마시나요?", 1, 5, 1)
months = st.slider("몇 개월 뒤를 볼까요?", 1, 12, 3)

# 당류 1g = 4kcal, 체중 1kg ≈ 7,700kcal 가정
extra_kcal = once_sugar * 4 * servings * 30 * months
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
      width=250,
  )
except Exception:
  st.warning(f"이미지 파일을 찾지 못했습니다: {sim_image_path}")

if simulated_step > initial_step:
  st.error("⚠️ 이 습관이 이어지면 체형 단계가 올라갈 수 있습니다!")
else:
  st.success("🎉 현재 체형 단계를 안전하게 유지할 수 있는 수준입니다.")
