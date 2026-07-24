# Развёртывание Оливии на сервере (тест через VPN)

Схема: сервер (Ubuntu/Debian, на нём VPN) крутит backend, ты подключаешься
к VPN с MacBook и открываешь киоск в Chrome. Микрофон в браузере работает
только в «безопасном контексте» — это ключевой нюанс, см. шаг 4.

## 1. Установка на сервере

```bash
ssh user@SERVER
git clone https://github.com/IDhide/AI-stomatology.git
cd AI-stomatology
git checkout claude/dental-ai-assistant-vq3vha

python3 -m venv .venv && source .venv/bin/activate
pip install -r server/requirements.txt

cp server/.env.example server/.env
nano server/.env        # вписать XAI_API_KEY, ELEVENLABS_API_KEY,
                        # ELEVENLABS_VOICE_ID, GROK_MODEL
```

Проверка: `./server/run.sh` → в соседней SSH-сессии
`curl localhost:8000/health` — должно показать llm/stt/tts и llm_model.

## 2. Автозапуск (systemd)

```bash
sudo tee /etc/systemd/system/olivia.service >/dev/null <<'EOF'
[Unit]
Description=Olivia dental AI kiosk backend
After=network-online.target

[Service]
Type=simple
User=USER_НА_СЕРВЕРЕ
WorkingDirectory=/home/USER_НА_СЕРВЕРЕ/AI-stomatology
ExecStart=/home/USER_НА_СЕРВЕРЕ/AI-stomatology/server/run.sh
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now olivia
journalctl -u olivia -f      # живые логи
```

Обновление версии: `cd AI-stomatology && git pull && sudo systemctl restart olivia`.

## 3. Доступ с MacBook

Два варианта, оба рабочие:

**А. SSH-туннель (рекомендую — микрофон работает сразу).**
```bash
ssh -N -L 8000:127.0.0.1:8000 user@SERVER
```
Открыть **http://localhost:8000** в Chrome на MacBook. Для браузера это
localhost → безопасный контекст → микрофон и wake word работают без
всяких сертификатов. Это и есть «общаться через localhost сервера».
(SSH-туннель работает и поверх VPN, и без него — лишь бы был SSH-доступ.)

**Б. Напрямую по VPN-адресу** — `http://10.x.x.x:8000` откроется, но
Chrome ЗАБЛОКИРУЕТ микрофон: http://IP — небезопасный контекст. Обходы:
  - разово для теста: `chrome://flags/#unsafely-treat-insecure-origin-as-secure`
    → вписать `http://10.x.x.x:8000` → Enabled → перезапуск Chrome;
  - правильно для постоянной работы (и для ТВ-панели в клинике):
    поставить Caddy с HTTPS на сервере — 4 строки конфига, скажи, добавлю.

## 4. Доступ «как обычный сайт» — для клиента, без SSH

Все три варианта дают настоящий HTTPS → микрофон работает в Chrome и
на телефоне. Выбор зависит от того, что важнее.

### Вариант А: Tailscale (максимальная приватность, рекомендую)
Приватная сеть между устройствами; снаружи сервис не виден вообще.
```bash
# на сервере
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
sudo tailscale serve --bg 8000     # даёт https://ИМЯ-СЕРВЕРА.ИМЯ-СЕТИ.ts.net
```
Клиент один раз ставит приложение Tailscale (iOS/Android/Mac — 2 минуты),
входит по твоему приглашению — и просто открывает ссылку в браузере.
Сертификат настоящий, ничего настраивать не надо. Кто не в твоей сети —
даже не узнает, что сервис существует.

#### Как «познакомить» клиента через ключ (Tailscale auth key)
Чтобы клиент не ждал ручного одобрения, а вошёл сам по одноразовому ключу:

1. Панель Tailscale → **Settings → Keys → Generate auth key**.
   Поставь: *Reusable* (если пустишь нескольких), *Ephemeral* (устройство
   само отвалится, когда выйдет), срок жизни — например 7 дней.
2. Отдай клиенту ключ (`tskey-auth-…`) и ссылку сервиса.
3. Клиент ставит приложение Tailscale, при входе выбирает
   **«Use an auth key»** и вставляет ключ — устройство сразу в твоей сети.
   На своём телефоне то же самое: приложение → auth key → готово.
4. Открывает `https://ИМЯ-СЕРВЕРА.ИМЯ-СЕТИ.ts.net` — и говорит с Оливией.

Ключ можно отозвать в той же панели в любой момент — доступ мгновенно
закрывается, ссылка снаружи всё так же невидима.

### Вариант Б: свой домен + Caddy (ноль установок у клиента)
Нужен домен (поддомен), направленный A-записью на IP сервера.
```bash
sudo apt install -y caddy
caddy hash-password   # ввести пароль для клиента, скопировать хэш
sudo tee /etc/caddy/Caddyfile >/dev/null <<'EOF'
olivia.ваш-домен.ru {
    basic_auth {
        clinic ХЭШ_ИЗ_КОМАНДЫ_ВЫШЕ
    }
    reverse_proxy 127.0.0.1:8000
}
EOF
sudo systemctl reload caddy
```
Caddy сам получает и продлевает сертификат Let's Encrypt, WebSocket
проксирует из коробки. Клиент открывает ссылку, один раз вводит
логин/пароль — и говорит с Оливией. С любого устройства, без установок.

### Вариант В: Cloudflare Tunnel (быстрая демка за 1 минуту)
Без домена, без открытых портов:
```bash
cloudflared tunnel --url http://localhost:8000
```
Выдаст случайную ссылку вида https://xxx.trycloudflare.com — кидаешь
клиенту, он открывает с телефона. Ссылка живёт, пока запущена команда.
Для постоянной работы у Cloudflare есть именованные туннели + Access
(вход по коду на e-mail), но для «показать сегодня» хватит одной команды.

**Резюме:** показать клиенту сегодня → В; приватный постоянный доступ для
своих → А; «просто сайт с паролем» без установок у клиента → Б.

## 5. Частые вопросы

- **VPN на сервере не мешает?** Нет: backend ходит наружу (api.x.ai,
  api.elevenlabs.io) через тот маршрут, который даёт VPN. Если VPN как раз
  для доступа к этим API — всё сложится само.
- **Логи разговоров** пишутся на сервере в `data/conversations/ГГГГ-ММ-ДД/`:
  `.jsonl` (для скриптов) + `.txt` (открыл и прочитал). Забрать на MacBook:
  `scp -r user@SERVER:~/AI-stomatology/data/conversations ./`
- **Порт наружу не торчит?** 8000 слушается на 0.0.0.0 — закрой его
  фаерволом от интернета (`sudo ufw allow from 10.0.0.0/8 to any port 8000`,
  `sudo ufw enable`), доступ только из VPN/туннеля.
