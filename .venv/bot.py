# FlexLend Bot - Refactored Version Based on Client Feedback
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

# Load environment variables
load_dotenv()
BOT_KEY = os.getenv("TELEGRAM_API_KEY")
API_BASE_URL = "https://api.coinrabbit.io"
API_KEY = os.getenv("API_KEY")
user_sessions = {}

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# Conversation states
(
    SELECT_COLLATERAL_CURRENCY,
    SELECT_COLLATERAL_NETWORK,
    ENTER_COLLATERAL_AMOUNT,
    SELECT_LOAN_CURRENCY,
    SELECT_LOAN_NETWORK,
    SELECT_LTV_PERCENT,
    ENTER_WALLET,
) = range(7)

# Start command
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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    token = authenticate_user(str(user_id))
    if token:
        user_sessions[user_id] = {"user_token": token}
        keyboard = [
            [InlineKeyboardButton("\U0001F4C8 Estimate a Loan", callback_data="start_estimate")]
        ]
        await update.message.reply_text(
            "\U0001F44B *Welcome to FlexLend!*\n\nI'm here to help you create a crypto-backed loan.\nClick below to get started.",
            parse_mode="Markdown",
        )
        await update.message.reply_text("\u2B07\uFE0F Choose an action:", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text("\u274C Authentication failed.")

# Step 1: Select Collateral Currency
async def handle_estimate_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    user_sessions[update.effective_user.id]["estimate"] = {}
    keyboard = [[InlineKeyboardButton(curr, callback_data=f"collat_curr:{curr}")]
                for curr in ["BTC", "ETH", "LTC"]]
    await update.callback_query.edit_message_text("Select Collateral Currency:", reply_markup=InlineKeyboardMarkup(keyboard))
    return SELECT_COLLATERAL_CURRENCY

# Step 2: Select Collateral Network
async def select_collateral_currency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    currency = update.callback_query.data.split(":")[1]
    user_sessions[update.effective_user.id]["estimate"]["from_code"] = currency
    keyboard = [[InlineKeyboardButton(currency, callback_data=f"collat_net:{currency}")]]
    await update.callback_query.edit_message_text("Select Collateral Network:", reply_markup=InlineKeyboardMarkup(keyboard))
    return SELECT_COLLATERAL_NETWORK

# Step 3: Enter Collateral Amount
async def select_collateral_network(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    network = update.callback_query.data.split(":")[1]
    user_sessions[update.effective_user.id]["estimate"]["from_network"] = network
    await update.callback_query.edit_message_text("Enter Collateral Amount (e.g. 0.1):")
    return ENTER_COLLATERAL_AMOUNT

# Step 4: Select Loan Currency
async def enter_collateral_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amount = update.message.text.strip()
    user_sessions[update.effective_user.id]["estimate"]["amount"] = amount
    keyboard = [[InlineKeyboardButton(curr, callback_data=f"loan_curr:{curr}")]
                for curr in ["USDT", "USDC"]]
    await update.message.reply_text("Select Loan Currency:", reply_markup=InlineKeyboardMarkup(keyboard))
    return SELECT_LOAN_CURRENCY

# Step 5: Select Loan Network
async def select_loan_currency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    loan_curr = update.callback_query.data.split(":")[1]
    user_sessions[update.effective_user.id]["estimate"]["to_code"] = loan_curr
    keyboard = [[InlineKeyboardButton(net, callback_data=f"loan_net:{net}")]
                for net in ["ETH", "TRX", "BSC"]]
    await update.callback_query.edit_message_text("Select Loan Network:", reply_markup=InlineKeyboardMarkup(keyboard))
    return SELECT_LOAN_NETWORK

# Step 6: Select LTV
async def select_loan_network(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    loan_net = update.callback_query.data.split(":")[1]
    user_sessions[update.effective_user.id]["estimate"]["to_network"] = loan_net
    keyboard = [[InlineKeyboardButton(f"{v}%", callback_data=f"ltv:{v}")]
                for v in [30, 40, 50, 60, 70]]
    await update.callback_query.edit_message_text("Select Loan-to-Value Ratio:", reply_markup=InlineKeyboardMarkup(keyboard))
    return SELECT_LTV_PERCENT

# Step 7: Show Estimate and Ask for Wallet
async def select_ltv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    ltv = update.callback_query.data.split(":")[1]
    user_id = update.effective_user.id
    user_sessions[user_id]["estimate"]["ltv_percent"] = float(ltv) / 100
    params = user_sessions[user_id]["estimate"]
    params["exchange"] = "direct"
    headers = {"x-api-key": API_KEY, "Content-Type": "application/json"}

    logging.info(f"[Estimate] Params: {params}")

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        r = requests.get(f"{API_BASE_URL}/v2/loans/estimate", headers=headers, params=params)
        r.raise_for_status()
        data = r.json()

        logging.info(f"[Estimate] API response: {data}")

        if data.get("result") and data.get("response"):
            res = data["response"]
            user_sessions[user_id]["latest_estimate"] = params
            await update.callback_query.edit_message_text(
                f"\U0001F3AF *Loan Estimate*\n\n"
                f"\U0001F4B5 *Receive:* `{res['amount_to']} {params['to_code']}` on `{params['to_network']}`\n"
                f"\U0001F4C5 *Interest:*\n"
                f"  \u2022 Year: `{res['interest_amounts']['year']}%`\n"
                f"  \u2022 Month: `{res['interest_amounts']['month']}%`\n"
                f"  \u2022 Day: `{res['interest_amounts']['day']}%`\n\n"
                f"\U0001F50E _Now, send your wallet to receive funds:_",
                parse_mode="Markdown"
            )
            return ENTER_WALLET
        else:
            await update.callback_query.edit_message_text("❌ Failed to get estimate.")
            return ConversationHandler.END

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 500:
            await update.callback_query.edit_message_text(
                "❌ CoinRabbit API returned an error. This currency/network combination might be unsupported.\n"
                "Try using BTC on BTC network with USDT on ETH."
            )
        else:
            await update.callback_query.edit_message_text("❌ Error getting estimate.")
        logging.error(f"[Estimate] HTTPError: {e}")
        logging.error(f"[Estimate] Params used: {params}")
        return ConversationHandler.END

    except Exception as e:
        logging.error(f"[Estimate] Unexpected error: {e}")
        logging.error(f"[Estimate] Params used: {params}")
        await update.callback_query.edit_message_text("❌ Unexpected error occurred.")
        return ConversationHandler.END




# --- Setup Main App ---
def main():
    app = ApplicationBuilder().token(BOT_KEY).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CallbackQueryHandler(handle_estimate_start, pattern="^start_estimate$")
        ],
        states={
            SELECT_COLLATERAL_CURRENCY: [CallbackQueryHandler(select_collateral_currency, pattern="^collat_curr:.*")],
            SELECT_COLLATERAL_NETWORK: [CallbackQueryHandler(select_collateral_network, pattern="^collat_net:.*")],
            ENTER_COLLATERAL_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_collateral_amount)],
            SELECT_LOAN_CURRENCY: [CallbackQueryHandler(select_loan_currency, pattern="^loan_curr:.*")],
            SELECT_LOAN_NETWORK: [CallbackQueryHandler(select_loan_network, pattern="^loan_net:.*")],
            SELECT_LTV_PERCENT: [CallbackQueryHandler(select_ltv, pattern="^ltv:.*")],
        },
        fallbacks=[]
    )

    app.add_handler(conv_handler)
    app.run_polling()

if __name__ == "__main__":
    main()
