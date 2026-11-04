import os
import io
import html
import hashlib

import streamlit as st
from openai import OpenAI
from audio_recorder_streamlit import audio_recorder


# 1. 페이지 설정
st.set_page_config(
    page_title="Thumbs Up AI",
    page_icon="👍🏻",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# 2. 화면 스타일
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
    font-size: 26px;
    font-weight: 750;
    color: #111;
    line-height: 1.3;
}
.brand-subtitle {
    font-size: 25px;
    font-weight: 750;
    color: #111;
    line-height: 1.35;
}
.brand-description {
    font-size: 13px;
    color: #333;
    margin-top: 14px;
}
.st-key-header_actions button {
    border: 0 !important;
    background: transparent !important;
    box-shadow: none !important;
    font-size: 24px !important;
    padding: 0 !important;
}

/* 2. 사용자 질문 카드 */
.question-card {
    box-sizing: border-box;
    width: min(100%, 365px);
    min-height: 182px;
    margin: 0 auto 20px;
    padding: 20px 22px;
    background: #fff;
    border: 1px solid #ededed;
    box-shadow: 0 1px 7px rgba(0, 0, 0, .10);
    color: #111;
    font-size: 19px;
    line-height: 1.55;
    overflow-wrap: anywhere;
    white-space: pre-wrap;
    text-align: left;
}
.question-card.is-empty {
    color: #999;
    display: flex;
    align-items: center;
    justify-content: center;
    text-align: center;
    font-size: 15px;
}

/* 3. 수평선과 마이크 */
.mic-rule {
    height: 1px;
    width: 100%;
    background: #505050;
}
.st-key-microphone_shell {
    width: 48px;
    height: 48px;
    margin: 0 auto;
    border: 1px solid #eeeeee !important;
    border-radius: 50% !important;
    background: #ffffff;
    box-shadow: 0 2px 8px rgba(0, 0, 0, .09);
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
}
.st-key-microphone_shell [data-testid="stCustomComponentV1"] {
    display: flex;
    align-items: center;
    justify-content: center;
}
.mic-hint {
    text-align: center;
    color: #999;
    font-size: 13px;
    margin-top: 7px;
}

/* 4. AI 응답 상태 표시 */
.status-bar {
    width: min(100%, 365px);
    min-height: 31px;
    margin: 18px auto;
    padding: 8px 14px;
    border-radius: 6px;
    background: #ededed;
    color: #555;
    font-size: 12px;
    text-align: center;
    box-sizing: border-box;
}

/* 5. AI 답변 영역 */
.answer-area {
    width: min(100%, 365px);
    margin: 0 auto;
}
.answer-box {
    background: #f3f3f3;
    border-radius: 7px;
    padding: 12px 15px;
    color: #424242;
    font-size: 13px;
    line-height: 1.6;
    overflow-wrap: anywhere;
    white-space: pre-wrap;
}
.answer-box.clamped {
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    overflow: hidden;
    white-space: normal;
}
.answer-heading {
    font-size: 15px;
    font-weight: 650;
    margin: 10px 0 9px;
}
.st-key-answer_more {
    width: min(100%, 365px);
    margin: 0 auto;
}
.st-key-answer_more button {
    border: none !important;
    background: transparent !important;
    box-shadow: none !important;
    color: #697589;
    font-size: 12px;
    width: 100%;
    justify-content: flex-end;
}
.st-key-answer_audio {
    width: min(100%, 365px);
    margin: 8px auto 0;
}
</style>
""", unsafe_allow_html=True)


# 3. 세션 상태
DEFAULTS = {
    "answer": "",
    "transcript": "",
    "audio_answer": None,
    "expanded": False,
    "history": [],
    "last_audio_hash": None,
    "audio_version": 0,
    "process_status": "마이크를 눌러 질문해 주세요.",
}

for name, default in DEFAULTS.items():
    if name not in st.session_state:
        st.session_state[name] = default


# 4. OpenAI API 연결
def get_client():
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        try:
            api_key = st.secrets.get("OPENAI_API_KEY")
        except Exception:
            api_key = None

    return OpenAI(api_key=api_key) if api_key else None


SYSTEM_PROMPT = """
당신은 Thumbs Up AI라는 한국어 음성 개인 비서입니다.

간결하고 자연스럽게 한국어로 말하듯 답하세요.
첨부된 문서가 있으면 참고하세요.

Google Calendar, 실시간 웹 검색, 주식 시세 조회는
아직 연결되지 않았으므로 실제로 조회하거나
실행하지 않은 작업을 완료했다고 말하지 마세요.
"""


# 5. STT → GPT → TTS
def process_audio(
    audio_bytes,
    reference_text="",
    status_placeholder=None
):

    def update_status(message):
        st.session_state.process_status = message

        if status_placeholder is not None:
            status_placeholder.markdown(
                f'<div class="status-bar">'
                f'{html.escape(message)}'
                f'</div>',
                unsafe_allow_html=True,
            )

    client = get_client()

    if client is None:
        update_status("API 키가 없습니다.")

        st.error(
            "OPENAI_API_KEY가 설정되지 않았습니다. "
            "Streamlit Cloud Secrets를 확인하세요."
        )
        return False

    try:
        # 음성 → 텍스트
        update_status("◌ 음성을 인식하고 있습니다...")

        with st.spinner("음성을 인식하고 있습니다..."):
            audio_file = io.BytesIO(audio_bytes)
            audio_file.name = "recording.wav"

            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )

            question = transcript.text.strip()

        if not question:
            update_status("음성을 인식하지 못했습니다.")
            st.warning("다시 녹음해 주세요.")
            return False

        # AI 답변 생성
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

        update_status("◌ 답변 준비중입니다 ...")

        with st.spinner("AI가 답변을 생성하고 있습니다..."):
            response = client.responses.create(
                model="gpt-4o-mini",
                input=messages
            )

            answer = (
                response.output_text.strip()
                or "답변을 생성하지 못했습니다."
            )

        # 텍스트 → 음성
        spoken_audio = None

        try:
            update_status("◌ 음성 답변을 준비하고 있습니다...")

            with st.spinner("음성 답변을 준비하고 있습니다..."):
                speech = client.audio.speech.create(
                    model="tts-1",
                    voice="nova",
                    input=answer[:4000]
                )

                spoken_audio = speech.read()

        except Exception as exc:
            st.warning(f"음성 합성 오류: {exc}")

        # 결과 저장
        st.session_state.transcript = question
        st.session_state.answer = answer
        st.session_state.audio_answer = spoken_audio
        st.session_state.expanded = False
        st.session_state.audio_version += 1

        update_status("✓ 답변이 준비되었습니다.")

        st.session_state.history.extend([
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer},
        ])

        return True

    except Exception as exc:
        update_status("답변 처리 중 문제가 발생했습니다.")
        st.error(f"음성 처리 중 오류: {exc}")
        return False


# 6. TXT 파일 읽기
reference_text = ""

current_file = st.session_state.get("txt_file")

if current_file is not None:
    reference_text = current_file.getvalue().decode(
        "utf-8-sig",
        errors="replace"
    )

just_processed = False


# 7. 메인 인터페이스
with st.container(key="assistant_card"):

    # 1번: 상단 헤더
    title_col, action_col = st.columns(
        [10, 2],
        vertical_alignment="top"
    )

    with title_col:
        st.markdown("""
        <div class="brand-title">Thumbs Up,</div>

        <div class="brand-subtitle">
            Your professional AI Voice Assistant
        </div>

        <div class="brand-description">
            당신만의 AI Voice Assistant ThumbsUp입니다.
            '녹음' 버튼을 눌러 질문해주세요.
        </div>
        """, unsafe_allow_html=True)

    with action_col:
        with st.container(key="header_actions"):
            menu_col, gear_col = st.columns(
                2,
                gap="small"
            )

            with menu_col:
                if st.button(
                    "☰",
                    key="menu_button",
                    help="메뉴"
                ):
                    st.toast(
                        "메뉴 기능은 다음 단계에서 연결합니다."
                    )

            with gear_col:
                if st.button(
                    "⚙",
                    key="settings_button",
                    help="설정"
                ):
                    st.toast(
                        "설정 기능은 다음 단계에서 연결합니다."
                    )

    st.write("")
    st.write("")

    # 2번: 사용자 질문 표시 영역
    question_area = st.empty()

    # 3번: 중앙 마이크 버튼
    st.write("")

    line_left, mic_col, line_right = st.columns(
        [5, 0.9, 5],
        gap="small",
        vertical_alignment="center"
    )

    with line_left:
        st.markdown(
            '<div class="mic-rule"></div>',
            unsafe_allow_html=True
        )

    with mic_col:
        with st.container(key="microphone_shell"):
            audio_bytes = audio_recorder(
                text="",
                icon_name="microphone",
                icon_size="2x",
                neutral_color="#555555",
                recording_color="#e04444",
                key="single_mic",
            )

    with line_right:
        st.markdown(
            '<div class="mic-rule"></div>',
            unsafe_allow_html=True
        )

    st.markdown(
        """
        <div class="mic-hint">
            마이크를 누르면 녹음이 시작되고,
            다시 누르면 종료됩니다.
        </div>
        """,
        unsafe_allow_html=True
    )

    st.write("")

    # 4번: AI 응답 상태 표시
    status_area = st.empty()

    status_area.markdown(
        f'<div class="status-bar">'
        f'{html.escape(st.session_state.process_status)}'
        f'</div>',
        unsafe_allow_html=True
    )

    # 녹음된 음성을 중복 처리하지 않음
    if audio_bytes:
        audio_hash = hashlib.sha256(
            audio_bytes
        ).hexdigest()

        if audio_hash != st.session_state.last_audio_hash:
            st.session_state.last_audio_hash = audio_hash

            just_processed = process_audio(
                audio_bytes,
                reference_text,
                status_area
            )

    # 음성 인식 결과를 질문 카드에 표시
    question_text = st.session_state.transcript

    if question_text:
        question_area.markdown(
            f'<div class="question-card">'
            f'{html.escape(question_text)}'
            f'</div>',
            unsafe_allow_html=True
        )

    else:
        question_area.markdown(
            """
            <div class="question-card is-empty">
                마이크를 눌러 질문해 주세요.
            </div>
            """,
            unsafe_allow_html=True
        )

    # 5번: AI 답변 영역
    answer = st.session_state.answer

    st.markdown(
        """
        <div class="answer-area">
            <div class="answer-heading">
                AI 답변
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    if answer:
        is_long = (
            len(answer) > 75
            or answer.count("\n") >= 2
        )

        clamped = (
            is_long
            and not st.session_state.expanded
        )

        css_class = (
            "answer-box clamped"
            if clamped
            else "answer-box"
        )

        st.markdown(
            f'<div class="answer-area">'
            f'<div class="{css_class}">'
            f'💬 {html.escape(answer)}'
            f'</div></div>',
            unsafe_allow_html=True
        )

        # 긴 답변 더보기 / 접기
        if is_long:
            with st.container(key="answer_more"):
                label = (
                    "접기 ⌃"
                    if st.session_state.expanded
                    else "더보기 ⌄"
                )

                if st.button(
                    label,
                    key="toggle_more"
                ):
                    st.session_state.expanded = (
                        not st.session_state.expanded
                    )
                    st.rerun()

        # AI 음성 재생
        if st.session_state.audio_answer:
            with st.container(key="answer_audio"):
                st.audio(
                    st.session_state.audio_answer,
                    format="audio/mp3",
                    autoplay=just_processed
                )

    else:
        st.markdown(
            """
            <div class="answer-area">
                <div class="answer-box">
                    💬 음성 질문에 대한 답변이
                    여기에 표시됩니다.
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )


# 8. 인식된 음성 확인
if st.session_state.transcript:
    with st.expander("인식된 음성 확인"):
        st.write(st.session_state.transcript)


# 9. 최근 대화 기록
with st.expander("최근 대화 기록"):

    if not st.session_state.history:
        st.caption("아직 대화 기록이 없습니다.")

    else:
        for message in st.session_state.history[-10:]:
            who = (
                "나"
                if message["role"] == "user"
                else "Thumbs Up AI"
            )

            st.markdown(f"**{who}**")
            st.write(message["content"])

        if st.button(
            "대화 초기화",
            key="clear_history"
        ):
            for name, default in DEFAULTS.items():
                st.session_state[name] = default

            st.rerun()


# 10. TXT 파일 첨부
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
