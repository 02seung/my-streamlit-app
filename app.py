
import os
import io
import streamlit as st
from openai import OpenAI

# -----------------------------------
# 기본 설정
# -----------------------------------
st.set_page_config(
    page_title="ThumpsUp AI",
    page_icon="👍🏻",
    layout="wide"
)

client = None
if os.getenv("OPENAI_API_KEY"):
    client = OpenAI()

# -----------------------------------
# 세션 상태
# -----------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []

if "last_transcript" not in st.session_state:
    st.session_state.last_transcript = ""

if "last_answer" not in st.session_state:
    st.session_state.last_answer = ""

if "mode" not in st.session_state:
    st.session_state.mode = "Speak"

# -----------------------------------
# CSS
# -----------------------------------
st.markdown("""
<style>
html, body, [class*="css"] {
    font-family: "Pretendard", "Noto Sans KR", sans-serif;
}

.block-container {
    padding-top: 1.5rem;
    padding-bottom: 2rem;
    max-width: 1200px;
}

#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}

.main-shell {
    background: #f8f8f8;
    border-radius: 28px;
    padding: 28px 36px 36px 36px;
    min-height: 80vh;
    box-shadow: 0 12px 35px rgba(0,0,0,0.05);
}

.brand {
    font-size: 30px;
    font-weight: 800;
    color: #222;
    margin-bottom: 4px;
}

.sub-brand {
    color: #888;
    font-size: 15px;
    margin-bottom: 30px;
}

.mode-tabs {
    display: flex;
    gap: 28px;
    align-items: center;
    margin-bottom: 18px;
}

.mode-chip-active {
    font-size: 18px;
    font-weight: 700;
    color: #7c96ff;
    border-bottom: 2px solid #7c96ff;
    padding-bottom: 6px;
}

.mode-chip {
    font-size: 18px;
    font-weight: 600;
    color: #444;
    padding-bottom: 6px;
}

.center-guide {
    text-align: center;
    color: #666;
    font-size: 15px;
    margin-bottom: 18px;
}

.command-card {
    background: white;
    border-radius: 24px;
    min-height: 220px;
    display: flex;
    align-items: center;
    justify-content: center;
    text-align: center;
    padding: 30px;
    font-size: 34px;
    line-height: 1.5;
    font-weight: 600;
    color: #222;
    box-shadow: 0 10px 30px rgba(0,0,0,0.05);
    margin-bottom: 30px;
}

.wave-wrap {
    text-align: center;
    margin-top: 25px;
    margin-bottom: 25px;
}

.mic-circle {
    width: 88px;
    height: 88px;
    margin: 0 auto;
    border-radius: 50%;
    background: radial-gradient(circle, #ffffff 0%, #eef3ff 70%);
    border: 1px solid #d7e0ff;
    box-shadow: 0 8px 25px rgba(124,150,255,0.35);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 34px;
}

.wave-line {
    width: 70%;
    margin: 16px auto 0 auto;
    height: 10px;
    border-radius: 999px;
    background: linear-gradient(90deg, #d6dfff, #f5c6cf, #d6dfff);
    opacity: 0.8;
}

.small-card {
    background: white;
    border-radius: 18px;
    padding: 18px 20px;
    box-shadow: 0 8px 20px rgba(0,0,0,0.04);
    margin-bottom: 14px;
}

.small-title {
    font-weight: 700;
    margin-bottom: 10px;
    color: #333;
}

.status-box {
    background: #f3f6ff;
    padding: 12px 14px;
    border-radius: 12px;
    color: #355;
    font-size: 14px;
    margin-top: 10px;
}

.bottom-buttons {
    display: flex;
    justify-content: flex-end;
    gap: 12px;
    margin-top: 20px;
}

.hint-list {
    color: #666;
    font-size: 14px;
    line-height: 1.8;
}
</style>
""", unsafe_allow_html=True)

# -----------------------------------
# AI 함수
# -----------------------------------
SYSTEM_PROMPT = """
당신은 ThumpsUp AI라는 음성 기반 개인 비서입니다.

역할:
- 사용자의 음성 명령을 이해하고 수행을 도와줍니다.
- 일정 관리, 웹 검색, 주식 정보, 파일 요약 요청을 구분합니다.
- 친절하고 간결하게 한국어로 답변합니다.
- 아직 실제 기능이 연결되지 않은 경우, 가능한 동작을 안내합니다.
"""

def speech_to_text(audio_bytes):
    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = "recording.wav"

    transcript = client.audio.transcriptions.create(
        model="whisper-1",
        file=audio_file
    )
    return transcript.text

def ask_ai(user_text, extra_text=""):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    if extra_text:
        messages.append({
            "role": "system",
            "content": f"참고 파일 내용:\n{extra_text[:15000]}"
        })

    for m in st.session_state.messages[-6:]:
        messages.append({"role": m["role"], "content": m["content"]})

    messages.append({"role": "user", "content": user_text})

    response = client.responses.create(
        model="gpt-4o-mini",
        input=messages
    )
    return response.output_text

# -----------------------------------
# UI 시작
# -----------------------------------
st.markdown('<div class="main-shell">', unsafe_allow_html=True)

top_left, top_right = st.columns([5, 1])

with top_left:
    st.markdown('<div class="brand">👍🏻 ThumpsUp AI</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-brand">Voice First Personal Assistant</div>', unsafe_allow_html=True)

with top_right:
    st.markdown(
        """
        <div style="text-align:right; color:#777; font-size:14px; margin-top:10px;">
        음성으로 모든 기능 제어
        </div>
        """,
        unsafe_allow_html=True
    )

tab1, tab2 = st.tabs(["Speak", "Listen"])

# -----------------------------------
# Speak 탭
# -----------------------------------
with tab1:
    st.markdown(
        """
        <div class="center-guide">
        마이크를 눌러 말씀해 주세요.<br>
        예: "내일 오후 3시에 회의 일정 등록해줘"
        </div>
        """,
        unsafe_allow_html=True
    )

    display_text = st.session_state.last_transcript if st.session_state.last_transcript else "무엇을 도와드릴까요?"

    st.markdown(
        f'<div class="command-card">{display_text}</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        """
        <div class="wave-wrap">
            <div class="mic-circle">🎙️</div>
            <div class="wave-line"></div>
        </div>
        """,
        unsafe_allow_html=True
    )

    left, right = st.columns([2.2, 1])

    with left:
        st.markdown('<div class="small-card">', unsafe_allow_html=True)
        st.markdown('<div class="small-title">음성 입력</div>', unsafe_allow_html=True)

        audio_value = st.audio_input("여기를 눌러 음성을 녹음하세요")

        run_voice = st.button("START RECORDING", use_container_width=True)

        if run_voice:
            if client is None:
                st.error("OPENAI_API_KEY가 설정되지 않았습니다.")
            elif audio_value is None:
                st.warning("먼저 음성을 녹음해주세요.")
            else:
                with st.spinner("음성을 인식하고 있습니다..."):
                    transcript = speech_to_text(audio_value.getvalue())
                    st.session_state.last_transcript = transcript

                st.success("음성 인식 완료")

        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="small-card">', unsafe_allow_html=True)
        st.markdown('<div class="small-title">텍스트 파일 첨부</div>', unsafe_allow_html=True)

        uploaded_file = st.file_uploader("참고용 TXT 파일 업로드", type=["txt"])

        file_text = ""
        if uploaded_file is not None:
            file_text = uploaded_file.read().decode("utf-8", errors="replace")
            st.markdown(
                f'<div class="status-box">업로드 완료: {uploaded_file.name}</div>',
                unsafe_allow_html=True
            )

        st.markdown('</div>', unsafe_allow_html=True)

    with right:
        st.markdown('<div class="small-card">', unsafe_allow_html=True)
        st.markdown('<div class="small-title">가능한 음성 명령</div>', unsafe_allow_html=True)
        st.markdown(
            """
            <div class="hint-list">
            - 오늘 일정 알려줘<br>
            - 내일 오후 2시에 회의 등록해줘<br>
            - 엔비디아 주가 알려줘<br>
            - 오늘 AI 뉴스 검색해줘<br>
            - 이 파일 요약해줘
            </div>
            """,
            unsafe_allow_html=True
        )
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="small-card">', unsafe_allow_html=True)
        st.markdown('<div class="small-title">상태</div>', unsafe_allow_html=True)

        if client:
            st.markdown(
                '<div class="status-box">OpenAI 연결 준비 완료</div>',
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                '<div class="status-box">OpenAI API 키가 필요합니다</div>',
                unsafe_allow_html=True
            )

        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("### AI 실행")

    command_text = st.text_input(
        "인식된 문장을 수정하거나 직접 입력할 수 있습니다",
        value=st.session_state.last_transcript
    )

    if st.button("SUBMIT", use_container_width=True):
        if client is None:
            st.error("OPENAI_API_KEY가 설정되지 않았습니다.")
        elif not command_text.strip():
            st.warning("명령을 입력하거나 음성을 인식해주세요.")
        else:
            with st.spinner("ThumpsUp AI가 처리 중입니다..."):
                answer = ask_ai(command_text, file_text)
                st.session_state.last_answer = answer
                st.session_state.messages.append({"role": "user", "content": command_text})
                st.session_state.messages.append({"role": "assistant", "content": answer})

# -----------------------------------
# Listen 탭
# -----------------------------------
with tab2:
    st.markdown(
        '<div class="small-card"><div class="small-title">AI 응답</div></div>',
        unsafe_allow_html=True
    )

    if st.session_state.last_answer:
        st.markdown(
            f'<div class="command-card" style="font-size:28px;">{st.session_state.last_answer}</div>',
            unsafe_allow_html=True
        )
    else:
        st.info("아직 AI 응답이 없습니다.")

    st.markdown("### 최근 대화")

    if not st.session_state.messages:
        st.write("대화 기록이 없습니다.")
    else:
        for msg in st.session_state.messages[-8:]:
            role = "사용자" if msg["role"] == "user" else "ThumpsUp AI"
            st.markdown(f"**{role}**")
            st.write(msg["content"])

        if st.button("대화 초기화", use_container_width=True):
            st.session_state.messages = []
            st.session_state.last_transcript = ""
            st.session_state.last_answer = ""
            st.rerun()

st.markdown('</div>', unsafe_allow_html=True)
