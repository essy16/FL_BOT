import os
# import telebot
import logging
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters


# BOT_KEY = os.getenv('TELEGRAM_API_KEY')
BOT_KEY = "7723028849:AAHkW2FDyBK05KmFyofKGpdrMN9Pa96hMmI"
# bot = telebot.TeleBot(BOT_KEY)

API_BASE_URL = "https://api.coinrabbit.io"

API_KEY = "04b6e4b9-ba09-4d0b-9b6f-13a0bc7cb348"
user_sessions = {}


# --- Setup Logging --- (It's essential for tracking bot process and helping us as deveelopers to track issues within the bot)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)


def authenticate_user(external_id: str) -> str:
    url = f"{API_BASE_URL}/v2/auth/partner"
    headers = {
        "x-api-key": API_KEY,
        "Content-Type": "application/json"
    }
    body = {
        "external_id": external_id
    }
    try:
        response = requests.post(url, headers=headers, json=body)
        print("STATUS:", response.status_code)
        print("RESPONSE:", response.text)
        response.raise_for_status()
        data = response.json()
        token = data.get("response", {}).get("token")
        if not token:
            raise Exception("Token not found in API response.")
        return token
    except Exception as e:
        logging.error(f"Authentication failed: {e}")
        return None
  
    

# --- Command Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_user_id = update.effective_user.id

    # Authenticate the user (using their Telegram ID as external_id)
    user_token = authenticate_user(str(telegram_user_id))
    if user_token:
        user_sessions[telegram_user_id] = {
            "user_token": user_token,
            "latest_estimate": None,
            "current_loan_id": None
        }
        await update.message.reply_text(
            "✅ Successfully authenticated!\nYou can now estimate a loan with /estimate or see /help for more options."
        )
    else:
        await update.message.reply_text(
            "❌ Sorry, authentication failed. Please try again later."
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Here are the commands you can use:\n"
        "/start - Authenticate yourself\n"
        "/estimate - Estimate a loan\n"
        "/create - Create a loan\n"
        "/confirm - Confirm a loan\n"
        "/pledge - Pledge your collateral\n"
        "/myloans - View your active loans\n"
        "/help - Show this help message"
    )


async def estimate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_user_id = update.effective_user.id

    if telegram_user_id not in user_sessions:
        await update.message.reply_text("❌ Please authenticate first using /start.")
        return

    user_token = user_sessions[telegram_user_id]["user_token"]

    # Check if user provided enough arguments
    if len(context.args) != 4:
        await update.message.reply_text(
            "⚠️ Please send the loan details in this format:\n\n"
            "`from_code from_network amount ltv_percent`\n\n"
            "Example:\n`BTC BTC 0.1 50`",
            parse_mode="Markdown"
        )
        return

    from_code, from_network, amount, ltv_percent = context.args

    url = f"{API_BASE_URL}/v2/loans/estimate"
    headers = {
        "x-api-key": API_KEY,
        "Content-Type": "application/json"
    }
    params = {
        "from_code": from_code.upper(),
        "from_network": from_network.upper(),
        "to_code": "USDT",        # Hardcoded for now
        "to_network": "TRX",      # Hardcoded for now
        "amount": amount,
        "ltv_percent": ltv_percent,
        "exchange": "direct"
    }

    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()

        # Extract info from API response
        loan_amount = data.get("loan_amount")
        yearly_interest = data.get("interest_year_percent")
        monthly_interest = data.get("interest_month_percent")
        daily_interest = data.get("interest_day_percent")

        if loan_amount:
            await update.message.reply_text(
                f"🎯 Loan Estimate:\n"
                f"- Borrow Amount: {loan_amount} USDT\n"
                f"- Interest per Year: {yearly_interest}%\n"
                f"- Interest per Month: {monthly_interest}%\n"
                f"- Interest per Day: {daily_interest}%"
            )
            # Save this estimate if needed later
            user_sessions[telegram_user_id]["latest_estimate"] = params
        else:
            await update.message.reply_text("❌ Could not estimate loan. Please check your input.")

    except Exception as e:
        logging.error(f"Loan estimation failed: {e}")
        await update.message.reply_text("❌ An error occurred while estimating your loan. Please try again later.")


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Sorry, I didn't understand that command. Use /help to see available commands."
    )

# --- Main Application ---
def main():
    app = ApplicationBuilder().token(BOT_KEY).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("estimate", estimate))
    app.add_handler(MessageHandler(filters.COMMAND, unknown))  # Catch unknown commands

    app.run_polling()  # ✅ Only ONE app.run_polling()
    app = ApplicationBuilder().token(BOT_KEY).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("estimate", estimate)) 
    app.add_handler(MessageHandler(filters.COMMAND, unknown))  # Catch unknown commands

    app = ApplicationBuilder().token(BOT_KEY).build()

    # Register command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.COMMAND, unknown))  # Catch unknown commands

    # Start bot
    app.run_polling()

if __name__ == "__main__":
    main()