# 알뜰티켓 — 상품권·티켓 매입 랜딩 + 어드민 구현 (Claude Code 핸드오프)

## 0. 프로젝트 개요
- 서비스명: 알뜰티켓
- 성격: 상품권/기프티콘 정상 매입(중고매입) 랜딩페이지 + 상담·운영 어드민
- **디자인 확정본: 동봉된 `index.html`(랜딩), `admin.html`(어드민)** — 이 두 파일이 디자인의 단일 기준. 마크업/CSS/JS 동작을 그대로 유지하면서 Flask + Jinja2로 템플릿화할 것. 임의로 레이아웃·모션·카피를 변경하지 말 것.
- 컬러 토큰: `--yellow:#FFC933 --deep:#F2A900 --pale:#FFF6DC --ink:#191919 --navy:#1F2437 --gray:#767676 --gray-l:#F7F7F9`
- 폰트: Pretendard Variable (jsdelivr CDN, 현행 유지)
- 아이콘: 인라인 SVG 스프라이트(`<symbol>`+`<use>`) — **이모지 사용 금지**



## 1. 기술 스택
- Flask + Jinja2 SSR + MariaDB (Cafe24 가상서버, gunicorn + nginx — 기존 표준 구성)
- 어드민 인증: 세션 기반 (bcrypt 해시)
- 채널톡(ChannelIO) 임베드 + 웹훅, 텔레그램 알림 봇
- 프론트 JS: 바닐라 (index.html 내 스크립트 유지)

## 2. 랜딩 페이지 구성 (index.html 섹션 순서 — 변경 금지)
1. **헤더**: 스티키, 스크롤 시 `.scrolled` 섀도, 앵커 내비 + "빠른 상담" 필 버튼
2. **히어로**: "카톡 한번으로 끝! 내 비상금 한도 바로찾기!" + 상품권 카드 스택 3장(플로팅 모션, 노란 글로우)
   - AI 모델 이미지 확보 시 `.stack` 블록을 `<img class="hero-model" src="...">`로 교체 (CSS 슬롯 준비됨)
3. **스탯 콜아웃**: "평균 96,500원 상품권을 현금으로 받았어요" — `#avgAmt` 카운트업, 바운스 셰브론, 대형 노란 CTA
4. **브랜드 소개**: 컬러 아이브로우 + 타이틀 + 회색 설명(키워드 볼드) + 필 버튼 (센터 정렬)
5. **폰 목업 섹션** (회색 bg, 상단 56px 곡률): 아이폰 목업(다이나믹 아일랜드, 실시간 시계 `#phTime`) + 양옆 플로팅 토스트(입금 알림 / 카톡 알림)
6. **매입 시세**: 실물풍 상품권 카드 6종 그리드 — 카드 규격 비율 1.586, 브랜드별 그라데이션(`g-green/blue/orange/violet/pink/dark`), 바코드 스트립·광택은 CSS pseudo. **시세 수치는 rates 테이블에서 SSR 렌더**
7. **실시간 진행현황**: 네이비 상단바(회전 새로고침 아이콘 + `#liveTime` 기준 시각) + 성함/상품종류/매입금액(컬러)/상태배지 테이블. `#liveBody` 8초 주기 갱신
8. **이용 후기**: 네이비 섹션(상단 곡률), 카드 슬라이더 — 좌우 화살표 + 도트 + 6초 자동, `reviews` 배열은 DB화(선택) 또는 하드코딩 유지
9. **신뢰 섹션**: 4카드(사업자등록/통신판매업/HTTPS/본인계좌 원칙) — 서류 썸네일은 CSS. 실제 서류 스캔본 확보 시 `.doc`을 `<img>`로 교체
10. **FAQ**: details/summary 4개
11. **문의 폼** `#inqForm` → `POST /api/inquiry` (현재 alert 스텁을 fetch로 교체)
12. **푸터** + **우측 플로팅 4종**(채널톡/카카오톡/전화/TOP, 호버 툴팁)

### 유지해야 할 JS 동작
- 스크롤 리빌: IntersectionObserver, 형제 순서 기반 스태거 (`transitionDelay = idx*0.08s`)
- 카운트업: `#avgAmt` (뷰포트 진입 시 1.3s 이징)
- 라이브 피드: 8초 주기 새 행 prepend + `rowIn`/`rowFlash` 애니메이션, 5행 유지, `document.hidden` 시 정지
- 후기 슬라이더: 페이드 전환, 수동 조작 시 오토 타이머 리셋
- `prefers-reduced-motion` 전체 비활성 가드(`RM`) 유지
- **교체 지점**: `feedRow()` 더미 생성 → `GET /api/live-feed` 폴링 / `openChannel()` alert → `ChannelIO('showMessenger')` / 폼 alert → fetch POST

## 3. 어드민 (admin.html 기준 — 단일 화면)
- `/admin/login` → 바로 **상담 리스트** 단일 페이지 (대시보드/통계/시세관리/피드관리 화면 없음. 만들지 말 것)
- 상단 필터 칩(전체/신규/상담중/입금완료/보류) + 이름/연락처 검색 + 페이지네이션
- 테이블 컬럼: 접수시각 / 유입(채널톡·하단폼·전화·카카오) / 이름 / 연락처 / 상품권·금액대 / 문의 내용 / 상태 select
- 상태 select 변경 시 즉시 `PATCH /api/admin/inquiries/<id>` 저장 (색상 클래스 전환 JS는 admin.html에 있음)
- '입금완료' 전환 시 JS prompt로 매입금액(원) 입력(선택) → `amount_final` 저장
- 랜딩의 실시간 진행현황은 어드민에서 따로 관리하지 않고 **입금완료 건에서 자동 생성** (6절 참조)
- 매입 시세는 어드민 관리 없이 템플릿 상수(config) 하드코딩 — 변경 시 코드 수정

## 4. DB 스키마 (MariaDB — 2테이블만)
```sql
CREATE TABLE inquiries (
  id INT AUTO_INCREMENT PRIMARY KEY,
  source ENUM('form','channeltalk','phone','kakao') NOT NULL DEFAULT 'form',
  name VARCHAR(40) NOT NULL,
  phone VARCHAR(20) NOT NULL,
  category VARCHAR(40),
  amount_range VARCHAR(20),
  memo TEXT,
  status ENUM('new','consulting','done','hold') DEFAULT 'new',
  amount_final INT NULL,               -- 입금완료 시 입력한 매입금액 (랜딩 피드 노출용)
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_status_created (status, created_at)
);

CREATE TABLE admins (
  id INT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(40) UNIQUE NOT NULL,
  password_hash VARCHAR(200) NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```
매입 시세·평균 매입가·후기는 DB 없이 템플릿/config 상수로 관리.

## 5. API 라우트
| Method | Path | 설명 |
|---|---|---|
| GET | `/` | 랜딩 SSR — 시세 상수, 초기 피드 5건 주입 |
| POST | `/api/inquiry` | 폼 접수. rate limit IP당 5회/시간, honeypot 필드, 접수 시 텔레그램 알림 |
| GET | `/api/live-feed` | 입금완료(`status=done`, `amount_final` 有) 최신 5건 마스킹 JSON + 서버시각 (8초 폴링) |
| POST | `/webhook/channeltalk` | 채널톡 신규 상담 → inquiries(source=channeltalk) 자동 생성 |
| GET/POST | `/admin/login` | 로그인 |
| GET | `/admin?status=&q=&page=` | 상담 리스트 (필터·검색·페이지네이션) |
| PATCH | `/api/admin/inquiries/<id>` | 상태/매입금액 변경 |

## 6. 비즈니스 로직
- 이름 마스킹: 성만 남기고 `김**님` 형식 (2자 성명은 `김*님`) — `/api/live-feed` 응답 시 적용
- 랜딩 실시간 진행현황 = 입금완료 건 자동 노출: `status='done' AND amount_final IS NOT NULL` 최신 5건. 초기엔 데이터가 없으므로 5건 미만일 때 index.html의 더미 생성 로직으로 채움 (실데이터 우선)
- 문의 접수·상태변경 텔레그램 알림 (세인약품 패턴 재사용, token/chat_id는 .env)
- 채널톡: `<head>`에 ChannelIO 부트 스크립트, `openChannel()` → `ChannelIO('showMessenger')`
- 랜딩 시세 표기 3곳(히어로 카드 스택 / 폰 목업 / 시세 카드 그리드)은 config 상수 하나로 Jinja2 렌더해 동기화

## 7. 배포/운영
- Cafe24 가상서버, gunicorn + nginx
- .env: DB 접속정보, SECRET_KEY, CHANNELTALK_PLUGIN_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
- `/admin` robots.txt Disallow, 어드민 경로 rate limit
- 개인정보처리방침 페이지 1장 추가 (문의 데이터 보관·파기 주기 명시), 폼 동의 문구와 일치시킬 것
- 푸터 사업자 정보 placeholder(OOO/000-00-00000)는 실제 값으로 교체 후 오픈

## 8. 남은 에셋 TODO (대표 확인 필요)
- [ ] 히어로 AI 모델 이미지 (프롬프트 전달됨 — 누끼 PNG, 3:4) → `.stack` 교체
- [ ] 신뢰 섹션 실제 서류 스캔본 (사업자등록증/통신판매업신고증, 민감정보 마스킹)
- [ ] 실제 매입률 수치, 고객센터 번호, 채널톡 플러그인 키, 카카오톡 채널 URL
- [ ] 후기 실제 데이터 교체 (현재 예시 문구)

## 9. 작업 순서
1. Flask 스캐폴딩 + 2테이블 마이그레이션 + 시세/후기 config 상수 정리
2. `index.html` → `templates/index.html` Jinja2 변환 (시세 3곳 바인딩, JS 동작 무손실)
3. `/api/inquiry`, `/api/live-feed` 구현 + 프론트 스텁 3곳(fetch/폴링/ChannelIO) 교체
4. 어드민 로그인 + `admin.html` 템플릿화 (상담 리스트 단일 화면: 필터·검색·페이지네이션·상태 PATCH·입금완료 시 금액 prompt)
5. 텔레그램 알림 + 채널톡 웹훅
6. 모바일 QA (390px: 토스트 위치, 카드 그리드 2열, 히어로 스택, 어드민 테이블) → 배포
