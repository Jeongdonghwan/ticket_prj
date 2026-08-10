"""텔레그램 알림 봇 — token/chat_id 미설정 또는 전송 실패 시 조용히 skip."""
import os
import threading

import requests


def _send(text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=3,
        )
    except requests.RequestException:
        pass


def notify(text):
    """알림 전송 (백그라운드 스레드 — 요청 응답을 지연시키지 않음)."""
    threading.Thread(target=_send, args=(text,), daemon=True).start()


def notify_new_inquiry(inq):
    amt = inq.get("amount_final")
    notify(
        "[알뜰티켓] 새 문의 접수\n"
        f"유입: {inq.get('source_label', inq.get('source', ''))}\n"
        f"이름: {inq.get('name', '')}\n"
        f"연락처: {inq.get('phone', '')}\n"
        f"신청 금액: {f'{amt:,}원' if amt else '-'}\n"
        f"내용: {(inq.get('memo') or '-')[:200]}"
    )


def notify_status_change(name, phone, status_label, amount_final=None):
    msg = f"[알뜰티켓] 상태 변경 → {status_label}\n이름: {name}\n연락처: {phone}"
    if amount_final:
        msg += f"\n매입금액: {amount_final:,}원"
    notify(msg)
