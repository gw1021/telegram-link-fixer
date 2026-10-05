# telegram-link-fixer

텔레그램 그룹에 올라온 링크의 추적 파라미터를 제거하고, X/Instagram/TikTok/Reddit 링크는 임베드가 되는 도메인으로 바꿔 답장으로 올리는 봇.

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

봇은 다른 사용자의 메시지를 편집하거나 삭제하지 않는다. URL만 있는 메시지에 변환된 링크를 **답장**으로 올린다.

- **URL만 있는 메시지** (텍스트, caption 모두): 원본은 그대로 두고 변환된 링크만 답장한다.
- **글자가 섞인 메시지**: 아무것도 하지 않는다.
- 변환할 링크가 없으면 아무것도 하지 않는다.

## 설치

Python 3.10 이상, `python-telegram-bot` 20.8 이상이 필요하다.

1. [@BotFather](https://t.me/BotFather)에서 봇을 만들고 토큰을 받는다.
2. `/setprivacy`에서 해당 봇을 **Disable**로 설정한다. 이미 그룹에 있던 봇은 다시 초대해야 적용된다.
3. 봇을 그룹에 초대한다. 관리자 권한은 필요 없다.

```bash
git clone https://github.com/gw1021/telegram-link-fixer.git
cd telegram-link-fixer
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
BOT_TOKEN=123456:ABC... ./venv/bin/python link_fixer_bot.py
```

## 환경변수

| 이름 | 필수 | 설명 |
|---|---|---|
| `BOT_TOKEN` | O | BotFather 토큰 |

## systemd

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
ExecStart=/home/pi/telegram-link-fixer/venv/bin/python link_fixer_bot.py
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
- 미리보기가 안 뜸: 임베드 서비스 도메인이 바뀌었을 수 있으므로 `RULES`의 `host`를 교체

## 제한

- Instagram `/share/...` 링크는 리다이렉트를 따라가야 하므로 처리하지 않는다.
- 편집된 메시지는 처리하지 않는다.
- 링크 앞뒤에 글자가 있는 메시지는 처리하지 않는다.
- 숨겨진 하이퍼링크(text_link)는 처리하지 않는다.
- 임베드 서비스는 제3자 서비스이므로 중단되거나 도메인이 바뀔 수 있다.

## License

MIT
