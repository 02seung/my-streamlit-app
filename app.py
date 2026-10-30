

import os
import streamlit as st
from openai import OpenAI

# OpenAI 클라이언트 생성
client = OpenAI()

# 페이지 설정
st.set_page_config(page_title=" 다국어 번역기 ", page_icon=" 🌐")
st.title("  🌐번역기  ")
st.write("  번역할 문장을 써주세요  ")

# 사용자 입력(텍스트)
korean_text = st.text_area(
    "번역할 한글 문장을 입력하세요.",
    height=150,
    placeholder="예: 인공지능은 우리의 일상과 업무 방식을 빠르게 변화시키고 있습니다."
)
language = st.selectbox("언어선택",["영어", "일본어", "중국어", "불어", "독일어"], index=0)

# 번역 버튼
if st.button("  번역하기  "):

    if not korean_text.strip():
        st.warning("  한글을 입력해주세요   ")
    else:
        with st.spinner("번역 중입니다..."):

            # 시스템 역할
            sys_role = """
            당신은 여러 언어를 모두 잘 하는 전문 번역가 입니다. 원하는 언어로 자연스럽고 정확하게 번역하세요
            원문의 의미를 훼손 하지 말고 유지하세요
            """

            # 프롬프트 구성
            prompt = f"""
            다음 문장을 {language}로 번역하세요.
            ---
            "{korean_text}"
            """

            # GPT 호출
            response = client.responses.create(
                model="gpt-4o-mini",
                input=[
                    {"role": "system", "content": sys_role  },
                    {"role": "user", "content": prompt   }
                ]
            )

            # 결과 출력
            translated_text = response.output_text

            st.subheader("✅ 번역 완료")
            st.success(   translated_text   )
