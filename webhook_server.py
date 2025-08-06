import os
import json
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from bot import application, confirm_checkout  # Reuse your existing app & logic
import logging

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

# --- Telegram Webhook Route ---
@app.route("/webhook", methods=["POST"])
async def telegram_webhook():
    if request.method == "POST":
        data = request.get_json(force=True)
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
        return "ok"
    return "invalid method", 405


# --- PayPal Webhook (Mock Example) ---
@app.route("/paypal/webhook", methods=["POST"])
def paypal_webhook():
    data = request.get_json()

    # 👇 Replace this with real IPN validation later
    payer_email = data.get("payer_email")
    amount = float(data.get("amount", 0))
    user_id = data.get("custom")  # Should be Telegram user ID sent in checkout

    logging.info(f"✅ PayPal payment from {payer_email} for ${amount:.2f} (User ID: {user_id})")

    # TODO: Match this user/order and confirm it automatically
    # You could load cart_data.json and call confirm_checkout() if you're confident

    return jsonify({"status": "received"}), 200


# --- Startup Webhook Registration ---
if __name__ == "__main__":
    TOKEN = os.getenv("TELEGRAM_API_TOKEN")
    PUBLIC_URL = os.getenv("PUBLIC_URL")  # set this in Render secrets like https://your-service.onrender.com

    if not PUBLIC_URL:
        raise Exception("Missing PUBLIC_URL in env!")

    async def main():
        await application.bot.set_webhook(f"{PUBLIC_URL}/webhook")
        print(f"🚀 Webhook set to {PUBLIC_URL}/webhook")

    import asyncio
    asyncio.run(main())

    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
