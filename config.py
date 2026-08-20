"""알뜰티켓 템플릿 상수 — 시세/평균가/연락처 단일 소스.

랜딩의 시세 표기 3곳(히어로 카드 스택 / 폰 목업 / 시세 카드 그리드)은
전부 이 파일의 상수로 렌더되어 동기화된다. (CLAUDE.md 6절)
시세 변경 시 이 파일만 수정하면 된다.
"""

# TODO(대표 확인): 실제 매입률 수치로 교체 — CLAUDE.md 8절
# grad: index.html의 브랜드 그라데이션 클래스(g-green/blue/orange/violet/pink/dark)
RATES = [
    {"name": "문화상품권",     "sub": "CULTURELAND",           "grad": "g-green",  "rate": "96.5%",    "small": "매입률"},
    {"name": "도서문화상품권", "sub": "BOOK & CULTURE",        "grad": "g-blue",   "rate": "95.0%",    "small": "매입률"},
    {"name": "해피머니",       "sub": "HAPPY MONEY",           "grad": "g-orange", "rate": "94.5%",    "small": "매입률"},
    {"name": "백화점상품권",   "sub": "DEPARTMENT GIFT CARD",  "grad": "g-violet", "rate": "95.0%",    "small": "매입률"},
    {"name": "모바일 기프티콘","sub": "MOBILE GIFTICON",       "grad": "g-pink",   "rate": "시세 상담", "small": "브랜드별"},
    {"name": "게임문화상품권", "sub": "GAME &amp; CULTURE",    "grad": "g-dark",   "rate": "93.0%",    "small": "매입률"},
]

# 히어로 카드 스택 뒤 2장 = 문화상품권 / 백화점상품권 (index.html 디자인 확정본 기준)
HERO_RATES = [RATES[0], RATES[3]]

# 문화상품권 10만원권 매입가 (원) — 히어로 dark카드 / 스탯 카운트업 / 폰 목업 3곳에 표기
# TODO(대표 확인): 실제 매입가로 교체. RATES의 문화상품권 매입률과 일치시킬 것 (96.5% → 96,500원)
CULTURE_100K_PRICE = 2000000

# TODO(대표 확인): 실제 고객센터 번호로 교체 — CLAUDE.md 8절
PHONE_NUMBER = "0000-0000"

# TODO(대표 확인): 실제 카카오톡 채널 URL로 교체 (예: https://pf.kakao.com/_xxxxxx) — CLAUDE.md 8절
KAKAO_CHANNEL_URL = "#"

# 어드민 상담 리스트 페이지당 행 수
ADMIN_PAGE_SIZE = 20

# 사이트 대표 URL (canonical/OG/sitemap 기준) — 알뜰티켓.com 의 퓨니코드
SITE_URL = "https://xn--ig2bo1yush92d.com"

# 검색 노출용 사이트 설명 (meta description / OG)
SITE_DESCRIPTION = "카톡 한 번으로 끝나는 간편 매입 서비스, 알뜰티켓. 30초 시세 조회, 평균 7분 입금, 본인 명의 계좌 안전거래. 연중무휴 09:00~24:00 상담."
