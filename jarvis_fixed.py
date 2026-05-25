#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import subprocess
import json
import threading
import time
import re
import shutil
import random
import glob
import math
import array
import datetime
import requests
import smtplib
import socket
import psutil
import pyperclip
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import tempfile
import argparse

# ----------------------------------------------------------------------
# ПАРСИНГ ФЛАГА GUI
# ----------------------------------------------------------------------
parser = argparse.ArgumentParser()
parser.add_argument("--gui", action="store_true", help="Запустить графический интерфейс")
args = parser.parse_args()

# ----------------------------------------------------------------------
# ГЛОБАЛЬНЫЕ ФЛАГИ: говорит ли Jarvis и активирован ли ассистент
# ----------------------------------------------------------------------
speaking_flag = False
is_active = False

# ----------------------------------------------------------------------
# АКТИВАЦИОННЫЕ ФРАЗЫ И НАСТРОЙКИ
# ----------------------------------------------------------------------
ACTIVATION_PHRASES = ["хэй джарвис", "джарвис", "слуга", "подопечный"]
ACTIVATION_RESPONSE = "Добро пожаловать, сэр"
TIMEOUT_AFTER_COMMAND = 240        # секунд бездействия до деактивации
DEACTIVATION_WORDS = ["отбой", "спасибо", "хватит", "отключайся", "замолчи"]

# ----------------------------------------------------------------------
# ОЗВУЧКА С БЛОКИРОВКОЙ МИКРОФОНА
# ----------------------------------------------------------------------
def speak_text(text):
    global speaking_flag
    print(f"Jarvis: {text}")
    speaking_flag = True
    try:
        try:
            from gtts import gTTS
            tts = gTTS(text=text, lang='ru', slow=False)
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as f:
                tts.save(f.name)
                if 'pygame' in sys.modules:
                    import pygame
                    pygame.mixer.music.load(f.name)
                    pygame.mixer.music.play()
                    while pygame.mixer.music.get_busy():
                        time.sleep(0.05)
                else:
                    subprocess.run(['mpg123', f.name], check=False)
                os.unlink(f.name)
            return
        except:
            pass
        try:
            import pyttsx3
            engine = pyttsx3.init()
            for v in engine.getProperty('voices'):
                if 'russian' in v.name.lower() or 'русский' in v.name.lower():
                    engine.setProperty('voice', v.id)
                    break
            engine.setProperty('rate', 150)
            engine.say(text)
            engine.runAndWait()
            return
        except:
            pass
        subprocess.run(['espeak', '-v', 'ru', text], check=False)
    finally:
        speaking_flag = False

def activation_response():
    speak_text(ACTIVATION_RESPONSE)

def deactivate_after_timeout():
    global is_active
    time.sleep(TIMEOUT_AFTER_COMMAND)
    if is_active:
        is_active = False
        speak_text("Отключаюсь, сэр. Позовите меня снова, если я понадоблюсь.")

# ----------------------------------------------------------------------
# НАСТРОЙКИ (почта, новости, MQTT – при необходимости заполните)
# ----------------------------------------------------------------------
EMAIL_ADDRESS = ""
EMAIL_PASSWORD = ""
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
RECIPIENT_EMAIL = ""
NEWS_API_KEY = ""
MQTT_BROKER = "localhost"
MQTT_PORT = 1883

# ----------------------------------------------------------------------
# ЗВУКОВЫЕ ЭФФЕКТЫ
# ----------------------------------------------------------------------
SOUND_PACK_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Jarvis_Sound_Pack")
if not os.path.isdir(SOUND_PACK_DIR):
    SOUND_PACK_DIR = None

KEYWORD_MAP = {
    "activation": ["да сэр", "джарвис"],
    "default":    ["всегда к вашим услугам", "всёгда", "хорошо", "выполняю"],
    "create":     ["создали новый элемент", "создано"],
    "danger":     ["аварийное", "осторожно"],
    "hide":       ["незамеченным", "скрыто"],
}

try:
    import pygame
    pygame.mixer.init()
    SOUND_ENABLED = True
except:
    SOUND_ENABLED = False

sound_cache = {}

def load_sounds():
    if not SOUND_ENABLED or not SOUND_PACK_DIR:
        return
    for wav in glob.glob(os.path.join(SOUND_PACK_DIR, "*.wav")) + glob.glob(os.path.join(SOUND_PACK_DIR, "*.mp3")):
        name = os.path.basename(wav).lower()
        for cat, kw in KEYWORD_MAP.items():
            if any(k in name for k in kw):
                try:
                    sound_cache.setdefault(cat, []).append(pygame.mixer.Sound(wav))
                    print(f"Звук {cat}: {os.path.basename(wav)}")
                except:
                    pass
        if "да сэр(второй)" in name:
            sound_cache.setdefault("default_alt", []).append(pygame.mixer.Sound(wav))

def play_category(category):
    sounds = sound_cache.get(category) or sound_cache.get("default") or sound_cache.get("default_alt")
    if sounds:
        random.choice(sounds).play()
    else:
        beep()

def beep():
    if SOUND_ENABLED:
        try:
            duration = 0.2
            samples = int(22050 * duration)
            buf = array.array('h', [int(32767 * math.sin(2 * math.pi * 800 * t / 22050)) for t in range(samples)])
            pygame.mixer.Sound(buffer=buf.tobytes()).play()
        except:
            pass
    else:
        print('\a', end='', flush=True)

# ----------------------------------------------------------------------
# СИСТЕМНЫЕ КОМАНДЫ
# ----------------------------------------------------------------------
def run_cmd(cmd, capture=False):
    try:
        if capture:
            return subprocess.check_output(cmd, shell=True, text=True).strip()
        else:
            subprocess.run(cmd, shell=True, check=False)
    except:
        return ""

def volume_set(p): run_cmd(f"pactl set-sink-volume @DEFAULT_SINK@ {max(0,min(100,p))}%"); play_category("default")
def volume_change(d): run_cmd(f"pactl set-sink-volume @DEFAULT_SINK@ {d}%"); play_category("default")
def volume_mute(): run_cmd("pactl set-sink-mute @DEFAULT_SINK@ toggle"); play_category("default")
def brightness_set(p): run_cmd(f"brightnessctl s {max(0,min(100,p))}%"); play_category("default")
def brightness_change(d): run_cmd(f"brightnessctl s {d}%"); play_category("default")
def get_brightness():
    try:
        cur = int(run_cmd("brightnessctl g", capture=True))
        maxb = int(run_cmd("brightnessctl m", capture=True))
        return int(round(cur / maxb * 100))
    except:
        return None
def lock_screen(): run_cmd("loginctl lock-session"); play_category("default")
def sleep(): run_cmd("systemctl suspend"); play_category("default")
def shutdown(): play_category("danger"); run_cmd("systemctl poweroff")
def reboot(): play_category("danger"); run_cmd("systemctl reboot")
def get_time(): now = time.strftime("%H:%M"); speak_text(f"Сейчас {now}"); return now
def get_date(): today = time.strftime("%d.%m.%Y"); speak_text(f"Сегодня {today}"); return today

def window_close(): run_cmd("xdotool getactivewindow windowclose"); play_category("default")
def window_minimize(): run_cmd("xdotool getactivewindow windowminimize"); play_category("default")
def window_maximize(): wid = run_cmd("xdotool getactivewindow", capture=True); run_cmd(f"xdotool windowsize {wid} 100% 100%"); play_category("default")
def window_normalize(): wid = run_cmd("xdotool getactivewindow", capture=True); run_cmd(f"xdotool windowstate {wid} 0"); play_category("default")
def window_switch(): run_cmd("xdotool key Alt+Tab"); play_category("default")
def show_desktop(): run_cmd("xdotool key Super+d"); play_category("default")
def mouse_left_click(): run_cmd("xdotool click 1"); play_category("default")
def mouse_right_click(): run_cmd("xdotool click 3"); play_category("default")
def mouse_double_click(): run_cmd("xdotool click --repeat 2 1"); play_category("default")
def mouse_move(dx, dy): run_cmd(f"xdotool mousemove_relative -- {dx} {dy}"); play_category("default")
def kill_process(name): run_cmd(f"pkill -f {name}"); play_category("default")
def get_cpu(): val = psutil.cpu_percent(interval=1); speak_text(f"Загрузка процессора {val}%"); return val
def get_memory(): mem = psutil.virtual_memory(); msg = f"Занято {mem.used//1024**2} МБ из {mem.total//1024**2} МБ ({mem.percent}%)"; speak_text(msg); return msg
def get_disk(): usage = shutil.disk_usage("/"); msg = f"Свободно {usage.free//1024**2} МБ из {usage.total//1024**2} МБ"; speak_text(msg); return msg
def system_info(): return f"Имя: {socket.gethostname()}\nЦП: {psutil.cpu_percent()}%\nПамять: {psutil.virtual_memory().percent}%\nДиск: {shutil.disk_usage('/').percent}%"

def media_play_pause(): run_cmd("playerctl play-pause"); play_category("default")
def media_next(): run_cmd("playerctl next"); play_category("default")
def media_prev(): run_cmd("playerctl previous"); play_category("default")
def media_stop(): run_cmd("playerctl stop"); play_category("default")

def open_folder(path): run_cmd(f"xdg-open '{os.path.expanduser(path)}'"); play_category("default")
def create_folder(path): os.makedirs(path, exist_ok=True); play_category("create")
def delete_file(path): os.remove(path) if os.path.isfile(path) else None; play_category("default")
def copy_file(src, dst): shutil.copy2(src, dst); play_category("default")
def move_file(src, dst): shutil.move(src, dst); play_category("default")
def take_screenshot():
    name = f"screenshot_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    path = os.path.join(os.path.expanduser("~/Pictures"), name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    run_cmd(f"gnome-screenshot -f '{path}'")
    speak_text(f"Скриншот сохранён: {name}")
    play_category("default")
def toggle_keyboard_layout(): run_cmd("setxkbmap -query | grep layout | grep -q us && setxkbmap ru || setxkbmap us"); play_category("default")

def get_weather():
    try:
        geo = requests.get('http://ip-api.com/json/').json()
        city = geo.get('city', 'Москва') if geo.get('status') != 'fail' else 'Москва'
        g = requests.get(f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&language=ru&format=json").json()
        if not g.get("results"): return f"Город {city} не найден."
        lat, lon = g["results"][0]["latitude"], g["results"][0]["longitude"]
        name = g["results"][0]["name"]
        w = requests.get(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true").json()
        curr = w.get("current_weather", {})
        temp = curr.get("temperature")
        wind = curr.get("windspeed")
        code = curr.get("weathercode")
        desc = "ясно"
        if code in [51,53,55,61,63,65,80,81,82]: desc = "дождь"
        elif code in [71,73,75,77,85,86]: desc = "снег"
        elif code in [95,96,99]: desc = "гроза"
        return f"Погода в {name}: {temp}°C, {desc}, ветер {wind} м/с."
    except Exception as e: return f"Ошибка погоды: {e}"

def get_news():
    if not NEWS_API_KEY: return "Новости не настроены"
    try:
        data = requests.get(f"https://newsapi.org/v2/top-headlines?country=ru&category=technology&apiKey={NEWS_API_KEY}").json()
        articles = data.get("articles", [])[:5]
        if not articles: return "Новостей нет"
        return "Новости технологий:\n" + "\n".join(f"{i+1}. {a['title']}" for i,a in enumerate(articles))
    except: return "Ошибка новостей"

def set_reminder(text, sec):
    def _r(): time.sleep(sec); speak_text(f"Напоминание: {text}"); play_category("default")
    threading.Thread(target=_r, daemon=True).start()
    return f"Напомню через {sec} секунд: {text}"
def set_timer(sec):
    def _t(): time.sleep(sec); play_category("danger"); speak_text(f"Таймер на {sec} секунд завершён!")
    threading.Thread(target=_t, daemon=True).start()
    return f"Таймер на {sec} секунд"
def send_email_report():
    if not EMAIL_ADDRESS: return "Email не настроен"
    try:
        msg = MIMEMultipart(); msg["From"]=EMAIL_ADDRESS; msg["To"]=RECIPIENT_EMAIL; msg["Subject"]="Отчёт от Jarvis"
        msg.attach(MIMEText(system_info(), "plain"))
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT); server.starttls(); server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.send_message(msg); server.quit()
        return "Отчёт отправлен"
    except Exception as e: return f"Ошибка почты: {e}"
def mqtt_publish(msg):
    try:
        import paho.mqtt.client as mqtt
        c = mqtt.Client(); c.connect(MQTT_BROKER, MQTT_PORT, 60); c.publish("jarvis/command", msg); c.disconnect()
        return f"MQTT: {msg}"
    except: return "MQTT не подключён"
def open_youtube(): run_cmd("xdg-open https://youtube.com"); play_category("default"); speak_text("Открываю YouTube")

# ----------------------------------------------------------------------
# НЕЙРОСЕТЬ (Ollama) – Qwen2.5:3b
# ----------------------------------------------------------------------
def is_ollama_available():
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=2)
        return r.status_code == 200
    except:
        return False

def ask_ollama(prompt, model="qwen2.5:3b"):
    if not is_ollama_available():
        return "Нейросеть не доступна. Убедитесь, что Ollama запущен (ollama serve) и модель загружена."
    try:
        full_prompt = f"Ты — голосовой ассистент Джарвис. Отвечай только на русском языке, грамотно, кратко и по делу. Не выдумывай факты. Вопрос: {prompt}"
        resp = requests.post("http://localhost:11434/api/generate",
                             json={"model": model, "prompt": full_prompt, "stream": False, "options": {"num_predict": 256}},
                             timeout=30)
        if resp.status_code == 200:
            answer = resp.json().get("response", "Нет ответа").strip()
            return answer if answer else "Нейросеть не дала ответа."
        else:
            return f"Ошибка нейросети: HTTP {resp.status_code}"
    except requests.exceptions.Timeout:
        return "Нейросеть отвечает слишком долго. Попробуйте позже."
    except Exception as e:
        return f"Ошибка нейросети: {e}"

# ----------------------------------------------------------------------
# ОСНОВНОЙ ОБРАБОТЧИК КОМАНД (с авто-отправкой в нейросеть)
# ----------------------------------------------------------------------
def process_command(raw_cmd):
    global is_active
    if not raw_cmd:
        return
    raw_cmd = raw_cmd.strip()
    cmd_lower = raw_cmd.lower()

    # --- 1. Активация ---
    # Проверяем, есть ли в начале фразы активационное слово
    activation_used = None
    for phrase in ACTIVATION_PHRASES:
        if cmd_lower.startswith(phrase):
            activation_used = phrase
            break
        # также может быть не в начале, но тогда активируем без удаления?
        # Лучше если фраза содержит активацию в любом месте – активируем, но команду не обрезаем
        # Однако для удобства: если активация в начале – удаляем её из команды
    if activation_used:
        if not is_active:
            is_active = True
            activation_response()
            threading.Thread(target=deactivate_after_timeout, daemon=True).start()
        # Удаляем активационную фразу из команды, чтобы обработать остаток
        remaining = raw_cmd[len(activation_used):].strip()
        if remaining:
            # Рекурсивно обработаем остаток как команду уже в активном состоянии
            process_command(remaining)
        return

    # Если есть активационная фраза не в начале? Например "сделай то-то джарвис"
    # На всякий случай проверим вхождение
    if not is_active:
        for phrase in ACTIVATION_PHRASES:
            if phrase in cmd_lower:
                if not is_active:
                    is_active = True
                    activation_response()
                    threading.Thread(target=deactivate_after_timeout, daemon=True).start()
                # Если после активации есть ещё текст – обработаем
                # Удаляем первое вхождение фразы
                idx = cmd_lower.find(phrase)
                if idx != -1:
                    remaining = raw_cmd[:idx] + raw_cmd[idx+len(phrase):]
                    remaining = remaining.strip()
                    if remaining:
                        process_command(remaining)
                return

    # --- Если не активны – игнорируем всё ---
    if not is_active:
        return

    # --- 2. Деактивация ---
    if cmd_lower in DEACTIVATION_WORDS:
        is_active = False
        speak_text("Всегда рад помочь, сэр. До связи.")
        return

    # --- 3. Специальные команды (без ключевых слов, но с паттернами) ---
    # youtube
    if "ютуб" in cmd_lower or "youtube" in cmd_lower:
        open_youtube(); return
    # погода
    if "погода" in cmd_lower:
        speak_text(get_weather()); play_category("default"); return
    # новости
    if "новости" in cmd_lower:
        speak_text(get_news()); play_category("default"); return
    # напомни через ...
    remind = re.search(r"напомни через\s+(\d+)\s+(.+)", cmd_lower)
    if remind:
        speak_text(set_reminder(remind.group(2), int(remind.group(1)))); play_category("default"); return
    # таймер ...
    timer = re.search(r"таймер\s+(\d+)", cmd_lower)
    if timer:
        speak_text(set_timer(int(timer.group(1)))); play_category("default"); return
    # скопируй текст ...
    if cmd_lower.startswith("скопируй текст "):
        pyperclip.copy(raw_cmd[15:]); speak_text("Текст скопирован в буфер"); play_category("default"); return
    # умный дом ...
    mqtt_match = re.search(r"умный дом\s+(.+)", cmd_lower)
    if mqtt_match:
        speak_text(mqtt_publish(mqtt_match.group(1))); play_category("default"); return

    # --- 4. Команды с числами ---
    m = re.search(r"громкость\s+(\d+)", cmd_lower)
    if m: volume_set(int(m.group(1))); return
    m = re.search(r"яркость\s+(\d+)", cmd_lower)
    if m: brightness_set(int(m.group(1))); return
    m = re.search(r"двинь мышь влево на (\d+)", cmd_lower)
    if m: mouse_move(-int(m.group(1)), 0); return
    m = re.search(r"двинь мышь вправо на (\d+)", cmd_lower)
    if m: mouse_move(int(m.group(1)), 0); return
    m = re.search(r"двинь мышь вверх на (\d+)", cmd_lower)
    if m: mouse_move(0, -int(m.group(1))); return
    m = re.search(r"двинь мышь вниз на (\d+)", cmd_lower)
    if m: mouse_move(0, int(m.group(1))); return
    m = re.search(r"заверши процесс (\w+)", cmd_lower)
    if m: kill_process(m.group(1)); return
    m = re.search(r"создай папку (.+)", cmd_lower)
    if m: create_folder(os.path.expanduser(m.group(1))); return
    m = re.search(r"удали файл (.+)", cmd_lower)
    if m: delete_file(os.path.expanduser(m.group(1))); return
    m = re.search(r"скопируй (.+) в (.+)", cmd_lower)
    if m: copy_file(os.path.expanduser(m.group(1)), os.path.expanduser(m.group(2))); return
    m = re.search(r"перемести (.+) в (.+)", cmd_lower)
    if m: move_file(os.path.expanduser(m.group(1)), os.path.expanduser(m.group(2))); return

    # --- 5. Фиксированные команды (словарь) ---
    fixed = {
        "громче": lambda: volume_change(5),
        "тише": lambda: volume_change(-5),
        "выключи звук": volume_mute,
        "включи звук": volume_mute,
        "ярче": lambda: brightness_change(10),
        "темнее": lambda: brightness_change(-10),
        "яркость": lambda: speak_text(f"Яркость {get_brightness()}%"),
        "заблокируй экран": lock_screen,
        "спящий режим": sleep,
        "выключи компьютер": shutdown,
        "перезагрузи компьютер": reboot,
        "который час": get_time,
        "какое сегодня число": get_date,
        "закрой окно": window_close,
        "сверни окно": window_minimize,
        "разверни окно": window_maximize,
        "нормальное окно": window_normalize,
        "смени окно": window_switch,
        "покажи рабочий стол": show_desktop,
        "кликни": mouse_left_click,
        "правый клик": mouse_right_click,
        "двойной клик": mouse_double_click,
        "двинь мышь влево": lambda: mouse_move(-50, 0),
        "двинь мышь вправо": lambda: mouse_move(50, 0),
        "двинь мышь вверх": lambda: mouse_move(0, -50),
        "двинь мышь вниз": lambda: mouse_move(0, 50),
        "загрузка процессора": get_cpu,
        "свободная память": get_memory,
        "свободное место на диске": get_disk,
        "состояние системы": lambda: speak_text(system_info()),
        "пауза": media_play_pause,
        "продолжи": media_play_pause,
        "следующий трек": media_next,
        "предыдущий трек": media_prev,
        "стоп": media_stop,
        "открой домашнюю папку": lambda: open_folder("~"),
        "открой загрузки": lambda: open_folder("~/Загрузки"),
        "открой рабочий стол": lambda: open_folder("~/Рабочий стол"),
        "проверь интернет": lambda: speak_text("Интернет есть" if run_cmd("ping -c 1 8.8.8.8") else "Интернета нет"),
        "мой ip": lambda: speak_text(f"IP: {run_cmd('curl -s ifconfig.me', capture=True)}"),
        "включи вайфай": lambda: run_cmd("nmcli radio wifi on"),
        "выключи вайфай": lambda: run_cmd("nmcli radio wifi off"),
        "скопируй": lambda: speak_text("Что скопировать?"),
        "вставь": lambda: speak_text(f"Буфер: {pyperclip.paste()[:200]}"),
        "запусти терминал": lambda: run_cmd("gnome-terminal &"),
        "запусти браузер": lambda: run_cmd("firefox &"),
        "запусти редактор": lambda: run_cmd("code &"),
        "открой гугл": lambda: run_cmd("xdg-open https://google.com"),
        "открой яндекс": lambda: run_cmd("xdg-open https://ya.ru"),
        "скриншот": take_screenshot,
        "смени раскладку": toggle_keyboard_layout,
        "отчёт на почту": lambda: speak_text(send_email_report()),
        "что ты умеешь": lambda: speak_text("Я умею управлять громкостью, яркостью, окнами, мышью, процессами, медиа, файлами, сетью, буфером, делать скриншоты, переключать раскладку, ставить таймеры, напоминания, показывать погоду, новости, состояние системы, отправлять отчёт на почту, общаться через нейросеть и выполнять bash-команды."),
        "помощь": lambda: speak_text("Команды: громче, тише, выключи звук, громкость число, ярче, темнее, яркость, заблокируй экран, спящий режим, выключи компьютер, перезагрузи компьютер, который час, какое сегодня число, закрой окно, сверни окно, разверни окно, нормальное окно, смени окно, покажи рабочий стол, кликни, правый клик, двойной клик, двигай мышь, загрузка процессора, свободная память, свободное место, состояние системы, пауза, следующий трек, предыдущий трек, открой домашнюю папку, открой загрузки, проверь интернет, мой ip, включи вайфай, выключи вайфай, скопируй, вставь, запусти терминал, запусти браузер, открой гугл, открой яндекс, открой youtube, скриншот, смени раскладку, таймер 10, напомни через 30 купить молоко, погода, новости, отчёт на почту, спроси, что ты умеешь, отбой чтобы выключить меня"),
    }
    for phrase, action in fixed.items():
        if cmd_lower == phrase or cmd_lower.startswith(phrase + " ") or cmd_lower.endswith(" " + phrase):
            action()
            return

    # --- 6. Если ничего не подошло – отправляем в нейросеть ---
    speak_text("Обращаюсь к нейросети...")
    answer = ask_ollama(raw_cmd)
    speak_text(answer)
    play_category("default")

# ----------------------------------------------------------------------
# РАСПОЗНАВАНИЕ РЕЧИ (Google или Vosk)
# ----------------------------------------------------------------------
try:
    import speech_recognition as sr
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "SpeechRecognition"])
    import speech_recognition as sr

MODEL_PATH = "vosk-model-small-ru-0.22"
if os.path.exists(MODEL_PATH):
    try:
        import vosk
        vosk.SetLogLevel(-1)
        model = vosk.Model(MODEL_PATH)
        rec_vosk = vosk.KaldiRecognizer(model, 16000)
        use_vosk = True
        print("Используется офлайн-распознавание Vosk")
    except:
        use_vosk = False
        print("Vosk не загрузился, используем Google")
else:
    use_vosk = False
    print("Модель Vosk не найдена, используем Google Speech Recognition")

# ----------------------------------------------------------------------
# КОНСОЛЬНЫЙ РЕЖИМ
# ----------------------------------------------------------------------
def console_mode():
    global speaking_flag, is_active
    recognizer = sr.Recognizer()
    mic = sr.Microphone()
    recognizer.energy_threshold = 200
    recognizer.dynamic_energy_threshold = False
    recognizer.pause_threshold = 0.5
    recognizer.phrase_time_limit = 6

    with mic as source:
        recognizer.adjust_for_ambient_noise(source, duration=1.5)
        # Никакой фразы при запуске

        def text_input():
            while True:
                try:
                    line = sys.stdin.readline().strip()
                    if line:
                        process_command(line)
                except:
                    time.sleep(0.1)
        threading.Thread(target=text_input, daemon=True).start()

        while True:
            if speaking_flag:
                time.sleep(0.1)
                continue
            try:
                audio = recognizer.listen(mic, timeout=3, phrase_time_limit=6)
            except sr.WaitTimeoutError:
                continue
            text = ""
            if use_vosk:
                if rec_vosk.AcceptWaveform(audio.get_wav_data()):
                    text = json.loads(rec_vosk.Result()).get("text", "")
            else:
                try:
                    text = recognizer.recognize_google(audio, language="ru-RU")
                except:
                    pass
            if text and len(text) >= 3:
                print(f"Распознано: {text}")
                beep()
                if is_active:
                    print("[Активен]")
                else:
                    print("[Ожидание активации]")
                process_command(text)
            time.sleep(0.1)

# ----------------------------------------------------------------------
# ГРАФИЧЕСКИЙ РЕЖИМ (PySide6)
# ----------------------------------------------------------------------
def gui_mode():
    global speaking_flag, is_active
    from PySide6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QWidget, QTextEdit,
                                   QLineEdit, QPushButton, QHBoxLayout, QLabel)
    from PySide6.QtCore import Qt, QThread, Signal
    from PySide6.QtGui import QFont

    class Worker(QThread):
        new_command = Signal(str)
        def __init__(self):
            super().__init__()
            self.recognizer = None
            self.mic = None

        def run(self):
            global speaking_flag, is_active
            try:
                self.recognizer = sr.Recognizer()
                self.recognizer.energy_threshold = 200
                self.recognizer.dynamic_energy_threshold = False
                self.recognizer.pause_threshold = 0.5
                self.recognizer.phrase_time_limit = 4
                self.mic = sr.Microphone()
                with self.mic as source:
                    self.recognizer.adjust_for_ambient_noise(source, duration=1)
                print("Микрофон готов")
            except Exception as e:
                print(f"Ошибка микрофона: {e}")
                return

            while True:
                if speaking_flag:
                    time.sleep(0.1)
                    continue
                try:
                    with self.mic as source:
                        audio = self.recognizer.listen(source, timeout=1, phrase_time_limit=4)
                except sr.WaitTimeoutError:
                    continue
                except Exception as e:
                    print(f"Ошибка записи: {e}")
                    time.sleep(0.5)
                    continue
                text = ""
                if use_vosk:
                    if rec_vosk.AcceptWaveform(audio.get_wav_data()):
                        text = json.loads(rec_vosk.Result()).get("text", "")
                else:
                    try:
                        text = self.recognizer.recognize_google(audio, language="ru-RU")
                    except:
                        pass
                if text and len(text) >= 3:
                    self.new_command.emit(text)
                time.sleep(0.1)

    class JarvisGUI(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("Jarvis Assistant")
            self.setMinimumSize(800, 600)
            self.setStyleSheet("""
                QMainWindow { background-color: #1e1e2e; }
                QTextEdit, QLineEdit { background-color: #2a2a3a; color: #f0f0f0; border: 1px solid #3a3a4a; border-radius: 8px; font-size: 14px; }
                QPushButton { background-color: #3a3a4a; color: white; border-radius: 8px; padding: 8px; font-weight: bold; }
                QPushButton:hover { background-color: #4a4a5a; }
                QLabel { color: #f0f0f0; font-size: 16px; font-weight: bold; }
            """)
            central = QWidget()
            self.setCentralWidget(central)
            layout = QVBoxLayout(central)
            self.output = QTextEdit()
            self.output.setReadOnly(True)
            self.output.setFont(QFont("Monospace", 10))
            
            self.status_label = QLabel("🔴 Ожидание активации (скажите 'хэй джарвис')")
            self.status_label.setStyleSheet("color: #ff5555; font-weight: bold;")
            layout.addWidget(self.status_label)
            layout.addWidget(self.output)
            
            input_layout = QHBoxLayout()
            self.input_line = QLineEdit()
            self.input_line.setPlaceholderText("Введите команду...")
            self.input_line.returnPressed.connect(self.send_text_command)
            self.send_btn = QPushButton("Отправить")
            self.send_btn.clicked.connect(self.send_text_command)
            input_layout.addWidget(self.input_line)
            input_layout.addWidget(self.send_btn)
            layout.addLayout(input_layout)
            # Не говорим ничего при запуске, только пишем в лог
            self.append_message("Jarvis", "Ассистент запущен. Скажите «хэй джарвис», чтобы активировать меня.")
            self.worker = Worker()
            self.worker.new_command.connect(self.on_voice_command)
            self.worker.start()
            
            self.status_timer = threading.Thread(target=self.update_status, daemon=True)
            self.status_timer.start()

        def update_status(self):
            while True:
                if is_active:
                    self.status_label.setText("🟢 АКТИВЕН (слушаю команды)")
                    self.status_label.setStyleSheet("color: #55ff55; font-weight: bold;")
                else:
                    self.status_label.setText("🔴 Ожидание активации (скажите 'хэй джарвис')")
                    self.status_label.setStyleSheet("color: #ff5555; font-weight: bold;")
                time.sleep(0.5)

        def append_message(self, sender, msg):
            self.output.append(f"[{sender}] {msg}")
            self.output.verticalScrollBar().setValue(self.output.verticalScrollBar().maximum())

        def send_text_command(self):
            text = self.input_line.text().strip()
            if text:
                self.input_line.clear()
                self.append_message("Вы", text)
                self.execute(text)

        def on_voice_command(self, text):
            status = "Активен" if is_active else "Ожидание"
            self.append_message(f"Голос [{status}]", text)
            self.execute(text)

        def execute(self, cmd):
            def gui_print(*args, **kwargs):
                builtins_print(*args, **kwargs)
                msg = " ".join(str(a) for a in args)
                if msg.startswith("Jarvis:"):
                    self.append_message("Jarvis", msg[7:].strip())
            import builtins
            global builtins_print
            builtins_print = builtins.print
            builtins.print = gui_print
            try:
                process_command(cmd)
            finally:
                builtins.print = builtins_print

    app = QApplication(sys.argv)
    window = JarvisGUI()
    window.show()
    sys.exit(app.exec())

# ----------------------------------------------------------------------
# ЗАПУСК
# ----------------------------------------------------------------------
if __name__ == "__main__":
    load_sounds()
    print("Проверка модели Qwen2.5:3b...")
    result = subprocess.run(["ollama", "list"], capture_output=True, text=True)
    if "qwen2.5:3b" not in result.stdout:
        print("Модель qwen2.5:3b не найдена. Загружаем...")
        subprocess.run(["ollama", "pull", "qwen2.5:3b"])
    else:
        print("Модель qwen2.5:3b уже установлена.")
    
    if args.gui:
        try:
            import PySide6
        except ImportError:
            print("PySide6 не установлен. Установите: pip install PySide6")
            sys.exit(1)
        gui_mode()
    else:
        console_mode()