"""
app.py
R&D 사업 제안요청서(RFP) 분석 시스템 - Flask 메인 애플리케이션

실행:
    python app.py
또는
    flask --app app run --debug
"""

import json
import os
import re
import secrets
from functools import wraps

import requests
from dotenv import load_dotenv
from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from models import (
    DEFAULT_CAPABILITIES,
    SETTING_KEY_CAPABILITIES,
    AnalysisHistory,
    Settings,
    db,
    init_db,
)

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# --------------------------------------------------------------------------
# LLM 설정 (.env 에서 주입)
# --------------------------------------------------------------------------
def env_str(name, default=""):
    """환경변수를 안전하게 읽는다.

    배포 플랫폼이나 셸에 따라 값 앞뒤에 BOM(\\ufeff)·공백·따옴표가 섞여 들어오는
    경우가 있어 모두 제거한다. (예: PowerShell 파이프로 등록한 값)
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    cleaned = raw.replace("﻿", "").strip().strip("'\"").strip()
    return cleaned if cleaned else default


def env_int(name, default):
    try:
        return int(env_str(name, str(default)))
    except (TypeError, ValueError):
        return default


LLM_PROVIDER = env_str("LLM_PROVIDER", "gemini").lower()  # gemini | anthropic

GEMINI_API_KEY = env_str("GEMINI_API_KEY")
GEMINI_MODEL = env_str("GEMINI_MODEL", "gemini-3-flash-preview")

ANTHROPIC_API_KEY = env_str("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = env_str("ANTHROPIC_MODEL", "claude-sonnet-4-5")

MAX_TEXT_CHARS = env_int("MAX_TEXT_CHARS", 180000)
HISTORY_LIMIT = env_int("HISTORY_LIMIT", 50)

# --------------------------------------------------------------------------
# 접근 제한 설정
#   APP_PASSWORD 가 비어 있으면 인증 없이 동작 (로컬 개발용)
#   공개 배포 시에는 반드시 APP_PASSWORD 와 SECRET_KEY 를 설정할 것
# --------------------------------------------------------------------------
APP_PASSWORD = env_str("APP_PASSWORD")
SECRET_KEY = env_str("SECRET_KEY") or secrets.token_hex(32)

# --------------------------------------------------------------------------
# DB 경로
#   Vercel 등 서버리스 환경은 프로젝트 디렉토리가 읽기전용이므로 /tmp 사용.
#   /tmp 는 휘발성이라 인스턴스가 재시작되면 분석 이력이 초기화된다.
# --------------------------------------------------------------------------
IS_SERVERLESS = bool(os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"))
DB_PATH = env_str("DATABASE_PATH") or (
    "/tmp/rfp_analysis.db" if IS_SERVERLESS else os.path.join(BASE_DIR, "rfp_analysis.db")
)
DATABASE_URL = env_str("DATABASE_URL")
if DATABASE_URL.startswith("postgres://"):  # SQLAlchemy 2.x 호환
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)


def create_app():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL or ("sqlite:///" + DB_PATH)
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["JSON_AS_ASCII"] = False
    app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024  # 32MB
    app.secret_key = SECRET_KEY

    db.init_app(app)
    init_db(app)
    return app


app = create_app()


# --------------------------------------------------------------------------
# 비밀번호 게이트
# --------------------------------------------------------------------------
PUBLIC_ENDPOINTS = {"login", "healthz", "static"}


@app.before_request
def require_login():
    if not APP_PASSWORD:
        return None
    if request.endpoint in PUBLIC_ENDPOINTS:
        return None
    if session.get("authed"):
        return None
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    return redirect(url_for("login", next=request.path))


@app.route("/login", methods=["GET", "POST"])
def login():
    if not APP_PASSWORD:
        return redirect(url_for("index"))

    error = None
    if request.method == "POST":
        if secrets.compare_digest(request.form.get("password", ""), APP_PASSWORD):
            session["authed"] = True
            session.permanent = True
            target = request.args.get("next") or url_for("index")
            # 외부 사이트로의 오픈 리다이렉트 방지
            if not target.startswith("/") or target.startswith("//") or "\\" in target:
                target = url_for("index")
            return redirect(target)
        error = "비밀번호가 올바르지 않습니다."

    return render_template("login.html", error=error), (401 if error else 200)


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ==========================================================================
# 분석 결과 JSON 스키마 (Gemini responseSchema / 프롬프트 공용)
# ==========================================================================
def get_json_schema():
    return {
        "type": "OBJECT",
        "properties": {
            "projectMeta": {
                "type": "OBJECT",
                "properties": {
                    "title": {"type": "STRING"},
                    "dDay": {"type": "STRING", "description": "YYYY-MM-DD 형식"},
                    "recommendation": {
                        "type": "OBJECT",
                        "properties": {
                            "status": {"type": "STRING"},
                            "class": {
                                "type": "STRING",
                                "description": "bg-gray-800 text-white 또는 bg-gray-500 text-white",
                            },
                        },
                    },
                    "agency": {"type": "STRING"},
                    "noticeNumber": {"type": "STRING"},
                    "duration": {"type": "STRING"},
                    "budget": {"type": "STRING"},
                    "fundingRatio": {"type": "STRING"},
                    "eligibility": {"type": "STRING"},
                    "dates": {"type": "STRING"},
                },
            },
            "goals": {
                "type": "OBJECT",
                "properties": {
                    "finalGoal": {"type": "STRING"},
                    "annualGoals": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "year": {"type": "STRING"},
                                "goal": {"type": "STRING"},
                            },
                        },
                    },
                    "policyBackground": {"type": "STRING"},
                    "keywords": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "kpis": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "name": {"type": "STRING"},
                                "target": {"type": "STRING"},
                                "method": {"type": "STRING"},
                                "time": {"type": "STRING"},
                                "source": {"type": "STRING"},
                            },
                        },
                    },
                },
            },
            "execution": {
                "type": "OBJECT",
                "properties": {
                    "wbs": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "task": {"type": "STRING"},
                                "desc": {"type": "STRING"},
                                "type": {
                                    "type": "STRING",
                                    "description": "필수 또는 선택",
                                },
                                "source": {"type": "STRING"},
                            },
                        },
                    },
                    "deliverables": {"type": "STRING"},
                    "schedule": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "task": {"type": "STRING"},
                                "y1": {"type": "NUMBER"},
                                "y2": {"type": "NUMBER"},
                                "y3": {"type": "NUMBER"},
                            },
                        },
                    },
                },
            },
            "ttaPerspective": {
                "type": "OBJECT",
                "properties": {
                    "role": {"type": "STRING"},
                    "roleReason": {"type": "STRING"},
                    "tasksAndBudget": {"type": "STRING"},
                    "mapping": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "req": {"type": "STRING"},
                                "tta": {"type": "STRING"},
                                "match": {"type": "STRING", "description": "상, 중, 하"},
                                "reason": {"type": "STRING"},
                            },
                        },
                    },
                    "gaps": {"type": "STRING"},
                    "risks": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "type": {"type": "STRING"},
                                "level": {"type": "STRING", "description": "상, 중, 하"},
                                "desc": {"type": "STRING"},
                            },
                        },
                    },
                },
            },
            "judgment": {
                "type": "OBJECT",
                "properties": {
                    "scores": {
                        "type": "OBJECT",
                        "properties": {
                            "competency": {"type": "NUMBER"},
                            "strategy": {"type": "NUMBER"},
                            "resources": {"type": "NUMBER"},
                            "competitiveness": {"type": "NUMBER"},
                            "riskMgt": {"type": "NUMBER"},
                        },
                    },
                    "totalScore": {"type": "NUMBER"},
                    "recommendationDesc": {"type": "STRING"},
                    "points": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "todo": {"type": "ARRAY", "items": {"type": "STRING"}},
                },
            },
        },
    }


def build_prompt(text, capabilities):
    return f"""당신은 국가 R&D 사업 기획·평가 전문가이자 아래 명시된 연구소의 전략 담당자입니다.
업로드된 R&D 사업 제안요청서(RFP)를 분석하여 정해진 JSON 형식으로 응답하세요.

[우리 연구소 역량]
{capabilities}

[지시사항]
1. 원문에 기반하여 작성하되, 금액/기간/지표는 수치를 정확히 기재할 것.
2. 각 항목의 끝에 출처(예: [3페이지])를 명시할 것. 원문에 없으면 "RFP 미기재"로 작성.
   단, projectMeta.title, projectMeta.dDay, goals.keywords 에는 출처를 붙이지 말고 값만 기재할 것.
3. WBS(세부과제)는 개발, 실증, 표준화, 인증 등 3~5개로 구조화할 것. 간트 차트(schedule) 값은 y1, y2, y3 연차별 투입 비중(0~100)을 입력할 것.
4. TTA 관점 분석(4,5섹션)은 위 '우리 연구소 역량'을 바탕으로 객관적이고 전략적인 [분석의견]을 작성할 것. (이해상충 등 리스크 필수 포함)
5. judgment.scores 의 5개 항목과 totalScore 는 0~100 사이 정수로 산정할 것.

[RFP 텍스트]
{text}
"""


# ==========================================================================
# LLM 호출
# ==========================================================================
class LLMError(RuntimeError):
    pass


def _extract_json(raw):
    """모델 응답 문자열에서 JSON 객체만 뽑아 파싱"""
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except ValueError:
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end <= start:
            raise LLMError("모델 응답에서 JSON을 찾을 수 없습니다.")
        return json.loads(raw[start : end + 1])


def call_gemini(prompt):
    if not GEMINI_API_KEY:
        raise LLMError(
            "GEMINI_API_KEY 가 설정되지 않았습니다. .env 파일을 확인해 주세요."
        )

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": get_json_schema(),
        },
    }
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY,
    }

    last_err = None
    for attempt in range(3):
        try:
            res = requests.post(url, headers=headers, json=payload, timeout=180)
            if res.status_code >= 400:
                raise LLMError(f"Gemini HTTP {res.status_code}: {res.text[:500]}")
            data = res.json()
            candidates = data.get("candidates") or []
            if not candidates:
                raise LLMError(f"Gemini 응답이 비어있습니다: {str(data)[:300]}")
            parts = candidates[0].get("content", {}).get("parts") or []
            text = "".join(p.get("text", "") for p in parts)
            return _extract_json(text)
        except Exception as e:  # noqa: BLE001
            last_err = e
    raise LLMError(str(last_err))


def call_anthropic(prompt):
    if not ANTHROPIC_API_KEY:
        raise LLMError(
            "ANTHROPIC_API_KEY 가 설정되지 않았습니다. .env 파일을 확인해 주세요."
        )

    schema_text = json.dumps(get_json_schema(), ensure_ascii=False, indent=2)
    payload = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": 16000,
        "system": (
            "너는 국가 R&D 사업 분석 전문가다. 반드시 아래 스키마를 따르는 "
            "단일 JSON 객체만 출력하고, 설명 문장이나 코드블록 표기는 절대 쓰지 마라.\n\n"
            + schema_text
        ),
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {
        "content-type": "application/json",
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
    }

    last_err = None
    for attempt in range(3):
        try:
            res = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload,
                timeout=240,
            )
            if res.status_code >= 400:
                raise LLMError(f"Anthropic HTTP {res.status_code}: {res.text[:500]}")
            data = res.json()
            blocks = data.get("content") or []
            text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
            return _extract_json(text)
        except Exception as e:  # noqa: BLE001
            last_err = e
    raise LLMError(str(last_err))


def run_llm(prompt):
    if LLM_PROVIDER == "anthropic":
        return call_anthropic(prompt)
    return call_gemini(prompt)


# ==========================================================================
# 라우팅
# ==========================================================================
@app.get("/")
def index():
    history = (
        AnalysisHistory.query.order_by(AnalysisHistory.created_at.desc())
        .limit(HISTORY_LIMIT)
        .all()
    )
    capabilities = Settings.get(SETTING_KEY_CAPABILITIES, DEFAULT_CAPABILITIES)
    return render_template(
        "index.html",
        history=[h.to_summary() for h in history],
        capabilities=capabilities,
        llm_provider=LLM_PROVIDER,
        llm_model=ANTHROPIC_MODEL if LLM_PROVIDER == "anthropic" else GEMINI_MODEL,
        auth_enabled=bool(APP_PASSWORD),
        serverless=IS_SERVERLESS,
    )


@app.post("/api/analyze")
def api_analyze():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"ok": False, "error": "요청 형식이 올바르지 않습니다."}), 400

    text = body.get("text") or ""
    filename = body.get("filename") or "직접 입력 문서"
    if not isinstance(text, str) or not isinstance(filename, str):
        return (
            jsonify({"ok": False, "error": "text·filename 은 문자열이어야 합니다."}),
            400,
        )
    text = text.strip()
    filename = filename.strip() or "직접 입력 문서"

    if len(text) < 50:
        return (
            jsonify({"ok": False, "error": "분석할 텍스트가 부족합니다. (최소 50자)"}),
            400,
        )

    truncated = len(text) > MAX_TEXT_CHARS
    prompt = build_prompt(text[:MAX_TEXT_CHARS], Settings.get(
        SETTING_KEY_CAPABILITIES, DEFAULT_CAPABILITIES
    ))

    try:
        result = run_llm(prompt)
    except LLMError as e:
        app.logger.exception("LLM 호출 실패")
        return jsonify({"ok": False, "error": str(e)}), 502
    except Exception as e:  # noqa: BLE001
        app.logger.exception("분석 중 예외")
        return jsonify({"ok": False, "error": f"분석 중 오류: {e}"}), 500

    title = (result.get("projectMeta") or {}).get("title") or "(사업명 미기재)"

    entry = AnalysisHistory(
        filename=filename,
        project_title=title[:500],
        raw_text=text,
    )
    entry.result = result
    db.session.add(entry)
    db.session.commit()

    # 최근 N건만 보관
    stale = (
        AnalysisHistory.query.order_by(AnalysisHistory.created_at.desc())
        .offset(HISTORY_LIMIT)
        .all()
    )
    if stale:
        for row in stale:
            db.session.delete(row)
        db.session.commit()

    history = (
        AnalysisHistory.query.order_by(AnalysisHistory.created_at.desc())
        .limit(HISTORY_LIMIT)
        .all()
    )
    return jsonify(
        {
            "ok": True,
            "id": entry.id,
            "truncated": truncated,
            "data": result,
            "history": [h.to_summary() for h in history],
        }
    )


@app.get("/api/history")
def api_history_list():
    rows = (
        AnalysisHistory.query.order_by(AnalysisHistory.created_at.desc())
        .limit(HISTORY_LIMIT)
        .all()
    )
    return jsonify({"ok": True, "history": [r.to_summary() for r in rows]})


@app.get("/api/history/<int:entry_id>")
def api_history_detail(entry_id):
    entry = db.session.get(AnalysisHistory, entry_id)
    if entry is None:
        return jsonify({"ok": False, "error": "해당 분석 이력이 없습니다."}), 404
    return jsonify({"ok": True, **entry.to_dict()})


@app.delete("/api/history/<int:entry_id>")
def api_history_delete(entry_id):
    entry = db.session.get(AnalysisHistory, entry_id)
    if entry is None:
        return jsonify({"ok": False, "error": "해당 분석 이력이 없습니다."}), 404
    db.session.delete(entry)
    db.session.commit()
    return jsonify({"ok": True})


@app.get("/api/settings")
def api_settings_get():
    return jsonify(
        {
            "ok": True,
            "capabilities": Settings.get(
                SETTING_KEY_CAPABILITIES, DEFAULT_CAPABILITIES
            ),
        }
    )


@app.post("/api/settings")
def api_settings_post():
    body = request.get_json(silent=True) or {}
    value = (body.get("capabilities") or "").strip()
    if not value:
        return jsonify({"ok": False, "error": "역량 내용이 비어 있습니다."}), 400
    Settings.set(SETTING_KEY_CAPABILITIES, value)
    return jsonify({"ok": True, "capabilities": value})


@app.get("/healthz")
def healthz():
    return jsonify(
        {
            "ok": True,
            "provider": LLM_PROVIDER,
            "model": ANTHROPIC_MODEL if LLM_PROVIDER == "anthropic" else GEMINI_MODEL,
            "key_configured": bool(
                ANTHROPIC_API_KEY if LLM_PROVIDER == "anthropic" else GEMINI_API_KEY
            ),
            "auth_enabled": bool(APP_PASSWORD),
            "serverless": IS_SERVERLESS,
            "history_count": AnalysisHistory.query.count(),
        }
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
