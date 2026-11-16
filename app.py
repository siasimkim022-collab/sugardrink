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

# 세션 상태 초기화 (화면이 바뀌어도 입력값이 유지되도록 저장)
defaults = {
    "step": 1,
    "gender": "남자",
    "age": 25,
    "height": 175.0,
    "weight": 65.0,
    "barcode": "",
    "prod_name": None,
    "found_100ml": None,
    "source_type": None,
    "sugar_per_100ml": 10.0,
    "vol_choice": "250ml (작은 캔)",
    "custom_vol": 300,
    "servings": 1,
    "months": 3,
    "scan_reset_cnt": 0,
}
for k, v in defaults.items():
  if k not in st.session_state:
    st.session_state[k] = v


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

  # 제로/무설탕 제품은 일반 설탕 음료보다 먼저 판별
  if any(w in norm_name for w in ["제로", "zero", "무설탕", "무당"]):
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

  # 2단계: Open Food Facts API로 100ml 기준 당류 직접 조회 (0~100g 범위 검증)
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
        val = round(float(nutriments["sugars_100g"]), 1)
        if 0 <= val <= 100:
          sugar_100ml = val
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


# 공통 헤더 및 단계 진행바
current_step = st.session_state.step
st.title("액상과당 타임머신 시뮬레이터 🥤")
st.progress(current_step / 5)
st.caption(f"단계 {current_step} / 5")
st.write("---")

# =========================================================
# [Step 1] 기본 정보 입력 화면
# =========================================================
if current_step == 1:
  st.subheader("👤 1단계: 기본 정보를 입력해주세요")
  st.write("내 현재 체형을 분석하기 위해 기본 신체 정보를 입력합니다.")

  col1, col2 = st.columns(2)
  with col1:
    gender_idx = 0 if st.session_state.gender == "남자" else 1
    gender = st.radio("성별을 선택하세요", ["남자", "여자"], index=gender_idx)
  with col2:
    age = st.number_input(
        "나이를 입력하세요",
        min_value=10,
        max_value=100,
        value=int(st.session_state.age),
    )

  col3, col4 = st.columns(2)
  with col3:
    height = st.number_input(
        "키(cm)를 입력하세요",
        min_value=100.0,
        max_value=250.0,
        value=float(st.session_state.height),
    )
  with col4:
    weight = st.number_input(
        "몸무게(kg)를 입력하세요",
        min_value=30.0,
        max_value=200.0,
        value=float(st.session_state.weight),
    )

  st.write("")
  if st.button("다음: 현재 체형 확인하기 ▶", use_container_width=True):
    st.session_state.gender = gender
    st.session_state.age = age
    st.session_state.height = height
    st.session_state.weight = weight
    st.session_state.step = 2
    st.rerun()

# =========================================================
# [Step 2] 현재 체형 진단 화면
# =========================================================
elif current_step == 2:
  height_m = st.session_state.height / 100.0
  initial_bmi = st.session_state.weight / (height_m**2)
  initial_step = get_bmi_step(initial_bmi)
  prefix = "boy" if st.session_state.gender == "남자" else "girl"

  st.subheader(f"📊 2단계: 나의 현재 체형 진단 (BMI: {initial_bmi:.1f})")
  st.write(
      f"키 **{st.session_state.height:.1f}cm**, 몸무게"
      f" **{st.session_state.weight:.1f}kg** 기준 현재 상태입니다."
  )

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

  st.write("")
  col_prev, col_next = st.columns(2)
  with col_prev:
    if st.button("◀ 이전 (정보 수정)", use_container_width=True):
      st.session_state.step = 1
      st.rerun()
  with col_next:
    if st.button("다음: 음료 바코드 확인하기 ▶", use_container_width=True):
      st.session_state.step = 3
      st.rerun()

# =========================================================
# [Step 3] 음료 바코드 및 제품 확인 화면
# =========================================================
elif current_step == 3:
  st.subheader("📷 3단계: 음료 바코드 및 제품 확인")
  st.write("음료의 바코드를 스캔하거나 번호를 입력하면 자동으로 다음 단계로 넘어갑니다.")

  reset_cnt = st.session_state.scan_reset_cnt
  barcode_input = ""

  if SCAN_OK:
    photo = st.camera_input(
        "바코드를 가까이, 선명하게 비춰 촬영하세요", key=f"cam_{reset_cnt}"
    )
    if photo:
      img = Image.open(photo).convert("L")
      results = decode(img)
      if not results:
        img = ImageOps.autocontrast(img)
        img = img.resize((img.width * 2, img.height * 2))
        results = decode(img)
      if results:
        barcode_input = results[0].data.decode("utf-8")
      else:
        st.warning("바코드를 인식하지 못했어요. 다시 찍거나 아래에 직접 입력해 주세요.")
  else:
    st.info("바코드 스캔 기능을 불러오지 못해 직접 입력만 가능합니다.")

  manual = st.text_input(
      "또는 바코드 번호 직접 입력 후 엔터(Enter)",
      placeholder="바코드 숫자(8~14자리)를 입력하세요",
      key=f"manual_{reset_cnt}",
  )
  if manual.strip():
    barcode_input = manual.strip()

  # 바코드가 숫자 8~14자리로 인식되면 조회 후 바로 4단계로 전환
  if barcode_input.strip():
    bc_clean = barcode_input.strip()
    if re.fullmatch(r"\d{8,14}", bc_clean):
      with st.spinner("제품 정보를 조회하고 다음 단계로 이동하는 중..."):
        prod_name, found_100ml, source_type = lookup_nutrition_100ml(bc_clean)

      st.session_state.barcode = bc_clean
      st.session_state.prod_name = prod_name
      st.session_state.found_100ml = found_100ml
      st.session_state.source_type = source_type
      st.session_state.sugar_per_100ml = (
          float(found_100ml) if found_100ml is not None else 10.0
      )
      st.session_state.step = 4
      st.rerun()
    else:
      st.warning(
          "유효한 상품 바코드(숫자 8~14자리)가 아닙니다. 바코드를 다시 찍거나 숫자로"
          " 입력해 주세요."
      )

  st.write("---")
  col_prev, col_skip = st.columns(2)
  with col_prev:
    if st.button("◀ 이전 (현재 체형)", use_container_width=True):
      st.session_state.step = 2
      st.rerun()
  with col_skip:
    if st.button("바코드 없이 직접 입력하기 ▶", use_container_width=True):
      st.session_state.barcode = ""
      st.session_state.prod_name = None
      st.session_state.found_100ml = None
      st.session_state.source_type = None
      st.session_state.sugar_per_100ml = 10.0
      st.session_state.step = 4
      st.rerun()

# =========================================================
# [Step 4] 당류 섭취량 및 기간 설정 화면
# =========================================================
elif current_step == 4:
  st.subheader("🍬 4단계: 당류 섭취량 및 기간 설정")

  # 3단계 바코드 조회 결과 요약 안내
  if st.session_state.barcode:
    st.success(f"인식된 바코드: **{st.session_state.barcode}**")
    if st.session_state.prod_name:
      st.info(f"✨ 제품명: **{st.session_state.prod_name}**")
    else:
      st.warning(
          "바코드 DB에서 제품명을 찾지 못했어요 (2018년 이후 신제품이거나 미등록"
          " 바코드일 수 있습니다). 아래에 직접 입력해 주세요."
      )

    if st.session_state.found_100ml is not None:
      if st.session_state.source_type == "db":
        st.success(
            "✅ Open Food Facts(사용자 등록 데이터) 100ml당 당류:"
            f" **{st.session_state.found_100ml}g**"
        )
      else:
        st.info(
            f"💡 100ml당 당류(참고용 대표값): **{st.session_state.found_100ml}g**"
            " (라벨과 다르면 아래에서 수정하세요)"
        )
    else:
      st.warning(
          "당류 정보가 등록되지 않은 음료입니다. 영양성분표를 보고 100ml당 당류를"
          " 입력해 주세요."
      )

  sugar_per_100ml = st.number_input(
      "100ml당 당류(g)를 입력하세요 (총 당류 ÷ 총 내용량 × 100)",
      min_value=0.0,
      max_value=100.0,
      value=float(st.session_state.sugar_per_100ml),
      step=0.1,
  )

  vol_options = [
      "250ml (작은 캔)",
      "355ml (큰 캔)",
      "500ml (페트병)",
      "직접 입력",
  ]
  vol_idx = (
      vol_options.index(st.session_state.vol_choice)
      if st.session_state.vol_choice in vol_options
      else 0
  )
  vol_choice = st.radio(
      "한 번에 마시는 양(ml)을 선택하세요",
      vol_options,
      index=vol_idx,
      horizontal=True,
  )

  if vol_choice == "250ml (작은 캔)":
    volume_ml = 250
    custom_vol = st.session_state.custom_vol
  elif vol_choice == "355ml (큰 캔)":
    volume_ml = 355
    custom_vol = st.session_state.custom_vol
  elif vol_choice == "500ml (페트병)":
    volume_ml = 500
    custom_vol = st.session_state.custom_vol
  else:
    custom_vol = st.number_input(
        "마시는 양(ml)을 직접 입력하세요",
        min_value=10,
        max_value=3000,
        value=int(st.session_state.custom_vol),
        step=10,
    )
    volume_ml = custom_vol

  once_sugar = round(sugar_per_100ml * volume_ml / 100.0, 1)
  st.info(
      f"🥤 1회 섭취 당류: **{once_sugar}g** (100ml당 {sugar_per_100ml:.1f}g ×"
      f" {volume_ml}ml)"
  )

  servings = st.slider(
      "하루에 몇 번 마시나요?", 1, 5, int(st.session_state.servings)
  )
  months = st.slider(
      "몇 개월 뒤를 볼까요?", 1, 12, int(st.session_state.months)
  )

  st.write("")
  col_prev, col_next = st.columns(2)
  with col_prev:
    if st.button("◀ 이전 (바코드 다시 입력)", use_container_width=True):
      st.session_state.barcode = ""
      st.session_state.prod_name = None
      st.session_state.found_100ml = None
      st.session_state.source_type = None
      st.session_state.scan_reset_cnt += 1
      st.session_state.step = 3
      st.rerun()
  with col_next:
    if st.button("다음: 미래 체형 결과 보기 🔮", use_container_width=True):
      st.session_state.sugar_per_100ml = sugar_per_100ml
      st.session_state.vol_choice = vol_choice
      st.session_state.custom_vol = custom_vol
      st.session_state.servings = servings
      st.session_state.months = months
      st.session_state.step = 5
      st.rerun()

# =========================================================
# [Step 5] 최종 시뮬레이션 결과 화면
# =========================================================
elif current_step == 5:
  height_m = st.session_state.height / 100.0
  weight = st.session_state.weight
  initial_bmi = weight / (height_m**2)
  initial_step = get_bmi_step(initial_bmi)
  prefix = "boy" if st.session_state.gender == "남자" else "girl"

  vol_choice = st.session_state.vol_choice
  if vol_choice == "250ml (작은 캔)":
    volume_ml = 250
  elif vol_choice == "355ml (큰 캔)":
    volume_ml = 355
  elif vol_choice == "500ml (페트병)":
    volume_ml = 500
  else:
    volume_ml = st.session_state.custom_vol

  once_sugar = round(st.session_state.sugar_per_100ml * volume_ml / 100.0, 1)
  servings = st.session_state.servings
  months = st.session_state.months

  # 당류 1g = 4kcal, 체중 1kg ≈ 7,700kcal 가정
  extra_kcal = once_sugar * 4 * servings * 30 * months
  simulated_weight = weight + extra_kcal / 7700
  simulated_bmi = simulated_weight / (height_m**2)
  simulated_step = get_bmi_step(simulated_bmi)

  st.subheader(f"🔮 5단계: {months}개월 뒤 예상 체형 결과")
  st.write(
      f"예상 체중: **{simulated_weight:.1f}kg** (현재 대비"
      f" **+{simulated_weight - weight:.1f}kg**) / 예상 BMI:"
      f" **{simulated_bmi:.1f}**"
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

  drink_label = st.session_state.prod_name or "직접 입력 음료"
  st.info(
      f"📋 시뮬레이션 요약: **{drink_label}** ({volume_ml}ml, 당류"
      f" {once_sugar}g) × 하루 {servings}회 × {months}개월 = 누적 추가 열량"
      f" **{extra_kcal:,.0f} kcal**"
  )

  st.write("")
  col_prev, col_restart = st.columns(2)
  with col_prev:
    if st.button("◀ 섭취량/기간 다시 조절하기", use_container_width=True):
      st.session_state.step = 4
      st.rerun()
  with col_restart:
    if st.button("처음부터 다시 하기 🔄", use_container_width=True):
      st.session_state.barcode = ""
      st.session_state.prod_name = None
      st.session_state.found_100ml = None
      st.session_state.source_type = None
      st.session_state.scan_reset_cnt += 1
      st.session_state.step = 1
      st.rerun()
