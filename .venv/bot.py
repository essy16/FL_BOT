# FlexLend Bot - GUI-Enhanced Loan Workflow
import os
import logging
import requests
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ConversationHandler,
)

load_dotenv()
BOT_KEY = os.getenv("TELEGRAM_API_KEY")
API_BASE_URL = "https://api.coinrabbit.io"
API_KEY = os.getenv("API_KEY")
user_sessions = {}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# --- Conversation States ---
ESTIMATE_AMOUNT, CONFIRM_WALLET, PLEDGE_ADDRESS = range(3)


# --- Auth Function ---
def authenticate_user(external_id: str) -> str:
    try:
        r = requests.post(
            f"{API_BASE_URL}/v2/auth/partner",
            headers={"x-api-key": API_KEY, "Content-Type": "application/json"},
            json={"external_id": external_id},
        )
        r.raise_for_status()
        return r.json().get("response", {}).get("token")
    except Exception as e:
        logging.error(f"Authentication failed: {e}")
        return None


# --- START ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    token = authenticate_user(str(user_id))
    if token:
        user_sessions[user_id] = {"user_token": token}
        keyboard = [
            [InlineKeyboardButton("📈 Estimate a Loan", callback_data="estimate")]
        ]
        await update.message.reply_text(
            "👋 Welcome to *FlexLend*!", parse_mode="Markdown"
        )
        await update.message.reply_text(
            "👇 Choose an action:", reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text("❌ Authentication failed.")


# --- Handle Main Menu ---
async def handle_menu_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "estimate":
        await query.edit_message_text(
            "💰 Please enter loan details: Format: `BTC BTC 0.1 0.8`",
            parse_mode="Markdown",
        )
        return ESTIMATE_AMOUNT
    elif query.data == "create":
        return await create_loan(update, context)
    elif query.data == "confirm":
        await query.edit_message_text("🪪 Send your wallet address to receive funds:")
        return CONFIRM_WALLET
    elif query.data == "pledge":
        await query.edit_message_text("🔐 Send your collateral return address:")
        return PLEDGE_ADDRESS
    elif query.data == "myloans":
        return await view_loans(update, context)


# --- Handle Estimate Input ---
async def process_estimate_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_sessions:
        await update.message.reply_text("❌ Please start with /start")
        return ConversationHandler.END

    args = update.message.text.strip().split()
    if len(args) != 4:
        await update.message.reply_text(
            "⚠️ Format error. Use: `BTC BTC 0.1 0.8`", parse_mode="Markdown"
        )
        return ESTIMATE_AMOUNT

    from_code, from_network, amount, ltv_percent = args
    params = {
        "from_code": from_code.upper(),
        "from_network": from_network.upper(),
        "to_code": "USDT",
        "to_network": "ETH",
        "amount": amount,
        "ltv_percent": ltv_percent,
        "exchange": "direct",
    }
    headers = {"x-api-key": API_KEY, "Content-Type": "application/json"}

    try:
        r = requests.get(
            f"{API_BASE_URL}/v2/loans/estimate", headers=headers, params=params
        )
        r.raise_for_status()
        data = r.json()
        if data.get("result") and data.get("response"):
            res = data["response"]
            user_sessions[user_id]["latest_estimate"] = params
            await update.message.reply_text(
                f"🎯 *Loan Estimate*\n- Amount: {res['amount_to']} USDT\n"
                f"- Yearly: {res['interest_amounts']['year']}%\n"
                f"- Monthly: {res['interest_amounts']['month']}%\n"
                f"- Daily: {res['interest_amounts']['day']}%",
                parse_mode="Markdown",
            )
            keyboard = [
                [InlineKeyboardButton("📝 Create Loan", callback_data="create")]
            ]
            await update.message.reply_text(
                "✅ Continue below:", reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.message.reply_text("❌ Failed to estimate. Please try again.")
    except Exception as e:
        logging.error(f"Estimate error: {e}")
        await update.message.reply_text("❌ Error occurred.")
    return ConversationHandler.END


# --- Create Loan ---
async def create_loan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = user_sessions.get(user_id)
    if not session or not session.get("latest_estimate"):
        await update.callback_query.edit_message_text(
            "⚠️ Please estimate your loan first."
        )
        return ConversationHandler.END
    estimate = session["latest_estimate"]
    headers = {
        "x-api-key": API_KEY,
        "x-user-token": session["user_token"],
        "Content-Type": "application/json",
    }
    payload = {
        "deposit": {
            "currency_code": estimate["from_code"],
            "currency_network": estimate["from_network"],
            "expected_amount": estimate["amount"],
        },
        "loan": {"currency_code": "USDT", "currency_network": "ETH"},
        "ltv_percent": estimate["ltv_percent"],
        "referral": "qUwXXaSe1S",
    }
    try:
        r = requests.post(f"{API_BASE_URL}/v2/loans", headers=headers, json=payload)
        r.raise_for_status()
        data = r.json().get("response", {})
        loan_id = data.get("loan_id")
        if loan_id:
            user_sessions[user_id]["current_loan_id"] = loan_id
            await update.callback_query.edit_message_text(
                f"🎉 Loan Created!\nID: `{loan_id}`\nTap below to confirm it.",
                parse_mode="Markdown",
            )
            keyboard = [
                [InlineKeyboardButton("✅ Confirm Loan", callback_data="confirm")]
            ]
            await update.callback_query.message.reply_text(
                "👇", reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.callback_query.edit_message_text("❌ Could not create loan.")
    except Exception as e:
        logging.error(f"Loan creation failed: {e}")
        await update.callback_query.edit_message_text("❌ Server error.")
    return ConversationHandler.END


async def process_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = user_sessions.get(user_id)
    if not session or "current_loan_id" not in session:
        await update.message.reply_text("❌ No loan created.")
        return ConversationHandler.END

    wallet = update.message.text.strip()
    payload = {"loan": {"receive_address": wallet}, "agreed_to_tos": True}
    headers = {
        "x-api-key": API_KEY,
        "x-user-token": session["user_token"],
        "Content-Type": "application/json",
    }
    try:
        r = requests.post(
            f"{API_BASE_URL}/v2/loans/{session['current_loan_id']}/confirm",
            headers=headers,
            json=payload,
        )
        r.raise_for_status()
        await update.message.reply_text("✅ Loan confirmed. Funds will arrive shortly.")
        keyboard = [
            [InlineKeyboardButton("🔐 Pledge Collateral", callback_data="pledge")]
        ]
        await update.message.reply_text(
            "Next step:", reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        logging.error(f"Confirm error: {e}")
        await update.message.reply_text("❌ Could not confirm loan.")
    return ConversationHandler.END


# --- Pledge Address Input ---
async def process_pledge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = user_sessions.get(user_id)
    if not session or "current_loan_id" not in session:
        await update.message.reply_text("❌ No active loan found.")
        return ConversationHandler.END

    addr = update.message.text.strip()
    headers = {
        "x-api-key": API_KEY,
        "x-user-token": session["user_token"],
        "Content-Type": "application/json",
    }
    payload = {"address": addr, "extra_id": None}
    try:
        r = requests.post(
            f"{API_BASE_URL}/v2/loans/{session['current_loan_id']}/pledge",
            headers=headers,
            json=payload,
        )
        r.raise_for_status()
        deposit = r.json().get("response", {}).get("deposit_address")
        if deposit:
            await update.message.reply_text(
                f"📥 Send your collateral to: `{deposit}`", parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("❌ Failed to get deposit address.")
    except Exception as e:
        logging.error(f"Pledge error: {e}")
        await update.message.reply_text("❌ Error during pledge.")
    return ConversationHandler.END


# --- View Loans ---
async def view_loans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    token = user_sessions.get(user_id, {}).get("user_token")
    if not token:
        await update.callback_query.edit_message_text(
            "❌ Please authenticate with /start"
        )
        return

    try:
        r = requests.get(
            f"{API_BASE_URL}/v2/loans",
            headers={"x-api-key": API_KEY, "x-user-token": token},
        )
        r.raise_for_status()
        loans = r.json().get("response", [])
        if not loans:
            await update.callback_query.edit_message_text("📭 No active loans.")
            return
        txt = "📋 *Active Loans:*\n"
        for loan in loans:
            txt += f"\n• ID: `{loan['loan_id']}`\n  Amount: {loan['loan']['expected_amount']} USDT\n  Status: {loan['status']}\n"
        await update.callback_query.edit_message_text(txt, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"View error: {e}")
        await update.callback_query.edit_message_text("❌ Couldn't fetch loan info.")
    return ConversationHandler.END


# --- Setup Main App ---
def main():
    app = ApplicationBuilder().token(BOT_KEY).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ESTIMATE_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_estimate_input)
            ],
            CONFIRM_WALLET: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_wallet)
            ],
            PLEDGE_ADDRESS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_pledge)
            ],
        },
        fallbacks=[
            MessageHandler(
                filters.COMMAND,
                lambda u, c: u.message.reply_text("Unknown. Try /start"),
            )
        ],
    )

    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(handle_menu_click))
    app.run_polling()


if __name__ == "__main__":
    main()
