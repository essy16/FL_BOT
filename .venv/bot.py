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

    if len(context.args) != 4:
        await update.message.reply_text(
            "⚠️ Please send the loan details in this format:\n\n"
            "`from_code from_network amount ltv_percent`\n\n"
            "Example:\n`/estimate BTC BTC 1 50`",
            parse_mode="Markdown"
        )
        return

    from_code, from_network, amount, ltv_percent = context.args
    # ltv_percent = str(float(ltv_percent) / 100)  # Convert 50 to 0.5

    url = f"{API_BASE_URL}/v2/loans/estimate"
    headers = {
        "x-api-key": API_KEY,
        "Content-Type": "application/json"
    }
    params = {
    "from_code": from_code.strip().upper(),
    "from_network": from_network.strip().upper(),
    "to_code": "USDT",
    "to_network": "ETH",
    "amount": str(amount).strip(),
    "ltv_percent": ltv_percent,
    "exchange": "direct"
}

    try:
        response = requests.get(url, headers=headers, params=params)
        print("Requested URL:", response.url)
        response.raise_for_status()
        data = response.json()
        print("DEBUG: Raw API Response:", data)

        if str(data.get("result")).lower() == "true" and data.get("response"):
            loan_data = data["response"]
            loan_amount = loan_data.get("amount_to")
            interest = loan_data.get("interest_amounts", {})

            yearly_interest = interest.get("year")
            monthly_interest = interest.get("month")
            daily_interest = interest.get("day")

            await update.message.reply_text(
                f"🎯 Loan Estimate:\n"
                f"- Borrow Amount: {loan_amount} USDT\n"
                f"- Interest per Year: {yearly_interest}%\n"
                f"- Interest per Month: {monthly_interest}%\n"
                f"- Interest per Day: {daily_interest}%"
            )

            user_sessions[telegram_user_id]["latest_estimate"] = {
                "from_code": from_code.upper(),
                "from_network": from_network.upper(),
                "amount": amount,
                "ltv_percent": ltv_percent
            }

        else:
            await update.message.reply_text(f"❌ Could not estimate loan. Reason: {data.get('message', 'Unknown error')}")

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

    if not user_token:
        await update.message.reply_text("❌ Missing user token. Please restart with /start.")
        print("❌ ERROR: Missing user token.")
        return

    if not latest_estimate:
        await update.message.reply_text("⚠️ Please first use /estimate to get a loan offer before creating a loan.")
        print("⚠️ ERROR: No estimate found for user.")
        return

    # Correct the ltv_percent here: divide by 100
    corrected_ltv_percent = latest_estimate["ltv_percent"]
    # str(float(latest_estimate["ltv_percent"]) / 100)

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
            "currency_code": "USDT",
            "currency_network": "ETH"
        },
        "ltv_percent": corrected_ltv_percent,
        "referral": "qUwXXaSe1S"
    }

    print("📤 Creating loan request...")
    print("POST URL:", url)
    print("HEADERS:", headers)
    print("PAYLOAD:", payload)

    try:
        response = requests.post(url, headers=headers, json=payload)
        print("STATUS:", response.status_code)
        print("RESPONSE:", response.text)

        data = response.json()
        response_data = data.get("response", {})


        loan_id = response_data.get("loan_id")

        if loan_id:
            await update.message.reply_text(
                f"🎯 Loan Created Successfully!\n"
                f"- Loan ID: `{loan_id}`\n\n"
                f"👉 Please continue with /confirm to get your deposit address and finalize the loan.",
                parse_mode="Markdown"
            )
            user_sessions[telegram_user_id]["current_loan_id"] = loan_id
        else:
            msg = data.get("message", "Unknown error")
            await update.message.reply_text(f"❌ Failed to create loan. Server says: {msg}")
    except Exception as e:
        logging.error(f"Loan creation failed: {e}")
        await update.message.reply_text("❌ An error occurred while creating your loan. Please try again later.")


async def confirm_loan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_user_id = update.effective_user.id

    if telegram_user_id not in user_sessions:
        await update.message.reply_text("❌ Please authenticate first using /start.")
        return

    user_data = user_sessions.get(telegram_user_id)
    user_token = user_data.get("user_token")
    loan_id = user_data.get("current_loan_id")

    if not user_token or not loan_id:
        await update.message.reply_text("⚠️ No loan to confirm. Please create one with /create.")
        return

    if len(context.args) != 1:
        await update.message.reply_text("⚠️ Please provide the wallet address where you want to receive the loan.\n\nExample:\n`/confirm TXg5...yourAddress`", parse_mode="Markdown")
        return

    receive_address = context.args[0]

    url = f"{API_BASE_URL}/v2/loans/{loan_id}/confirm"
    headers = {
        "x-api-key": API_KEY,
        "x-user-token": user_token,
        "Content-Type": "application/json"
    }
    payload = {
        "loan": {
            "receive_address": receive_address
        },
        "agreed_to_tos": True
    }

    print("📤 Confirming loan...")
    print("POST URL:", url)
    print("HEADERS:", headers)
    print("PAYLOAD:", payload)

    try:
        response = requests.post(url, headers=headers, json=payload)
        print("STATUS:", response.status_code)
        print("RESPONSE:", response.text)

        data = response.json()
        if str(data.get("result")).lower() == "true" or "response" in data:
            await update.message.reply_text("✅ Loan confirmed! Funds will be sent to your provided address.")
        else:
            msg = data.get("message", "Unknown error")
            await update.message.reply_text(f"❌ Could not confirm loan. Server says: {msg}")

    except Exception as e:
        logging.error(f"Loan confirmation failed: {e}")
        await update.message.reply_text("❌ An error occurred while confirming your loan.")


async def pledge_collateral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_user_id = update.effective_user.id

    if telegram_user_id not in user_sessions:
        await update.message.reply_text("❌ Please authenticate first using /start.")
        return

    user_data = user_sessions.get(telegram_user_id)
    user_token = user_data.get("user_token")
    loan_id = user_data.get("current_loan_id")

    if not user_token or not loan_id:
        await update.message.reply_text("⚠️ No loan to pledge for. Please create a loan first with /create.")
        return

    if len(context.args) != 1:
        await update.message.reply_text("⚠️ Please provide the address you’ll use to send the collateral.")
        return

    pledge_address = context.args[0]

    url = f"{API_BASE_URL}/v2/loans/{loan_id}/pledge"
    headers = {
        "x-api-key": API_KEY,
        "x-user-token": user_token,
        "Content-Type": "application/json"
    }
    payload = {
        "address": pledge_address,
        "extra_id": None
    }

    print("\n📤 Pledging collateral...")
    print("POST URL:", url)
    print("HEADERS:", headers)
    print("PAYLOAD:", payload)

    try:
        response = requests.post(url, headers=headers, json=payload)
        print("STATUS:", response.status_code)
        print("RESPONSE:", response.text)

        data = response.json()
        deposit_address = data.get("response", {}).get("deposit_address")

        if deposit_address:
            await update.message.reply_text(
                f"✅ Please send your collateral to this address:\n`{deposit_address}`",
        parse_mode="Markdown"
            )
        else:
            msg = data.get("message", "Unknown error")
            await update.message.reply_text(f"❌ Failed to pledge collateral. Server says: {msg}")

    except Exception as e:
        logging.error(f"Collateral pledge failed: {e}")
        await update.message.reply_text("❌ An error occurred while pledging collateral.")





async def view_loans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_user_id = update.effective_user.id

    if telegram_user_id not in user_sessions:
        await update.message.reply_text("❌ Please authenticate first using /start.")
        return

    user_token = user_sessions[telegram_user_id].get("user_token")
    url = f"{API_BASE_URL}/v2/loans"
    headers = {
        "x-api-key": API_KEY,
        "x-user-token": user_token
    }

    print("\n📥 Fetching active loans...")
    print("GET URL:", url)
    print("HEADERS:", headers)

    try:
        response = requests.get(url, headers=headers)
        print("STATUS:", response.status_code)
        print("RESPONSE:", response.text)

        data = response.json()
        loans = data.get("response", [])

        if not loans:
            await update.message.reply_text("📭 You have no active loans.")
            return

        reply = "📄 *Your Active Loans:*\n"
        for loan in loans:
            loan_id = loan.get("loan_id")
            amount = loan.get("loan", {}).get("expected_amount")
            status = loan.get("status")
            reply += f"\n• ID: `{loan_id}`\n  Amount: {amount} USDT\n  Status: {status}\n"

        await update.message.reply_text(reply, parse_mode="Markdown")

    except Exception as e:
        logging.error(f"Fetching loans failed: {e}")
        await update.message.reply_text("❌ An error occurred while fetching your active loans.")

# Register these new commands in your main() method:
# app.add_handler(CommandHandler("pledge", pledge_collateral))
# app.add_handler(CommandHandler("myloans", view_loans))



# --- Main Application ---
def main():
    app = ApplicationBuilder().token(BOT_KEY).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("estimate", estimate))
    app.add_handler(CommandHandler("create", create_loan))
    app.add_handler(CommandHandler("confirm", confirm_loan))
    app.add_handler(CommandHandler("pledge", pledge_collateral))
    app.add_handler(CommandHandler("myloans", view_loans))


    app.add_handler(MessageHandler(filters.COMMAND, unknown))

    app.run_polling()


if __name__ == "__main__":
    main()