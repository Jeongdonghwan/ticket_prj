"""맥스페이 — 랜딩 + 상담 어드민 (Flask + MariaDB)"""
import io
import os
import re
import secrets
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime
from email.utils import format_datetime
from functools import wraps
from html import escape as xml_escape
from urllib.parse import quote

from dotenv import load_dotenv

load_dotenv()

import bcrypt
import click
from flask import (
    Flask, Response, abort, jsonify, redirect, render_template,
    request, session, url_for,
)
from markupsafe import Markup
from PIL import Image, ImageOps

import config
import db
import mdlite
import qa_compose
from notify import notify_new_inquiry, notify_status_change

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-secret")
app.config["MAX_CONTENT_LENGTH"] = 6 * 1024 * 1024  # 업로드 5MB + 여유
db.init_app(app)

try:
    from zoneinfo import ZoneInfo
    KST = ZoneInfo("Asia/Seoul")
except Exception:  # tzdata 미설치 환경(Windows 등)은 서버 로컬 시각 사용
    KST = None

STATUS_LABELS = {"new": "신규", "consulting": "상담중", "done": "입금완료", "hold": "보류"}
SOURCE_LABELS = {"form": "하단폼", "channeltalk": "채널톡", "phone": "전화", "kakao": "카카오"}


def now_kst():
    return datetime.now(KST) if KST else datetime.now()


def mask_name(name):
    """성만 남기고 마스킹: 김지영→김**님, 김영→김*님 (CLAUDE.md 6절)"""
    name = (name or "").strip()
    if not name:
        return "고객님"
    return name[0] + "*" * max(len(name) - 1, 1) + "님"


# ── rate limit (인메모리, 단일 워커 기준) ─────────────────────────
_hits = defaultdict(deque)


def rate_limited(bucket, limit, window=3600):
    ip = (request.headers.get("X-Forwarded-For") or request.remote_addr or "?").split(",")[0].strip()
    dq = _hits[(bucket, ip)]
    now = time.time()
    while dq and dq[0] < now - window:
        dq.popleft()
    if len(dq) >= limit:
        return True
    dq.append(now)
    return False


@app.context_processor
def inject_constants():
    return {
        "RATES": config.RATES,
        "HERO_RATES": config.HERO_RATES,
        "CULTURE_100K_PRICE": config.CULTURE_100K_PRICE,
        "PHONE_NUMBER": config.PHONE_NUMBER,
        "KAKAO_CHANNEL_URL": config.KAKAO_CHANNEL_URL,
        "CHANNELTALK_PLUGIN_KEY": os.environ.get("CHANNELTALK_PLUGIN_KEY", ""),
        "SITE_URL": config.SITE_URL,
        "CHANNEL_TALK_URL": config.CHANNEL_TALK_URL,
        "SITE_DESCRIPTION": config.SITE_DESCRIPTION,
        "LENDER": {
            "name": config.LENDER_NAME, "ceo": config.LENDER_CEO, "reg_no": config.LENDER_REG_NO,
            "reg_authority": config.LENDER_REG_AUTHORITY, "address": config.LENDER_ADDRESS,
            "phone": config.LENDER_PHONE, "rate": config.LENDER_RATE,
            "overdue_rate": config.LENDER_OVERDUE_RATE, "extra_cost": config.LENDER_EXTRA_COST,
        },
        "csrf_token": csrf_token,
        "crumb_ld": crumb_ld,
    }


def abs_url(path):
    """canonical/sitemap용 절대 URL (한글·& 등 퍼센트 인코딩)"""
    return config.SITE_URL + quote(path, safe="/")


def crumb_ld(crumbs):
    return [{"@type": "ListItem", "position": i + 1, "name": name, "item": abs_url(url)}
            for i, (name, url) in enumerate(crumbs)]


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def check_csrf():
    tok = request.form.get("csrf") or request.headers.get("X-CSRF-Token") or ""
    if not secrets.compare_digest(tok, session.get("csrf", "")):
        abort(400, "CSRF 토큰이 올바르지 않습니다. 페이지를 새로고침 후 다시 시도하세요.")


def fetch_live_rows():
    """입금완료(amount_final 有) 최신 5건 → 랜딩 실시간 진행현황 (CLAUDE.md 6절)"""
    rows = db.query(
        "SELECT name, amount_final FROM inquiries "
        "WHERE status='done' AND amount_final IS NOT NULL "
        "ORDER BY updated_at DESC LIMIT 5"
    )
    return [
        {"name": mask_name(r["name"]), "amount": r["amount_final"], "done": True}
        for r in rows
    ]


# ── 공개 페이지 / API ─────────────────────────────────────────────
@app.get("/")
def index():
    return render_template("index.html", initial_feed=fetch_live_rows())


@app.get("/privacy")
def privacy():
    return render_template("privacy.html")


@app.get("/robots.txt")
def robots():
    return Response(
        "User-agent: *\nDisallow: /admin\nAllow: /qa/\nAllow: /blog/\n\n"
        f"Sitemap: {config.SITE_URL}/sitemap.xml\n",
        mimetype="text/plain",
    )


@app.get("/sitemap.xml")
def sitemap():
    pages = [("/", "1.0", None), ("/privacy", "0.3", None), ("/qa/", "0.8", None), ("/blog/", "0.7", None)]
    pages += [(f"/blog/{p['slug']}/", "0.6", p["updated_at"] or p["published_at"]) for p in live_posts()]
    pages += [(f"/qa/{it['slug']}/", "0.5", None) for it in qa_compose.ITEMS]
    items = "".join(
        f"<url><loc>{xml_escape(abs_url(path))}</loc>"
        + (f"<lastmod>{lm.strftime('%Y-%m-%d')}</lastmod>" if lm else "")
        + f"<priority>{pr}</priority></url>"
        for path, pr, lm in pages
    )
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{items}</urlset>')
    return Response(xml, mimetype="application/xml")


@app.get("/api/live-feed")
def api_live_feed():
    return jsonify({"rows": fetch_live_rows(),
                    "server_time": now_kst().strftime("%H:%M")})


@app.post("/webhook/channeltalk")
def webhook_channeltalk():
    """채널톡 신규 상담 웹훅 → inquiries(source=channeltalk) 자동 생성.

    TODO(채널톡 연동 시): 채널톡 데스크 > 웹훅 설정의 실제 페이로드 스키마에 맞춰
    아래 파싱 경로를 확인/조정할 것. 현재는 대표적인 필드 경로를 best-effort로 탐색.
    """
    data = request.get_json(silent=True) or {}
    entity = data.get("entity") or {}
    refers = data.get("refers") or {}
    user = refers.get("user") or {}
    profile = user.get("profile") or {}
    name = (profile.get("name") or user.get("name") or "채널톡 고객").strip()[:40]
    phone = (profile.get("mobileNumber") or profile.get("phone") or "-").strip()[:20]
    memo = (entity.get("plainText") or entity.get("message") or "채널톡 신규 상담").strip()[:2000]
    db.execute(
        "INSERT INTO inquiries (source, name, phone, memo) VALUES ('channeltalk', %s, %s, %s)",
        (name, phone, memo),
    )
    notify_new_inquiry({"source_label": "채널톡", "name": name, "phone": phone, "memo": memo})
    return jsonify({"ok": True})


# ── 대출 Q&A (data/qa_keywords.json + qa_compose.py) ──────────────
@app.get("/qa/")
def qa_hub():
    groups = qa_compose.hub_groups()
    ld = {"@context": "https://schema.org", "@type": "ItemList", "name": "대출 Q&A 주제",
          "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": g["base"][0]["kw"],
                               "url": abs_url(f"/qa/{g['base'][0]['slug']}/")}
                              for i, g in enumerate(groups)]}
    return render_template(
        "qa_hub.html", groups=groups, total=len(qa_compose.ITEMS), section="qa",
        page_title="대출 Q&A — 조건·서류·심사·금리 질문 모음 | 맥스페이",
        page_desc="소액대출·비상금대출·신용대출 등 대출 질문을 상품·대상자별로 정리했습니다. 금리와 한도는 심사에 따라 다르며 법정 최고금리 연 20% 이내입니다.",
        canonical=abs_url("/qa/"), crumbs=[("홈", "/"), ("대출 Q&A", "/qa/")], jsonld=[ld],
    )


@app.get("/qa/<slug>/")
def qa_page(slug):
    pg = qa_compose.compose(slug)
    if not pg:
        abort(404)
    path = f"/qa/{slug}/"
    ld = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
        for q, a in [(pg["kw"], pg["answer"])] + pg["faqs"]]}
    return render_template(
        "qa_page.html", pg=pg, section="qa",
        page_title=f"{pg['title']} | 맥스페이", page_desc=pg["description"], canonical=abs_url(path),
        crumbs=[("홈", "/"), ("대출 Q&A", "/qa/"), (pg["kw"], path)], jsonld=[ld],
    )


# ── 블로그 (posts 테이블) ────────────────────────────────────────
def kst_naive_now():
    """DB의 published_at 은 KST 기준 naive DATETIME"""
    return now_kst().replace(tzinfo=None, microsecond=0)


def live_posts(limit=None, offset=0):
    sql = ("SELECT * FROM posts WHERE status='published' AND published_at <= %s "
           "ORDER BY published_at DESC, id DESC")
    args = [kst_naive_now()]
    if limit:
        sql += " LIMIT %s OFFSET %s"
        args += [limit, offset]
    return db.query(sql, args)


def cover_url(post):
    img = post.get("cover_image")
    if not img:
        return config.SITE_URL + "/static/img/og-qa.png"
    return img if img.startswith("http") else config.SITE_URL + img


@app.get("/blog/")
def blog_list():
    size = config.BLOG_PAGE_SIZE
    total = db.query_one("SELECT COUNT(*) AS n FROM posts WHERE status='published' AND published_at <= %s",
                         (kst_naive_now(),))["n"]
    pages = max((total + size - 1) // size, 1)
    page = request.args.get("page", 1, type=int)
    if page < 1 or page > pages:
        abort(404)
    posts = live_posts(size, (page - 1) * size)
    ld = {"@context": "https://schema.org", "@type": "ItemList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "url": abs_url(f"/blog/{p['slug']}/"), "name": p["title"]}
        for i, p in enumerate(posts)]}
    return render_template(
        "blog_list.html", posts=posts, page=page, pages=pages, section="blog",
        page_title="블로그 — 대출 정보와 소식 | 맥스페이" + (f" ({page}쪽)" if page > 1 else ""),
        page_desc="대출을 알아볼 때 알아 두면 좋은 정보와 맥스페이 소식을 정리합니다.",
        canonical=abs_url("/blog/") + (f"?page={page}" if page > 1 else ""),
        crumbs=[("홈", "/"), ("블로그", "/blog/")], jsonld=[ld] if posts else [],
    )


@app.get("/blog/<slug>/")
def blog_post(slug):
    post = db.query_one("SELECT * FROM posts WHERE slug=%s AND status='published' AND published_at <= %s",
                        (slug, kst_naive_now()))
    if not post:
        abort(404)
    path = f"/blog/{slug}/"
    desc = post["summary"] or re.sub(r"[#*\[\]()!>-]", "", post["body"])[:150].strip()
    ld = {"@context": "https://schema.org", "@type": "Article", "headline": post["title"][:110],
          "description": desc, "image": [cover_url(post)],
          "datePublished": post["published_at"].isoformat() + "+09:00",
          "dateModified": (post["updated_at"] or post["published_at"]).isoformat() + "+09:00",
          "author": {"@type": "Organization", "name": "맥스페이", "url": config.SITE_URL + "/"},
          "publisher": {"@type": "Organization", "name": "맥스페이",
                        "logo": {"@type": "ImageObject", "url": config.SITE_URL + "/static/img/apple-touch-icon.png"}},
          "mainEntityOfPage": abs_url(path)}
    return render_template(
        "blog_post.html", post=post, section="blog",
        body_html=Markup(mdlite.render(post["body"], alt=post["title"])),
        related=qa_compose.match(post["title"] + " " + (post["summary"] or "")),
        page_title=f"{post['title']} | 맥스페이 블로그", page_desc=desc, canonical=abs_url(path),
        og_type="article", og_image=cover_url(post),
        crumbs=[("홈", "/"), ("블로그", "/blog/"), (post["title"], path)], jsonld=[ld],
    )


@app.get("/rss.xml")
def rss():
    def pub(dt):
        return format_datetime(dt.replace(tzinfo=KST)) if KST else format_datetime(dt) + " +0900"

    items = "".join(
        "<item>"
        f"<title>{xml_escape(p['title'])}</title>"
        f"<link>{xml_escape(abs_url('/blog/' + p['slug'] + '/'))}</link>"
        f"<guid isPermaLink=\"true\">{xml_escape(abs_url('/blog/' + p['slug'] + '/'))}</guid>"
        f"<pubDate>{pub(p['published_at'])}</pubDate>"
        f"<description>{xml_escape(p['summary'] or p['title'])}</description>"
        "</item>"
        for p in live_posts(30)
    )
    xml = ('<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
           "<title>맥스페이 블로그</title>"
           f"<link>{config.SITE_URL}/blog/</link>"
           "<description>대출 정보와 맥스페이 소식</description><language>ko</language>"
           f"{items}</channel></rss>")
    return Response(xml, mimetype="application/rss+xml")


# ── 어드민 ────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("admin_id"):
            if request.method in ("GET", "HEAD"):
                return redirect(url_for("admin_login"))
            return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
        return f(*args, **kwargs)
    return wrapper


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        if rate_limited("admin-login", limit=10):
            error = "시도 횟수를 초과했습니다. 잠시 후 다시 시도해주세요."
        else:
            username = (request.form.get("username") or "").strip()
            password = request.form.get("password") or ""
            row = db.query_one("SELECT * FROM admins WHERE username=%s", (username,))
            if row and bcrypt.checkpw(password.encode(), row["password_hash"].encode()):
                session.clear()
                session["admin_id"] = row["id"]
                return redirect(url_for("admin_list"))
            error = "아이디 또는 비밀번호가 올바르지 않습니다."
    return render_template("admin_login.html", error=error)


@app.get("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


@app.get("/admin")
@login_required
def admin_list():
    status = request.args.get("status", "")
    q = (request.args.get("q") or "").strip()
    page = max(request.args.get("page", 1, type=int), 1)
    size = config.ADMIN_PAGE_SIZE

    where, args = [], []
    if status in STATUS_LABELS:
        where.append("status=%s")
        args.append(status)
    if q:
        where.append("(name LIKE %s OR phone LIKE %s)")
        args += [f"%{q}%", f"%{q}%"]
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    total = db.query_one(f"SELECT COUNT(*) AS n FROM inquiries {where_sql}", args)["n"]
    pages = max((total + size - 1) // size, 1)
    page = min(page, pages)
    rows = db.query(
        f"SELECT * FROM inquiries {where_sql} ORDER BY created_at DESC LIMIT %s OFFSET %s",
        args + [size, (page - 1) * size],
    )
    for r in rows:
        r["source_label"] = SOURCE_LABELS.get(r["source"], r["source"])
        r["time_label"] = r["created_at"].strftime("%m-%d %H:%M") if r["created_at"] else "-"
    return render_template(
        "admin_list.html",
        rows=rows, status=status, q=q, page=page, pages=pages, total=total,
        status_labels=STATUS_LABELS,
    )


@app.patch("/api/admin/inquiries/<int:inq_id>")
@login_required
def api_admin_update(inq_id):
    data = request.get_json(silent=True) or {}
    status = data.get("status")
    if status not in STATUS_LABELS:
        return jsonify({"ok": False, "error": "잘못된 상태값입니다."}), 400
    row = db.query_one("SELECT * FROM inquiries WHERE id=%s", (inq_id,))
    if not row:
        return jsonify({"ok": False, "error": "존재하지 않는 문의입니다."}), 404

    amount_final = data.get("amount_final")
    if amount_final is not None:
        try:
            amount_final = int(amount_final)
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "매입금액은 숫자여야 합니다."}), 400

    if amount_final is not None:
        db.execute("UPDATE inquiries SET status=%s, amount_final=%s WHERE id=%s",
                   (status, amount_final, inq_id))
    else:
        db.execute("UPDATE inquiries SET status=%s WHERE id=%s", (status, inq_id))
    notify_status_change(row["name"], row["phone"], STATUS_LABELS[status],
                         amount_final=amount_final)
    return jsonify({"ok": True})


# ── 어드민: 블로그 ────────────────────────────────────────────────
def slugify(text):
    s = re.sub(r"[^0-9A-Za-z가-힣]+", "-", text or "").strip("-").lower()[:120].strip("-")
    return s or "post-" + uuid.uuid4().hex[:8]


@app.get("/admin/posts")
@login_required
def admin_posts():
    # ponytail: 페이지네이션 없이 최근 300개 — 글이 그 이상 쌓이면 admin_list 처럼 page 추가
    posts = db.query("SELECT id, slug, title, status, published_at, updated_at FROM posts "
                     "ORDER BY COALESCE(published_at, created_at) DESC, id DESC LIMIT 300")
    now = kst_naive_now()
    for p in posts:
        p["live"] = p["status"] == "published" and p["published_at"] is not None and p["published_at"] <= now
    return render_template("admin_posts.html", posts=posts)


@app.route("/admin/posts/new", methods=["GET", "POST"], endpoint="admin_post_new")
@app.route("/admin/posts/<int:post_id>/edit", methods=["GET", "POST"], endpoint="admin_post_edit")
@login_required
def admin_post_form(post_id=None):
    post = {}
    if post_id:
        post = db.query_one("SELECT * FROM posts WHERE id=%s", (post_id,))
        if not post:
            abort(404)
    if request.method == "GET":
        return render_template("admin_post_form.html", post=post)

    check_csrf()
    f = request.form
    post = dict(post, title=(f.get("title") or "").strip()[:200], summary=(f.get("summary") or "").strip()[:500],
                body=f.get("body") or "", cover_image=(f.get("cover_image") or "").strip()[:255],
                status=f.get("status") if f.get("status") in ("draft", "published") else "draft")
    post["slug"] = slugify((f.get("slug") or "").strip() or post["title"])
    error = None
    raw_pub = (f.get("published_at") or "").strip()
    try:
        post["published_at"] = datetime.strptime(raw_pub, "%Y-%m-%dT%H:%M") if raw_pub else None
    except ValueError:
        error, post["published_at"] = "발행 시각 형식이 올바르지 않습니다.", None
    if post["status"] == "published" and not post["published_at"]:
        post["published_at"] = kst_naive_now()
    if not post["title"] or not post["body"].strip():
        error = "제목과 본문을 입력하세요."
    elif post["cover_image"] and not post["cover_image"].startswith(("/static/uploads/", "https://")):
        error = "대표 이미지 주소가 올바르지 않습니다."
    elif db.query_one("SELECT id FROM posts WHERE slug=%s AND id<>%s", (post["slug"], post_id or 0)):
        error = f"이미 쓰는 주소(slug)입니다: {post['slug']}"
    if error:
        return render_template("admin_post_form.html", post=post, error=error), 400

    cols = ("slug", "title", "summary", "body", "cover_image", "status", "published_at")
    vals = [(post[c] or None) if c in ("summary", "cover_image") else post[c] for c in cols]
    if post_id:
        db.execute("UPDATE posts SET " + ", ".join(f"{c}=%s" for c in cols) + " WHERE id=%s", vals + [post_id])
    else:
        db.execute(f"INSERT INTO posts ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})", vals)
    return redirect(url_for("admin_posts"))


@app.post("/admin/posts/<int:post_id>/delete")
@login_required
def admin_post_delete(post_id):
    check_csrf()
    db.execute("DELETE FROM posts WHERE id=%s", (post_id,))
    return redirect(url_for("admin_posts"))


@app.post("/admin/posts/preview")
@login_required
def admin_post_preview():
    check_csrf()
    data = request.get_json(silent=True) or {}
    return jsonify({"html": mdlite.render(data.get("body") or "", alt=data.get("title") or "")})


UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "uploads")
MAX_UPLOAD = 5 * 1024 * 1024


@app.post("/admin/posts/upload")
@login_required
def admin_post_upload():
    """jpg/jpeg/png/webp, 5MB 이하 → Pillow 검증 → 긴 변 1600px webp (uuid 파일명)"""
    check_csrf()
    file = request.files.get("image")
    if not file or not file.filename:
        return jsonify({"error": "파일을 선택하세요."}), 400
    if file.filename.rsplit(".", 1)[-1].lower() not in ("jpg", "jpeg", "png", "webp"):
        return jsonify({"error": "jpg, png, webp 파일만 올릴 수 있습니다."}), 400
    data = file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        return jsonify({"error": "5MB 이하 파일만 올릴 수 있습니다."}), 400
    try:
        Image.open(io.BytesIO(data)).verify()
        img = Image.open(io.BytesIO(data))
        if img.format not in ("JPEG", "PNG", "WEBP"):
            raise ValueError(img.format)
        img = ImageOps.exif_transpose(img)
        img.thumbnail((1600, 1600))
        img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        name = uuid.uuid4().hex + ".webp"
        img.save(os.path.join(UPLOAD_DIR, name), "WEBP", quality=85)
    except Exception:
        return jsonify({"error": "이미지 파일이 아니거나 손상되었습니다."}), 400
    return jsonify({"url": f"/static/uploads/{name}"})


# ── CLI ──────────────────────────────────────────────────────────
@app.cli.command("init-db")
def init_db_command():
    """schema.sql 실행 — 전부 IF NOT EXISTS 라 운영 DB에 다시 돌려도 안전 (posts 테이블 추가 마이그레이션 겸용)."""
    with open(os.path.join(os.path.dirname(__file__), "schema.sql"), encoding="utf-8") as f:
        sql = f.read()
    conn = db.get_db()
    with conn.cursor() as cur:
        for stmt in [s.strip() for s in sql.split(";") if s.strip()]:
            cur.execute(stmt)
    click.echo("DB 초기화 완료.")


@app.cli.command("create-admin")
@click.argument("username")
@click.password_option()
def create_admin_command(username, password):
    """어드민 계정 생성/비밀번호 재설정: flask create-admin <username>"""
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    existing = db.query_one("SELECT id FROM admins WHERE username=%s", (username,))
    if existing:
        db.execute("UPDATE admins SET password_hash=%s WHERE username=%s", (pw_hash, username))
        click.echo(f"어드민 '{username}' 비밀번호를 재설정했습니다.")
    else:
        db.execute("INSERT INTO admins (username, password_hash) VALUES (%s, %s)",
                   (username, pw_hash))
        click.echo(f"어드민 '{username}' 계정을 생성했습니다.")


if __name__ == "__main__":
    app.run(debug=True)
