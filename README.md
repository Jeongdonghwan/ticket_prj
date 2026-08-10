# 알뜰티켓 — 상품권 매입 랜딩 + 상담 어드민

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
| `db.py` / `schema.sql` | MariaDB 헬퍼 / 테이블 2개(inquiries, admins) |
| `notify.py` | 텔레그램 알림 (미설정 시 자동 skip) |
| `templates/index.html` | 랜딩 (디자인본 무손실 Jinja2 변환) |
| `templates/admin_list.html` | 어드민 상담 리스트 단일 화면 (필터·검색·페이지네이션·상태 즉시 저장) |

## 배포 전 교체 지점 (CLAUDE.md 8절 — 코드 내 `TODO(대표 확인)` 주석 검색)

- 히어로 AI 모델 이미지 → `templates/index.html` `.stack` 블록
- 실제 서류 스캔본 → `templates/index.html` 신뢰 섹션 `.doc`
- 실제 매입률/매입가 → `config.py`
- 고객센터 번호·카카오톡 채널 URL → `config.py`
- 채널톡 플러그인 키 → `.env`
- 후기 실데이터 → `templates/index.html` `reviews` 배열
- 푸터/개인정보처리방침 사업자 정보 → `templates/index.html`, `templates/privacy.html`

## 운영 (Cafe24)

- gunicorn + nginx 표준 구성, `/admin` 은 `robots.txt` 에서 Disallow 처리됨
- 문의 API IP당 5회/시간, 어드민 로그인 IP당 10회/시간 rate limit (인메모리 — gunicorn 워커 1개 기준)
