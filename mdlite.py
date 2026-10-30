"""블로그 본문용 최소 마크다운 렌더러 — HTML을 먼저 이스케이프하므로 XSS 안전.

지원: # ## ### 제목(# 도 h2 — 페이지 h1은 글 제목 하나), 문단, - 목록, 1. 목록, **굵게**, [글](url), ![alt](url)
URL은 http(s)://, /경로, # 만 허용 (javascript: 등은 # 으로 대체).
자체 점검: python mdlite.py
"""
import html
import re

_SAFE_URL = re.compile(r"^(https?://|/(?!/)|#)", re.I)
_IMG = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_BOLD = re.compile(r"\*\*(.+?)\*\*")


def _url(u):
    return u if _SAFE_URL.match(u) else "#"


def _inline(t, alt):
    t = _IMG.sub(lambda m: f'<img src="{_url(m[2])}" alt="{(m[1] or alt).replace("*", "")}" loading="lazy">', t)
    t = _LINK.sub(lambda m: f'<a href="{_url(m[2])}"'
                  + (' rel="noopener nofollow" target="_blank"' if m[2].lower().startswith("http") else "")
                  + f">{m[1]}</a>", t)
    return _BOLD.sub(r"<strong>\1</strong>", t)


def render(text, alt=""):
    alt = html.escape(alt or "", quote=True)
    out, para, lst = [], [], None  # lst = ("ul"|"ol", [items])

    def flush():
        nonlocal para, lst
        if para:
            out.append("<p>" + " ".join(para) + "</p>")
            para = []
        if lst:
            out.append(f"<{lst[0]}>" + "".join(f"<li>{x}</li>" for x in lst[1]) + f"</{lst[0]}>")
            lst = None

    for raw in (text or "").replace("\r\n", "\n").split("\n"):
        line = _inline(html.escape(raw.strip(), quote=True), alt)
        m = re.match(r"^(#{1,3})\s+(.*)$", line)
        ul = re.match(r"^[-*]\s+(.*)$", line)
        ol = re.match(r"^\d+\.\s+(.*)$", line)
        if not line:
            flush()
        elif m:
            flush()
            tag = "h3" if len(m[1]) == 3 else "h2"
            out.append(f"<{tag}>{m[2]}</{tag}>")
        elif ul or ol:
            kind = "ul" if ul else "ol"
            if para or (lst and lst[0] != kind):
                flush()
            lst = lst or (kind, [])
            lst[1].append((ul or ol)[1])
        else:
            if lst:
                flush()
            para.append(line)
    flush()
    return "\n".join(out)


if __name__ == "__main__":
    h = render('<script>alert(1)</script>\n[x](javascript:alert(1)) ![a" onerror="x](/a.png)\n'
               '[y](//evil.com) **b** <img src=x onerror=alert(1)>\n\n## 제목\n- 하나\n- 둘\n1. 가\n\n![](https://e.com/i.webp)', alt="글")
    assert "<script" not in h and "javascript:" not in h and "<img src=x" not in h, h
    assert 'href="#"' in h and "<strong>b</strong>" in h and "<h2>제목</h2>" in h
    assert "<ul><li>하나</li><li>둘</li></ul><ol><li>가</li></ol>" in h.replace("\n", "")
    assert 'alt="글"' in h and 'onerror="x' not in h
    print("mdlite ok")
