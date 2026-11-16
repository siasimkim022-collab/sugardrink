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
    page_title="음료 당류 타임머신 시뮬레이터",
    page_icon="🥤",
    layout="centered",
)

# API 키 설정 (Streamlit Secrets 활용)
API_KEY = st.secrets["API_KEY"]

# 순수 추가 운동 소모 계수: (MET - 1) × 1회 운동시간(h) × 주당 횟수 ÷ 7
# 안정 시 에너지 소비량(1 MET)을 제외한 체중 1kg당 일평균 순수 추가 소모 열량(kcal/kg/일)
EXERCISE_OPTIONS = {
    "거의 안 함 (주 0회)": 0.0,
    "가벼운 운동 (주 1~2회 걷기·스트레칭)": 0.54,      # (3.5 - 1) × 0.75h × 2회 ÷ 7
    "규칙적 운동 (주 3~4회 헬스·러닝)": 1.88,        # (6.0 - 1) × 0.75h × 3.5회 ÷ 7
    "고강도 운동 (주 5회 이상 격렬한 운동)": 5.00,   # (8.0 - 1) × 1.0h × 5회 ÷ 7
}

# 평소 식사량에 따른 시뮬레이션용 일일 열량 가정치 (kcal/일)
FOOD_OPTIONS = {
    "소식하는 편 (가정치 -100 kcal/일)": -100,
    "보통 (기준 0 kcal/일)": 0,
    "많이 먹는 편 (가정치 +150 kcal/일)": 150,
    "과식·야식이 잦음 (가정치 +300 kcal/일)": 300,
}

# 세션 상태 초기화
defaults = {
    "step": 1,
    "gender": "남자",
    "age": 25,
    "height": 175.0,
    "weight": 65.0,
    "exercise": "거의 안 함 (주 0회)",
    "food_intake": "보통 (기준 0 kcal/일)",
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


# 기초대사량(BMR) 계산 함수 (Mifflin-St Jeor 공식)
def calc_bmr(gender, age, height, weight):
    base = 10 * weight + 6.25 * height - 5 * age
    return round(base + 5 if gender == "남자" else base - 161)


# 성인 BMI 기준 10단계 매핑 함수 (Step 2 = 정상 체중 기준)
def get_bmi_step(bmi):
    if bmi < 18.5:
        return 1   # 저체중
    elif bmi < 23.0:
        return 2   # 정상 체중 (기준 단계)
    elif bmi < 24.5:
        return 3   # 비만 전단계 (초기)
    elif bmi < 26.0:
        return 4   # 비만 전단계 ~ 1단계 비만 경계
    elif bmi < 27.5:
        return 5   # 1단계 비만 (초기)
    elif bmi < 29.0:
        return 6   # 1단계 비만 (후기)
    elif bmi < 30.5:
        return 7   # 2단계 비만 (초기)
    elif bmi < 32.5:
        return 8   # 2단계 비만 (중기)
    elif bmi < 35.0:
        return 9   # 2단계 비만 (후기)
    else:
        return 10  # 3단계 고도비만


def get_bmi_label(step):
    labels = {
        1: "저체중 (BMI 18.5 미만)",
        2: "정상 체중 (BMI 18.5~22.9)",
        3: "과체중 초기 (BMI 23.0~24.4)",
        4: "과체중·비만 경계 (BMI 24.5~25.9)",
        5: "1단계 비만 초기 (BMI 26.0~27.4)",
        6: "1단계 비만 후기 (BMI 27.5~28.9)",
        7: "2단계 비만 초기 (BMI 29.0~30.4)",
        8: "2단계 비만 중기 (BMI 30.5~32.4)",
        9: "2단계 비만 후기 (BMI 32.5~34.9)",
        10: "3단계 고도비만 (BMI 35.0 이상)",
    }
    return labels.get(step, "")


# 이미지에서 바코드 숫자 추출 (가로/세로 회전 및 명암 보정 포함)
def extract_barcode_from_image(image_file):
    img = Image.open(image_file).convert("L")
    candidates = [
        img,
        ImageOps.autocontrast(img).resize((img.width * 2, img.height * 2)),
        img.rotate(90, expand=True),
    ]
    for cand in candidates:
        results = decode(cand)
        if results:
            return results[0].data.decode("utf-8")
    return ""


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

    # 2단계: Open Food Facts API 조회 (sugars_100ml 및 액체 정규화 sugars_100g 확인)
    try:
        url_off = f"https://world.openfoodfacts.org/api/v2/product/{bc}.json"
        headers = {"User-Agent": "SugarDrinkSimulator/1.0"}
        data_off = requests.get(url_off, headers=headers, timeout=5).json()
        if data_off.get("status") == 1:
            product = data_off.get("product", {})
            if not prod_name:
                prod_name = product.get("product_name_ko") or product.get("product_name")
            nutriments = product.get("nutriments", {})
            raw_sugar = nutriments.get("sugars_100ml")
            if raw_sugar is None:
                raw_sugar = nutriments.get("sugars_100g")
            if raw_sugar is not None:
                val = round(float(raw_sugar), 1)
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
st.title("음료 당류 타임머신 시뮬레이터 🥤")
st.progress(current_step / 5)
st.caption(f"단계 {current_step} / 5")
st.write("---")

# =========================================================
# [Step 1] 기본 정보 및 생활 습관 입력 화면
# =========================================================
if current_step == 1:
    st.subheader("👤 1단계: 기본 정보 및 생활 습관을 입력해주세요")
    st.write("성인 신체 정보와 평소 운동량·식사량에 따라 당류 섭취 후 체중 변화가 달라집니다.")

    col1, col2 = st.columns(2)
    with col1:
        gender_idx = 0 if st.session_state.gender == "남자" else 1
        gender = st.radio("성별을 선택하세요", ["남자", "여자"], index=gender_idx)
    with col2:
        age = st.number_input(
            "나이(만 나이, 20세 이상 성인 기준)",
            min_value=20,
            max_value=100,
            value=max(20, int(st.session_state.age)),
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
    col5, col6 = st.columns(2)
    with col5:
        ex_keys = list(EXERCISE_OPTIONS.keys())
        ex_idx = (
            ex_keys.index(st.session_state.exercise)
            if st.session_state.exercise in ex_keys
            else 0
        )
        exercise = st.selectbox("🏃 평소 운동량은 어느 정도인가요?", ex_keys, index=ex_idx)
    with col6:
        food_keys = list(FOOD_OPTIONS.keys())
        food_idx = (
            food_keys.index(st.session_state.food_intake)
            if st.session_state.food_intake in food_keys
            else 1
        )
        food_intake = st.selectbox("🍚 평소 음식은 얼마나 드시나요?", food_keys, index=food_idx)

    st.caption(
        "※ 성인 BMI(대한비만학회 기준)를 적용하며, 운동량과 식사량은 에너지 수지 변화를"
        " 체험하기 위한 시뮬레이션 가정치입니다."
    )
    st.write("")
    if st.button("다음: 현재 체형 확인하기 ▶", use_container_width=True):
        st.session_state.gender = gender
        st.session_state.age = age
        st.session_state.height = height
        st.session_state.weight = weight
        st.session_state.exercise = exercise
        st.session_state.food_intake = food_intake
        st.session_state.step = 2
        st.rerun()

# =========================================================
# [Step 2] 현재 체형 진단 화면
# =========================================================
elif current_step == 2:
    height_m = st.session_state.height / 100.0
    initial_bmi = st.session_state.weight / (height_m ** 2)
    initial_step = get_bmi_step(initial_bmi)
    bmi_label = get_bmi_label(initial_step)
    bmr = calc_bmr(
        st.session_state.gender,
        st.session_state.age,
        st.session_state.height,
        st.session_state.weight,
    )
    prefix = "boy" if st.session_state.gender == "남자" else "girl"

    st.subheader(f"📊 2단계: 나의 현재 체형 진단 (BMI: {initial_bmi:.1f})")
    st.write(
        f"만 **{st.session_state.age}세**, 키 **{st.session_state.height:.1f}cm**, 몸무게"
        f" **{st.session_state.weight:.1f}kg** 기준 **{bmi_label}**입니다."
    )
    st.caption(
        f"추정 기초대사량(BMR): 약 {bmr:,d} kcal/일 · 운동: {st.session_state.exercise} ·"
        f" 식사량: {st.session_state.food_intake}"
    )

    initial_image_path = f"{prefix} {initial_step}.png"
    try:
        initial_img = Image.open(initial_image_path)
        st.image(
            initial_img,
            caption=f"현재 상태: Step {initial_step} / 10 ({bmi_label})",
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
    st.write("음료의 바코드를 촬영하거나 번호를 입력하면 자동으로 다음 단계로 넘어갑니다.")

    reset_cnt = st.session_state.scan_reset_cnt
    barcode_input = ""

    if SCAN_OK:
        uploaded_photo = st.file_uploader(
            "📸 후면 카메라로 바로 촬영하기 (눌러서 '사진 찍기' 선택)",
            type=["png", "jpg", "jpeg"],
            key=f"upload_{reset_cnt}",
        )
        if uploaded_photo:
            barcode_input = extract_barcode_from_image(uploaded_photo)
            if not barcode_input:
                st.warning("사진에서 바코드를 읽지 못했어요. 바코드가 선명하게 나오도록 다시 찍어주세요.")

        with st.expander("또는 웹 카메라로 직접 찍기 (전면 카메라가 켜지면 🔄 버튼으로 전환)"):
            photo = st.camera_input(
                "바코드를 가까이 비춰 촬영하세요", key=f"cam_{reset_cnt}"
            )
            if photo and not barcode_input:
                barcode_input = extract_barcode_from_image(photo)
                if not barcode_input:
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
        f"🥤 1회 음료 당류 섭취량: **{once_sugar}g** (100ml당 {sugar_per_100ml:.1f}g ×"
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
    initial_bmi = weight / (height_m ** 2)
    initial_step = get_bmi_step(initial_bmi)
    bmr = calc_bmr(
        st.session_state.gender,
        st.session_state.age,
        st.session_state.height,
        weight,
    )
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

    # 하루 음료 당류 섭취량 및 당류 유래 열량 (당류 1g = 4kcal)
    daily_sugar_g = round(once_sugar * servings, 1)
    drink_kcal_per_day = daily_sugar_g * 4

    # 식습관(가정치) 및 순수 추가 운동 소모 열량 ((MET - 1) × 체중 × 시간)
    food_kcal_per_day = FOOD_OPTIONS.get(st.session_state.food_intake, 0)
    net_ex_factor = EXERCISE_OPTIONS.get(st.session_state.exercise, 0.0)
    exercise_burn_per_day = round(weight * net_ex_factor)

    # 하루 순 열량 변화 및 1개월 / 설정 기간 누적 열량
    net_daily_kcal = drink_kcal_per_day + food_kcal_per_day - exercise_burn_per_day
    one_month_net_kcal = net_daily_kcal * 30
    total_net_kcal = net_daily_kcal * 30 * months

    # 체중 1kg ≈ 7,700kcal 환산 (교육용 가상 시뮬레이션)
    simulated_weight = max(35.0, weight + total_net_kcal / 7700)
    weight_diff = simulated_weight - weight
    simulated_bmi = simulated_weight / (height_m ** 2)
    simulated_step = get_bmi_step(simulated_bmi)

    if weight_diff >= 0.05:
        diff_text = f"+{weight_diff:.1f}kg"
        weight_color = "#FF4B4B"
    elif weight_diff <= -0.05:
        diff_text = f"{weight_diff:.1f}kg"
        weight_color = "#1E88E5"
    else:
        diff_text = "변화 없음 (0.0kg)"
        weight_color = "#2E7D32"

    st.subheader(f"🔮 5단계: {months}개월 뒤 예상 체형 시뮬레이션 결과")
    st.markdown(
        "<p style='font-size: 26px; font-weight: 700; line-height: 1.4;"
        f" margin-bottom: 8px;'>예상 체중: <span style='color:"
        f" {weight_color};'>{simulated_weight:.1f}kg</span> (현재 대비"
        f" {diff_text}) / 예상 BMI: {simulated_bmi:.1f}</p>",
        unsafe_allow_html=True,
    )

    # 현재 체형 vs 미래 예상 체형 나란히 비교
    col_before, col_after = st.columns(2)
    with col_before:
        st.markdown(f"**현재 체형 ({weight:.1f}kg · BMI {initial_bmi:.1f})**")
        try:
            st.image(
                Image.open(f"{prefix} {initial_step}.png"),
                caption=f"현재: Step {initial_step} / 10 ({get_bmi_label(initial_step)})",
                use_container_width=True,
            )
        except Exception:
            st.warning(f"이미지 파일 없음: {prefix} {initial_step}.png")

    with col_after:
        st.markdown(
            f"**{months}개월 뒤 예상 ({simulated_weight:.1f}kg · BMI {simulated_bmi:.1f})**"
        )
        try:
            st.image(
                Image.open(f"{prefix} {simulated_step}.png"),
                caption=f"{months}개월 뒤: Step {simulated_step} / 10 ({get_bmi_label(simulated_step)})",
                use_container_width=True,
            )
        except Exception:
            st.warning(f"이미지 파일 없음: {prefix} {simulated_step}.png")

    if simulated_step > initial_step:
        st.error("⚠️ 이 습관이 이어지면 체형 단계가 올라갈 수 있습니다!")
    elif weight_diff > 0.5:
        st.warning("⚠️ 체형 단계는 유지되지만 체중이 꾸준히 늘어나는 추세입니다.")
    else:
        st.success("🎉 운동과 식습관 균형 덕분에 현재 체형을 유지하거나 관리할 수 있는 수준입니다.")

    drink_label = st.session_state.prod_name or "직접 입력 음료"
    st.info(
        f"📋 **상세 에너지 수지 및 음료 당류 분석 ({drink_label})**\n"
        f"- **하루 음료 당류 섭취량:** **{daily_sugar_g:.1f}g/일** ({volume_ml}ml × {servings}회)\n"
        f"- **하루 음료 당류 유래 열량:** **+{drink_kcal_per_day:,.0f} kcal/일** (당류 1g = 4kcal)\n"
        f"- **평소 식사량 보정(시뮬레이션 가정치):** **{food_kcal_per_day:+d} kcal/일**"
        f" ({st.session_state.food_intake})\n"
        f"- **순수 추가 운동 소모 열량 ((MET-1)×체중×시간):** **-{exercise_burn_per_day:,d} kcal/일**"
        f" ({st.session_state.exercise})\n"
        f"- **1개월(30일) 누적 순 열량 변화:** **{one_month_net_kcal:+,.0f} kcal**\n"
        f"- **설정 기간({months}개월) 누적 순 열량 변화:** **{total_net_kcal:+,.0f} kcal**"
    )

    st.caption(
        f"※ 참고 기초대사량(만 {st.session_state.age}세 기준): 약 {bmr:,d} kcal/일 | 본 결과는"
        " 음료 당류 섭취와 생활 습관에 따른 에너지 수지 원리를 이해하기 위한 교육용 가상"
        " 시뮬레이션이며, 개인의 대사 적응이나 음료 내 기타 영양소(지방·단백질 등)에 따라"
        " 실제 체중 변화는 달라질 수 있습니다."
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
