
import os
import io
import html
import hashlib

import streamlit as st
from openai import OpenAI
from audiorecorder import audiorecorder


# ==========================================
# 1. 페이지 설정
# ==========================================
st.set_page_config(
    page_title="Thumbs Up AI",
    page_icon="👍🏻",
    layout="wide",
    initial_sidebar_state="collapsed"
)


# ==========================================
# 2. CSS 디자인
# ==========================================
st.markdown("""
<style>
.block-container {
    max-width: 1180px;
    padding-top: 2rem;
    padding-bottom: 2rem;
}

[data-testid="stSidebar"] {
    display: none;
}

/* 메인 카드 */
.st-key-assistant_card {
    background: white !important;
    border: 1px solid #e5e5e7 !important;
    border-radius: 26px !important;
    padding: 28px 34px 30px !important;
}

/* 로고 */
.brand-title {
    font-size: 24px;
    font-weight: 750;
    color: #202020;
}

/* 설정 버튼 */
.st-key-settings_button button {
    border: none !important;
    background: transparent !important;
    box-shadow: none !important;
    font-size: 25px;
}

/* 중앙 제목 */
.center-heading {
    font-size: 26px;
    font-weight: 750;
    text-align: center;
    color: #202020;
    margin-top: 12px;
}

.center-subtitle {
    font-size: 16px;
    color: #8b8b8b;
    text-align: center;
    margin-top: 12px;
}

/* 웨이브 */
.wave-left, .wave-right {
    height: 12px;
    border-radius: 100%;
    margin-top: 34px;
    filter: blur(2px);
    opacity: 0.75;
}

.wave-left {
    background: linear-gradient(
        90deg,
        transparent 0%,
        #c6d4ff 35%,
        #b9c7ff 65%,
        #f2c3d8 100%
    );
}

.wave-right {
    background: linear-gradient(
        90deg,
        #f2c3d8 0%,
        #c3cbff 40%,
        #c6d4ff 70%,
        transparent 100%
    );
}

/* 답변 영역 */
.answer-title {
    font-size: 20px;
    font-weight: 650;
    color: #222222;
    margin-bottom: 8px;
}

.answer-text {
    font-size: 17px;
    line-height: 1.7;
    color: #686868;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
}

.answer-text.clamped {
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
    overflow: hidden;
}

.st-key-more_button button {
    border: none !important;
    background: transparent !important;
    box-shadow: none !important;
    color: #687389;
}

/* 녹음 안내 */
.mic-hint {
    text-align: center;
    color: #959595;
    font-size: 13px;
    margin-top: 10px;
}
</style>
""", unsafe_allow_html=True)


# ==========================================
# 3. 상태 초기화
# ==========================================
DEFAULTS = {
    "answer": "",
    "transcript": "",
    "audio_answer": None,
    "expanded": False,
    "history": [],
    "last_audio_hash": None
}

for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ==========================================
# 4. OpenAI 클라이언트
# ==========================================
def get_client():
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        try:
            api_key = st.secrets.get("OPENAI_API_KEY")
        except Exception:
            api_key = None

    if not api_key:
        return None

    return OpenAI(api_key=api_key)


# ==========================================
# 5. 시스템 프롬프트
# ==========================================
SYSTEM_PROMPT = """
당신은 Thumbs Up AI라는 개인 음성 비서입니다.

규칙:
1. 사용자에게 자연스러운 한국어로 답변합니다.
2. 음성으로 듣기 편하게 간결하게 설명합니다.
3. 사용자의 명령 의도를 이해합니다.
4. 첨부된 텍스트 파일이 있다면 참고합니다.
5. 확인되지 않은 내용은 추측하지 않습니다.
6. 실제로 수행하지 않은 작업을 완료했다고 말하지 않습니다.

현재 Google Calendar, 실시간 웹 검색 및 주식 조회 API는
아직 연결되지 않았습니다.
"""


# ==========================================
# 6. 음성 처리 함수
# ==========================================
def process_audio(audio_bytes, reference_text=""):

    client = get_client()

    if client is None:
        st.error("OpenAI API 키가 설정되지 않았습니다.")
        return

    try:
        # 음성 -> 텍스트
        with st.spinner("음성을 인식하고 있습니다..."):

            audio_file = io.BytesIO(audio_bytes)
            audio_file.name = "recording.wav"

            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )

            question = transcript.text.strip()

        if not question:
            st.warning("음성을 인식하지 못했습니다.")
            return

        # 대화 메시지 구성
        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            }
        ]

        if reference_text:
            messages.append({
                "role": "system",
                "content": (
                    "참고 문서:\n"
                    + reference_text[:15000]
                )
            })

        messages.extend(
            st.session_state.history[-8:]
        )

        messages.append({
            "role": "user",
            "content": question
        })

        # AI 답변
        with st.spinner("Thumbs Up AI가 답변 중입니다..."):

            response = client.responses.create(
                model="gpt-4o-mini",
                input=messages
            )

            answer = response.output_text.strip()

        if not answer:
            answer = "답변을 생성하지 못했습니다."

        # 텍스트 -> 음성
        answer_audio = None

        try:
            with st.spinner("음성 답변을 준비하고 있습니다..."):

                speech = client.audio.speech.create(
                    model="tts-1",
                    voice="nova",
                    input=answer[:4000]
                )

                answer_audio = speech.read()

        except Exception as e:
            st.warning(f"음성 합성 오류: {e}")

        # 결과 저장
        st.session_state.transcript = question
        st.session_state.answer = answer
        st.session_state.audio_answer = answer_audio
        st.session_state.expanded = False

        st.session_state.history.extend([
            {
                "role": "user",
                "content": question
            },
            {
                "role": "assistant",
                "content": answer
            }
        ])

    except Exception as e:
        st.error(f"음성 처리 중 오류: {e}")


# ==========================================
# 7. 업로드 파일 읽기
# ==========================================
reference_text = ""

current_file = st.session_state.get("txt_file")

if current_file is not None:
    reference_text = current_file.getvalue().decode(
        "utf-8-sig",
        errors="replace"
    )


# ==========================================
# 8. 메인 카드
# ==========================================
with st.container(key="assistant_card"):

    # 상단 헤더
    logo_col, settings_col = st.columns(
        [15, 1],
        vertical_alignment="center"
    )

    with logo_col:
        st.markdown(
            '<div class="brand-title">'
            '👍🏻 Thumbs Up AI'
            '</div>',
            unsafe_allow_html=True
        )

    with settings_col:
        with st.container(key="settings_button"):
            if st.button(
                "⚙️",
                key="settings",
                help="설정"
            ):
                st.toast("설정 기능은 추후 추가 예정입니다.")

    st.divider()

    # 중앙 여백
    st.write("")
    st.write("")

    # ======================================
    # 9. 웨이브 + 실제 녹음 버튼
    # ======================================
    wave_l, mic_col, wave_r = st.columns(
        [5, 1.3, 5],
        gap="small",
        vertical_alignment="center"
    )

    with wave_l:
        st.markdown(
            '<div class="wave-left"></div>',
            unsafe_allow_html=True
        )

    with mic_col:

        # 실제 클릭 가능한 원형 녹음 버튼
        audio = audiorecorder(
            start_prompt="🎙️",
            stop_prompt="⏹️",
            custom_style={
                "width": "76px",
                "height": "76px",
                "borderRadius": "50%",
                "border": "1px solid #dce5ff",
                "background": "#f5f8ff",
                "boxShadow": (
                    "0 5px 22px "
                    "rgba(151,174,255,0.35)"
                ),
                "fontSize": "28px",
                "cursor": "pointer",
                "display": "inline-flex",
                "alignItems": "center",
                "justifyContent": "center",
                "padding": "0px"
            },
            start_style={
                "color": "#ee93a9"
            },
            stop_style={
                "color": "#e66584",
                "background": "#ffe9ee"
            },
            show_visualizer=False,
            key="main_microphone"
        )

    with wave_r:
        st.markdown(
            '<div class="wave-right"></div>',
            unsafe_allow_html=True
        )

    # ======================================
    # 10. 중앙 안내 문구
    # ======================================
    st.markdown("""
    <div class="center-heading">
        무엇을 도와드릴까요?
    </div>

    <div class="center-subtitle">
        마이크를 눌러 음성 명령을 시작하세요.
    </div>

    <div class="mic-hint">
        다시 누르면 녹음이 종료됩니다.
    </div>
    """, unsafe_allow_html=True)

    st.write("")
    st.write("")

    # ======================================
    # 11. 녹음 완료 시 자동 처리
    # ======================================
    if len(audio) > 0:

        # AudioSegment -> WAV 바이트
        audio_buffer = io.BytesIO()
        audio.export(audio_buffer, format="wav")

        audio_bytes = audio_buffer.getvalue()

        audio_hash = hashlib.sha256(
            audio_bytes
        ).hexdigest()

        if audio_hash != st.session_state.last_audio_hash:

            st.session_state.last_audio_hash = audio_hash

            process_audio(
                audio_bytes,
                reference_text
            )

    # ======================================
    # 12. AI 답변 영역
    # ======================================
    st.markdown(
        '<div class="answer-title">AI 답변</div>',
        unsafe_allow_html=True
    )

    answer = st.session_state.answer

    if answer:

        safe_answer = html.escape(answer)

        if st.session_state.expanded:
            css_class = "answer-text"
        else:
            css_class = "answer-text clamped"

        st.markdown(
            f"""
            <div class="{css_class}">
                {safe_answer}
            </div>
            """,
            unsafe_allow_html=True
        )

        # 긴 답변은 더보기
        is_long = (
            len(answer) > 85
            or answer.count("\n") >= 2
        )

        if is_long:
            with st.container(key="more_button"):

                button_text = (
                    "접기 ▲"
                    if st.session_state.expanded
                    else "더보기 ▼"
                )

                if st.button(
                    button_text,
                    key="toggle_more"
                ):
                    st.session_state.expanded = (
                        not st.session_state.expanded
                    )
                    st.rerun()

        # AI 음성 답변
        if st.session_state.audio_answer:
            st.audio(
                st.session_state.audio_answer,
                format="audio/mp3"
            )

    else:
        st.markdown(
            """
            <div class="answer-text">
                음성 명령에 대한 답변이 표시됩니다.
            </div>
            """,
            unsafe_allow_html=True
        )


# ==========================================
# 13. 인식된 음성
# ==========================================
if st.session_state.transcript:

    with st.expander("인식된 음성 확인"):
        st.write(st.session_state.transcript)


# ==========================================
# 14. 대화 기록
# ==========================================
with st.expander("최근 대화 기록"):

    if not st.session_state.history:
        st.caption("아직 대화 기록이 없습니다.")

    else:
        for message in st.session_state.history[-10:]:

            if message["role"] == "user":
                st.markdown("**나**")
            else:
                st.markdown("**Thumbs Up AI**")

            st.write(message["content"])

        if st.button("대화 초기화"):

            for key, value in DEFAULTS.items():
                st.session_state[key] = value

            st.rerun()


# ==========================================
# 15. 파일 업로드
# ==========================================
with st.expander("📎 참고 TXT 파일 첨부 (선택)"):

    uploaded_file = st.file_uploader(
        "텍스트 파일",
        type=["txt"],
        key="txt_file"
    )

    if uploaded_file is not None:
        st.success(
            f"{uploaded_file.name} 파일이 첨부되었습니다."
        )
