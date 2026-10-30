"""키워드 엑셀 → data/qa_keywords.json (앱은 런타임에 xlsx를 읽지 않음).

  python scripts/build_qa.py [엑셀 경로]

'키워드' 시트에서 구분 == '합법 대출 Q&A' 행만, 파일 순서대로 앞 2,000개.
'현금화 Q&A' 행은 절대 쓰지 않는다.
"""
import json
import os
import sys

import openpyxl

SRC = sys.argv[1] if len(sys.argv) > 1 else r"C:\side_Prj\loan_prj\keywords\대출_QA_키워드.xlsx"
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "qa_keywords.json")
LIMIT = 2000

ws = openpyxl.load_workbook(SRC, read_only=True)["키워드"]
rows = ws.iter_rows(values_only=True)
head = list(next(rows))
col = {name: head.index(name) for name in ("No", "키워드", "구분", "의도", "주제", "대상자")}

items, seen = [], set()
for r in rows:
    if r[col["구분"]] != "합법 대출 Q&A":
        continue
    kw = str(r[col["키워드"]]).strip()
    slug = kw.replace(" ", "-")
    if slug in seen:
        continue
    seen.add(slug)
    items.append({
        "no": r[col["No"]], "kw": kw, "slug": slug,
        "intent": r[col["의도"]], "topic": r[col["주제"]], "aud": r[col["대상자"]] or "",
    })
    if len(items) == LIMIT:
        break

with open(OUT, "w", encoding="utf-8") as f:
    f.write("[\n" + ",\n".join(json.dumps(i, ensure_ascii=False) for i in items) + "\n]\n")

print(f"{len(items)}개 → {os.path.normpath(OUT)}")
