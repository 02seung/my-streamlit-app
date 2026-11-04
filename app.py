
import os
import io
import re
import json
import html
import copy
import hashlib
from uuid import uuid4
from datetime import datetime

import streamlit as st
from openai import OpenAI
from audio_recorder_streamlit import audio_recorder

# 1. 페이지 설정
st.set_page_config(
    page_title="Thumbs Up AI",
    page_icon="👍🏻",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 2. 디자인
st.markdown("""
<style>
.block-container {
    max-width:1150px;
    padding-top:2rem;
}
[data-testid="stSidebar"] {
    background:#FFF0D7;
    border-left:3px solid #1595ff;
}
[data-testid="stSidebar"] .stButton button {
    width:100%;
    justify-content:flex-start;
    text-align:left;
    background:transparent;
    border:0;
    border-radius:8px;
    color:#222;
    box-shadow:none;
}
[data-testid="stSidebar"] .stButton button:hover {
    background:#FFD49B!important;
    color:#111!important;
}
[data-testid="stSidebar"] .stButton button[kind="primary"] {
    background:#FFDFAD;
}
.st-key-assistant_card {
    background:#fff;
    border:1px solid #e6e6e9!important;
    border-radius:26px!important;
    padding:26px 32px 30px!important;
}
.brand {
    font-size:25px;
    font-weight:750;
    line-height:1.35;
    color:#111;
}
.desc {
    font-size:13px;
    color:#333;
    margin-top:14px;
}
.st-key-header_actions button {
    border:0!important;
    background:transparent!important;
    box-shadow:none!important;
    font-size:24px!important;
}
.question {
    width:min(100%,365px);
    min-height:182px;
    margin:20px auto;
    padding:20px 22px;
    border:1px solid #eee;
    box-shadow:0 1px 7px #00000018;
    font-size:19px;
    white-space:pre-wrap;
    overflow-wrap:anywhere;
    box-sizing:border-box;
}
.rule {
    height:1px;
    background:#505050;
    width:100%;
}
.st-key-microphone_shell {
    width:55px;
    margin:0 auto;
    display:flex;
    justify-content:center;
}
.status {
    width:min(100%,365px);
    margin:18px auto;
    padding:10px 14px;
    background:#ededed;
    border-radius:6px;
    text-align:center;
    color:#555;
    font-size:12px;
}
.answer {
    width:min(100%,365px);
    margin:0 auto;
}
.answer-body {
    padding:12px 15px;
    background:#f3f3f3;
    border-radius:7px;
    font-size:13px;
    line-height:1.6;
    white-space:pre-wrap;
    overflow-wrap:anywhere;
}
.answer-body.short {
    display:-webkit-box;
    -webkit-box-orient:vertical;
    -webkit-line-clamp:2;
    overflow:hidden;
    white-space:normal;
}
.st-key-answer_more button {
    border:0!important;
    background:transparent!important;
    box-shadow:none!important;
}
</style>
""", unsafe_allow_html=True)

# 3. 기본 인물 데이터
PEOPLE = {
    "P001": {
        "name": "김민수",
        "title": "대리",
        "extra_aliases": ["민수 형"]
    },
    "P002": {
        "name": "박지연",
        "title": "과장",
        "extra_aliases": ["지연 누나"]
    },
    "P003": {
        "name": "김하늘",
        "title": "대리",
        "extra_aliases": []
    },
}

# 4. 세션 상태
DEFAULTS = {
    "transcript": "",
    "answer": "",
    "audio_answer": None,
    "history": [],
    "question_history": [],
    "selected_id": None,
    "last_audio_hash": None,
    "expanded": False,
    "pending_autoplay": False,
    "process_status": "마이크를 눌러 질문해 주세요.",
    "identity_people": copy.deepcopy(PEOPLE),
    "identity_enabled": True,
    "identity_context_enabled": True,
    "identity_last": None,
}

for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = copy.deepcopy(v)


# 5. OpenAI 연결
def get_client():
    key = os.getenv("OPENAI_API_KEY")

    if not key:
        try:
            key = st.secrets.get("OPENAI_API_KEY")
        except Exception:
            key = None

    return OpenAI(api_key=key) if key else None


# 6. 인물 데이터 검증
def validate_people(data):
    if not isinstance(data, dict) or len(data) > 100:
        raise ValueError(
            "인물 목록은 최대 100명의 JSON 객체여야 합니다."
        )

    result = {}

    for pid, p in data.items():
        if not isinstance(pid, str) or not re.fullmatch(
            r"[A-Za-z0-9_-]{1,32}", pid
        ):
            raise ValueError(
                "인물 ID는 영문·숫자·_·-만 가능합니다."
            )

        if not isinstance(p, dict):
            raise ValueError("인물 데이터는 객체여야 합니다.")

        name = p.get("name")
        title = p.get("title", "")
        aliases = p.get("extra_aliases", [])

        if not isinstance(name, str) or not (
            1 <= len(name.strip()) <= 60
        ):
            raise ValueError(f"{pid}: 이름을 확인하세요.")

        if not isinstance(title, str) or len(title) > 40:
            raise ValueError(f"{pid}: 직급을 확인하세요.")

        if (
            not isinstance(aliases, list)
            or len(aliases) > 30
            or not all(
                isinstance(a, str)
                and 1 <= len(a.strip()) <= 60
                for a in aliases
            )
        ):
            raise ValueError(
                f"{pid}: 별명은 30개 이하의 문자열이어야 합니다."
            )

        result[pid] = {
            "name": name.strip(),
            "title": title.strip(),
            "extra_aliases": list(
                dict.fromkeys(a.strip() for a in aliases)
            )
        }

    return result


# 7. 등록 호칭 기반 인물 식별
def rule_normalize(text, people):
    alias_map = {}

    for pid, person in people.items():
        name = person["name"]
        title = person["title"]

        aliases = {
            name,
            *person["extra_aliases"]
        }

        if title:
            aliases.update({
                name + title,
                name[0] + title,
                name[1:] + title
            })

        for alias in aliases:
            compact = re.sub(r"\s+", "", alias)

            alias_map.setdefault(
                compact, set()
            ).add(pid)

    matches = []
    unresolved = []

    if not alias_map:
        return text, matches, unresolved

    pattern = re.compile(
        r"(?<![가-힣A-Za-z0-9])(?:"
        + "|".join(
            r"\s*".join(map(re.escape, a))
            for a in sorted(
                alias_map,
                key=len,
                reverse=True
            )
        )
        + r")(?=(?:은|는|이|가|을|를|께서|에게|한테|의|도|만)?(?:[^가-힣A-Za-z0-9]|$))"
    )

    edits = []

    for m in pattern.finditer(text):
        ids = alias_map[
            re.sub(r"\s+", "", m.group())
        ]

        if len(ids) != 1:
            unresolved.append({
                "호칭": m.group(),
                "사유": "동일 호칭 인물 다수"
            })
            continue

        pid = next(iter(ids))
        p = people[pid]

        replacement = (
            f"{p['name']} {p['title']}".strip()
        )

        edits.append((
            m.start(),
            m.end(),
            replacement
        ))

        matches.append({
            "호칭": m.group(),
            "인물": replacement,
            "ID": pid,
            "방식": "등록 호칭"
        })

    for a, b, rep in reversed(edits):
        text = text[:a] + rep + text[b:]

    return text, matches, unresolved


# 8. AI 문맥 기반 인물 식별
def apply_identity(client, question, reference):
    people = st.session_state.identity_people

    if not st.session_state.identity_enabled or not people:
        st.session_state.identity_last = None
        return question, reference

    q, qm, qu = rule_normalize(question, people)

    r, rm, ru = rule_normalize(
        reference[:15000], people
    )

    matches = qm + rm
    unresolved = qu + ru

    if st.session_state.identity_context_enabled:
        try:
            schema = {
                "type": "object",
                "properties": {
                    "mentions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "part": {
                                    "type": "string",
                                    "enum": [
                                        "question",
                                        "reference"
                                    ]
                                },
                                "surface": {
                                    "type": "string"
                                },
                                "person_id": {
                                    "type": "string",
                                    "enum": list(people) + [
                                        "UNKNOWN"
                                    ]
                                },
                                "confidence": {
                                    "type": "string",
                                    "enum": ["high", "low"]
                                },
                                "reason": {
                                    "type": "string"
                                }
                            },
                            "required": [
                                "part",
                                "surface",
                                "person_id",
                                "confidence",
                                "reason"
                            ],
                            "additionalProperties": False
                        }
                    }
                },
                "required": ["mentions"],
                "additionalProperties": False
            }

            response = client.responses.create(
                model="gpt-4o-mini",
                input=[
                    {
                        "role": "system",
                        "content": (
                            "등록 인물과 질문·참고문서를 대조해 "
                            "미해결 호칭만 식별하세요. "
                            "확실하지 않으면 UNKNOWN/low. "
                            "성씨나 직급만으로 연결하지 마세요. "
                            "surface는 텍스트에 실제로 존재해야 합니다. "
                            "이미 정규화된 실명은 제외하세요."
                        )
                    },
                    {
                        "role": "user",
                        "content": json.dumps({
                            "people": [
                                {"id": pid, **p}
                                for pid, p in people.items()
                            ],
                            "question": q,
                            "reference": r
                        }, ensure_ascii=False)
                    }
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "identity_mentions",
                        "strict": True,
                        "schema": schema
                    }
                }
            )

            docs = {
                "question": q,
                "reference": r
            }

            edits = {
                "question": [],
                "reference": []
            }

            proposals = json.loads(
                response.output_text
            ).get("mentions", [])

            for item in proposals:
                part = item["part"]
                surface = item["surface"]
                pid = item["person_id"]

                if (
                    not surface
                    or len(surface) > 60
                    or pid == "UNKNOWN"
                    or item["confidence"] != "high"
                ):
                    unresolved.append({
                        "호칭": surface,
                        "사유": item["reason"]
                    })
                    continue

                found = list(re.finditer(
                    r"(?<![가-힣A-Za-z0-9])"
                    + re.escape(surface)
                    + r"(?![가-힣A-Za-z0-9])",
                    docs[part]
                ))

                if len(found) != 1:
                    unresolved.append({
                        "호칭": surface,
                        "사유": "위치 불명확"
                    })
                    continue

                p = people[pid]
                target = (
                    f"{p['name']} {p['title']}".strip()
                )

                edits[part].append((
                    found[0].start(),
                    found[0].end(),
                    target
                ))

                matches.append({
                    "호칭": surface,
                    "인물": target,
                    "ID": pid,
                    "방식": "AI 문맥"
                })

            for part in docs:
                accepted = []

                for start, end, target in sorted(
                    edits[part]
                ):
                    if accepted and start < accepted[-1][1]:
                        unresolved.append({
                            "호칭": docs[part][start:end],
                            "사유": "치환 구간 중복"
                        })
                        continue

                    accepted.append((
                        start, end, target
                    ))

                for start, end, target in reversed(accepted):
                    docs[part] = (
                        docs[part][:start]
                        + target
                        + docs[part][end:]
                    )

            q = docs["question"]
            r = docs["reference"]

        except Exception as exc:
            unresolved.append({
                "호칭": "AI 문맥 분석",
                "사유": f"분석 실패: {str(exc)[:120]}"
            })

    st.session_state.identity_last = {
        "original_question": question,
        "question": q,
        "matches": matches,
        "unresolved": unresolved
    }

    return q, r + reference[15000:]


# 9. 톱니바퀴 설정 팝업
@st.dialog("⚙️ 인물 식별 설정", width="large")
def show_settings():

    st.checkbox(
        "인물 구분 기능 사용",
        key="identity_enabled"
    )

    st.checkbox(
        "AI 문맥 기반 식별 사용",
        key="identity_context_enabled",
        disabled=not st.session_state.identity_enabled
    )

    st.caption(
        "등록된 이름·직급·별명을 우선 적용하고, "
        "남은 호칭은 AI가 문맥으로 분석합니다."
    )

    people = st.session_state.identity_people

    tab1, tab2 = st.tabs([
        "인물 관리",
        "최근 식별 결과"
    ])

    with tab1:

        st.dataframe(
            [
                {
                    "ID": pid,
                    "이름": p["name"],
                    "직급": p["title"],
                    "별명": ", ".join(
                        p["extra_aliases"]
                    )
                }
                for pid, p in people.items()
            ],
            use_container_width=True,
            hide_index=True
        )

        # 새 인물 등록
        with st.expander("➕ 새 인물 등록"):

            with st.form("add_person"):
                pid = st.text_input(
                    "인물 ID",
                    placeholder="P004"
                )

                name = st.text_input("이름")
                title = st.text_input("직급")

                aliases = st.text_input(
                    "별명 (쉼표로 구분)"
                )

                submitted = st.form_submit_button(
                    "등록"
                )

            if submitted:
                try:
                    if pid.strip() in people:
                        raise ValueError(
                            "이미 등록된 ID입니다."
                        )

                    new = validate_people({
                        pid.strip(): {
                            "name": name,
                            "title": title,
                            "extra_aliases": [
                                a.strip()
                                for a in aliases.split(",")
                                if a.strip()
                            ]
                        }
                    })

                    st.session_state.identity_people = {
                        **people,
                        **new
                    }

                    st.rerun()

                except ValueError as e:
                    st.error(str(e))

        # 인물 수정 및 삭제
        with st.expander("✏️ 인물 수정 및 삭제"):

            if people:
                selected = st.selectbox(
                    "인물 선택",
                    list(people),
                    format_func=lambda k: (
                        f"{people[k]['name']} ({k})"
                    )
                )

                p = people[selected]

                with st.form(f"edit_{selected}"):

                    new_name = st.text_input(
                        "이름 수정",
                        value=p["name"]
                    )

                    new_title = st.text_input(
                        "직급 수정",
                        value=p["title"]
                    )

                    new_alias = st.text_input(
                        "별명 수정",
                        value=", ".join(
                            p["extra_aliases"]
                        )
                    )

                    update = st.form_submit_button(
                        "수정 저장"
                    )

                if update:
                    try:
                        new = validate_people({
                            selected: {
                                "name": new_name,
                                "title": new_title,
                                "extra_aliases": [
                                    a.strip()
                                    for a in new_alias.split(",")
                                    if a.strip()
                                ]
                            }
                        })

                        st.session_state.identity_people = {
                            **people,
                            **new
                        }

                        st.rerun()

                    except ValueError as e:
                        st.error(str(e))

                confirm = st.checkbox(
                    "삭제를 확인했습니다",
                    key="confirm_delete"
                )

                if st.button(
                    "선택 인물 삭제",
                    disabled=not confirm
                ):
                    st.session_state.identity_people = {
                        k: v
                        for k, v in people.items()
                        if k != selected
                    }

                    st.rerun()

        # 인물 목록 공유
        with st.expander(
            "📁 인물 목록 JSON 가져오기 / 내보내기"
        ):

            st.download_button(
                "JSON 다운로드",
                json.dumps(
                    people,
                    ensure_ascii=False,
                    indent=2
                ),
                file_name="people.json",
                mime="application/json"
            )

            uploaded_people = st.file_uploader(
                "JSON 업로드",
                type=["json"],
                key="people_json"
            )

            if (
                uploaded_people is not None
                and st.button("업로드한 목록 적용")
            ):
                try:
                    if uploaded_people.size > 100000:
                        raise ValueError(
                            "100KB 이하 파일만 가능합니다."
                        )

                    new_people = validate_people(
                        json.loads(
                            uploaded_people.getvalue().decode(
                                "utf-8-sig"
                            )
                        )
                    )

                    st.session_state.identity_people = (
                        new_people
                    )

                    st.rerun()

                except (
                    UnicodeError,
                    ValueError,
                    TypeError
                ) as e:
                    st.error(
                        f"불러오기 실패: {e}"
                    )

        st.caption(
            "인물 정보는 현재 Streamlit 세션에만 저장됩니다."
        )

    with tab2:

        result = st.session_state.identity_last

        if result is None:
            st.info(
                "아직 인물 식별 결과가 없습니다."
            )

        else:
            st.write(
                "원본 질문:",
                result["original_question"]
            )

            st.write(
                "정규화된 질문:",
                result["question"]
            )

            st.write(
                "식별된 호칭:",
                result["matches"] or "없음"
            )

            st.write(
                "검토 필요:",
                result["unresolved"] or "없음"
            )


# 10. 이전 질문 선택
def select_question(qid):

    for item in st.session_state.question_history:

        if item["id"] == qid:

            st.session_state.selected_id = qid
            st.session_state.transcript = item["question"]
            st.session_state.answer = item["answer"]
            st.session_state.audio_answer = item["audio"]

            st.session_state.expanded = False
            st.session_state.pending_autoplay = False
            st.session_state.process_status = (
                "이전 질문을 불러왔습니다."
            )

            return


# 11. 음성 인식 → AI 분석 → 음성 답변
def process_audio(audio_bytes, reference):

    client = get_client()

    if client is None:
        st.error(
            "Streamlit Secrets에 OPENAI_API_KEY를 등록하세요."
        )
        return

    try:
        st.session_state.process_status = (
            "음성 인식 중..."
        )

        with st.spinner("음성을 인식하고 있습니다..."):

            audio_file = io.BytesIO(audio_bytes)
            audio_file.name = "recording.wav"

            question = (
                client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file
                ).text.strip()
            )

        if not question:
            st.warning(
                "음성 인식 결과가 없습니다."
            )
            return

        st.session_state.transcript = question

        # 인물 식별 기능 적용
        normalized_q, normalized_ref = apply_identity(
            client,
            question,
            reference
        )

        prompt = (
            "당신은 Thumbs Up AI라는 한국어 음성 비서입니다. "
            "간결하게 답하세요. "
            "검색·캘린더 작업을 실행하지 않았다면 "
            "완료했다고 말하지 마세요."
        )

        if normalized_ref:
            prompt += (
                "\n첨부 TXT 내용:\n"
                + normalized_ref[:15000]
            )

        messages = [
            {
                "role": "system",
                "content": prompt
            },
            *st.session_state.history[-8:],
            {
                "role": "user",
                "content": normalized_q
            }
        ]

        st.session_state.process_status = (
            "답변 준비중입니다..."
        )

        with st.spinner("AI가 답변을 생성하고 있습니다..."):

            response = client.responses.create(
                model="gpt-4o-mini",
                input=messages
            )

            answer = (
                response.output_text.strip()
                or "답변을 생성하지 못했습니다."
            )

        audio = None

        st.session_state.process_status = (
            "음성 답변 준비중..."
        )

        try:
            with st.spinner(
                "음성 답변을 준비하고 있습니다..."
            ):

                audio = client.audio.speech.create(
                    model="tts-1",
                    voice="nova",
                    input=answer[:4000]
                ).read()

        except Exception as e:
            st.warning(
                f"음성 합성에 실패했습니다: {e}"
            )

        st.session_state.answer = answer
        st.session_state.audio_answer = audio
        st.session_state.expanded = False
        st.session_state.pending_autoplay = (
            audio is not None
        )

        st.session_state.process_status = (
            "답변이 준비되었습니다."
        )

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

        qid = str(uuid4())

        st.session_state.question_history.insert(
            0,
            {
                "id": qid,
                "question": question,
                "answer": answer,
                "audio": audio,
                "date": datetime.now().isoformat()
            }
        )

        st.session_state.selected_id = qid

        st.rerun()

    except Exception as e:
        st.session_state.process_status = (
            "오류가 발생했습니다."
        )

        st.error(
            f"음성 처리 실패: {e}"
        )


# 12. TXT 첨부
with st.expander(
    "📎 참고 TXT 파일 첨부 (선택)"
):

    txt_file = st.file_uploader(
        "텍스트 파일",
        type=["txt"],
        key="reference_txt"
    )

    if txt_file is not None:
        st.success(
            f"{txt_file.name} 첨부됨"
        )

reference = (
    txt_file.getvalue().decode(
        "utf-8-sig",
        errors="replace"
    )
    if txt_file
    else ""
)


# 13. 메인 인터페이스
with st.container(key="assistant_card"):

    main, actions = st.columns(
        [10, 1],
        vertical_alignment="top"
    )

    with main:

        st.markdown(
            """
            <div class="brand">
                Thumbs Up,
                <br>
                Your professional AI Voice Assistant
            </div>

            <div class="desc">
                당신만의 AI Voice Assistant ThumbsUp입니다.
                녹음 버튼을 눌러 질문해주세요.
            </div>
            """,
            unsafe_allow_html=True
        )

    # 톱니바퀴 → 설정 팝업
    with actions:

        with st.container(
            key="header_actions"
        ):

            if st.button(
                "⚙",
                key="open_settings",
                help="인물 식별 설정"
            ):
                show_settings()

    st.write("")

    question_box = st.empty()

    # 중앙 마이크
    l, mic, r = st.columns(
        [5, 1, 5],
        vertical_alignment="center"
    )

    with l:
        st.markdown(
            '<div class="rule"></div>',
            unsafe_allow_html=True
        )

    with mic:

        with st.container(
            key="microphone_shell"
        ):

            recorded = audio_recorder(
                text="",
                icon_name="microphone",
                icon_size="2x",
                neutral_color="#555555",
                recording_color="#e04444",
                key="main_mic"
            )

    with r:
        st.markdown(
            '<div class="rule"></div>',
            unsafe_allow_html=True
        )

    st.caption(
        "마이크를 눌러 녹음을 시작하고 다시 눌러 종료하세요."
    )

    # 새로운 녹음 처리
    if recorded:

        digest = hashlib.sha256(
            recorded
        ).hexdigest()

        if digest != st.session_state.last_audio_hash:

            st.session_state.last_audio_hash = digest

            process_audio(
                recorded,
                reference
            )

    # 사용자 질문 표시
    q = st.session_state.transcript

    question_box.markdown(
        '<div class="question">'
        + html.escape(
            q or "마이크를 눌러 질문해 주세요."
        )
        + '</div>',
        unsafe_allow_html=True
    )

    # 처리 상태
    st.markdown(
        '<div class="status">'
        + html.escape(
            st.session_state.process_status
        )
        + '</div>',
        unsafe_allow_html=True
    )

    # AI 답변
    answer = st.session_state.answer

    st.markdown(
        '<div class="answer"><b>AI 답변</b></div>',
        unsafe_allow_html=True
    )

    if answer:

        is_long = (
            len(answer) > 75
            or answer.count("\n") >= 2
        )

        css = (
            "answer-body short"
            if is_long and not st.session_state.expanded
            else "answer-body"
        )

        st.markdown(
            '<div class="answer"><div class="'
            + css
            + '">💬 '
            + html.escape(answer)
            + '</div></div>',
            unsafe_allow_html=True
        )

        if is_long:

            with st.container(
                key="answer_more"
            ):

                if st.button(
                    "접기 ⌃"
                    if st.session_state.expanded
                    else "더보기 ⌄"
                ):

                    st.session_state.expanded = (
                        not st.session_state.expanded
                    )

                    st.rerun()

        # 음성 재생
        if st.session_state.audio_answer:

            st.audio(
                st.session_state.audio_answer,
                format="audio/mp3",
                autoplay=st.session_state.pending_autoplay
            )

            st.session_state.pending_autoplay = False

    else:

        st.markdown(
            """
            <div class="answer">
                <div class="answer-body">
                    💬 답변이 여기에 표시됩니다.
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )


# 14. 나의 질문 사이드바
with st.sidebar:

    st.markdown("### 나의 질문")
    st.divider()

    if not st.session_state.question_history:
        st.caption(
            "아직 저장된 질문이 없습니다."
        )

    for item in st.session_state.question_history:

        q = item["question"]

        label = (
            q[:22] + "..."
            if len(q) > 22
            else q
        )

        if st.button(
            label,
            key="q_" + item["id"],
            type=(
                "primary"
                if item["id"] == st.session_state.selected_id
                else "secondary"
            ),
            help=q,
            use_container_width=True
        ):

            select_question(
                item["id"]
            )

            st.rerun()

    st.divider()

    if st.button(
        "🗑 질문 기록 삭제",
        use_container_width=True
    ):

        for k in [
            "history",
            "question_history"
        ]:
            st.session_state[k] = []

        for k in [
            "transcript",
            "answer"
        ]:
            st.session_state[k] = ""

        st.session_state.audio_answer = None
        st.session_state.selected_id = None
        st.session_state.pending_autoplay = False

        st.session_state.process_status = (
            "마이크를 눌러 질문해 주세요."
        )

        st.rerun()
