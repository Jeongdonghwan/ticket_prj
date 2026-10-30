# 맥스페이 — 상품권 매입 랜딩 + 상담 어드민

Flask + Jinja2 + MariaDB. 디자인 확정본은 루트의 `index.html` / `admin.html`(정적 원본)이며,
실제 서비스 템플릿은 `templates/` 아래에 있습니다.

## 로컬 실행

### 1. 가상환경 + 의존성

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 2. MariaDB 준비

```sql
CREATE DATABASE ticket_db DEFAULT CHARACTER SET utf8mb4;
CREATE USER 'ticket'@'localhost' IDENTIFIED BY '비밀번호';
GRANT ALL PRIVILEGES ON ticket_db.* TO 'ticket'@'localhost';
```

### 3. 환경변수

```bash
# .env.example 을 복사해 실제 값 입력
copy .env.example .env      # Windows
cp .env.example .env        # macOS/Linux
```

- `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`, `CHANNELTALK_PLUGIN_KEY` 는 비워둬도 동작합니다(알림/채널톡만 비활성).

### 4. 테이블 생성 + 어드민 계정

```bash
flask init-db
flask create-admin admin     # 비밀번호 입력 프롬프트
```

### 5. 실행

```bash
flask run          # 또는 python app.py (debug)
```

- 랜딩: http://127.0.0.1:5000
- 어드민: http://127.0.0.1:5000/admin (로그인: 위에서 만든 계정)

## 구조

| 파일 | 역할 |
|---|---|
| `app.py` | 전체 라우트 (랜딩 SSR, 문의 API, 라이브 피드, 채널톡 웹훅, 어드민, CLI) |
| `config.py` | 매입 시세·평균가·연락처 상수 — **시세 변경은 이 파일만 수정** (랜딩 3곳 자동 동기화) |
| `db.py` / `schema.sql` | MariaDB 헬퍼 / 테이블 3개(inquiries, admins, posts) |
| `qa_compose.py` | 대출 Q&A 2,000쪽 본문 조합기 (주제·의도·대상자 축 + 해시 변형, 금지어 목록 `FORBIDDEN`) |
| `data/qa_keywords.json` | Q&A 키워드 2,000개 (`scripts/build_qa.py` 로 생성) |
| `mdlite.py` | 블로그 본문용 안전 마크다운 렌더러 (HTML 이스케이프 후 변환) |
| `templates/_seo_base.html` | Q&A·블로그 공통 레이아웃 (메타·og·JSON-LD·헤더·푸터) |
| `templates/_loan_disclosure.html` | 대부업 공시 블록 (Q&A·블로그 모든 페이지 하단) |
| `notify.py` | 텔레그램 알림 (미설정 시 자동 skip) |
| `templates/index.html` | 랜딩 (디자인본 무손실 Jinja2 변환) |
| `templates/admin_list.html` | 어드민 상담 리스트 단일 화면 (필터·검색·페이지네이션·상태 즉시 저장) |

## 대출 Q&A · 블로그

### 라우트

| 경로 | 설명 |
|---|---|
| `/qa/` | Q&A 허브 (주제 30개 × 질문, ItemList) |
| `/qa/<키워드-슬러그>/` | Q&A 2,000쪽 (예: `/qa/소액대출-조건/`) — FAQPage·BreadcrumbList |
| `/blog/` , `/blog/?page=2` | 블로그 목록 (발행 + 발행시각 지난 글만) |
| `/blog/<slug>/` | 블로그 글 (Article JSON-LD, 관련 Q&A 링크) |
| `/rss.xml` | 블로그 RSS (최근 30개) |
| `/sitemap.xml` | 메인·개인정보·허브 2개·Q&A 2,000·발행글 |
| `/admin/posts` | 어드민 블로그 목록 (상단 메뉴 "블로그") |
| `/admin/posts/new`, `/admin/posts/<id>/edit` | 글 작성/수정 |
| `POST /admin/posts/<id>/delete` | 삭제 (확인창 + CSRF) |
| `POST /admin/posts/preview`, `POST /admin/posts/upload` | 미리보기 / 이미지 업로드 (폼에서 호출) |

### Q&A 데이터 다시 만들기

```bash
python scripts/build_qa.py "C:\side_Prj\loan_prj\keywords\대출_QA_키워드.xlsx"   # '키워드' 시트, 구분='합법 대출 Q&A' 위에서 2,000개
python qa_compose.py    # 자체 점검: 2,000쪽 조합 + 본문 1,300자 이상 + 금지어 0건
```
- 문구를 고치려면 `qa_compose.py` 의 `TOPICS`(주제별 설명)·`AUDS`(대상자)·`sec_*` 함수만 수정하면 전 페이지에 반영됩니다.
- 수치는 **법정 최고금리 연 20%만** 씁니다. 승인·입금 보장 표현과 현금화 관련 단어는 `FORBIDDEN` 에 있고 자체 점검에서 걸립니다.

### 블로그 글 쓰기 (어드민)

1. 기존 DB 에 `flask init-db` 한 번 실행 → `posts` 테이블 추가 (IF NOT EXISTS 라 기존 데이터 안전)
2. `/admin` 로그인 → 상단 **블로그** → **새 글 쓰기**
3. 제목 · 주소(비우면 제목으로 자동) · 요약 · 대표 이미지 · 본문(마크다운) 입력, **미리보기**로 확인
4. 상태 **발행** + 발행 시각(비우면 지금, 미래면 예약) → 저장
- 이미지: jpg/png/webp, 5MB 이하 → 긴 변 1600px webp 로 `static/uploads/` 에 저장 (git 에 안 올라감 — 서버 백업 대상)
- 마크다운: `## 소제목`, `### 작은 제목`, `- 목록`, `1. 목록`, `**굵게**`, `[글](https://...)`, `![설명](이미지주소)` — HTML 은 글자로 표시됨(XSS 차단)
- 서버에 Pillow 필요: `pip install -r requirements.txt`

## 배포 전 교체 지점 (CLAUDE.md 8절 — 코드 내 `TODO(대표 확인)` 주석 검색)

- 히어로 AI 모델 이미지 → `templates/index.html` `.stack` 블록
- 실제 서류 스캔본 → `templates/index.html` 신뢰 섹션 `.doc`
- 실제 매입률/매입가 → `config.py`
- 고객센터 번호·카카오톡 채널 URL → `config.py`
- 채널톡 플러그인 키 → `.env`
- 후기 실데이터 → `templates/index.html` `reviews` 배열
- 푸터/개인정보처리방침 사업자 정보 → `templates/index.html`, `templates/privacy.html`
- **대부업 공시 (Q&A·블로그 전 페이지) → `config.py` `LENDER_*`** — 오픈 전 반드시 실제 값으로:
  `LENDER_NAME`(상호) · `LENDER_CEO`(대표자) · `LENDER_REG_NO`(대부업 등록번호) · `LENDER_REG_AUTHORITY`(등록기관) ·
  `LENDER_ADDRESS`(영업소 주소) · `LENDER_PHONE`(대표전화, Q&A CTA 전화 버튼에도 사용) · `LENDER_RATE`(예: 연 ○%~20% 이내) ·
  `LENDER_OVERDUE_RATE`(연체이자율) · `LENDER_EXTRA_COST`(이자 외 추가 비용, 없으면 "없음")
  - 경고문구 2종과 "중개수수료를 요구하거나 받는 것은 불법입니다" 는 `templates/_loan_disclosure.html` 에 고정

## 운영 (Cafe24)

- gunicorn + nginx 표준 구성, `/admin` 은 `robots.txt` 에서 Disallow 처리됨 (`/qa/`, `/blog/` 는 Allow)
- 블로그·어드민 폼은 세션 CSRF 토큰으로 보호
- 문의 API IP당 5회/시간, 어드민 로그인 IP당 10회/시간 rate limit (인메모리 — gunicorn 워커 1개 기준)
