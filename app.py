import urllib.parse
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


# 바코드 -> 제품명 및 당류(g) 자동 조회 함수
def lookup_nutrition(bc):
  prod_name = None
  sugar_options = []
  debug = {}

  # 1단계: 식품안전나라 C005로 한국 제품명 조회
  try:
    url_c005 = f"http://openapi.foodsafetykorea.go.kr/api/{API_KEY}/C005/json/1/5/BAR_CD={bc}"
    data_c005 = requests.get(url_c005, timeout=5).json()
    debug["C005"] = data_c005
    rows_c005 = data_c005.get("C005", {}).get("row", [])
    if rows_c005:
      prod_name = rows_c005[0].get("PRDLST_NM")
  except Exception as e:
    debug["C005_error"] = str(e)

  # 2단계: Open Food Facts API로 바코드 기반 당류 직접 조회
  try:
    url_off = f"https://world.openfoodfacts.org/api/v2/product/{bc}.json"
    headers = {"User-Agent": "SugarDrinkSimulator/1.0"}
    data_off = requests.get(url_off, headers=headers, timeout=5).json()
    debug["OpenFoodFacts_status"] = data_off.get("status")
    if data_off.get("status") == 1:
      product = data_off.get("product", {})
      if not prod_name:
        prod_name = product.get("product_name_ko") or product.get(
            "product_name"
        )
      nutriments = product.get("nutriments", {})
      serving_size = product.get("serving_size") or product.get("quantity")

      if nutriments.get("sugars_serving") is not None:
        val = float(nutriments["sugars_serving"])
        label = (
            f"OpenFoodFacts (1회 제공량 {serving_size or '기준'}): {val}g"
        )
        sugar_options.append({"label": label, "sugar": val})
      elif nutriments.get("sugars_100g") is not None:
        val = float(nutriments["sugars_100g"])
        label = f"OpenFoodFacts (100ml/100g 기준): {val}g"
        sugar_options.append({"label": label, "sugar": val})
  except Exception as e:
    debug["OpenFoodFacts_error"] = str(e)

  # 3단계: 식품안전나라 I2790에서 제품명(DESC_KOR)으로 영양성분 조회
  if prod_name:
    try:
      encoded_name = urllib.parse.quote(prod_name.strip())
      url_i2790 = f"http://openapi.foodsafetykorea.go.kr/api/{API_KEY}/I2790/json/1/5/DESC_KOR={encoded_name}"
      data_i2790 = requests.get(url_i2790, timeout=5).json()
      debug["I2790"] = data_i2790
      rows_i2790 = data_i2790.get("I2790", {}).get("row", [])
      for r in rows_i2790:
        raw_sugar = r.get("NUTR_CONT5")
        if raw_sugar not in (None, "", "-"):
          try:
            val = float(raw_sugar)
            desc = r.get("DESC_KOR", prod_name)
            size = r.get("SERVING_SIZE", "")
            size_txt = f" / 기준량 {size}" if size else ""
            sugar_options.append(
                {"label": f"식품안전나라 ({desc}{size_txt}): {val}g", "sugar": val}
            )
          except (TypeError, ValueError):
            pass
    except Exception as e:
      debug["I2790_error"] = str(e)

  return prod_name, sugar_options, debug


auto_sugar = 20.0
input_key = "sugar_default"

if barcode.strip():
  bc_clean = barcode.strip()
  with st.spinner("데이터베이스에서 제품명과 당류를 조회하는 중..."):
    prod_name, sugar_options, debug_info = lookup_nutrition(bc_clean)

  if prod_name:
    st.info(f"✨ 제품명: **{prod_name}**")
  else:
    st.warning("제품명을 찾지 못했어요.")

  if sugar_options:
    selected_idx = 0
    if len(sugar_options) > 1:
      labels = [opt["label"] for opt in sugar_options]
      chosen = st.selectbox(
          "조회된 영양성분 기준을 선택하세요 (용량/출처별)", labels
      )
      selected_idx = labels.index(chosen)

    auto_sugar = sugar_options[selected_idx]["sugar"]
    input_key = f"sugar_{bc_clean}_{selected_idx}"
    st.success(
        f"✅ 자동 조회된 당류: **{auto_sugar}g** ({sugar_options[selected_idx]['label']})"
    )
  else:
    input_key = f"sugar_{bc_clean}_none"
    st.warning(
        "이 음료의 당류 데이터가 DB에 없어 자동으로 불러오지 못했습니다. 아래에"
        " 영양성분표를 보고 입력해 주세요."
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
    key=input_key,
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
      width=250,
  )
except Exception:
  st.warning(f"이미지 파일을 찾지 못했습니다: {sim_image_path}")

if simulated_step > initial_step:
  st.error("⚠️ 이 습관이 이어지면 체형 단계가 올라갈 수 있습니다!")
else:
  st.success("🎉 현재 체형 단계를 안전하게 유지할 수 있는 수준입니다.")
