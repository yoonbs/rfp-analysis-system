# R&D 사업 제안요청서(RFP) 분석 시스템

**배포 주소: https://rfp-analysis-system.vercel.app** (접속 비밀번호 필요)

기존 단일 HTML 아티팩트를 **Python Flask + SQLite** 기반 웹 애플리케이션으로 재구성한 프로젝트입니다.
포멀한 공공기관 보고서 스타일(무채색·네이비톤·직각 모서리) UI를 그대로 유지하면서,
분석 이력과 연구소 역량 설정값을 서버 DB에 영구 저장합니다.

---

## 1. 디렉토리 구조

```
1st_webapp/
├── app.py                 # Flask 메인 애플리케이션 및 라우팅, LLM 호출
├── models.py              # SQLite 데이터베이스 모델 (AnalysisHistory, Settings)
├── requirements.txt       # 의존성 패키지 목록
├── .env.example           # 환경변수 템플릿 (복사해서 .env 생성)
├── templates/
│   ├── base.html          # 공통 레이아웃 (사이드바, 모달)
│   └── index.html         # 업로드 화면 + 결과 대시보드 (5개 섹션)
└── static/
    ├── css/style.css      # 커스텀 CSS (공공기관 포멀 스타일 + 인쇄 스타일)
    └── js/main.js         # 드래그앤드롭, PDF/HWPX 추출, 차트, API 연동
```

---

## 2. 설치 및 실행

### 2-1. 가상환경 생성 및 패키지 설치

**Windows (PowerShell / cmd)**

```bash
cd %USERPROFILE%\Desktop\1st_webapp
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

**macOS / Linux**

```bash
cd ~/Desktop/1st_webapp
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2-2. 환경변수(.env) 설정

`.env.example` 을 복사해 `.env` 를 만들고 API 키를 입력합니다.

```bash
copy .env.example .env
```

```ini
LLM_PROVIDER=gemini
GEMINI_API_KEY=여기에_발급받은_키를_입력
GEMINI_MODEL=gemini-3-flash-preview
```

Claude API를 쓰려면 `LLM_PROVIDER=anthropic` 으로 바꾸고 `ANTHROPIC_API_KEY` 를 채웁니다.

> API 키가 없어도 앱은 실행됩니다. 다만 `AI 분석 시작` 버튼을 누르면 키 미설정 안내가 표시됩니다.

### 2-3. 데이터베이스 초기화

별도 명령이 필요 없습니다. **앱을 처음 실행하면** `models.init_db()` 가
`rfp_analysis.db` 파일을 만들고 테이블과 기본 역량 설정값을 자동으로 생성합니다.

DB를 완전히 초기화하려면 파일을 지우고 다시 실행하면 됩니다.

```bash
del rfp_analysis.db
```

수동으로 테이블만 만들려면:

```bash
python -c "from app import app; from models import init_db; init_db(app); print('DB initialized')"
```

### 2-4. 앱 실행

```bash
python app.py
```

또는

```bash
flask --app app run --debug --port 5000
```

브라우저에서 **http://127.0.0.1:5000** 접속.

상태 확인용 엔드포인트: **http://127.0.0.1:5000/healthz**

---

## 3. 데이터베이스 모델

### `analysis_history`

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `id` | Integer (PK) | 분석 이력 ID |
| `filename` | String(255) | 업로드한 파일명 |
| `project_title` | String(500) | 분석된 사업명 |
| `raw_text` | Text | 추출된 RFP 원문 텍스트 |
| `result_json` | Text | LLM 분석결과 JSON 문자열 |
| `created_at` | DateTime | 분석일시 |

### `settings`

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `key` | String(100) (PK) | 설정 키 (`tta_capabilities`) |
| `value` | Text | 설정값 (연구소 역량 텍스트) |
| `updated_at` | DateTime | 최종 수정일시 |

---

## 4. API 명세

| 메서드 | 경로 | 설명 |
|---|---|---|
| `GET` | `/` | 메인 화면. DB의 히스토리 목록·역량 설정값을 템플릿에 전달 |
| `POST` | `/api/analyze` | `{text, filename}` 수신 → LLM 분석 → DB 저장 → `{ok, id, data, history}` 반환 |
| `GET` | `/api/history` | 히스토리 목록(경량) 조회 |
| `GET` | `/api/history/<id>` | 특정 이력의 원문 + 분석결과 JSON 조회 |
| `DELETE` | `/api/history/<id>` | 특정 이력 삭제 |
| `GET` | `/api/settings` | 연구소 역량 설정값 조회 |
| `POST` | `/api/settings` | `{capabilities}` 로 역량 설정값 갱신 |
| `GET` | `/healthz` | LLM 제공자·모델·키 설정 여부·이력 건수 확인 |

---

## 5. 처리 흐름

```
[브라우저]  파일 드래그앤드롭
    │  PDF.js / JSZip 으로 클라이언트에서 텍스트 추출  (서버 부하 최소화)
    ▼
POST /api/analyze  { text, filename }
    │
[Flask]  Settings 에서 연구소 역량 로드 → 프롬프트 구성
    │  Gemini(responseSchema) 또는 Claude 호출, 최대 3회 재시도
    ▼
  JSON 파싱 → AnalysisHistory 저장 (최근 HISTORY_LIMIT 건만 보관)
    │
    ▼
[브라우저]  대시보드 렌더링 (5개 섹션 + Chart.js 레이더 차트 + 간트 차트)
```

---

## 6. 주요 기능

- **파일 추출**: PDF(PDF.js), HWPX(JSZip + XML 파싱), TXT. HWP는 PDF/HWPX 변환 안내.
- **5개 분석 섹션**: 사업 개요 / 사업 목표(KPI) / 수행 내용(WBS·간트) / TTA 수행 가능성(역량 매핑·리스크) / 종합 판단(레이더 차트·To-Do).
- **역량 기반 재분석**: 4·5 섹션만 현재 역량 설정으로 다시 산출해 덮어씀.
- **히스토리**: 서버 DB에 영구 저장. 사이드바에서 클릭해 즉시 복원.
- **내보내기**: JSON 다운로드, 브라우저 인쇄(PDF 저장) — 인쇄 시 전체 섹션이 펼쳐지도록 CSS 처리.

---

## 7. Vercel 배포

### 7-1. 사전 준비

이 저장소에는 배포에 필요한 파일이 포함되어 있습니다.

- `api/index.py` — Vercel Python 서버리스 엔트리포인트
- `vercel.json` — 빌드/라우팅 설정 (모든 요청을 Flask 앱으로 전달, 최대 실행 60초)
- `.vercelignore` — 가상환경·DB·`.env` 제외

### 7-2. 배포

```bash
npx vercel login
npx vercel --prod
```

### 7-3. 환경변수 등록 (필수)

Vercel 대시보드 → Project → Settings → Environment Variables 에 등록하거나 CLI로 추가합니다.

```bash
npx vercel env add GEMINI_API_KEY production
npx vercel env add APP_PASSWORD production
npx vercel env add SECRET_KEY production
```

| 변수 | 필수 | 비고 |
|---|---|---|
| `GEMINI_API_KEY` | ✅ | 없으면 분석 시 오류 |
| `APP_PASSWORD` | ✅ | 공개 URL 접근 비밀번호. 비우면 **누구나 사용 가능** |
| `SECRET_KEY` | ✅ | 세션 서명 키. 미지정 시 인스턴스마다 달라져 로그인이 풀림 |
| `GEMINI_MODEL` | – | 기본 `gemini-3-flash-preview` |

`SECRET_KEY` 생성:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 7-4. ⚠️ 서버리스 환경의 제약

Vercel은 파일시스템이 읽기전용이고 인스턴스가 수시로 재시작되므로,
SQLite DB를 `/tmp` 에 생성합니다. 따라서 **분석 이력과 역량 설정이 영구 보관되지 않습니다.**
(분석 기능 자체는 정상 동작하며, 결과는 `JSON 다운로드`/`보고서 인쇄`로 보관할 수 있습니다.
사이드바에도 임시 저장소 안내가 표시됩니다.)

이력을 영구 보관하려면 외부 Postgres를 연결하세요. 코드 수정 없이 환경변수만 추가하면 됩니다.

```bash
# Neon, Supabase, Vercel Postgres 등에서 발급받은 접속 문자열
DATABASE_URL=postgresql://user:pw@host/dbname?sslmode=require
```

> `psycopg2-binary` 를 `requirements.txt` 에 추가해야 합니다.

또한 Vercel 서버리스 함수의 최대 실행 시간 제약이 있어,
문서가 매우 길면 분석이 타임아웃될 수 있습니다. 이 경우 `MAX_TEXT_CHARS` 를 줄이세요.

---

## 8. 환경변수 참고

| 변수 | 기본값 | 설명 |
|---|---|---|
| `LLM_PROVIDER` | `gemini` | `gemini` 또는 `anthropic` |
| `GEMINI_API_KEY` | – | Google AI Studio 발급 키 |
| `GEMINI_MODEL` | `gemini-3-flash-preview` | 사용 모델명 |
| `ANTHROPIC_API_KEY` | – | Anthropic 발급 키 |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-5` | 사용 모델명 |
| `APP_PASSWORD` | (없음) | 접속 비밀번호. 비우면 인증 없이 동작 |
| `SECRET_KEY` | 랜덤 생성 | 세션 서명 키. 배포 시 반드시 고정값 지정 |
| `DATABASE_URL` | (없음) | 지정 시 SQLite 대신 해당 DB 사용 |
| `MAX_TEXT_CHARS` | `180000` | LLM에 전송할 최대 글자 수 |
| `HISTORY_LIMIT` | `50` | 보관할 최근 분석 이력 건수 |

---

## 9. 참고 사항

- 개발 서버(`debug=True`)는 로컬 테스트 전용입니다. 외부 공개 시 `gunicorn`/`waitress` 등 WSGI 서버를 사용하세요.
- `.env` 와 `rfp_analysis.db` 는 `.gitignore` 에 포함되어 있습니다. API 키를 커밋하지 마세요.
- `GEMINI_MODEL` 값은 계정에서 사용 가능한 모델명으로 바꿔 쓸 수 있습니다 (예: `gemini-2.5-flash`).
