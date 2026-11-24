import base64
import random
import re
import time
from PIL import Image, ImageOps
import requests
import streamlit as st
import streamlit.components.v1 as components

try:
    from pyzbar.pyzbar import decode
    PHOTO_SCAN_OK = True
except Exception:
    PHOTO_SCAN_OK = False

# 페이지 설정
st.set_page_config(
    page_title="음료 당류 타임머신 시뮬레이터",
    page_icon="🥤",
    layout="centered",
)

# API 키 설정 (Streamlit Secrets 활용)
API_KEY = st.secrets["API_KEY"]

# 평소 일상 활동량에 따른 시뮬레이션용 일일 변화 가정치 (kcal/일)
ACTIVITY_OPTIONS = {
    "주로 앉아서 생활 (학생·사무직 등, 기준 0 kcal/일)": 0,
    "보통 활동 (출퇴근·가사·가벼운 걷기, -80 kcal/일)": 80,
    "활동적인 편 (서서 일하거나 이동이 많음, -180 kcal/일)": 180,
    "매우 활동적 (활동량이 매우 많은 직업·생활, -300 kcal/일)": 300,
}

# 순수 추가 운동 소모 계수: (MET - 1) × 1회 운동시간(h) × 주당 횟수 ÷ 7
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

# 중간 전환용 건강 Tip 목록
HEALTH_TIPS = [
    "소화 속도를 늦추는 '거꾸로 식사법': 식사 시 채소 → 단백질·지방 → 탄수화물 순서로 실천해 보세요!",
    "액상과당 음료는 고체 음식보다 포만감이 적어 열량을 과잉 섭취하기 쉽고, 과당은 간에서 대사되며 과잉 시 체지방 합성으로 이어질 수 있습니다.",
    "음료를 마신 뒤 10~15분만 가볍게 걸어도 식후 혈당이 급격히 오르는 것을 완화하는 데 도움이 될 수 있어요!",
    "세계보건기구(WHO)는 첨가당을 하루 총 열량의 10% 미만으로, 추가 건강 이득을 위해서는 5% 미만(성인 약 25g 이내)으로 줄이도록 권고합니다.",
    "음료 뒷면 영양성분표를 볼 때는 '100ml당' 기준인지 '총 내용량' 기준인지 꼭 확인해 보세요!",
    "탄산음료 대신 탄산수에 레몬이나 라임을 띄워 마시면 청량감은 살리고 당류는 0g으로 줄일 수 있어요.",
    "과일 주스도 식이섬유가 걸러진 상태라 생과일을 통째로 먹는 것보다 혈당이 더 빠르게 오를 수 있습니다.",
    "단 음료를 자주 마시면 단맛 자극에 익숙해져 점점 더 강한 단맛을 찾게 되는 경향이 생길 수 있습니다.",
]

# 6단계 처방용 운동 목록 및 등산 코스 데이터
EXERCISE_TYPES = ["뛰기", "계단 오르기", "등산하기", "수영하기"]

MOUNTAIN_COURSES = [
    {"name": "남산 (서울)", "hours": 1.2, "note": "순환 산책로·정상 왕복 기준"},
    {"name": "아차산 (서울·구리)", "hours": 1.5, "note": "고구려정·정상 왕복 기준"},
    {"name": "청계산 (서울·과천)", "hours": 2.5, "note": "매봉 왕복 코스 기준"},
    {"name": "관악산 (서울·안양)", "hours": 3.0, "note": "연주대 왕복 코스 기준"},
    {"name": "북한산 (서울·고양)", "hours": 3.5, "note": "백운대 왕복 코스 기준"},
    {"name": "한라산 (제주)", "hours": 8.0, "note": "성판악~백록담 왕복 기준"},
]

# 세션 상태 초기화
defaults = {
    "step": 1,
    "gender": "남자",
    "age": 25,
    "height": 175.0,
    "weight": 65.0,
    "activity": "주로 앉아서 생활 (학생·사무직 등, 기준 0 kcal/일)",
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
    "scroll_id": 0,
    "pending_tip_step": None,
    "current_tip": "",
    "shown_tips": [],
    "selected_workout": None,
    "selected_mountain": None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

if "tip_target_steps" not in st.session_state:
    st.session_state.tip_target_steps = random.sample(
        [2, 3, 4, 5, 6], k=random.randint(1, 2)
    )


# 화면 이동 시 스크롤을 최상단으로 초기화하는 함수
# 화면 이동 시 스크롤을 최상단으로 초기화하는 함수
def scroll_to_top():
    sid = st.session_state.get("scroll_id", 0)
    components.html(
        f"""
        <!-- scroll_{sid} -->
        <script>
          function resetScrollTop() {{
            try {{
              const doc = window.parent.document;
              window.parent.scrollTo({{ top: 0, left: 0, behavior: 'instant' }});
              const targets = doc.querySelectorAll(
                '[data-testid="stMain"], [data-testid="stAppViewContainer"], section.main, .main, html, body'
              );
              targets.forEach((el) => {{
                el.scrollTop = 0;
              }});
              const topHeading = doc.querySelector('h1');
              if (topHeading) {{
                topHeading.scrollIntoView({{ behavior: 'instant', block: 'start' }});
              }}
            }} catch (e) {{}}
          }}
          resetScrollTop();
          setTimeout(resetScrollTop, 50);
          setTimeout(resetScrollTop, 150);
          setTimeout(resetScrollTop, 300);
        </script>
        """,
        height=1,
    )


# 단계 전환 헬퍼 함수 (랜덤 Tip 1~2회 자동 표시 포함)
def go_to_step(target_step, allow_tip=True):
    st.session_state.scroll_id += 1
    if allow_tip and target_step in st.session_state.tip_target_steps:
        st.session_state.tip_target_steps.remove(target_step)
        candidates = [t for t in HEALTH_TIPS if t not in st.session_state.shown_tips]
        if not candidates:
            st.session_state.shown_tips = []
            candidates = HEALTH_TIPS[:]
        chosen_tip = random.choice(candidates)
        st.session_state.shown_tips.append(chosen_tip)
        st.session_state.current_tip = chosen_tip
        st.session_state.pending_tip_step = target_step
    else:
        st.session_state.pending_tip_step = None
        st.session_state.step = target_step
    st.rerun()


# 기초대사량(BMR) 계산 함수 (Mifflin-St Jeor 공식)
def calc_bmr(gender, age, height, weight):
    base = 10 * weight + 6.25 * height - 5 * age
    return round(base + 5 if gender == "남자" else base - 161)


# 성인 BMI 기준 10단계 매핑 함수 (대한비만학회 기준: 23 비만전단계 / 25 1단계 / 30 2단계 / 35 3단계)
def get_bmi_step(bmi):
    if bmi < 18.5:
        return 1   # 저체중
    elif bmi < 23.0:
        return 2   # 정상 체중
    elif bmi < 24.0:
        return 3   # 비만 전단계 (초기)
    elif bmi < 25.0:
        return 4   # 비만 전단계 (후기)
    elif bmi < 26.5:
        return 5   # 1단계 비만 (초기)
    elif bmi < 28.0:
        return 6   # 1단계 비만 (중기)
    elif bmi < 30.0:
        return 7   # 1단계 비만 (후기)
    elif bmi < 32.5:
        return 8   # 2단계 비만 (초기)
    elif bmi < 35.0:
        return 9   # 2단계 비만 (후기)
    else:
        return 10  # 3단계 고도비만


def get_bmi_label(step):
    labels = {
        1: "저체중",
        2: "정상 체중",
        3: "비만 전단계 초기",
        4: "비만 전단계 후기",
        5: "1단계 비만 초기",
        6: "1단계 비만 중기",
        7: "1단계 비만 후기",
        8: "2단계 비만 초기",
        9: "2단계 비만 후기",
        10: "3단계 고도비만",
    }
    return labels.get(step, "")


def format_hours_minutes(total_hours):
    if total_hours <= 0:
        return "0분"
    total_mins = round(total_hours * 60)
    hrs = total_mins // 60
    mins = total_mins % 60
    if hrs == 0:
        return f"약 {mins}분"
    elif mins == 0:
        return f"약 {hrs:,d}시간"
    return f"약 {hrs:,d}시간 {mins}분"


# 로컬 이미지를 HTML 나란히 배치를 위한 Base64 문자열로 변환
def img_to_base64(path):
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except Exception:
        return ""


# 사진 업로드 보조용 바코드 추출 함수
def extract_barcode_from_image(image_file):
    if not PHOTO_SCAN_OK:
        return ""
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


# 브라우저 내장 실시간 바코드 스캐너 (추가 파이썬 패키지 불필요)
def render_auto_barcode_scanner():
    scanner_html = """
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8" />
      <script src="https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js"></script>
      <style>
        body {
          margin: 0;
          padding: 0;
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
          background: transparent;
        }
        .wrap {
          border: 2px dashed #94A3B8;
          border-radius: 12px;
          padding: 10px;
          background: #F8FAFC;
          text-align: center;
        }
        #reader {
          width: 100%;
          max-width: 380px;
          margin: 0 auto;
          border-radius: 8px;
          overflow: hidden;
        }
        #status {
          font-size: 13px;
          font-weight: 600;
          color: #334155;
          margin-top: 8px;
        }
        #startBtn {
          display: none;
          margin: 8px auto 0 auto;
          padding: 8px 16px;
          font-size: 14px;
          font-weight: 700;
          color: #FFFFFF;
          background: #2563EB;
          border: none;
          border-radius: 8px;
          cursor: pointer;
        }
      </style>
    </head>
    <body>
      <div class="wrap">
        <div id="reader"></div>
        <div id="status">📷 후면 카메라를 켜는 중입니다... 바코드를 비춰주세요.</div>
        <button id="startBtn" onclick="startCamera()">카메라 다시 시작하기</button>
      </div>

      <script>
        let html5QrCode = null;
        let hasScanned = false;

        function sendBarcodeToStreamlit(code) {
          try {
            const parentDoc = window.parent.document;
            const inputs = parentDoc.querySelectorAll('input[type="text"]');
            let targetInput = null;
            for (const inp of inputs) {
              if ((inp.placeholder || "").includes("바코드")) {
                targetInput = inp;
                break;
              }
            }
            if (targetInput) {
              const nativeSetter = Object.getOwnPropertyDescriptor(
                window.parent.HTMLInputElement.prototype,
                "value"
              ).set;
              nativeSetter.call(targetInput, code);
              targetInput.dispatchEvent(new Event("input", { bubbles: true }));
              targetInput.dispatchEvent(
                new KeyboardEvent("keydown", {
                  key: "Enter",
                  code: "Enter",
                  keyCode: 13,
                  which: 13,
                  bubbles: true,
                })
              );
              targetInput.dispatchEvent(new Event("change", { bubbles: true }));
              targetInput.blur();
            }
          } catch (e) {
            document.getElementById("status").innerText =
              "✅ 인식된 바코드: " + code + " (아래 입력칸에 입력해 주세요)";
          }
        }

        function onScanSuccess(decodedText) {
          if (hasScanned) return;
          const clean = (decodedText || "").trim();
          if (/^\\d{8,14}$/.test(clean)) {
            hasScanned = true;
            document.getElementById("status").style.color = "#16A34A";
            document.getElementById("status").innerText =
              "✅ 바코드 인식 완료 (" + clean + ")! 다음 단계로 이동합니다...";
            if (html5QrCode) {
              html5QrCode.stop().catch(() => {});
            }
            sendBarcodeToStreamlit(clean);
          }
        }

        function startCamera() {
          document.getElementById("startBtn").style.display = "none";
          document.getElementById("status").style.color = "#334155";
          document.getElementById("status").innerText =
            "📷 후면 카메라를 켜는 중입니다... 바코드를 비춰주세요.";

          if (!html5QrCode) {
            html5QrCode = new Html5Qrcode("reader");
          }
          const config = {
            fps: 12,
            qrbox: { width: 250, height: 120 },
            aspectRatio: 1.5,
          };
          html5QrCode
            .start({ facingMode: "environment" }, config, onScanSuccess, () => {})
            .then(() => {
              document.getElementById("status").innerText =
                "🔍 바코드를 사각형 안에 비추면 자동으로 찍힙니다!";
            })
            .catch((err) => {
              document.getElementById("status").style.color = "#DC2626";
              document.getElementById("status").innerText =
                "⚠️ 브라우저 카메라 권한을 허용하거나 아래 사진 촬영/직접 입력을 이용해 주세요.";
              document.getElementById("startBtn").style.display = "inline-block";
            });
        }

        window.addEventListener("load", startCamera);
      </script>
    </body>
    </html>
    """
    components.html(scanner_html, height=275)


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

    if any(w in norm_name for w in ["제로", "zero", "무설탕", "무당"]):
        return 0.0

    for key in sorted(KOREAN_DRINK_SUGAR_100ML.keys(), key=len, reverse=True):
        if key in norm_name:
            return KOREAN_DRINK_SUGAR_100ML[key]
    return None


def lookup_nutrition_100ml(bc):
    prod_name = None
    sugar_100ml = None
    source_type = None

    # 1단계: 식품안전나라 C005로 한국 제품명 조회
    try:
        url_c005 = f"http://openapi.foodsafetykorea.go.kr/api/{API_KEY}/C005/json/1/5/BAR_CD={bc}"
        data_c005 = requests.get(url_c005, timeout=5).json()
        rows_c005 = data_c005.get("C005", {}).get("row", [])
        if rows_c005:
            prod_name = rows_c005[0].get("PRDLST_NM")
    except Exception:
        pass

    # 2단계: Open Food Facts API 조회
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


# 매 페이지 렌더링 시 최상단 스크롤 실행
scroll_to_top()

# =========================================================
# [중간 전환] 건강 Tip 카드 화면 (전체 과정 중 1~2회 랜덤 표시)
# =========================================================
if st.session_state.pending_tip_step is not None:
    next_s = st.session_state.pending_tip_step
    st.title("음료 당류 타임머신 시뮬레이터 🥤")
    st.progress(next_s / 6)
    st.caption(f"단계 {next_s} / 6 이동 중...")
    st.write("---")

    tip_html = f"""
    <div style="min-height: 48vh; display: flex; align-items: center; justify-content: center; padding: 12px 0;">
        <div style="width: 100%; max-width: 520px; background: linear-gradient(135deg, #ECFDF5 0%, #EFF6FF 100%); border: 2px solid #10B981; border-radius: 16px; padding: 28px 22px; text-align: center; box-shadow: 0 6px 18px rgba(16,185,129,0.14);">
            <div style="display: inline-block; background: #10B981; color: #FFFFFF; font-size: 13px; font-weight: 800; padding: 4px 12px; border-radius: 999px; margin-bottom: 14px;">
                💡 잠깐! 당류 건강 Tip
            </div>
            <div style="font-size: 18px; font-weight: 800; color: #0F172A; line-height: 1.6; word-break: keep-all;">
                {st.session_state.current_tip}
            </div>
            <div style="font-size: 12px; color: #64748B; margin-top: 16px;">
                잠시 후 다음 화면으로 자동으로 넘어갑니다...
            </div>
        </div>
    </div>
    """
    st.markdown(tip_html, unsafe_allow_html=True)
    st.session_state.scroll_id += 1
    scroll_to_top()

    time.sleep(2.6)
    st.session_state.step = next_s
    st.session_state.pending_tip_step = None
    st.session_state.scroll_id += 1
    st.rerun()

# 공통 헤더 및 단계 진행바
current_step = st.session_state.step
st.title("음료 당류 타임머신 시뮬레이터 🥤")
st.progress(current_step / 6)
st.caption(f"단계 {current_step} / 6")
st.write("---")

# =========================================================
# [Step 1] 기본 정보 및 생활 습관 입력 화면
# =========================================================
if current_step == 1:
    st.subheader("👤 1단계: 기본 정보 및 생활 습관을 입력해주세요")
    st.write("성인 신체 정보와 평소 활동량·운동량·식사량에 따라 당류 섭취 후 체중 변화가 달라집니다.")

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
            value=round(float(st.session_state.height), 1),
            step=0.1,
            format="%.1f",
        )
    with col4:
        weight = st.number_input(
            "몸무게(kg)를 입력하세요",
            min_value=30.0,
            max_value=200.0,
            value=round(float(st.session_state.weight), 1),
            step=0.1,
            format="%.1f",
        )

    st.write("")
    col5, col6 = st.columns(2)
    with col5:
        act_keys = list(ACTIVITY_OPTIONS.keys())
        act_idx = (
            act_keys.index(st.session_state.activity)
            if st.session_state.activity in act_keys
            else 0
        )
        activity = st.selectbox("🚶 평소 일상 활동량은 어느 정도인가요?", act_keys, index=act_idx)
    with col6:
        ex_keys = list(EXERCISE_OPTIONS.keys())
        ex_idx = (
            ex_keys.index(st.session_state.exercise)
            if st.session_state.exercise in ex_keys
            else 0
        )
        exercise = st.selectbox("🏃 평소 운동량은 어느 정도인가요?", ex_keys, index=ex_idx)

    food_keys = list(FOOD_OPTIONS.keys())
    food_idx = (
        food_keys.index(st.session_state.food_intake)
        if st.session_state.food_intake in food_keys
        else 1
    )
    food_intake = st.selectbox("🍚 평소 음식은 얼마나 드시나요?", food_keys, index=food_idx)

    st.caption(
        "※ 성인 BMI(대한비만학회 기준)를 적용하며, 활동량·운동량·식사량은 현재 체중 유지 기준에서"
        " 생활 습관 변화가 더해졌을 때의 에너지 수지를 체험하기 위한 교육용 시뮬레이션 가정치입니다."
    )
    st.write("")
    if st.button("다음: 현재 체형 확인하기 ▶", use_container_width=True):
        st.session_state.gender = gender
        st.session_state.age = age
        st.session_state.height = round(height, 1)
        st.session_state.weight = round(weight, 1)
        st.session_state.activity = activity
        st.session_state.exercise = exercise
        st.session_state.food_intake = food_intake
        go_to_step(2, allow_tip=True)

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
        f"추정 기초대사량(BMR): 약 {bmr:,d} kcal/일 · 활동량: {st.session_state.activity} ·"
        f" 운동: {st.session_state.exercise} · 식사량: {st.session_state.food_intake}"
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
            go_to_step(1, allow_tip=False)
    with col_next:
        if st.button("다음: 음료 바코드 확인하기 ▶", use_container_width=True):
            go_to_step(3, allow_tip=True)

# =========================================================
# [Step 3] 음료 바코드 자동 실시간 스캔 화면
# =========================================================
elif current_step == 3:
    st.subheader("📷 3단계: 음료 바코드 자동 스캔")
    st.write("카메라 화면에 바코드를 비추면 **셔터를 누르지 않아도 자동 인식**되어 넘어갑니다.")

    reset_cnt = st.session_state.scan_reset_cnt
    barcode_input = ""

    # 브라우저 내장 실시간 자동 스캐너 실행
    render_auto_barcode_scanner()

    # 자동 인식 결과를 받거나 직접 입력하는 입력칸
    manual = st.text_input(
        "바코드 번호 자동 입력 / 직접 입력 후 엔터(Enter)",
        placeholder="바코드 숫자(8~14자리)가 자동 입력되거나 직접 입력하세요",
        key=f"manual_{reset_cnt}",
    )
    if manual.strip():
        barcode_input = manual.strip()

    if PHOTO_SCAN_OK:
        with st.expander("📸 사진 찍기 / 갤러리 이미지로 인식하기"):
            uploaded_photo = st.file_uploader(
                "바코드 사진을 선택하거나 촬영하세요",
                type=["png", "jpg", "jpeg"],
                key=f"upload_{reset_cnt}",
            )
            if uploaded_photo and not barcode_input:
                barcode_input = extract_barcode_from_image(uploaded_photo)
                if not barcode_input:
                    st.warning("사진에서 바코드를 읽지 못했어요. 바코드가 선명하게 나오도록 다시 찍어주세요.")

    if barcode_input.strip():
        bc_clean = barcode_input.strip()
        if re.fullmatch(r"\d{8,14}", bc_clean):
            with st.spinner(f"바코드({bc_clean}) 인식 완료! 제품 정보를 조회하는 중..."):
                prod_name, found_100ml, source_type = lookup_nutrition_100ml(bc_clean)

            st.session_state.barcode = bc_clean
            st.session_state.prod_name = prod_name
            st.session_state.found_100ml = found_100ml
            st.session_state.source_type = source_type
            st.session_state.sugar_per_100ml = (
                float(found_100ml) if found_100ml is not None else 10.0
            )
            go_to_step(4, allow_tip=True)
        else:
            st.warning(
                f"인식된 값({bc_clean})이 일반 상품 바코드(숫자 8~14자리)가 아닙니다. 음료 바코드를 다시 비춰주세요."
            )

    st.write("---")
    col_prev, col_skip = st.columns(2)
    with col_prev:
        if st.button("◀ 이전 (현재 체형)", use_container_width=True):
            go_to_step(2, allow_tip=False)
    with col_skip:
        if st.button("바코드 없이 직접 입력하기 ▶", use_container_width=True):
            st.session_state.barcode = ""
            st.session_state.prod_name = None
            st.session_state.found_100ml = None
            st.session_state.source_type = None
            st.session_state.sugar_per_100ml = 10.0
            go_to_step(4, allow_tip=True)

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
        value=round(float(st.session_state.sugar_per_100ml), 1),
        step=0.1,
        format="%.1f",
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
            go_to_step(3, allow_tip=False)
    with col_next:
        if st.button("다음: 미래 체형 결과 보기 🔮", use_container_width=True):
            st.session_state.sugar_per_100ml = round(sugar_per_100ml, 1)
            st.session_state.vol_choice = vol_choice
            st.session_state.custom_vol = custom_vol
            st.session_state.servings = servings
            st.session_state.months = months
            go_to_step(5, allow_tip=True)

# =========================================================
# [Step 5] 체형 시뮬레이션 결과 화면 (한눈에 보는 과거 -> 추정 체형 비교)
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

    daily_sugar_g = round(once_sugar * servings, 1)
    drink_kcal_per_day = daily_sugar_g * 4

    food_kcal_per_day = FOOD_OPTIONS.get(st.session_state.food_intake, 0)
    activity_burn_per_day = ACTIVITY_OPTIONS.get(st.session_state.activity, 0)
    net_ex_factor = EXERCISE_OPTIONS.get(st.session_state.exercise, 0.0)
    exercise_burn_per_day = round(weight * net_ex_factor)

    net_daily_kcal = (
        drink_kcal_per_day
        + food_kcal_per_day
        - activity_burn_per_day
        - exercise_burn_per_day
    )
    one_month_net_kcal = net_daily_kcal * 30
    total_net_kcal = net_daily_kcal * 30 * months

    simulated_weight = max(35.0, weight + total_net_kcal / 7700)
    weight_diff = simulated_weight - weight
    simulated_bmi = simulated_weight / (height_m ** 2)
    simulated_step = get_bmi_step(simulated_bmi)

    if weight_diff >= 0.05:
        diff_badge = f"+{weight_diff:.1f}kg"
        accent_color = "#DC2626"
    elif weight_diff <= -0.05:
        diff_badge = f"{weight_diff:.1f}kg"
        accent_color = "#2563EB"
    else:
        diff_badge = "0.0kg"
        accent_color = "#16A34A"

    st.subheader(f"🔮 5단계: {months}개월 뒤 체형 변화 결과")

    before_b64 = img_to_base64(f"{prefix} {initial_step}.png")
    after_b64 = img_to_base64(f"{prefix} {simulated_step}.png")

    before_img_html = (
        f'<img src="data:image/png;base64,{before_b64}"'
        ' style="width:100%; max-width:125px; height:145px; object-fit:contain; margin:6px auto; display:block;" />'
        if before_b64
        else f'<div style="height:145px; display:flex; align-items:center; justify-content:center; color:#6B7280; font-size:12px;">{prefix} {initial_step}.png</div>'
    )
    after_img_html = (
        f'<img src="data:image/png;base64,{after_b64}"'
        ' style="width:100%; max-width:125px; height:145px; object-fit:contain; margin:6px auto; display:block;" />'
        if after_b64
        else f'<div style="height:145px; display:flex; align-items:center; justify-content:center; color:#6B7280; font-size:12px;">{prefix} {simulated_step}.png</div>'
    )

    comparison_html = f"""
    <div style="display:flex; align-items:center; justify-content:space-between; gap:6px; margin:8px 0 12px 0;">
        <div style="flex:1; background:#F8FAFC; border:1px solid #E2E8F0; border-radius:12px; padding:10px 6px; text-align:center;">
            <div style="font-size:12px; font-weight:700; color:#475569;">과거(현재) 체형</div>
            <div style="font-size:23px; font-weight:900; color:#0F172A; line-height:1.2; margin:4px 0 2px 0; letter-spacing:-0.02em;">{weight:.1f}kg</div>
            {before_img_html}
            <div style="font-size:11px; color:#64748B;">BMI {initial_bmi:.1f} · Step {initial_step} ({get_bmi_label(initial_step)})</div>
        </div>
        <div style="font-size:22px; font-weight:900; color:#64748B; padding:0 2px;">➔</div>
        <div style="flex:1; background:#FFFBEB; border:2px solid #F59E0B; border-radius:12px; padding:10px 6px; text-align:center;">
            <div style="font-size:12px; font-weight:700; color:#B45309;">추정 체형 ({months}개월 후)</div>
            <div style="font-size:23px; font-weight:900; color:{accent_color}; line-height:1.2; margin:4px 0 2px 0; letter-spacing:-0.02em;">{simulated_weight:.1f}kg <span style="font-size:15px; font-weight:800;">({diff_badge})</span></div>
            {after_img_html}
            <div style="font-size:11px; color:#64748B;">BMI {simulated_bmi:.1f} · Step {simulated_step} ({get_bmi_label(simulated_step)})</div>
        </div>
    </div>
    """
    st.markdown(comparison_html, unsafe_allow_html=True)

    if simulated_step > initial_step:
        st.error(f"⚠️ 체형 단계가 Step {initial_step} → Step {simulated_step}로 올라갈 수 있습니다!")
    elif weight_diff > 0.5:
        st.warning(f"⚠️ 체형 단계는 유지되지만 체중이 {diff_badge} 늘어나는 추세입니다.")
    else:
        st.success("🎉 현재 체형을 안정적으로 유지할 수 있는 수준입니다.")

    drink_label = st.session_state.prod_name or "직접 입력 음료"
    with st.expander(f"📋 상세 칼로리·당류 분석 보기 ({drink_label})"):
        st.markdown(
            f"- **하루 음료 당류 섭취량:** **{daily_sugar_g:.1f}g/일** ({volume_ml}ml × {servings}회)\n"
            f"- **하루 음료 당류 유래 열량:** **+{drink_kcal_per_day:,.0f} kcal/일** (당류 1g = 4kcal)\n"
            f"- **평소 식사량 보정(시뮬레이션 가정치):** **{food_kcal_per_day:+d} kcal/일**"
            f" ({st.session_state.food_intake})\n"
            f"- **평소 일상 활동 소모 열량(가정치):** **-{activity_burn_per_day:,d} kcal/일**"
            f" ({st.session_state.activity})\n"
            f"- **순수 추가 운동 소모 열량 ((MET-1)×체중×시간):** **-{exercise_burn_per_day:,d} kcal/일**"
            f" ({st.session_state.exercise})\n"
            f"- **1개월(30일) 누적 순 열량 변화:** **{one_month_net_kcal:+,.0f} kcal**\n"
            f"- **설정 기간({months}개월) 누적 순 열량 변화:** **{total_net_kcal:+,.0f} kcal**\n\n"
            f"※ 참고 기초대사량(만 {st.session_state.age}세 기준): 약 {bmr:,d} kcal/일 | 생활 습관 항목은"
            " 현재 체중 유지 기준을 벗어난 변화를 체험하기 위한 교육용 가상 가정치입니다."
        )

    st.write("")
    col_prev, col_next = st.columns(2)
    with col_prev:
        if st.button("◀ 섭취량/기간 조절", use_container_width=True):
            go_to_step(4, allow_tip=False)
    with col_next:
        if st.button("다음: 소모 운동량 처방 보기 🏃 ▶", use_container_width=True):
            st.session_state.selected_workout = random.choice(EXERCISE_TYPES)
            st.session_state.selected_mountain = random.choice(MOUNTAIN_COURSES)
            go_to_step(6, allow_tip=True)

# =========================================================
# [Step 6] 누적 섭취량 소모 운동 처방 화면
# =========================================================
elif current_step == 6:
    weight = st.session_state.weight
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

    daily_sugar_g = round(once_sugar * servings, 1)
    total_drink_sugar_g = daily_sugar_g * 30 * months
    total_drink_kcal = total_drink_sugar_g * 4

    if st.session_state.selected_workout not in EXERCISE_TYPES:
        st.session_state.selected_workout = random.choice(EXERCISE_TYPES)
    if st.session_state.selected_mountain is None:
        st.session_state.selected_mountain = random.choice(MOUNTAIN_COURSES)

    workout = st.session_state.selected_workout
    mountain = st.session_state.selected_mountain

    st.subheader(f"🏃 6단계: {months}개월 누적 당류 칼로리 소모 처방")
    st.info(
        f"🥤 **{months}개월({30 * months}일)** 동안 마신 음료의 총 당류는"
        f" **{total_drink_sugar_g:,.1f}g**, 누적 열량은 **{total_drink_kcal:,.0f} kcal**입니다.\n\n"
        f"현재 체중(**{weight:.1f}kg**) 기준으로 이 누적 열량을 모두 태우려면 아래만큼 운동해야 해요!"
    )

    # 운동별 순수 추가 소모 계수 (MET - 1)
    workout_specs = {
        "뛰기": {
            "emoji": "🏃",
            "net_met": 7.5,  # 러닝(약 8km/h, MET 8.5)
            "color": "#DC2626",
            "bg": "#FEF2F2",
            "border": "#FCA5A5",
        },
        "계단 오르기": {
            "emoji": "🪜",
            "net_met": 7.0,  # 계단 오르기(MET 8.0)
            "color": "#D97706",
            "bg": "#FFFBEB",
            "border": "#FCD34D",
        },
        "등산하기": {
            "emoji": "⛰️",
            "net_met": 6.0,  # 등산(MET 7.0)
            "color": "#059669",
            "bg": "#ECFDF5",
            "border": "#6EE7B7",
        },
        "수영하기": {
            "emoji": "🏊",
            "net_met": 6.5,  # 수영(자유형·평영 보통, MET 7.5)
            "color": "#2563EB",
            "bg": "#EFF6FF",
            "border": "#93C5FD",
        },
    }

    spec = workout_specs[workout]
    kcal_per_hour = max(1.0, spec["net_met"] * weight)
    req_hours = total_drink_kcal / kcal_per_hour if total_drink_kcal > 0 else 0.0
    time_text = format_hours_minutes(req_hours)

    if total_drink_kcal <= 0:
        detail_desc = "선택하신 음료는 당류 0g(0 kcal)이라 추가로 태워야 할 열량이 없습니다! 🎉"
    elif workout == "뛰기":
        est_km = round(req_hours * 8.0, 1)
        detail_desc = f"시속 8km 속도로 약 <b>{est_km:,.1f}km</b>를 달려야 소모되는 열량입니다."
    elif workout == "계단 오르기":
        est_floors = round(req_hours * 60 * 3.5)
        detail_desc = f"아파트 계단 기준 약 <b>{est_floors:,d}층</b>을 걸어 올라가야 소모되는 열량입니다."
    elif workout == "등산하기":
        climb_count = round(req_hours / mountain["hours"], 1)
        detail_desc = (
            f"지정 산: <b>{mountain['name']}</b> ({mountain['note']}, 1회 약 {mountain['hours']}시간)<br/>"
            f"👉 <b>{mountain['name']}</b> 코스를 약 <b>{climb_count:,.1f}번</b> 등산해야 소모되는 열량입니다!"
        )
    else:  # 수영하기
        est_laps = round(req_hours * 45)
        detail_desc = f"25m 수영장 레인 기준 약 <b>{est_laps:,d}바퀴</b>를 왕복해야 소모되는 열량입니다."

    workout_card_html = f"""
    <div style="background:{spec['bg']}; border:2px solid {spec['border']}; border-radius:16px; padding:22px 16px; margin:10px 0 16px 0; text-align:center;">
        <div style="font-size:15px; font-weight:800; color:{spec['color']}; margin-bottom:6px;">
            {spec['emoji']} 추천 소모 운동: {workout}
        </div>
        <div style="font-size:30px; font-weight:900; color:#0F172A; line-height:1.25; margin:6px 0 10px 0;">
            총 {time_text}
        </div>
        <div style="font-size:14px; color:#334155; line-height:1.6; word-break:keep-all;">
            {detail_desc}
        </div>
        <div style="font-size:11px; color:#64748B; margin-top:10px;">
            ※ {weight:.1f}kg 기준 시간당 약 {round(kcal_per_hour):,d} kcal 순수 추가 소모
        </div>
    </div>
    """
    st.markdown(workout_card_html, unsafe_allow_html=True)

    st.caption("👇 아래 버튼을 눌러 다른 운동 방법으로도 확인해 보세요! (등산하기를 다시 누르면 다른 산이 지정됩니다)")
    btn_cols = st.columns(4)
    btn_labels = [
        ("🏃 뛰기", "뛰기"),
        ("🪜 계단 오르기", "계단 오르기"),
        ("⛰️ 등산하기", "등산하기"),
        ("🏊 수영하기", "수영하기"),
    ]
    for idx, (label, w_name) in enumerate(btn_labels):
        with btn_cols[idx]:
            is_active = workout == w_name
            if st.button(
                label,
                key=f"wk_btn_{w_name}",
                use_container_width=True,
                type="primary" if is_active else "secondary",
            ):
                if w_name == "등산하기":
                    other_mountains = [
                        m for m in MOUNTAIN_COURSES if m["name"] != mountain["name"]
                    ]
                    st.session_state.selected_mountain = random.choice(other_mountains)
                st.session_state.selected_workout = w_name
                st.rerun()

    st.write("---")
    col_prev, col_restart = st.columns(2)
    with col_prev:
        if st.button("◀ 이전 (체형 변화 결과)", use_container_width=True):
            go_to_step(5, allow_tip=False)
    with col_restart:
        if st.button("처음부터 다시 하기 🔄", use_container_width=True):
            st.session_state.barcode = ""
            st.session_state.prod_name = None
            st.session_state.found_100ml = None
            st.session_state.source_type = None
            st.session_state.scan_reset_cnt += 1
            st.session_state.selected_workout = None
            st.session_state.selected_mountain = None
            st.session_state.tip_target_steps = random.sample(
                [2, 3, 4, 5, 6], k=random.randint(1, 2)
            )
            go_to_step(1, allow_tip=False)
