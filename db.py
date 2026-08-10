"""MariaDB 커넥션 헬퍼 — 요청당 커넥션(flask.g) 관리."""
import os

import pymysql
from flask import g


def _connect():
    return pymysql.connect(
        host=os.environ.get("DB_HOST", "127.0.0.1"),
        port=int(os.environ.get("DB_PORT", "3306")),
        user=os.environ.get("DB_USER", "ticket"),
        password=os.environ.get("DB_PASSWORD", ""),
        database=os.environ.get("DB_NAME", "ticket_db"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def get_db():
    if "db" not in g:
        g.db = _connect()
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query(sql, args=None):
    with get_db().cursor() as cur:
        cur.execute(sql, args)
        return cur.fetchall()


def query_one(sql, args=None):
    with get_db().cursor() as cur:
        cur.execute(sql, args)
        return cur.fetchone()


def execute(sql, args=None):
    """INSERT/UPDATE/DELETE 실행, lastrowid 반환."""
    with get_db().cursor() as cur:
        cur.execute(sql, args)
        return cur.lastrowid


def init_app(app):
    app.teardown_appcontext(close_db)
