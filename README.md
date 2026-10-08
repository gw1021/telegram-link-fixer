# telegram-link-fixer

텔레그램 그룹에 올라온 링크의 추적 파라미터를 제거하고, X/Instagram/TikTok/Reddit 링크는 임베드가 되는 도메인으로 바꿔 올리는 봇. URL만 있는 텍스트 메시지는 변환 링크를 올린 뒤 원본을 삭제해 중복 표시를 줄인다.

## 변환 규칙

| 대상 | 변환 |
|---|---|
| X / Twitter (`/user/status/id`) | `fixupx.com`, 쿼리 제거 |
| Instagram (`/p/`, `/reel/`, `/reels/`, `/tv/`) | `kkinstagram.com`, 쿼리 제거 |
| TikTok (`/@user/video/id`) | `vxtiktok.com`, 쿼리 제거 |
| Reddit (`/r/sub/comments/...`) | `rxddit.com`, 쿼리 제거 |
| YouTube / youtu.be | `v`, `list`, `t`만 유지 |
| 그 외 | `utm_*`, `fbclid`, `gclid`, `igshid`, `si` 등 추적 파라미터 제거 |

`t.me` 링크와 다른 봇의 메시지는 무시한다. **URL만 있는 메시지**만 처리하며, 문장 속에 섞인 링크는 건드리지 않는다.

## 동작

URL만 있는 텍스트 메시지는 **작성자 이름 + 변환 링크 + 미리보기**를 새 메시지로 올리고, 전송에 성공하면 원본을 삭제한다. 새 메시지의 발신자는 봇이다.

- **URL만 있는 텍스트 메시지**: `공유자: 작성자 이름 (@사용자명)`과 링크를 올린 뒤 원본을 삭제한다. 이름을 누르면 작성자 프로필로 연결되며, 사용자명이 없는 경우에도 이름에 프로필 링크를 건다. 여러 링크 중 변환 대상이 아닌 링크도 함께 보존한다.
- 이름과 성이 모두 한글이고 성이 1~2글자이면 `권우 최` 대신 `최권우`처럼 성+이름 순서로 붙여 표시한다. 외국어 이름이나 성 없이 등록한 이름은 기존 표기를 유지한다.
- 익명 관리자나 채널 명의의 메시지는 개인 계정 대신 Telegram이 제공하는 그룹/채널 이름을 표시한다.
- **사진/영상 등의 URL만 있는 caption**: 첨부물을 보존하기 위해 원본은 그대로 두고 변환된 링크만 답장한다.
- **글자가 섞인 메시지**: 아무것도 하지 않는다.
- 변환할 링크가 없으면 아무것도 하지 않는다.
- 포럼에서는 같은 토픽에 올리고, 원본이 답장이었다면 그 답장 대상을 유지한다.
- 새 메시지 전송에 실패하면 원본을 삭제하지 않는다. 원본 삭제에 실패하면 두 메시지가 남고 로그에 오류를 기록한다.
- 미리보기는 첫 번째 변환 링크를 사용하며, 표시 여부는 Telegram과 임베드 서비스에 따라 달라질 수 있다.

## 설치

Python 3.10 이상과 [uv](https://docs.astral.sh/uv/)가 필요하다.

1. [@BotFather](https://t.me/BotFather)에서 봇을 만들고 토큰을 받는다.
2. `/setprivacy`에서 해당 봇을 **Disable**로 설정한다. 이미 그룹에 있던 봇은 다시 초대해야 적용된다.
3. 봇을 그룹에 초대하고 **관리자**로 지정한다. 슈퍼그룹에서는 **메시지 삭제** 권한을 켠다. 다른 추가 관리 권한은 필요 없다. 원본 삭제에 필요한 권한은 [Telegram Bot API 안내](https://core.telegram.org/bots/api#deletemessage)를 참고한다.

```bash
git clone https://github.com/gw1021/telegram-link-fixer.git
cd telegram-link-fixer
uv sync
BOT_TOKEN=123456:ABC... uv run python link_fixer_bot.py
```

`uv sync`가 프로젝트의 `.venv`와 필요한 의존성을 관리한다.

## 환경변수

| 이름 | 필수 | 설명 |
|---|---|---|
| `BOT_TOKEN` | O | BotFather 토큰 |

## systemd

먼저 프로젝트 디렉터리에서 의존성을 동기화한다.

```bash
cd /home/pi/telegram-link-fixer
uv sync
```

`/etc/linkfixer/env` (권한 `600`):

```
BOT_TOKEN=123456:ABC...
```

`/etc/systemd/system/linkfixer.service`:

```ini
[Unit]
Description=Telegram Link Fixer Bot
After=network-online.target
Wants=network-online.target

[Service]
User=pi
WorkingDirectory=/home/pi/telegram-link-fixer
EnvironmentFile=/etc/linkfixer/env
ExecStart=/home/pi/telegram-link-fixer/.venv/bin/python link_fixer_bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now linkfixer
journalctl -u linkfixer -f
```

## 규칙 수정

`link_fixer_bot.py`의 `RULES`에 항목을 추가한다.

```python
"example.com": {"host": "embed.example.com", "keep": set(), "path_re": r"^/post/\d+"},
```

- `host`: 교체할 도메인 (생략 시 유지)
- `keep`: 남길 쿼리 파라미터 (소문자)
- `path_re`: 이 경로일 때만 적용 (생략 시 전체)

규칙이 없는 사이트에서 제거할 파라미터는 `TRACKING_EXACT`, `TRACKING_PREFIXES`에 추가한다.

## 문제 해결

- 반응이 없음: Privacy Mode가 Disable인지, 봇을 재초대했는지 확인
- 원본과 변환 링크가 둘 다 남음: 봇의 관리자/메시지 삭제 권한과 로그를 확인. 사진/영상 caption의 원본은 삭제하지 않는 것이 정상 동작
- 미리보기가 안 뜸: 임베드 서비스 도메인이 바뀌었을 수 있으므로 `RULES`의 `host`를 교체

## 제한

- Instagram `/share/...` 링크는 리다이렉트를 따라가야 하므로 처리하지 않는다.
- 편집된 메시지는 처리하지 않는다.
- 링크 앞뒤에 글자가 있는 메시지는 처리하지 않는다.
- 숨겨진 하이퍼링크(text_link)는 처리하지 않는다.
- 원본을 삭제하면 원본 메시지의 반응과 해당 메시지를 가리키던 답장 연결은 새 메시지로 이전되지 않는다.
- 임베드 서비스는 제3자 서비스이므로 중단되거나 도메인이 바뀔 수 있다.

## License

MIT
