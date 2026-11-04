
import os
import io
import html
import hashlib

import streamlit as st
from openai import OpenAI
from streamlit_mic_recorder import mic_recorder


# ==========================================
# 1. 페이지 설정
# ==========================================
st.set_page_config(
    page_title="Thumbs Up AI",
    page_icon="👍🏻",
    layout="wide"
)


# ==========================================
# 2. CSS 디자인
# ==========================================
st.markdown("""
<style>
.block-container {
    max-width: 1180px;
    padding-top: 1.5rem;
    padding-bottom: 2rem;
}

[data-testid="stSidebar"] {
    display: none;
}

.st-key-assistant_card {
    border: 1px solid #e5e5e7 !important;
    border-radius: 26px !important;
    padding: 25px 32px 28px !important;
    background: #ffffff;
    box-shadow: none;
}

.brand-title {
    font-size: 23px;
    font-weight: 750;
    color: #151515;
    padding-top: 6px;
}

.center-heading {
    font-size: 25px;
    font-weight: 750;
    text-align: center;
    color: #111;
    margin-top: 14px;
}

.center-subtitle {
    font-size: 17px;
    color: #888;
    text-align: center;
    margin-top: 12px;
}

.answer-title {
    font-size: 20px;
    font-weight: 600;
    color: #202020;
    margin-bottom: 8px;
}

.answer-text {
    font-size: 18px;
    line-height: 1.65;
    color: #686868;
    overflow-wrap: anywhere;
    white-space: pre-wrap;
}

.answer-text.clamped {
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
    overflow: hidden;
}

.st-key-answer_more button {
    border: none;
    box-shadow: none;
    padding: 0;
    color: #676e82;
}

.st-key-gear button {
    border: 0 !important;
    background: transparent !important;
    font-size: 24px;
    padding: 0 5px;
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

for name, default in DEFAULTS.items():
    if name not in st.session_state:
        st.session_state[name] = default


# ==========================================
# 4. OpenAI 클라이언트
# ==========================================
def get_client():
    api_key = os.environ.get("OPENAI_API_KEY")

    if not api_key:
        try:
            api_key = st.secrets.get("OPENAI_API_KEY")
        except Exception:
            api_key = None

    return OpenAI(api_key=api_key) if api_key else None


# ==========================================
# 5. AI 시스템 프롬프트
# ==========================================
SYSTEM_PROMPT = """
당신은 Thumbs Up AI라는 한국어 음성 기반 개인 비서입니다.

역할:
1. 사용자의 음성 명령을 이해합니다.
2. 질문에 자연스럽고 간결한 한국어로 답변합니다.
3. 첨부된 텍스트 파일이 있다면 참고합니다.
4. 사용자가 요청하는 작업의 의도를 파악합니다.
5. 실제로 실행하지 않은 작업을 완료했다고 말하지 않습니다.

주의:
Google Calendar, 실시간 웹 검색, 주식 시세 조회 등의
외부 기능은 아직 연결되지 않았습니다.
"""


# ==========================================
# 6. 음성 명령 처리
# ==========================================
def handle_audio(audio_bytes, reference_text):

    client = get_client()

    if client is None:
        st.error(
            "OpenAI API 키가 설정되지 않았습니다. "
            "Streamlit Cloud Secrets를 확인하세요."
        )
        return

    try:
        # STT: 음성 -> 텍스트
        with st.spinner("음성을 인식하고 있어요..."):

            sound_file = io.BytesIO(audio_bytes)
            sound_file.name = "recording.wav"

            result = client.audio.transcriptions.create(
                model="whisper-1",
                file=sound_file
            )

            question = result.text.strip()

        if not question:
            st.warning("음성이 인식되지 않았습니다.")
            return

        # AI 입력 메시지
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
                    "첨부 자료:\n"
                    + reference_text[:15000]
                )
            })

        # 이전 대화 포함
        messages.extend(
            st.session_state.history[-8:]
        )

        messages.append({
            "role": "user",
            "content": question
        })

        # GPT 응답 생성
        with st.spinner("Thumbs Up AI가 답변 중이에요..."):

            response = client.responses.create(
                model="gpt-4o-mini",
                input=messages
            )

            answer = response.output_text.strip()

        # TTS: AI 음성 답변
        spoken_audio = None

        if answer:
            try:
                with st.spinner("음성 답변 준비 중..."):

                    speech = client.audio.speech.create(
                        model="tts-1",
                        voice="nova",
                        input=answer[:4000]
                    )

                    spoken_audio = speech.read()

            except Exception as exc:
                st.warning(
                    f"음성 파일 생성 오류: {exc}"
                )

        # 결과 저장
        st.session_state.transcript = question
        st.session_state.answer = (
            answer or "답변을 생성하지 못했습니다."
        )
        st.session_state.audio_answer = spoken_audio
        st.session_state.expanded = False

        st.session_state.history.extend([
            {
                "role": "user",
                "content": question
            },
            {
                "role": "assistant",
                "content": st.session_state.answer
            }
        ])

    except Exception as exc:
        st.error(
            f"음성 처리 중 오류가 발생했어요: {exc}"
        )


# ==========================================
# 7. 참고 파일 가져오기
# ==========================================
current_file = st.session_state.get("txt_file")

reference_text = ""

if current_file is not None:
    reference_text = current_file.getvalue().decode(
        "utf-8-sig",
        errors="replace"
    )


# ==========================================
# 8. 메인 인터페이스
# ==========================================
with st.container(key="assistant_card"):

    # 상단 로고 및 설정 버튼
    logo, settings = st.columns(
        [15, 1],
        vertical_alignment="center"
    )

    with logo:
        st.markdown(
            '<div class="brand-title">'
            '👍🏻 Thumbs Up AI'
            '</div>',
            unsafe_allow_html=True
        )

    with settings:
        with st.container(key="gear"):

            if st.button(
                "⚙️",
                key="settings",
                help="설정"
            ):
                st.toast(
                    "설정 기능은 추후 추가할 예정입니다."
                )

    st.divider()

    # 중앙 공간
    st.write("")
    st.write("")

    # ======================================
    # 9. 중앙 음성 녹음 버튼
    # ======================================
    mic_left, mic_center, mic_right = st.columns(
        [5, 1.3, 5]
    )

    with mic_center:

        audio = mic_recorder(
            start_prompt="🎙️",
            stop_prompt="⏹️",
            just_once=False,
            use_container_width=True,
            key="voice_recorder"
        )

    st.markdown(
        """
        <div class="center-heading">
            무엇을 도와드릴까요?
        </div>

        <div class="center-subtitle">
            마이크를 눌러 음성 명령을 시작하세요.
        </div>
        """,
        unsafe_allow_html=True
    )

    st.write("")
    st.write("")

    # ======================================
    # 10. 음성 자동 처리
    # ======================================
    if audio and audio.get("bytes"):

        audio_bytes = audio["bytes"]

        # 동일한 음성 중복 처리 방지
        audio_hash = hashlib.sha256(
            audio_bytes
        ).hexdigest()

        if audio_hash != st.session_state.last_audio_hash:

            st.session_state.last_audio_hash = audio_hash

            handle_audio(
                audio_bytes,
                reference_text
            )

    # ======================================
    # 11. AI 답변 표시
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

        # 긴 답변은 더보기 표시
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
# 12. 최근 대화 기록
# ==========================================
with st.expander("최근 대화 기록"):

    if not st.session_state.history:
        st.caption("아직 대화 기록이 없습니다.")

    for message in st.session_state.history[-10:]:

        if message["role"] == "user":
            st.markdown("**나**")
        else:
            st.markdown("**Thumbs Up AI**")

        st.write(message["content"])

    if st.session_state.history:

        if st.button("대화 초기화"):

            for name, value in DEFAULTS.items():
                st.session_state[name] = value

            st.rerun()


# ==========================================
# 13. 참고 TXT 파일 첨부
# ==========================================
with st.expander("📎 참고 텍스트 파일 첨부 (선택)"):

    uploaded_file = st.file_uploader(
        "TXT 파일",
        type=["txt"],
        key="txt_file"
    )

    if uploaded_file is not None:
        st.success(
            f"{uploaded_file.name} 파일이 첨부되었습니다."
        )
