
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import streamlit as st
from openai import OpenAI, OpenAIError

st.set_page_config(page_title="ThumbsUp AI", page_icon="👍🏻", layout="wide")

st.title("Thumbs Up, Your Professional AI Voice Assistant")

st.write("당신만의 AI Voice Assistant ThumbsUp입니다.\n무엇이든 음성으로 질문해주세요.")

with st.sidebar:
    mode = st.radio("답변 방식", ["교통 공지 검색", "일반 상담"])
    st.caption("공개된 교통 공지를 확인합니다. 경로별 실시간 소요시간과 열차 도착 시각은 지도나 교통정보 서비스에서 확인하세요.")

def render_answer(response):
    """검색 출처를 답변의 해당 위치에 클릭 가능한 링크로 붙입니다."""
    parts = []
    for item in response.output:
        if item.type != "message":
            continue
        for content in item.content:
            if content.type != "output_text":
                continue
            answer = content.text
            citations = sorted(
                (entry for entry in content.annotations if entry.type == "url_citation"),
                key=lambda entry: entry.end_index,
                reverse=True,
            )
            for number, citation in reversed(list(enumerate(reversed(citations), start=1))):
                url = citation.url
                if urlsplit(url).scheme in {"http", "https"}:
                    url = url.replace("<", "%3C").replace(">", "%3E")
                    end = citation.end_index
                    answer = answer[:end] + f" [출처 {number}](<{url}>)" + answer[end:]
            parts.append(answer)
    return "\n\n".join(parts)


st.session_state.setdefault("messages", [])
for message in st.session_state.messages:
    st.chat_message(message["role"]).markdown(message["content"])

with st.form("question", clear_on_submit=True):
    question = st.text_input("김대리님, 무엇을 도와드릴까요?")
    recording = st.audio_input("또는 음성으로 질문하기")
    submitted = st.form_submit_button("보내기")

if submitted:
    if not question.strip() and recording is None:
        st.warning("질문을 입력하거나 녹음해 주세요.")
        st.stop()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        st.error("OPENAI_API_KEY를 설정해 주세요.")
        st.stop()
    client = OpenAI(api_key=api_key, timeout=60)

    try:
        if not question.strip():
            question = client.audio.transcriptions.create(
                model="whisper-1",
                file=("question.wav", recording.getvalue(), "audio/wav"),
            ).text
    except OpenAIError:
        st.error("음성 변환에 실패했습니다. API 설정을 확인하거나 텍스트로 질문해 주세요.")
        st.stop()

    if not question.strip():
        st.warning("녹음에서 질문을 인식하지 못했습니다.")
        st.stop()

    st.chat_message("user").write(question)
    with st.spinner("출퇴근 정보를 확인하고 있습니다..."):
        now = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST")
        search = mode == "교통 공지 검색"
        options = {"tools": [{"type": "web_search"}]} if search else {}
        guidance = (
            "교통 공지나 사고, 통제, 지연을 묻는 경우 웹 검색으로 확인하세요. "
            "공식 교통기관이나 운영기관을 우선하고, 공지의 발표 시각과 적용 시간, 구간을 구분하세요. "
            "지역이나 노선이 불분명하면 한 가지 확인 질문을 하세요. "
            "현재 적용되는 공지를 확인할 수 없다면 확인할 수 없었다고 답하세요."
            if search else
            "일반 상담 모드입니다. 현재 교통 상태는 확인하지 않았다고 안내하세요. "
            "공개 공지가 필요한 경우 교통 공지 검색 모드를 안내하세요."
        )
        try:
            result = client.responses.create(
                model="gpt-4.1-mini",
                instructions=(
                    "당신은 30~40대 직장인 김대리의 한국어 출퇴근 비서입니다. "
                    "사용자를 김대리님이라고 부르고 결론부터 간단하게 답하세요. "
                    f"현재 한국 시각은 {now}입니다. {guidance} "
                    "이전 대화의 교통 상태를 현재 상태로 인용하지 마세요. "
                    "실시간 열차·버스 도착, 경로별 자동차 소요시간과 혼잡도를 추정하지 마세요. "
                    "그 수치가 필요한 경우 사용자가 지도 앱이나 교통기관의 실시간 화면에서 "
                    "어떤 역·방면이나 출발지·목적지를 확인하면 되는지 안내하세요."
                ),
                input=[*st.session_state.messages[-10:], {"role": "user", "content": question}],
                **options,
            )
            answer = render_answer(result) or "답변을 받지 못했습니다. 다시 질문해 주세요."
        except OpenAIError:
            st.error("답변을 받지 못했습니다. API 키, 모델 접근 권한 또는 사용 한도를 확인해 주세요.")
            st.stop()

    st.chat_message("assistant").markdown(answer)
    st.session_state.messages.extend([
        {"role": "user", "content": question},
        {"role": "assistant", "content": answer},
    ])
