"""알뜰티켓 — 랜딩 + 상담 어드민 (Flask + MariaDB)"""
import os
import time
from collections import defaultdict, deque
from datetime import datetime
from functools import wraps

from dotenv import load_dotenv

load_dotenv()

import bcrypt
import click
from flask import (
    Flask, Response, abort, jsonify, redirect, render_template,
    request, session, url_for,
)

import config
import db
from notify import notify_new_inquiry, notify_status_change

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-secret")
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
    }


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
    return Response("User-agent: *\nDisallow: /admin\n", mimetype="text/plain")


@app.post("/api/inquiry")
def api_inquiry():
    data = request.get_json(silent=True) or request.form
    # honeypot: 봇이 채우는 숨김 필드 — 채워져 있으면 저장 없이 정상 응답
    if (data.get("website") or "").strip():
        return jsonify({"ok": True})
    if rate_limited("inquiry", limit=5):
        return jsonify({"ok": False, "error": "요청이 너무 많습니다. 잠시 후 다시 시도해주세요."}), 429
    name = (data.get("name") or "").strip()[:40]
    phone = (data.get("phone") or "").strip()[:20]
    if not name or not phone:
        return jsonify({"ok": False, "error": "이름과 연락처를 입력해주세요."}), 400
    category = (data.get("category") or "").strip()[:40] or None
    amount_range = (data.get("amount") or "").strip()[:20] or None
    memo = (data.get("memo") or "").strip()[:2000] or None
    db.execute(
        "INSERT INTO inquiries (source, name, phone, category, amount_range, memo) "
        "VALUES ('form', %s, %s, %s, %s, %s)",
        (name, phone, category, amount_range, memo),
    )
    notify_new_inquiry({"source_label": "하단폼", "name": name, "phone": phone,
                        "category": category, "amount_range": amount_range, "memo": memo})
    return jsonify({"ok": True}), 201


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


# ── CLI ──────────────────────────────────────────────────────────
@app.cli.command("init-db")
def init_db_command():
    """schema.sql 실행 (테이블 생성)."""
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
