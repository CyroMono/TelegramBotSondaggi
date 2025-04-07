import gspread
import logging
import re
import requests
from bs4 import BeautifulSoup
import urllib.parse
from google.oauth2.service_account import Credentials
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, PollAnswerHandler, ContextTypes
import os
import json

# === CONFIG ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# === GOOGLE SHEETS ===
scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

google_credentials_json = os.getenv("GOOGLE_CREDENTIALS")

if google_credentials_json:
    # Carica il contenuto JSON come dizionario
    credentials_info = json.loads(google_credentials_json)
    creds = Credentials.from_service_account_info(credentials_info, scopes=scope)
else:
    print("Errore: la variabile d'ambiente 'GOOGLE_CREDENTIALS' non è impostata.")
    exit(1)

client = gspread.authorize(creds)
sheet = client.open("Sondaggioni").sheet1

# === VARIABILI ===
current_poll_id = None
poll_message_id = None
poll_chat_id = None
poll_options = []
poll_votes = [0, 0]
poll_row = 2


def cerca_immagine(query):
    headers = {
        "User-Agent": "Mozilla/5.0"
    }
    query_encoded = urllib.parse.quote_plus(query)
    url = f"https://www.bing.com/images/search?q={query_encoded}&form=HDRSC2"

    resp = requests.get(url, headers=headers)
    soup = BeautifulSoup(resp.text, "html.parser")

    # Cerca immagini nella struttura HTML di Bing
    image_elements = soup.find_all("a", class_="iusc")

    for element in image_elements:
        m = element.get("m")
        if m:
            try:
                data = eval(m)  # contiene JSON-like con info immagine
                if "murl" in data:
                    return data["murl"]
            except:
                continue

    return None

async def new_round(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_poll_id, poll_message_id, poll_chat_id, poll_options, poll_votes, poll_row

    # Recupera i dati dalla riga corrente
    row = sheet.row_values(poll_row)
    if len(row) < 2 or not row[0] or not row[1]:
        await update.message.reply_text("Nessuna opzione disponibile. Usa /start per ripartire.")
        return

    option1, option2 = row[0], row[1]
    poll_options = [option1, option2]
    poll_votes = [0, 0]
    poll_chat_id = update.effective_chat.id

    # immagini
    url1 = cerca_immagine(option1)
    url2 = cerca_immagine(option2)

    if url1:
        await context.bot.send_photo(chat_id=poll_chat_id, photo=url1, caption=option1)
    else:
        await context.bot.send_message(chat_id=poll_chat_id, text=f"[Nessuna immagine trovata] {option1}")

    if url2:
        await context.bot.send_photo(chat_id=poll_chat_id, photo=url2, caption=option2)
    else:
        await context.bot.send_message(chat_id=poll_chat_id, text=f"[Nessuna immagine trovata] {option2}")

    # Invia il sondaggio
    msg = await context.bot.send_poll(
        chat_id=poll_chat_id,
        question="Scegli!",
        options=poll_options,
        is_anonymous=False
    )
    current_poll_id = msg.poll.id
    poll_message_id = msg.message_id

    # Fissa il sondaggio nel gruppo
    await context.bot.pin_message(chat_id=poll_chat_id, message_id=poll_message_id)

async def receive_vote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global poll_votes, poll_options, poll_row, current_poll_id

    answer = update.poll_answer
    if answer.poll_id != current_poll_id:
        return

    selected = answer.option_ids[0]
    poll_votes[selected] += 1

    if poll_votes[selected] >= 6:
        winner = poll_options[selected]
        await context.bot.stop_poll(poll_chat_id, poll_message_id)
        sheet.update_cell(poll_row, 3, winner)
        await context.bot.send_message(chat_id=poll_chat_id, text=f"🏆 Vince: {winner}!\nProssimo round...")
        poll_row += 1
        await new_round(update, context)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global poll_row
    poll_row = 2

    # Cerca la prima riga vuota nella colonna dei vincitori (colonna 3)
    while True:
        winner = sheet.cell(poll_row, 3).value
        if not winner:  # Se la cella del vincitore è vuota
            break  # Trova la prima riga con il vincitore vuoto
        poll_row += 1  # Se la cella del vincitore non è vuota, passa alla riga successiva

    await update.message.reply_text(f"🔁 Riparto dalla riga {poll_row}.")
    await new_round(update, context)

async def main():
    logging.basicConfig(level=logging.INFO)
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("newround", new_round))
    app.add_handler(PollAnswerHandler(receive_vote))

    print("✅ Bot avviato.")
    await app.run_polling()

if __name__ == '__main__':
    import asyncio
    import nest_asyncio

    nest_asyncio.apply()
    asyncio.get_event_loop().run_until_complete(main())
