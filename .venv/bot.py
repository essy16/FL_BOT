import os
# import telebot
import logging
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


print(os.getenv('API_KEY'))


BOT_KEY = os.getenv('TELEGRAM_API_KEY')
# BOT_KEY = "7723028849:AAHkW2FDyBK05KmFyofKGpdrMN9Pa96hMmI"
# bot = telebot.TeleBot(BOT_KEY)

API_BASE_URL = "https://api.coinrabbit.io"

API_KEY = os.getenv('API_KEY')
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
            "Example:\n`/estimate BTC BTC 1 0.5`",
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
        "to_code": "USDT",            # Hardcoded to USDT
        "to_network": "ETH",          
        "amount": amount,              
        "ltv_percent": ltv_percent,    
        "exchange": "reverse"          
    }

    try:
        response = requests.get(url, headers=headers, params=params)
        print("Requested URL:", response.url)  # ✅ Print for debug
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


async def create_loan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_user_id = update.effective_user.id

    if telegram_user_id not in user_sessions:
        await update.message.reply_text("❌ Please authenticate first using /start.")
        return

    user_data = user_sessions.get(telegram_user_id)
    user_token = user_data.get("user_token")
    latest_estimate = user_data.get("latest_estimate")

    if not latest_estimate:
        await update.message.reply_text("⚠️ Please first use /estimate to get a loan offer before creating a loan.")
        return

    url = f"{API_BASE_URL}/v2/loans"
    headers = {
        "x-api-key": API_KEY,
        "x-user-token": user_token,
        "Content-Type": "application/json"
    }

    payload = {
        "deposit": {
            "currency_code": latest_estimate["from_code"],
            "currency_network": latest_estimate["from_network"],
            "expected_amount": latest_estimate["amount"]
        },
        "loan": {
            "currency_code": "USDT",          # Hardcoded to USDT
            "currency_network": "TRX"         # Hardcoded to TRX
        },
        "ltv_percent": latest_estimate["ltv_percent"],
        "referral": "qUwXXaSe1S"               # Optional: your referral code
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

        loan_id = data.get("loan_id")
        deposit_address = data.get("deposit_address")

        if loan_id and deposit_address:
            await update.message.reply_text(
                f"🎯 Loan Created Successfully!\n"
                f"- Loan ID: `{loan_id}`\n"
                f"- Deposit Address: `{deposit_address}`\n\n"
                f"👉 Please send your collateral to the address above to activate your loan.",
                parse_mode="Markdown"
            )
            # Save current loan_id in session
            user_sessions[telegram_user_id]["current_loan_id"] = loan_id
        else:
            await update.message.reply_text("❌ Failed to create loan. Please try again later.")

    except Exception as e:
        logging.error(f"Loan creation failed: {e}")
        await update.message.reply_text("❌ An error occurred while creating your loan. Please try again later.")


# --- Main Application ---
def main():
    app = ApplicationBuilder().token(BOT_KEY).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("estimate", estimate))
    app.add_handler(CommandHandler("create", create_loan))
    app.add_handler(MessageHandler(filters.COMMAND, unknown))

    app.run_polling()


if __name__ == "__main__":
    main()