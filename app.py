
import os
import io
import streamlit as st
from openai import OpenAI
from streamlit_mic_recorder import mic_recorder

# -----------------------------------
# 페이지 설정
# -----------------------------------
st.set_page_config(
    page_title="ThumpsUp AI",
    page_icon="👍🏻",
    layout="wide"
)

# -----------------------------------
# OpenAI 클라이언트
# -----------------------------------
client = None
if os.getenv("OPENAI_API_KEY"):
    client = OpenAI()

# -----------------------------------
# 세션 상태
# -----------------------------------
if "transcript" not in st.session_state:
    st.session_state.transcript = ""

if "answer" not in st.session_state:
    st.session_state.answer = ""

if "history" not in st.session_state:
    st.session_state.history = []

if "uploaded_text" not in st.session_state:
    st.session_state.uploaded_text = ""

# -----------------------------------
# CSS
# -----------------------------------
st.markdown("""
<style>
.block-container {
    max-width: 1200px;
    padding-top: 1.2rem;
    padding-bottom: 2rem;
}

#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}

.main-wrap {
    background: #f7f7f8;
    border-radius: 28px;
    padding: 24px 28px 40px 28px;
}

.top-brand {
    text-align: center;
    margin-bottom: 18px;
}

.brand-title {
    font-size: 30px;
    font-weight: 800;
    color: #222;
}

.brand-sub {
    font-size: 14px;
    color: #777;
    margin-top: 4px;
}

.center-card {
    background: white;
    border-radius: 26px;
    min-height: 220px;
    display: flex;
    align-items: center;
    justify-content: center;
    text-align: center;
    padding: 30px 40px;
    box-shadow: 0 10px 30px rgba(0,0,0,0.04);
    font-size: 30px;
    font-weight: 600;
    line-height: 1.5;
    color: #222;
    margin-top: 20px;
    margin-bottom: 34px;
}

.wave-wrap {
    text-align: center;
    margin-top: 10px;
    margin-bottom: 24px;
}

.fake-mic {
    width: 130px;
    height: 130px;
    margin: 0 auto 18px auto;
    border-radius: 50%;
    background: radial-gradient(circle, #f8fbff 0%, #edf2ff 80%);
    border: 1px solid #dfe5ff;
    box-shadow: 0 10px 30px rgba(145, 165, 255, 0.25);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 52px;
}

.wave-line {
    width: 75%;
    height: 12px;
    margin: 0 auto;
    border-radius: 999px;
    background: linear-gradient(90deg, #cfdcff, #f1c3cf, #d6cfff);
    opacity: 0.95;
}

.section-title {
    font-size: 18px;
    font-weight: 700;
    margin-bottom: 8px;
    color: #333;
}

.info-box {
    background: white;
    padding: 18px;
    border-radius: 18px;
    box-shadow: 0 6px 20px rgba(0,0,0,0.03);
    margin-bottom: 14px;
}

.small-text {
    color: #666;
    font-size: 14px;
    line-height: 1.7;
}

.status-chip {
    display: inline-block;
    padding: 8px 12px;
    border-radius: 999px;
    background: #eef4ff;
    color: #446;
    font-size: 13px;
    margin-top: 8px;
}

div[data-testid="stFileUploader"] {
    background: white;
    border-radius: 16px;
    padding: 10px;
}

div[data-testid="stAudio"] {
    margin-top: 10px;
}

.history-box {
    background: white;
    border-radius: 18px;
    padding: 18px;
    box-shadow: 0 6px 20px rgba(0,0,0,0.03);
}
</style>
""", unsafe_allow_html=True)

# -----------------------------------
# 시스템 프롬프트
# -----------------------------------
SYSTEM_PROMPT = """
당신은 ThumpsUp AI라는 음성 기반 개인 비서입니다.

역할:
- 사용자의 음성 명령을 이해하고 친절하게 답합니다.
- 일정 관리, 웹 검색, 주식 조회, 파일 요약 요청을 구분합니다.
- 한국어로 간결하고 이해하기 쉽게 답합니다.
- 아직 실제 기능이 연결되지 않은 경우에는 거짓으로 실행했다고 말하지 말고,
  현재 가능한 안내를 제공합니다.
"""

# -----------------------------------
# 함수
# -----------------------------------
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
            "content": f"다음 참고 파일 내용도 함께 고려하세요:\n{extra_text[:15000]}"
        })

    for item in st.session_state.history[-6:]:
        messages.append(item)

    messages.append({"role": "user", "content": user_text})

    response = client.responses.create(
        model="gpt-4o-mini",
        input=messages
    )

    return response.output_text

def process_audio(audio_bytes):
    if client is None:
        st.error("OPENAI_API_KEY가 설정되지 않았습니다.")
        return

    with st.spinner("음성을 인식하고 있습니다..."):
        transcript = speech_to_text(audio_bytes)
        st.session_state.transcript = transcript

    with st.spinner("ThumpsUp AI가 답변을 생성하고 있습니다..."):
        answer = ask_ai(transcript, st.session_state.uploaded_text)
        st.session_state.answer = answer

    st.session_state.history.append({"role": "user", "content": transcript})
    st.session_state.history.append({"role": "assistant", "content": answer})

# -----------------------------------
# 상단
# -----------------------------------
st.markdown('<div class="main-wrap">', unsafe_allow_html=True)

st.markdown("""
<div class="top-brand">
    <div class="brand-title">👍🏻 ThumpsUp AI</div>
    <div class="brand-sub">Voice First Personal Assistant</div>
</div>
""", unsafe_allow_html=True)

display_text = "무엇을 도와드릴까요?"
if st.session_state.answer:
    display_text = st.session_state.answer
elif st.session_state.transcript:
    display_text = st.session_state.transcript

st.markdown(
    f'<div class="center-card">{display_text}</div>',
    unsafe_allow_html=True
)

st.markdown("""
<div class="wave-wrap">
    <div class="fake-mic">🎙️</div>
    <div class="wave-line"></div>
</div>
""", unsafe_allow_html=True)

# -----------------------------------
# 실제 음성 입력 영역
# -----------------------------------
st.markdown("### 음성 입력")
st.caption("아래 마이크 버튼을 눌러 녹음한 뒤, 완료하면 자동으로 인식합니다.")

audio = mic_recorder(
    start_prompt="🎙️ 마이크 버튼을 눌러 녹음 시작",
    stop_prompt="⏹️ 녹음 종료",
    just_once=True,
    use_container_width=True,
    key="voice_recorder"
)

if audio:
    audio_bytes = audio["bytes"]
    st.audio(audio_bytes, format="audio/wav")
    process_audio(audio_bytes)

st.divider()

# -----------------------------------
# 하단 영역
# -----------------------------------
left, right = st.columns([1.2, 1])

with left:
    st.markdown('<div class="info-box">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">참고 파일 업로드</div>', unsafe_allow_html=True)
    uploaded_file = st.file_uploader("TXT 파일 업로드", type=["txt"], label_visibility="collapsed")

    if uploaded_file is not None:
        st.session_state.uploaded_text = uploaded_file.read().decode("utf-8", errors="replace")
        st.markdown(
            f'<div class="status-chip">업로드 완료: {uploaded_file.name}</div>',
            unsafe_allow_html=True
        )

    st.markdown(
        '<div class="small-text">파일을 업로드한 뒤 음성으로 "이 파일 요약해줘"처럼 말하면 됩니다.</div>',
        unsafe_allow_html=True
    )
    st.markdown('</div>', unsafe_allow_html=True)

with right:
    st.markdown('<div class="info-box">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">예시 음성 명령</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="small-text">
    - 오늘 일정 알려줘<br>
    - 내일 오후 3시에 회의 등록해줘<br>
    - 삼성전자 주가 알려줘<br>
    - 오늘 AI 뉴스 검색해줘<br>
    - 이 파일 요약해줘
    </div>
    """, unsafe_allow_html=True)

    if client:
        st.markdown('<div class="status-chip">OpenAI 연결 준비 완료</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="status-chip">OpenAI API 키 필요</div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

# -----------------------------------
# 최근 대화
# -----------------------------------
st.markdown("### 최근 대화")

if not st.session_state.history:
    st.info("아직 대화 기록이 없습니다.")
else:
    st.markdown('<div class="history-box">', unsafe_allow_html=True)
    for msg in st.session_state.history[-8:]:
        role = "사용자" if msg["role"] == "user" else "ThumpsUp AI"
        st.markdown(f"**{role}**")
        st.write(msg["content"])
    st.markdown('</div>', unsafe_allow_html=True)

    if st.button("대화 초기화", use_container_width=True):
        st.session_state.transcript = ""
        st.session_state.answer = ""
        st.session_state.history = []
        st.rerun()

st.markdown('</div>', unsafe_allow_html=True)
