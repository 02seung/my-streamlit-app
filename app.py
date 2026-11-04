import os
import io
import re
import json
import html
import copy
import sqlite3
import hashlib
import calendar
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from uuid import uuid4

import streamlit as st
from openai import OpenAI
from audio_recorder_streamlit import audio_recorder

# ==========================================
# 1. 기본 설정
# ==========================================

st.set_page_config(
    page_title="Thumbs Up AI",
    page_icon="👍🏻",
    layout="wide",
    initial_sidebar_state="expanded"
)

KST = ZoneInfo("Asia/Seoul")
DB_PATH = os.environ.get(
    "THUMBS_DB_PATH",
    "thumbs_calendar.db"
)

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
    }
}

DEFAULTS = {
    "sidebar_open": False,
    "transcript": "",
    "answer": "",
    "audio_answer": None,
    "history": [],
    "question_history": [],
    "selected_id": None,
    "last_audio_hash": None,
    "expanded": False,
    "autoplay": False,
    "status": "마이크를 눌러 질문해 주세요.",
    "identity_people": PEOPLE,
    "identity_enabled": True,
    "identity_last": None,
    "calendar_month": datetime.now(
        KST
    ).date().replace(day=1).isoformat(),
    "calendar_day": datetime.now(
        KST
    ).date().isoformat()
}

for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = copy.deepcopy(v)


# ==========================================
# 2. 디자인
# ==========================================

st.markdown("""
<style>
.block-container {
    max-width: 1150px;
    padding-top: 2rem;
    padding-bottom: 2rem;
}
[data-testid="stSidebar"] {
    background: #fff0d7;
    border-left: 3px solid #1595ff;
}
[data-testid="stSidebarCollapsedControl"] {
    display: none !important;
}
[data-testid="stSidebar"] .stButton button {
    width: 100%;
    justify-content: flex-start;
    text-align: left;
    background: transparent;
    border: 0;
    border-radius: 8px;
    color: #222;
    box-shadow: none;
}
[data-testid="stSidebar"] .stButton button:hover {
    background: #ffd49b !important;
    color: #111 !important;
}
[data-testid="stSidebar"] .stButton button[kind="primary"] {
    background: #ffdfad !important;
}
.st-key-assistant_card {
    background: white;
    border: 1px solid #e6e6e9 !important;
    border-radius: 26px !important;
    padding: 26px 32px 30px !important;
}
.brand {
    font-size: 25px;
    font-weight: 750;
    line-height: 1.35;
    color: #111;
}
.desc {
    font-size: 13px;
    color: #333;
    margin-top: 14px;
}
.st-key-header_actions button {
    border: 0 !important;
    background: transparent !important;
    box-shadow: none !important;
    font-size: 23px !important;
    padding: 0 !important;
}
.question {
    width: min(100%,365px);
    min-height: 182px;
    margin: 20px auto;
    padding: 20px 22px;
    border: 1px solid #eee;
    box-shadow: 0 1px 7px #00000018;
    font-size: 19px;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    box-sizing: border-box;
}
.rule {
    height: 1px;
    background: #505050;
    width: 100%;
}
.status {
    width: min(100%,365px);
    margin: 18px auto;
    padding: 10px 14px;
    background: #ededed;
    border-radius: 6px;
    text-align: center;
    color: #555;
    font-size: 12px;
}
.answer {
    width: min(100%,365px);
    margin: 0 auto;
}
.answer-body {
    padding: 12px 15px;
    background: #f3f3f3;
    border-radius: 7px;
    font-size: 13px;
    line-height: 1.6;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
}
.answer-body.short {
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
    overflow: hidden;
    white-space: normal;
}
.st-key-answer_more button {
    border: 0 !important;
    background: transparent !important;
    box-shadow: none !important;
}
</style>
""" + (
    "<style>[data-testid='stSidebar']"
    "{display:none!important}</style>"
    if not st.session_state.sidebar_open
    else ""
), unsafe_allow_html=True)


# ==========================================
# 3. OpenAI API
# ==========================================

def get_client():
    key = os.environ.get("OPENAI_API_KEY")

    if not key:
        try:
            key = st.secrets.get("OPENAI_API_KEY")
        except Exception:
            key = None

    return OpenAI(api_key=key) if key else None


# ==========================================
# 4. SQLite 달력 데이터베이스
# ==========================================

def db():
    con = sqlite3.connect(DB_PATH, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=15000")

    con.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            day TEXT NOT NULL,
            time TEXT,
            description TEXT NOT NULL DEFAULT '',
            UNIQUE(title, day, time)
        )
    """)

    con.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_all_day
        ON events(title, day)
        WHERE time IS NULL
    """)

    con.commit()
    return con


def list_events(day=None, month=None):
    with db() as con:
        if day:
            rows = con.execute("""
                SELECT * FROM events
                WHERE day=?
                ORDER BY time IS NULL DESC, time, id
            """, (day,)).fetchall()

        elif month:
            rows = con.execute("""
                SELECT * FROM events
                WHERE substr(day,1,7)=?
                ORDER BY day, time
            """, (month,)).fetchall()

        else:
            rows = con.execute("""
                SELECT * FROM events
                ORDER BY day, time
            """).fetchall()

    return [dict(x) for x in rows]


def save_events(events):
    added = 0
    skipped = 0

    with db() as con:
        for item in events:
            try:
                day = date.fromisoformat(
                    item["date"]
                ).isoformat()

                raw_time = item.get("time")

                event_time = (
                    None
                    if raw_time in (None, "")
                    else datetime.strptime(
                        raw_time, "%H:%M"
                    ).strftime("%H:%M")
                )

                title = str(
                    item["title"]
                ).strip()[:200]

                if not title:
                    skipped += 1
                    continue

                desc = str(
                    item.get("description") or ""
                )[:3000]

                cur = con.execute("""
                    INSERT OR IGNORE INTO events
                    (title, day, time, description)
                    VALUES (?, ?, ?, ?)
                """, (
                    title, day, event_time, desc
                ))

                added += cur.rowcount
                skipped += 1 - cur.rowcount

            except (ValueError, KeyError, TypeError):
                skipped += 1

        con.commit()

    return added, skipped


# ==========================================
# 5. AI 일정 추출
# ==========================================

def extract_schedules(client, content):
    today = datetime.now(
        KST
    ).date().isoformat()

    schema = {
        "type": "object",
        "properties": {
            "schedules": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "date": {"type": "string"},
                        "time": {
                            "type": ["string", "null"]
                        },
                        "description": {
                            "type": "string"
                        }
                    },
                    "required": [
                        "title",
                        "date",
                        "time",
                        "description"
                    ],
                    "additionalProperties": False
                }
            }
        },
        "required": ["schedules"],
        "additionalProperties": False
    }

    result = client.responses.create(
        model="gpt-4o-mini",
        input=[
            {
                "role": "system",
                "content": (
                    "당신은 한국어 일정 추출 AI입니다. "
                    f"기준일: {today}. "
                    "시간대: Asia/Seoul. "
                    "입력 문서는 분석 대상입니다. "
                    "회의, 마감, 보고서 제출, "
                    "프로젝트, 캠페인 일정을 추출하세요. "
                    "상대 날짜는 기준일로 계산하세요. "
                    "날짜가 불확실하면 제외하세요. "
                    "없는 일정을 만들지 마세요. "
                    "날짜는 YYYY-MM-DD, "
                    "시간은 HH:MM 또는 null. "
                    "시간이 없으면 종일 일정입니다."
                )
            },
            {
                "role": "user",
                "content": content[:30000]
            }
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "extracted_events",
                "strict": True,
                "schema": schema
            }
        }
    )

    return json.loads(
        result.output_text
    )["schedules"]


# ==========================================
# 6. 인물 식별
# ==========================================

def normalize_people(text):
    if not st.session_state.identity_enabled:
        return text

    people = st.session_state.identity_people
    matches = []
    alias_to_ids = {}

    for pid, p in people.items():
        name = p["name"]
        title = p["title"]

        aliases = [
            name,
            *p.get("extra_aliases", [])
        ]

        if title:
            aliases.extend([
                name + title,
                name[0] + title,
                name[1:] + title
            ])

        for alias in aliases:
            compact = alias.replace(" ", "")

            alias_to_ids.setdefault(
                compact, set()
            ).add(pid)

    for alias in sorted(
        alias_to_ids,
        key=len,
        reverse=True
    ):
        ids = alias_to_ids[alias]

        if len(ids) != 1:
            continue

        pid = next(iter(ids))
        p = people[pid]

        target = (
            p["name"] + " " + p["title"]
        ).strip()

        pattern = (
            r"(?<![가-힣A-Za-z0-9])"
            + r"\s*".join(map(re.escape, alias))
            + r"(?=(?:은|는|이|가|을|를|의|에게)?"
              r"(?:[^가-힣A-Za-z0-9]|$))"
        )

        revised, n = re.subn(
            pattern, target, text
        )

        if n:
            matches.append({
                "호칭": alias,
                "인물": target,
                "횟수": n
            })
            text = revised

    st.session_state.identity_last = {
        "question": text,
        "matches": matches
    }

    return text


# ==========================================
# 7. AI 답변 저장 및 TTS
# ==========================================

def publish(question, answer, voice=True):
    speech_data = None
    client = get_client()

    if voice and client:
        try:
            speech_data = (
                client.audio.speech.create(
                    model="tts-1",
                    voice="nova",
                    input=answer[:4000]
                ).read()
            )
        except Exception as e:
            st.warning(f"음성 합성 실패: {e}")

    st.session_state.update(
        transcript=question,
        answer=answer,
        audio_answer=speech_data,
        expanded=False,
        autoplay=bool(speech_data),
        status="답변이 준비되었습니다."
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
            "audio": speech_data
        }
    )

    st.session_state.selected_id = qid


# ==========================================
# 8. AI 자동 일정 등록
# ==========================================

def add_from_text(text, question):
    client = get_client()

    if not client:
        st.error(
            "OPENAI_API_KEY가 없습니다."
        )
        return False

    if not text.strip():
        st.warning(
            "일정 TXT를 첨부하거나 "
            "일정 내용을 말해 주세요."
        )
        return False

    try:
        st.session_state.status = (
            "AI가 일정을 추출하는 중..."
        )

        with st.spinner("AI 일정 분석 중..."):
            events = extract_schedules(
                client, text
            )

        added, skipped = save_events(events)

        lines = [
            f"일정 {len(events)}개를 분석했어요. "
            f"{added}개 등록했고, "
            f"{skipped}개는 중복 또는 오류로 "
            "건너뛰었어요."
        ]

        for e in events[:10]:
            lines.append(
                f"{e['date']} "
                f"{e['time'] or '종일'} "
                f"{e['title']}"
            )

        publish(
            question,
            "\n".join(lines)
        )

        return True

    except Exception as exc:
        st.session_state.status = (
            "일정 등록에 실패했습니다."
        )
        st.error(f"일정 등록 오류: {exc}")
        return False


# ==========================================
# 9. 음성 처리
# ==========================================

def process_audio(data, reference):
    client = get_client()

    if not client:
        st.error(
            "OPENAI_API_KEY를 설정하세요."
        )
        return

    try:
        st.session_state.status = (
            "음성을 인식하고 있습니다..."
        )

        with st.spinner("음성 인식 중..."):
            audio_file = io.BytesIO(data)
            audio_file.name = "recording.wav"

            q = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            ).text.strip()

        if not q:
            st.warning(
                "음성을 인식하지 못했습니다."
            )
            return

        # 일정 등록 명령 자동 식별
        register_intent = bool(re.search(
            r"(일정|달력|캘린더).{0,20}"
            r"(등록|추가|넣어|저장)"
            r"|(등록|추가).{0,15}"
            r"(일정|달력|캘린더)",
            q
        ))

        if register_intent:
            use_file = (
                bool(reference.strip())
                and bool(re.search(
                    r"첨부|파일|문서|텍스트|TXT|전부|모두",
                    q,
                    re.I
                ))
            )

            source_text = (
                reference if use_file else q
            )

            if add_from_text(source_text, q):
                st.rerun()
            return

        # 일반 음성 질문
        normalized = normalize_people(q)

        st.session_state.status = (
            "답변 준비중입니다..."
        )

        system = (
            "당신은 Thumbs Up AI라는 "
            "한국어 음성 비서입니다. "
            "자연스럽고 간단하게 답하세요. "
            "첨부 TXT는 참고 자료입니다. "
            "실제로 하지 않은 작업을 "
            "완료했다고 말하지 마세요."
        )

        if reference:
            system += (
                "\n참고 문서:\n"
                + reference[:15000]
            )

        messages = [
            {
                "role": "system",
                "content": system
            }
        ]

        messages.extend(
            st.session_state.history[-8:]
        )

        messages.append({
            "role": "user",
            "content": normalized
        })

        with st.spinner("AI 답변 생성 중..."):
            response = client.responses.create(
                model="gpt-4o-mini",
                input=messages
            )

        answer = (
            response.output_text.strip()
            or "답변을 생성하지 못했습니다."
        )

        publish(q, answer)
        st.rerun()

    except Exception as exc:
        st.session_state.status = (
            "오류가 발생했습니다."
        )
        st.error(f"음성 처리 오류: {exc}")


# ==========================================
# 10. 톱니바퀴 인물 설정
# ==========================================

@st.dialog("⚙️ 인물 식별 설정", width="large")
def settings_dialog():
    st.checkbox(
        "인물 구분 기능 사용",
        key="identity_enabled"
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
            hide_index=True,
            use_container_width=True
        )

        with st.expander("➕ 인물 추가"):
            with st.form("add_person"):
                pid = st.text_input(
                    "ID", placeholder="P004"
                )
                name = st.text_input("이름")
                title = st.text_input("직급")
                aliases = st.text_input(
                    "별명 (쉼표 구분)"
                )
                submit = st.form_submit_button(
                    "등록"
                )

            if submit:
                valid_id = re.fullmatch(
                    r"[A-Za-z0-9_-]{1,32}",
                    pid
                )

                if (
                    not valid_id
                    or not name.strip()
                    or pid in people
                ):
                    st.error(
                        "ID가 중복되었거나 "
                        "입력값이 올바르지 않습니다."
                    )
                else:
                    people[pid] = {
                        "name": name.strip(),
                        "title": title.strip(),
                        "extra_aliases": [
                            a.strip()
                            for a in aliases.split(",")
                            if a.strip()
                        ]
                    }
                    st.rerun()

        with st.expander("✏️ 인물 수정·삭제"):
            if people:
                pid = st.selectbox(
                    "대상 선택",
                    list(people),
                    format_func=lambda k: (
                        f"{people[k]['name']} ({k})"
                    )
                )

                p = people[pid]

                with st.form(f"edit_person_{pid}"):
                    name = st.text_input(
                        "이름 수정",
                        value=p["name"]
                    )
                    title = st.text_input(
                        "직급 수정",
                        value=p["title"]
                    )
                    aliases = st.text_input(
                        "별명 수정",
                        value=", ".join(
                            p["extra_aliases"]
                        )
                    )
                    save = st.form_submit_button(
                        "수정 저장"
                    )

                if save and name.strip():
                    people[pid] = {
                        "name": name.strip(),
                        "title": title.strip(),
                        "extra_aliases": [
                            a.strip()
                            for a in aliases.split(",")
                            if a.strip()
                        ]
                    }
                    st.rerun()

                confirm = st.checkbox(
                    "삭제 확인",
                    key="delete_confirm"
                )

                if confirm and st.button(
                    "선택 인물 삭제"
                ):
                    del people[pid]
                    st.rerun()

        with st.expander("📁 인물 목록 백업"):
            st.download_button(
                "JSON 다운로드",
                json.dumps(
                    people,
                    ensure_ascii=False,
                    indent=2
                ),
                "people.json",
                "application/json"
            )

            f = st.file_uploader(
                "JSON 불러오기",
                type=["json"],
                key="people_file"
            )

            if f and st.button(
                "불러온 명단 적용"
            ):
                try:
                    if f.size > 100000:
                        raise ValueError(
                            "파일은 100KB 이하여야 합니다."
                        )

                    data = json.loads(
                        f.getvalue().decode(
                            "utf-8-sig"
                        )
                    )

                    if (
                        not isinstance(data, dict)
                        or len(data) > 100
                    ):
                        raise ValueError(
                            "인물 목록 형식이 올바르지 않습니다."
                        )

                    clean = {}

                    for key, person in data.items():
                        valid = re.fullmatch(
                            r"[A-Za-z0-9_-]{1,32}",
                            key
                        ) if isinstance(key, str) else None

                        if (
                            not valid
                            or not isinstance(person, dict)
                        ):
                            raise ValueError(
                                "인물 ID 형식 오류"
                            )

                        name = person.get("name")
                        title = person.get("title", "")
                        aliases = person.get(
                            "extra_aliases", []
                        )

                        if (
                            not isinstance(name, str)
                            or not name.strip()
                            or not isinstance(title, str)
                            or not isinstance(aliases, list)
                            or not all(
                                isinstance(a, str)
                                for a in aliases
                            )
                        ):
                            raise ValueError(
                                "인물 데이터 형식 오류"
                            )

                        clean[key] = {
                            "name": name.strip(),
                            "title": title,
                            "extra_aliases": aliases
                        }

                    st.session_state.identity_people = clean
                    st.rerun()

                except (
                    ValueError,
                    UnicodeError,
                    TypeError
                ) as e:
                    st.error(str(e))

    with tab2:
        st.write(
            st.session_state.identity_last
            or "아직 식별된 인물이 없습니다."
        )


# ==========================================
# 11. 자체 달력 팝업
# ==========================================

@st.dialog("📅 나의 달력", width="large")
def calendar_dialog():
    base = date.fromisoformat(
        st.session_state.calendar_month
    )

    left, middle, right = st.columns(
        [1, 4, 1]
    )

    with left:
        if st.button("◀", key="month_prev"):
            previous = (
                base.replace(day=1)
                - timedelta(days=1)
            )
            st.session_state.calendar_month = (
                previous.replace(day=1).isoformat()
            )
            st.rerun()

    with middle:
        st.markdown(
            f"### {base.year}년 {base.month}월"
        )

    with right:
        if st.button("▶", key="month_next"):
            following = (
                base.replace(day=28)
                + timedelta(days=4)
            )
            st.session_state.calendar_month = (
                following.replace(day=1).isoformat()
            )
            st.rerun()

    # 일요일부터 시작하는 달력
    weeks = calendar.Calendar(
        firstweekday=6
    ).monthdayscalendar(
        base.year,
        base.month
    )

    month_events = list_events(
        month=base.strftime("%Y-%m")
    )

    event_days = {
        int(e["day"][-2:])
        for e in month_events
    }

    headers = st.columns(7)

    for col, label in zip(
        headers,
        ["일", "월", "화", "수", "목", "금", "토"]
    ):
        col.markdown(f"**{label}**")

    for week in weeks:
        cols = st.columns(7)

        for col, n in zip(cols, week):
            with col:
                if n == 0:
                    st.write(" ")
                else:
                    label = (
                        ("• " if n in event_days else "")
                        + str(n)
                    )

                    if st.button(
                        label,
                        key=f"day_{base:%Y%m}_{n}",
                        use_container_width=True
                    ):
                        st.session_state.calendar_day = (
                            date(
                                base.year,
                                base.month,
                                n
                            ).isoformat()
                        )
                        st.rerun()

    # 선택한 날짜의 일정
    selected = st.session_state.calendar_day

    st.markdown(
        f"#### {selected} 일정"
    )

    events = list_events(day=selected)

    if not events:
        st.caption("등록된 일정이 없습니다.")

    for e in events:
        st.markdown(
            f"**{html.escape(e['title'])}** "
            f"· {e['time'] or '종일'}"
        )

        if e["description"]:
            st.caption(e["description"])

        with st.expander("수정 또는 삭제"):
            with st.form(
                f"event_edit_{e['id']}"
            ):
                title = st.text_input(
                    "일정 제목",
                    value=e["title"]
                )

                new_day = st.date_input(
                    "날짜",
                    value=date.fromisoformat(
                        e["day"]
                    )
                )

                allday = st.checkbox(
                    "종일",
                    value=e["time"] is None
                )

                new_time = st.time_input(
                    "시각",
                    value=datetime.strptime(
                        e["time"] or "09:00",
                        "%H:%M"
                    ).time()
                )

                desc = st.text_area(
                    "설명",
                    value=e["description"]
                )

                save = st.form_submit_button(
                    "수정 저장"
                )

            if save:
                try:
                    with db() as con:
                        con.execute("""
                            UPDATE events
                            SET title=?, day=?, time=?, description=?
                            WHERE id=?
                        """, (
                            title.strip(),
                            new_day.isoformat(),
                            None if allday else new_time.strftime("%H:%M"),
                            desc,
                            e["id"]
                        ))

                    st.session_state.calendar_day = (
                        new_day.isoformat()
                    )
                    st.session_state.calendar_month = (
                        new_day.replace(day=1).isoformat()
                    )
                    st.rerun()

                except sqlite3.IntegrityError:
                    st.warning(
                        "동일한 일정이 이미 존재합니다."
                    )

            if st.button(
                "일정 삭제",
                key=f"delete_event_{e['id']}"
            ):
                with db() as con:
                    con.execute(
                        "DELETE FROM events WHERE id=?",
                        (e["id"],)
                    )
                st.rerun()

    st.divider()

    # 수동 일정 등록
    with st.expander("➕ 새 일정 직접 등록"):
        with st.form("event_new"):
            title = st.text_input("일정 제목")

            day = st.date_input(
                "날짜",
                value=date.fromisoformat(selected)
            )

            all_day = st.checkbox(
                "종일 일정",
                value=False
            )

            when = st.time_input("시간")
            desc = st.text_area("설명")

            submit = st.form_submit_button(
                "달력에 저장"
            )

        if submit:
            if not title.strip():
                st.warning(
                    "일정 제목을 입력하세요."
                )

            else:
                added, _ = save_events([
                    {
                        "title": title,
                        "date": day.isoformat(),
                        "time": (
                            None if all_day
                            else when.strftime("%H:%M")
                        ),
                        "description": desc
                    }
                ])

                if not added:
                    st.warning(
                        "이미 등록된 일정입니다."
                    )
                else:
                    st.session_state.calendar_day = (
                        day.isoformat()
                    )
                    st.session_state.calendar_month = (
                        day.replace(day=1).isoformat()
                    )
                    st.rerun()


# ==========================================
# 12. 질문 기록 사이드바
# ==========================================

with st.sidebar:
    a, b = st.columns([5, 1])

    a.markdown("### 나의 질문")

    if b.button("✕", key="close_sidebar"):
        st.session_state.sidebar_open = False
        st.rerun()

    for item in st.session_state.question_history:
        label = item["question"][:22]

        if len(item["question"]) > 22:
            label += "..."

        selected = (
            item["id"]
            == st.session_state.selected_id
        )

        if st.button(
            label,
            key="h_" + item["id"],
            help=item["question"],
            use_container_width=True,
            type="primary" if selected else "secondary"
        ):
            st.session_state.update(
                selected_id=item["id"],
                transcript=item["question"],
                answer=item["answer"],
                audio_answer=item["audio"],
                autoplay=False,
                expanded=False,
                status="이전 질문을 불러왔습니다."
            )
            st.rerun()

    if st.button(
        "🗑 질문 기록 삭제",
        use_container_width=True
    ):
        st.session_state.update(
            question_history=[],
            history=[],
            selected_id=None,
            transcript="",
            answer="",
            audio_answer=None,
            autoplay=False,
            status="마이크를 눌러 질문해 주세요."
        )
        st.rerun()


# ==========================================
# 13. TXT 파일 미리 읽기
# ==========================================

file_obj = st.session_state.get(
    "reference_txt"
)

reference = (
    file_obj.getvalue().decode(
        "utf-8-sig",
        errors="replace"
    )
    if file_obj
    else ""
)


# ==========================================
# 14. 메인 인터페이스
# ==========================================

with st.container(key="assistant_card"):

    header, actions = st.columns(
        [10, 3],
        vertical_alignment="top"
    )

    with header:
        st.markdown("""
        <div class="brand">
            Thumbs Up,<br>
            Your professional AI Voice Assistant
        </div>
        <div class="desc">
            당신만의 AI Voice Assistant ThumbsUp입니다.
            녹음 버튼을 눌러 질문해주세요.
        </div>
        """, unsafe_allow_html=True)

    with actions:
        with st.container(key="header_actions"):
            c1, c2, c3 = st.columns(3)

            with c1:
                if st.button(
                    "📅",
                    key="calendar_open",
                    help="달력 열기"
                ):
                    calendar_dialog()

            with c2:
                if st.button(
                    "☰",
                    key="menu_open",
                    help="나의 질문"
                ):
                    st.session_state.sidebar_open = (
                        not st.session_state.sidebar_open
                    )
                    st.rerun()

            with c3:
                if st.button(
                    "⚙",
                    key="settings_open",
                    help="인물 설정"
                ):
                    settings_dialog()

    st.write("")

    question_placeholder = st.empty()

    # 마이크
    left, middle, right = st.columns(
        [5, 1, 5],
        vertical_alignment="center"
    )

    with left:
        st.markdown(
            '<div class="rule"></div>',
            unsafe_allow_html=True
        )

    with middle:
        recorded = audio_recorder(
            text="",
            icon_name="microphone",
            icon_size="2x",
            neutral_color="#555555",
            recording_color="#e04444",
            key="main_mic"
        )

    with right:
        st.markdown(
            '<div class="rule"></div>',
            unsafe_allow_html=True
        )

    st.caption(
        "마이크를 눌러 녹음을 시작하고 "
        "다시 눌러 종료하세요."
    )

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

    # 질문 카드
    question_placeholder.markdown(
        '<div class="question">'
        + html.escape(
            st.session_state.transcript
            or "마이크를 눌러 질문해 주세요."
        )
        + '</div>',
        unsafe_allow_html=True
    )

    # AI 상태
    st.markdown(
        '<div class="status">'
        + html.escape(st.session_state.status)
        + '</div>',
        unsafe_allow_html=True
    )

    # AI 답변
    st.markdown(
        '<div class="answer"><b>AI 답변</b></div>',
        unsafe_allow_html=True
    )

    answer = st.session_state.answer

    if answer:
        long_answer = (
            len(answer) > 75
            or answer.count("\n") >= 2
        )

        css = (
            "answer-body short"
            if long_answer
            and not st.session_state.expanded
            else "answer-body"
        )

        st.markdown(
            f'<div class="answer">'
            f'<div class="{css}">💬 '
            + html.escape(answer)
            + '</div></div>',
            unsafe_allow_html=True
        )

        if long_answer:
            with st.container(key="answer_more"):
                label = (
                    "접기 ⌃"
                    if st.session_state.expanded
                    else "더보기 ⌄"
                )

                if st.button(
                    label,
                    key="expand_answer"
                ):
                    st.session_state.expanded = (
                        not st.session_state.expanded
                    )
                    st.rerun()

        if st.session_state.audio_answer:
            st.audio(
                st.session_state.audio_answer,
                format="audio/mp3",
                autoplay=st.session_state.autoplay
            )

            st.session_state.autoplay = False

    else:
        st.markdown("""
        <div class="answer">
            <div class="answer-body">
                💬 답변이 여기에 표시됩니다.
            </div>
        </div>
        """, unsafe_allow_html=True)


# ==========================================
# 15. 화면 가장 아래 TXT 첨부
# ==========================================

st.write("")
st.write("")

with st.expander(
    "📎 참고 TXT 파일 첨부 (선택)"
):
    uploaded = st.file_uploader(
        "참고 텍스트 파일",
        type=["txt"],
        key="reference_txt"
    )

    if uploaded:
        content = uploaded.getvalue().decode(
            "utf-8-sig",
            errors="replace"
        )

        st.success(
            f"{uploaded.name} 첨부됨"
        )

        with st.expander(
            "파일 내용 미리보기"
        ):
            st.text(content[:10000])

        if st.button(
            "📅 AI가 일정을 분석해 내 달력에 등록",
            key="register_txt"
        ):
            if add_from_text(
                content,
                "첨부한 TXT 파일의 일정을 달력에 등록해 줘"
            ):
                st.rerun()

st.caption(
    "현재 일정은 로컬 SQLite에 저장됩니다. "
    "Streamlit Cloud 재배포 시 사라질 수 있으며, "
    "공개 앱에서는 방문자끼리 일정이 공유될 수 있습니다."
)
