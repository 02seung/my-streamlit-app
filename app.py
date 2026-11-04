
import os
import io
import html
import hashlib

import streamlit as st
from openai import OpenAI
from audio_recorder_streamlit import audio_recorder


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

/* 페이지 */
.block-container {
    max-width: 1180px;
    padding-top: 2rem;
    padding-bottom: 2rem;
}

[data-testid="stSidebar"] {
    display: none;
}

/* 전체 메인 카드 */
.st-key-assistant_card {
    background: #ffffff !important;
    border: 1px solid #e5e5e7 !important;
    border-radius: 28px !important;
    padding: 28px 34px 35px !important;
}

/* 상단 로고 */
.brand-title {
    font-size: 24px;
    font-weight: 750;
    color: #202020;
}

/* 설정 버튼 */
.st-key-settings_area button {
    border: none !important;
    background: transparent !important;
    box-shadow: none !important;
    font-size: 25px !important;
}

/* 마이크 컨테이너 */
.st-key-microphone_shell {
    width: 112px !important;
    height: 112px !important;
    margin: 0 auto !important;
    background: #f4f7ff !important;
    border: 1px solid #dce5ff !important;
    border-radius: 50% !important;
    box-shadow: 0 6px 25px rgba(150,170,255,0.18);
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    padding: 10px !important;
}

/* 웨이브 */
.wave-left {
    width: 100%;
    height: 10px;
    margin-top: 50px;
    border-radius: 100%;
    background: linear-gradient(
        90deg,
        transparent,
        #d3dfff,
        #b9c8ff,
        #f2bfd4
    );
    filter: blur(2px);
}

.wave-right {
    width: 100%;
    height: 10px;
    margin-top: 50px;
    border-radius: 100%;
    background: linear-gradient(
        90deg,
        #f2bfd4,
        #b9c8ff,
        #d3dfff,
        transparent
    );
    filter: blur(2px);
}

/* 중앙 문구 */
.center-heading {
    font-size: 26px;
    font-weight: 750;
    text-align: center;
    color: #202020;
    margin-top: 24px;
}

.center-subtitle {
    font-size: 16px;
    text-align: center;
    color: #888888;
    margin-top: 10px;
}

.mic-hint {
    font-size: 13px;
    text-align: center;
    color: #aaa;
    margin-top: 10px;
}

/* AI 답변 */
.answer-title {
    font-size: 20px;
    font-weight: 650;
    color: #252525;
    margin-bottom: 12px;
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

/* 더보기 버튼 */
.st-key-answer_more button {
    border: none !important;
    background: transparent !important;
    box-shadow: none !important;
    color: #687389 !important;
}

</style>
""", unsafe_allow_html=True)


# ==========================================
# 3. 세션 상태 초기화
# ==========================================
DEFAULTS = {
    "answer": "",
    "transcript": "",
    "audio_answer": None,
    "expanded": False,
    "history": [],
    "last_audio_hash": None,
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
당신은 Thumbs Up AI라는 한국어 개인 음성 비서입니다.

역할:
1. 사용자의 음성 질문을 이해합니다.
2. 자연스럽고 친절한 한국어로 답변합니다.
3. 음성으로 듣기 편하도록 간결하게 답변합니다.
4. 첨부된 텍스트 파일을 참고할 수 있습니다.
5. 불확실한 정보는 추측하지 않습니다.
6. 실제로 수행하지 않은 작업을 완료했다고 말하지 않습니다.

현재 Google Calendar, 실시간 웹 검색,
주식 조회 API는 아직 연결되지 않았습니다.
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

        # ----------------------------------
        # STT: 음성 -> 텍스트
        # ----------------------------------
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

        # ----------------------------------
        # AI 입력 메시지
        # ----------------------------------
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
                    "참고 파일 내용:\n"
                    + reference_text[:15000]
                )
            })

        # 이전 대화 기록
        messages.extend(
            st.session_state.history[-8:]
        )

        messages.append({
            "role": "user",
            "content": question
        })

        # ----------------------------------
        # GPT 답변 생성
        # ----------------------------------
        with st.spinner("Thumbs Up AI가 답변 중입니다..."):

            response = client.responses.create(
                model="gpt-4o-mini",
                input=messages
            )

            answer = response.output_text.strip()

        if not answer:
            answer = "답변을 생성하지 못했습니다."

        # ----------------------------------
        # TTS: 텍스트 -> 음성
        # ----------------------------------
        answer_audio = None

        try:
            with st.spinner("음성 답변을 생성하고 있습니다..."):

                speech = client.audio.speech.create(
                    model="tts-1",
                    voice="nova",
                    input=answer[:4000]
                )

                answer_audio = speech.read()

        except Exception as e:
            st.warning(f"음성 합성 오류: {e}")

        # ----------------------------------
        # 상태 저장
        # ----------------------------------
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
# 7. TXT 파일 가져오기
# ==========================================
reference_text = ""

current_file = st.session_state.get("txt_file")

if current_file is not None:

    reference_text = current_file.getvalue().decode(
        "utf-8-sig",
        errors="replace"
    )


# ==========================================
# 8. 메인 인터페이스
# ==========================================
with st.container(key="assistant_card"):

    # --------------------------------------
    # 상단 헤더
    # --------------------------------------
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
        with st.container(key="settings_area"):

            if st.button(
                "⚙️",
                key="settings",
                help="설정"
            ):
                st.toast("설정 기능은 추후 추가 예정입니다.")

    st.divider()

    st.write("")
    st.write("")

    # ======================================
    # 9. 웨이브 + 단일 마이크 버튼
    # ======================================
    wave_left, mic_col, wave_right = st.columns(
        [5, 1.5, 5],
        gap="small",
        vertical_alignment="center"
    )

    with wave_left:

        st.markdown(
            '<div class="wave-left"></div>',
            unsafe_allow_html=True
        )

    with mic_col:

        with st.container(key="microphone_shell"):

            # 실제 녹음 버튼은 하나만 존재
            audio_bytes = audio_recorder(
                text="",
                icon_name="microphone",
                icon_size="3x",

                # 녹음 대기: 연보라색
                neutral_color="#9b91b5",

                # 녹음 중: 분홍색
                recording_color="#ec789b",

                # 버튼을 직접 눌러 녹음 종료
                # 자동 침묵 종료는 사용하지 않음
                energy_threshold=(-1.0, 1.0),
                pause_threshold=3600,

                auto_start=False,
                key="single_mic"
            )

    with wave_right:

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
    # 11. 녹음 종료 후 자동 실행
    # ======================================
    if audio_bytes:

        audio_hash = hashlib.sha256(
            audio_bytes
        ).hexdigest()

        # 동일한 음성 중복 처리 방지
        if audio_hash != st.session_state.last_audio_hash:

            st.session_state.last_audio_hash = audio_hash

            process_audio(
                audio_bytes,
                reference_text
            )

    # ======================================
    # 12. AI 답변 표시
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
            <div class="{css_class}">{safe_answer}</div>
            """,
            unsafe_allow_html=True
        )

        # 긴 답변은 더보기
        is_long = (
            len(answer) > 85
            or answer.count("\n") >= 2
        )

        if is_long:

            with st.container(key="answer_more"):

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
                format="audio/mp3",
                autoplay=True
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
# 13. 인식된 음성 확인
# ==========================================
if st.session_state.transcript:

    with st.expander("인식된 음성 확인"):

        st.write(
            st.session_state.transcript
        )


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
