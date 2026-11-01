"""data/blog_seed.json 의 글을 posts 에 넣는다 (같은 slug 가 있으면 건너뜀). 서버: ./venv/bin/python scripts/seed_blog.py"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import app, kst_naive_now
import db

with app.app_context():
    n = 0
    for p in json.load(open(os.path.join(os.path.dirname(__file__), "..", "data", "blog_seed.json"), encoding="utf-8")):
        if db.query_one("SELECT id FROM posts WHERE slug=%s", (p["slug"],)):
            continue
        db.execute("INSERT INTO posts (slug, title, summary, body, cover_image, status, published_at) VALUES (%s,%s,%s,%s,%s,'published',%s)",
                   (p["slug"], p["title"], p["summary"], p["body"], p["cover_image"], kst_naive_now()))
        n += 1
    print(f"블로그 글 {n}개 추가")
