
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
    initial_sidebar_state="collapsed",
)


# ==========================================
# 2. CSS 디자인
# ==========================================
st.markdown("""
<style>
.block-container {
    max-width: 1150px;
    padding-top: 2rem;
    padding-bottom: 2rem;
}

[data-testid="stSidebar"] {
    display: none;
}

.st-key-assistant_card {
    background: #fff;
    border: 1px solid #e6e6e9 !important;
    border-radius: 26px !important;
    padding: 26px 32px 30px !important;
}

.brand-title {
    font-size: 24px;
    font-weight: 750;
    color: #222;
}

.st-key-settings_area button {
    border: none !important;
    background: transparent !important;
    box-shadow: none !important;
    font-size: 24px;
}

.wave-left, .wave-right {
    height: 8px;
    border-radius: 100%;
    filter: blur(2px);
    opacity: .85;
}

.wave-left {
    background: linear-gradient(
        90deg,
        transparent,
        #c8d7ff,
        #f0bcd6
    );
}

.wave-right {
    background: linear-gradient(
        90deg,
        #f0bcd6,
        #c8d7ff,
        transparent
    );
}

.st-key-microphone_shell {
    width: 94px;
    height: 94px;
    margin: 0 auto;
    border: 1px solid #e0e8ff !important;
    border-radius: 50% !important;
    background: #f5f8ff;
    box-shadow: 0 5px 22px #ccd8ff70;
    display: flex;
    align-items: center;
    justify-content: center;
}

.center-heading {
    text-align: center;
    font-size: 25px;
    font-weight: 750;
    margin-top: 20px;
}

.center-subtitle {
    text-align: center;
    color: #888;
    font-size: 16px;
    margin-top: 10px;
}

.mic-hint {
    text-align: center;
    color: #999;
    font-size: 13px;
    margin-top: 7px;
}

.answer-title {
    font-size: 20px;
    font-weight: 650;
    margin-bottom: 8px;
}

.answer-text {
    font-size: 17px;
    color: #62656e;
    line-height: 1.7;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
}

.answer-text.clamped {
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
    overflow: hidden;
}

.st-key-answer_more button {
    border: none !important;
    background: transparent !important;
    box-shadow: none !important;
    color: #697589;
}
</style>
""", unsafe_allow_html=True)


# ==========================================
# 3. 세션 상태
# ==========================================
DEFAULTS = {
    "answer": "",
    "transcript": "",
    "audio_answer": None,
    "expanded": False,
    "history": [],
    "last_audio_hash": None,
    "audio_version": 0,
}

for name, default in DEFAULTS.items():
    if name not in st.session_state:
        st.session_state[name] = default


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
# 5. AI 시스템 프롬프트
# ==========================================
SYSTEM_PROMPT = """
당신은 Thumbs Up AI라는 한국어 음성 개인 비서입니다.

간결하고 자연스럽게 한국어로 말하듯 답하세요.
첨부된 문서가 있으면 참고하세요.

Google Calendar, 실시간 웹 검색, 주식 시세 조회는
아직 연결되지 않았으므로 실제로 조회하거나
실행하지 않은 작업을 완료했다고 말하지 마세요.
"""


# ==========================================
# 6. 음성 처리 함수
# ==========================================
def process_audio(audio_bytes, reference_text=""):

    client = get_client()

    if client is None:
        st.error(
            "OPENAI_API_KEY가 설정되지 않았습니다. "
            "Streamlit Cloud Secrets를 확인하세요."
        )
        return False

    try:
        # STT: 음성 -> 텍스트
        with st.spinner("음성을 인식하고 있습니다..."):

            audio_file = io.BytesIO(audio_bytes)
            audio_file.name = "recording.wav"

            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )

            question = transcript.text.strip()

        if not question:
            st.warning(
                "음성이 인식되지 않았습니다. 다시 녹음해 주세요."
            )
            return False

        # AI 입력 메시지 구성
        system_text = SYSTEM_PROMPT

        if reference_text:
            system_text += (
                "\n\n첨부 문서 내용:\n"
                + reference_text[:15000]
            )

        messages = [
            {"role": "system", "content": system_text}
        ]

        messages.extend(st.session_state.history[-8:])

        messages.append({
            "role": "user",
            "content": question
        })

        # GPT 응답
        with st.spinner(
            "Thumbs Up AI가 답변을 생성하고 있습니다..."
        ):

            response = client.responses.create(
                model="gpt-4o-mini",
                input=messages
            )

            answer = (
                response.output_text.strip()
                or "답변을 생성하지 못했습니다."
            )

        # TTS: 텍스트 -> 음성
        spoken_audio = None

        try:
            with st.spinner(
                "음성 답변을 준비하고 있습니다..."
            ):

                speech = client.audio.speech.create(
                    model="tts-1",
                    voice="nova",
                    input=answer[:4000]
                )

                spoken_audio = speech.read()

        except Exception as exc:
            st.warning(f"음성 합성 오류: {exc}")

        # 상태 저장
        st.session_state.transcript = question
        st.session_state.answer = answer
        st.session_state.audio_answer = spoken_audio
        st.session_state.expanded = False
        st.session_state.audio_version += 1

        st.session_state.history.extend([
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer}
        ])

        return True

    except Exception as exc:
        st.error(f"음성 처리 중 오류: {exc}")
        return False


# ==========================================
# 7. 참고 파일 읽기
# ==========================================
reference_text = ""

current_file = st.session_state.get("txt_file")

if current_file is not None:
    reference_text = current_file.getvalue().decode(
        "utf-8-sig",
        errors="replace"
    )

just_processed = False


# ==========================================
# 8. 메인 인터페이스
# ==========================================
with st.container(key="assistant_card"):

    # 상단 로고 / 설정
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
                key="settings_button",
                help="설정"
            ):
                st.toast(
                    "설정 창은 추후 연결할 예정입니다."
                )

    st.divider()

    st.write("")
    st.write("")

    # ======================================
    # 9. 웨이브 + 단일 마이크 버튼
    # ======================================
    wave_left, mic_col, wave_right = st.columns(
        [5, 1.6, 5],
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

            # 하나의 마이크로 녹음 시작/종료
            audio_bytes = audio_recorder(
                text="",
                icon_name="microphone",
                icon_size="3x",
                neutral_color="#9b91b5",
                recording_color="#ec789b",
                key="single_mic"
            )

    with wave_right:
        st.markdown(
            '<div class="wave-right"></div>',
            unsafe_allow_html=True
        )

    # 중앙 안내 문구
    st.markdown("""
    <div class="center-heading">
        무엇을 도와드릴까요?
    </div>

    <div class="center-subtitle">
        마이크를 눌러 음성 명령을 시작하세요.
    </div>

    <div class="mic-hint">
        같은 버튼을 다시 누르면 녹음이 종료됩니다.
    </div>
    """, unsafe_allow_html=True)

    st.write("")
    st.write("")

    # ======================================
    # 10. 녹음 완료 시 자동 실행
    # ======================================
    if audio_bytes:

        audio_hash = hashlib.sha256(
            audio_bytes
        ).hexdigest()

        if audio_hash != st.session_state.last_audio_hash:

            st.session_state.last_audio_hash = audio_hash

            just_processed = process_audio(
                audio_bytes,
                reference_text
            )

    # ======================================
    # 11. AI 답변 출력
    # ======================================
    st.markdown(
        '<div class="answer-title">AI 답변</div>',
        unsafe_allow_html=True
    )

    answer = st.session_state.answer

    if answer:

        if st.session_state.expanded:
            css_class = "answer-text"
        else:
            css_class = "answer-text clamped"

        safe_answer = html.escape(answer)

        st.markdown(
            f'<div class="{css_class}">'
            f'{safe_answer}'
            f'</div>',
            unsafe_allow_html=True
        )

        # 긴 답변의 더보기 버튼
        is_long = (
            len(answer) > 85
            or answer.count("\n") >= 2
        )

        if is_long:
            with st.container(key="answer_more"):

                if st.session_state.expanded:
                    label = "접기 ▲"
                else:
                    label = "더보기 ▼"

                if st.button(
                    label,
                    key="toggle_more"
                ):
                    st.session_state.expanded = (
                        not st.session_state.expanded
                    )
                    st.rerun()

        # TTS 음성 재생
        if st.session_state.audio_answer:
            st.audio(
                st.session_state.audio_answer,
                format="audio/mp3",
                autoplay=just_processed
            )

    else:
        st.markdown(
            '<div class="answer-text">'
            '음성 명령에 대한 답변이 표시됩니다.'
            '</div>',
            unsafe_allow_html=True
        )


# ==========================================
# 12. 음성 인식 결과 확인
# ==========================================
if st.session_state.transcript:

    with st.expander("인식된 음성 확인"):
        st.write(st.session_state.transcript)


# ==========================================
# 13. 최근 대화 기록
# ==========================================
with st.expander("최근 대화 기록"):

    if not st.session_state.history:
        st.caption("아직 대화 기록이 없습니다.")

    else:
        for message in st.session_state.history[-10:]:

            if message["role"] == "user":
                who = "나"
            else:
                who = "Thumbs Up AI"

            st.markdown(f"**{who}**")
            st.write(message["content"])

        if st.button(
            "대화 초기화",
            key="clear_history"
        ):
            for name, default in DEFAULTS.items():
                st.session_state[name] = default

            st.rerun()


# ==========================================
# 14. TXT 파일 업로드
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
