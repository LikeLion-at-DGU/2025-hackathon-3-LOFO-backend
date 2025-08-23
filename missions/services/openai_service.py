from openai import OpenAI
import os, json, re, base64

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

#H JSON 형식만 추출
def _json_only(s: str):
     s = s.strip() # ```json 또는 ``` 로 감싸진 경우 제거
     if s.startswith("```"):
          s = re.sub(r"^```(?:json)?", "", s).strip()
          s = re.sub(r"```$", "", s).strip()
     try:
          return json.loads(s)
     except Exception: # 실패 시, 문자열 끝 기준으로 배열 또는 객체 패턴 재검색 후 재파싱
          m = re.search(r"\[.*\]\s*$", s, re.S) or re.search(r"\{.*\}\s*$", s, re.S)
          if m:
               return json.loads(m.group(0))
          raise # 끝까지 안되면 상위에서 처리


#모델 응답을 내부 DB 저장 스키마로 변환
''' 
    입력: {"steps":[{mission_title, reference, due} *3]} 또는 [{mission_title, reference, due} *3]
    출력: {"steps":[{step,title,description,reference,due} *3]}
'''
def _normalize_plan_minimal(data) -> dict:
     # steps 수집
     if isinstance(data, dict):
          steps = data.get("steps")
          if steps is None and any(k in data for k in ("1","2","3",1,2,3)):
               steps = [data.get(str(i)) or data.get(i) or {} for i in (1,2,3)]
     else:
          steps = data

     if not isinstance(steps, list):
          steps = []

     # 3개로 맞춤
     steps = [s or {} for s in steps[:3]]
     while len(steps) < 3:
          steps.append({})

     fixed = []
     for i, raw in enumerate(steps, start=1):
          raw = raw or {}
          # title: mission_title 또는 title 둘 다 허용
          title = (
               str(raw.get("mission_title") or raw.get("title") or "").strip()
               or f"단계 {i}"
          )
          # description: 비면 기본 안내문
          desc = (
               str(raw.get("description") or "").strip()
               or "이 단계의 산출물을 한 페이지로 정리해 업로드하세요."
          )

          # reference: list/str 모두 허용 + 불릿 클린업 + 최소 1줄 보장
          ref = raw.get("reference", "")
          if isinstance(ref, list):
               ref = "\n".join(
                    f"- {str(x).strip().lstrip('-').strip()}"
                    for x in ref if str(x).strip()
               )
          ref = str(ref).strip()
          # 불릿만 남은 라인 제거
          ref = "\n".join(ln for ln in (ln.strip() for ln in ref.splitlines()) if ln and ln != "-")
          if not ref:
               ref = "- 형식/규격: PNG 10장 또는 TXT 1개"

          due = str(raw.get("due", "")).strip() or None

          fixed.append({
               "step": i,
               "title": title,
               "description": desc,
               "reference": ref,
               "due": due,
          })
     return {"steps": fixed}

def build_plan(
     goal: str,
     deadline_date_str: str,
     request_title: str | None = None,
     request_desc: str | None = None,
     store_name: str | None = None,
     category: str | None = None,
     ) -> dict:
     system = "JSON만 출력. 설명·예시 금지."
     user = f"""
아래 맥락을 반영해 이 목표 달성을 위한 3단계 계획을 생성하라.
출력은 JSON 배열 3개 원소이며, 각 원소는 mission_title, description, reference, due만 가진다.

[가게/요청 맥락]
- 가게명: {store_name or ""}
- 요청 카테고리: {category or ""}
- 요청 제목: {request_title or ""}
- 요청 설명: {(request_desc or "")[:160]}

[사용자 목표]
- {goal}

[마감일]
- 최종 마감: {deadline_date_str} (3단계는 반드시 이 날짜 이내)
""".strip()

     resp = client.chat.completions.create(
          model="gpt-4o-mini",
          messages=[
               {"role": "system", "content": system},
               {"role": "user", "content": user},
          ],
          temperature=0.0,
          max_tokens=380,  # ← 넉넉히
          response_format={
               "type": "json_schema",
               "json_schema": {
                    "name": "plan",
                    "schema": {
                         "type": "object",
                         "properties": {
                         "steps": {
                              "type": "array",
                              "minItems": 3,
                              "maxItems": 3,
                              "items": {
                                   "type": "object",
                                   "properties": {
                                        "mission_title": {"type": "string"},
                                        "description": {"type": "string"},
                                        "reference": {"type": "string"},
                                        "due": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$"}
                                   },
                                   "required": ["mission_title", "description", "reference", "due"],
                                   "additionalProperties": False
                              }
                         }
                         },
                         "required": ["steps"],
                         "additionalProperties": False
                    }
               }
          }
     )

     raw = resp.choices[0].message.content
     try:
          data = json.loads(raw)
     except Exception:
          # 혹시 라이브러리/모델 변경 등으로 dict로 오는 경우도 방어
          data = raw if isinstance(raw, dict) else _json_only(raw)
     return _normalize_plan_minimal(data)



# ---------- 이미지 인코딩 ----------
def _img_to_data_url(uploaded_file) -> str | None:
     name = (uploaded_file.name or "").lower()
     ct   = getattr(uploaded_file, "content_type", "") or mimetypes.guess_type(name)[0] or ""
     if not (name.endswith((".png", ".jpg", ".jpeg")) or (ct and ct.startswith("image/"))):
          return None
     # (선택) 용량 제한이 필요하면 여기서 체크
     # if getattr(uploaded_file, "size", 0) > 6 * 1024 * 1024:
     #     return None
     raw = uploaded_file.read()
     uploaded_file.seek(0)
     b64 = base64.b64encode(raw).decode("utf-8")
     mime = ct or ("image/png" if name.endswith(".png") else "image/jpeg")
     return f"data:{mime};base64,{b64}"



# missionstep 피드백 
def build_step_feedback(
     goal: str,
     step_no: int,
     step_title: str,
     note: str = "",
     image_data_urls: list[str] | None = None,
     file_names: list[str] | None = None,
     extra_texts: list[str] | None = None,
     ) -> tuple[str, dict]:
     """
     return: (feedback_text, usage_info)
     usage_info = {"prompt_tokens": int, "completion_tokens": int, "total_tokens": int}
     """
     image_data_urls = image_data_urls or []
     file_names      = file_names or []
     extra_texts     = extra_texts or []

     # ✅ 톤앤매너 지침 반영
     system = "너는 청년 사용자가 만든 콘텐츠에 대해 피드백을 주는 AI 코치다. JSON이 아니라 순수 텍스트만 출력해라."

     user_prompt = f"""
     [목표]
     {goal}

     [단계]
     {step_no}단계: {step_title}

     [메모]
     {note or "없음"}

     [톤앤매너 지침]
     - 항상 잘한 점을 먼저 말한다.
     - 개선 아이디어는 1~2개만, 추상적이 아니라 바로 적용 가능한 **구체적 팁**으로 제시한다.
     - 다음 단계는 단순 지시가 아니라, **다음 미션과 연결되는 사전 연습(1.5단계/2.5단계)**처럼 짧게 제시한다.
     - 마무리 멘트는 짧고 긍정적으로, 성취감과 반복 참여 의욕을 주도록 한다.

     [출력 구조]
     잘한 점: [칭찬, 1~2문장]

     개선 아이디어:
     - [구체적 보완 팁1]
     - [구체적 보완 팁2] (선택적)

     다음 단계: [다음 미션과 연결되는 1.5단계/2.5단계 액션 제안, 한 문장]

     마무리 멘트: [짧고 긍정적인 동기부여 멘트]
     """.strip()

     content = [{"type": "text", "text": user_prompt}]

     if file_names:
          content.append({"type": "text", "text": "[파일명]\n" + ", ".join(file_names)})
     for url in image_data_urls:
          content.append({"type": "image_url", "image_url": {"url": url}})
     for t in extra_texts:
          snippet = (t[:1000] + "…") if len(t) > 1000 else t
          content.append({"type": "text", "text": f"[텍스트 발췌]\n{snippet}"})

     resp = client.chat.completions.create(
          model="gpt-4o-mini",
          messages=[
               {"role": "system", "content": system},
               {"role": "user", "content": content},
          ],
          temperature=0.4,  # 살짝 다양성 줘도 자연스러운 표현 가능
          max_tokens=320,
     )

     feedback_text = resp.choices[0].message.content.strip()
     usage_info = {
          "prompt_tokens": getattr(resp.usage, "prompt_tokens", None),
          "completion_tokens": getattr(resp.usage, "completion_tokens", None),
          "total_tokens": getattr(resp.usage, "total_tokens", None),
     }
     return feedback_text, usage_info
