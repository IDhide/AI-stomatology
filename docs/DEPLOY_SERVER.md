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

## 4. Частые вопросы

- **VPN на сервере не мешает?** Нет: backend ходит наружу (api.x.ai,
  api.elevenlabs.io) через тот маршрут, который даёт VPN. Если VPN как раз
  для доступа к этим API — всё сложится само.
- **Логи разговоров** пишутся на сервере в `data/conversations/ГГГГ-ММ-ДД/`:
  `.jsonl` (для скриптов) + `.txt` (открыл и прочитал). Забрать на MacBook:
  `scp -r user@SERVER:~/AI-stomatology/data/conversations ./`
- **Порт наружу не торчит?** 8000 слушается на 0.0.0.0 — закрой его
  фаерволом от интернета (`sudo ufw allow from 10.0.0.0/8 to any port 8000`,
  `sudo ufw enable`), доступ только из VPN/туннеля.
