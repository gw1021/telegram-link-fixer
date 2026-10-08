import logging
import os
import re
import sys
from html import escape
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from telegram import LinkPreviewOptions, ReplyParameters, Update
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

# 실행: BOT_TOKEN=123:ABC python link_fixer_bot.py
TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    sys.exit("BOT_TOKEN 환경변수를 설정하세요")

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO
)
log = logging.getLogger("linkfixer")

URL_RE = re.compile(r"https?://[^\s<>]+")
TRAILING = ".,)!?>]\"'"

# 건드리지 않을 도메인
IGNORE_HOSTS = {"t.me", "telegram.me"}

# 사이트별 규칙 (키는 www./m./mobile. 제거 후 소문자 호스트)
#   host:    바꿀 도메인 (없으면 그대로)
#   keep:    남길 쿼리 파라미터 (소문자, 나머지는 제거)
#   path_re: 이 경로일 때만 적용 (없으면 전체)
RULES = {
    "twitter.com": {"host": "fixupx.com", "keep": set(), "path_re": r"^/\w+/status/\d+"},
    "x.com": {"host": "fixupx.com", "keep": set(), "path_re": r"^/\w+/status/\d+"},
    "instagram.com": {"host": "kkinstagram.com", "keep": set(), "path_re": r"^/(p|reel|reels|tv)/"},
    "tiktok.com": {"host": "vxtiktok.com", "keep": set(), "path_re": r"^/@[^/]+/video/\d+"},
    "reddit.com": {"host": "rxddit.com", "keep": set(), "path_re": r"^/r/\w+/comments/"},
    "youtube.com": {"keep": {"v", "list", "t"}},
    "youtu.be": {"keep": {"t"}},
}

# 규칙 없는 사이트에서 제거할 일반 추적 파라미터 (소문자 비교)
TRACKING_PREFIXES = ("utm_",)
TRACKING_EXACT = {
    "fbclid", "gclid", "dclid", "msclkid", "igshid", "igsh", "mc_cid", "mc_eid",
    "ref_src", "ref_url", "spm", "si", "_hsenc", "_hsmi",
}


def normalize_host(host: str) -> str:
    host = host.lower()
    for prefix in ("www.", "mobile.", "m."):
        if host.startswith(prefix):
            host = host[len(prefix):]
    return host


def fix_url(url: str) -> str | None:
    """바뀐 URL을 반환. 바꿀 게 없으면 None."""
    url = url.rstrip(TRAILING)
    try:
        parts = urlsplit(url)
        host = normalize_host(parts.hostname or "")
    except ValueError:
        return None
    if not host or host in IGNORE_HOSTS:
        return None

    query = parse_qsl(parts.query, keep_blank_values=True)
    rule = RULES.get(host)

    if rule:
        if "path_re" in rule and not re.match(rule["path_re"], parts.path):
            return None
        new_host = rule.get("host")
        new_query = [(k, v) for k, v in query if k.lower() in rule["keep"]]
    else:
        new_host = None
        new_query = [
            (k, v) for k, v in query
            if k.lower() not in TRACKING_EXACT
            and not k.lower().startswith(TRACKING_PREFIXES)
        ]

    # 도메인 교체도 없고 제거된 파라미터도 없으면 변경 없음
    if new_host is None and len(new_query) == len(query):
        return None

    scheme = "https" if new_host else parts.scheme
    netloc = new_host or parts.netloc
    return urlunsplit((scheme, netloc, parts.path, urlencode(new_query), parts.fragment))


async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message  # 새 메시지만 처리하고 편집된 메시지는 제외
    if not msg:
        return
    text = msg.text or msg.caption  # 사진/영상 caption도 검사
    if not text:
        return
    if msg.from_user and msg.from_user.is_bot and not msg.sender_chat:
        return
    # URL 외의 글자가 있으면 대상이 아님
    if URL_RE.sub("", text).strip():
        return

    fixed_links: list[str] = []
    replacement_links: list[str] = []
    for url in URL_RE.findall(text):
        fixed = fix_url(url)
        if fixed and fixed not in fixed_links:
            fixed_links.append(fixed)
        # 원본을 삭제하므로 변환 대상이 아닌 링크도 빠뜨리지 않는다.
        replacement = fixed or url
        if replacement not in replacement_links:
            replacement_links.append(replacement)
    if not fixed_links:
        return

    # caption이 붙은 사진/영상 등은 보존하고 기존처럼 링크만 답장한다.
    if not msg.text:
        try:
            await msg.reply_text("\n".join(fixed_links))
        except TelegramError:
            log.exception("답장 실패")
        return

    if msg.sender_chat:
        author = escape(msg.sender_chat.title or msg.sender_chat.username or "알 수 없음")
    elif msg.from_user:
        label = msg.from_user.full_name
        first_name = msg.from_user.first_name.strip()
        last_name = (msg.from_user.last_name or "").strip()
        # 한글 이름과 1~2글자 한글 성이 따로 등록되어 있으면 성+이름으로 표시한다.
        if re.fullmatch(r"[가-힣]+", first_name) and re.fullmatch(r"[가-힣]{1,2}", last_name):
            label = last_name + first_name
        if msg.from_user.username:
            label += f" (@{msg.from_user.username})"
        author = msg.from_user.mention_html(label)
    else:
        author = "알 수 없음"

    # 원본이 답장이었다면 그 답장 대상을 유지한다. 삭제할 원본에는 답장하지 않는다.
    reply_parameters = None
    if msg.reply_to_message:
        reply_parameters = ReplyParameters(
            message_id=msg.reply_to_message.message_id,
            allow_sending_without_reply=True,
        )

    try:
        await context.bot.send_message(
            chat_id=msg.chat_id,
            text=f"공유자: {author}\n\n" + "\n".join(escape(link) for link in replacement_links),
            parse_mode=ParseMode.HTML,
            message_thread_id=msg.message_thread_id if msg.is_topic_message else None,
            reply_parameters=reply_parameters,
            link_preview_options=LinkPreviewOptions(url=fixed_links[0]),
        )
    except TelegramError:
        log.exception("변환 링크 전송 실패: 원본 유지")
        return

    # 전송이 확인된 뒤에만 원본을 삭제한다.
    try:
        await msg.delete()
    except TelegramError:
        log.exception("원본 삭제 실패: 봇의 관리자/메시지 삭제 권한 확인 필요")


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    log.error("처리 중 오류", exc_info=context.error)


def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(
        MessageHandler((filters.TEXT | filters.CAPTION) & ~filters.COMMAND, handle)
    )
    app.add_error_handler(on_error)
    log.info("봇 시작")
    app.run_polling()


if __name__ == "__main__":
    main()
