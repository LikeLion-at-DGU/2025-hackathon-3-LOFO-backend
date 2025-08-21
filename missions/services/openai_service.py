# missions/services/openai_service.py
from openai import OpenAI
import os, json, re, base64

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

PHASE_TITLES = [
    "콘셉트 및 스타일 연구",
    "정보 구조 및 콘텐츠 구성",
    "최종 결과물 제작",
]

def _json_only(s: str) -> dict:
    s = s.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?", "", s).strip()
        s = re.sub(r"```$", "", s).strip()
    if not (s.startswith("{") and s.endswith("}")):
        m = re.search(r"\{.*\}\s*$", s, re.S)
        if m:
            s = m.group(0)
    return json.loads(s)

def _as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        # 원소를 모두 문자열로
        return [str(v).strip() for v in value if str(v).strip()]
    # 문자열이면 줄바꿈/•/- 기준으로 분해
    txt = str(value)
    parts = re.split(r"\n|•|- |\u2022", txt)
    return [p.strip() for p in parts if p and p.strip()]

def _normalize_plan(data: dict) -> dict:
    steps = data.get("steps") or data.get("plan") or data.get("phases") or data.get("stages")
    if isinstance(steps, dict):
        steps = [steps.get(str(i)) for i in (1, 2, 3)]
    if not isinstance(steps, list):
        raise ValueError("steps가 리스트가 아님")

    fixed = []
    for idx in range(3):
        raw = steps[idx] if idx < len(steps) else {}
        raw = raw if isinstance(raw, dict) else {}
        title = PHASE_TITLES[idx]  # 제목 고정
        desc  = raw.get("description") or raw.get("desc") or raw.get("details") or ""
        ref   = raw.get("reference") or raw.get("ref") or raw.get("resources") or []
        due   = raw.get("due") or raw.get("due_date") or raw.get("deadline") or None

        ref_list = _as_list(ref)

        # 업로드/형식 지침이 없다면 기본 권장 한두 줄 보강
        if not any("업로드" in r for r in ref_list):
            ref_list.append("업로드: 단계 산출물을 파일로 첨부")
        if not any(("형식" in r) or ("규격" in r) for r in ref_list):
            # 단계별 기본 권장 형식
            if idx == 0:
                ref_list.append("형식/규격: 무드보드 PDF(A4, 150dpi) 또는 PNG 10~15장")
            elif idx == 1:
                ref_list.append("형식/규격: 카피 + 와이어프레임 PDF(A4) 또는 Figma 링크")
            else:
                ref_list.append("형식/규격: 최종 패키지(ZIP) — PNG/JPG(1080x1080), PDF(출력용), 소스파일")

        fixed.append({
            "step": idx + 1,
            "title": title,
            "description": str(desc).strip(),
            "reference": ref_list,   # ← list[str] 로 유지
            "due": str(due).strip() if due else None,
        })

    return {"steps": fixed}

def build_plan(
    goal: str,
    deadline_date_str: str,
    request_title: str | None = None,
    request_desc: str | None = None,
) -> dict:
    """
    goal + request 정보 + deadline 기반 3단계 계획(JSON)
    반환: {"steps":[{step,title,description,reference(list[str]),due}, x3]}
    """
    system = (
        "말투: 존댓말은 쓰되, 격식이 아니라 부드럽고 편안한 대화체"
        "형식: 강요 없이 제안형/선택형 표현 사용"
        "지양: 반말·딱딱한 설명·명령조·평가적인 어투"
        "너는 실제 디자인/콘텐츠 제작 프로젝트의 멘토다. "
        "반드시 JSON만 출력해라."
    )

    # 프롬프트: 조건 고정 + 맥락(goal + request)
    user = f"""
[역할]
너는 실제 디자인·콘텐츠 제작 프로젝트의 멘토입니다.

[입력 맥락]
- goal: {goal}
- request_title: {request_title or ""}
- request_desc: {request_desc or ""}
- 최종 마감일(deadline): {deadline_date_str}

[조건]
1) 3단계 구조(제목 고정):
   1단계: 콘셉트 및 스타일 연구 (타겟, 브랜드, 톤앤매너, 비주얼 방향 확립)
   2단계: 정보 구조 및 콘텐츠 구성 (카피라이팅, 페이지 흐름, 와이어프레임)
   3단계: 최종 결과물 제작 (완성본 디자인, 납품용 패키지)

2) 각 단계 필수 필드:
   - title: 카드 상단에 들어갈 포괄적 미션 (위 제목으로 고정)
   - description: 그 단계에서 수행할 구체 작업의 '한 줄 요약'(작업 조건·분량 포함)
   - reference: 세부 지침의 목록(list). 모든 단계는 업로드 가능한 결과물이 반드시 존재해야 하며,
                파일 형식/규격 추천을 반드시 포함(예: '형식/규격: ...').
   - due: 실제 날짜 문자열(YYYY-MM-DD). 최종 마감일을 기준으로 단계 난이도 고려해 일정 배분.
          (단순 균등 분배 금지. 2단계를 더 길게 두는 편을 우선 고려)

3) 각 단계는 독립적으로 실무 역량을 키울 수 있도록 설계하고,
   산출물은 즉시 업로드 가능하며 AI 피드백을 받을 수 있어야 한다.

[출력 형식(JSON만)]
{{
  "steps": [
    {{
      "step": 1,
      "title": "콘셉트 및 스타일 연구",
      "description": "...(한 줄 요약, 조건/분량 포함)",
      "reference": ["...", "...", "업로드: ...", "형식/규격: ..."],
      "due": "YYYY-MM-DD"
    }},
    {{
      "step": 2,
      "title": "정보 구조 및 콘텐츠 구성",
      "description": "...",
      "reference": ["...", "...", "업로드: ...", "형식/규격: ..."],
      "due": "YYYY-MM-DD"
    }},
    {{
      "step": 3,
      "title": "최종 결과물 제작",
      "description": "...",
      "reference": ["...", "...", "업로드: ...", "형식/규격: ..."],
      "due": "YYYY-MM-DD"
    }}
  ]
}}
"""

    # 1차 호출 (JSON 강제)
    resp = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.3,  # 드리프트 줄임
        max_tokens=900,
        response_format={"type": "json_object"},
    )

    raw = resp.choices[0].message.content
    try:
        data = json.loads(raw)
    except Exception:
        data = _json_only(raw)

    try:
        return _normalize_plan(data)
    except Exception:
        # 2차 시도(더 엄격)
        resp2 = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user + "\n반드시 위 JSON 스키마를 정확히 따르고, reference는 문자열 목록(list)로만 출력."},
            ],
            temperature=0.0,
            max_tokens=900,
            response_format={"type": "json_object"},
        )
        raw2 = resp2.choices[0].message.content
        try:
            data2 = json.loads(raw2)
        except Exception:
            data2 = _json_only(raw2)
        return _normalize_plan(data2)


def _img_to_data_url(uploaded_file) -> str | None:
    name = (uploaded_file.name or "").lower()
    ct   = getattr(uploaded_file, "content_type", "") or ""
    if not (name.endswith((".png", ".jpg", ".jpeg")) or ct.startswith("image/")):
        return None
    if getattr(uploaded_file, "size", 0) > 6 * 1024 * 1024:  # 6MB 초과는 스킵
        return None
    raw = uploaded_file.read()
    uploaded_file.seek(0)  # 혹시 재사용할 수 있으니 포인터 복구
    b64 = base64.b64encode(raw).decode("utf-8")
    mime = ct or ("image/png" if name.endswith(".png") else "image/jpeg")
    return f"data:{mime};base64,{b64}"


def build_step_feedback(
    goal: str,
    step_no: int,
    step_title: str,
    note: str = "",
    image_data_urls: list[str] | None = None,   # data:image/...;base64,....
    file_names: list[str] | None = None,        # 업로드 파일명 목록(표시용)
    extra_texts: list[str] | None = None,       # PDF에서 뽑은 텍스트 등
) -> str:
    image_data_urls = image_data_urls or []
    file_names      = file_names or []
    extra_texts     = extra_texts or []

    system = (
        "당신은 디자인·콘텐츠 제작 프로젝트의 멘토입니다. "
        "친근한 존댓말로, 실무에 바로 적용 가능한 피드백을 주세요. "
        "항상 구체적인 개선 포인트와 다음 액션을 함께 제시하세요."
    )

    content = [
        {"type": "text", "text":
            f"[목표]\n{goal}\n\n"
            f"[현재 단계]\n{step_no}단계: {step_title}\n\n"
            f"[메모/요청]\n{note or '메모 없음'}\n\n"
            "[응답 형식]\n"
            "- 총평 (한 줄)\n- 잘한 점 (목록)\n- 개선 포인트 (목록)\n"
            "- 다음 액션 (목록, 바로 실행 가능한 수준)\n- 업로드 체크리스트 (파일 규격/형식 포함)\n"
        }
    ]

    if file_names:
        content.append({"type": "text", "text": "[제출 파일]\n" + ", ".join(file_names)})

    for url in image_data_urls:
        content.append({"type": "image_url", "image_url": {"url": url}})

    for t in extra_texts:
        # 너무 길면 잘라서 전달
        snippet = (t[:4000] + "…") if len(t) > 4000 else t
        content.append({"type": "text", "text": f"[파일 내용 발췌]\n{snippet}"})

    resp = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ],
        temperature=0.35,
        max_tokens=800,
    )
    return resp.choices[0].message.content.strip()