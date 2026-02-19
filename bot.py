import os
import logging
from flask import Flask, request

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters

# ==================== CONFIGURATION ====================
BOT_TOKEN = os.getenv("BOT_TOKEN")  # set in Render Environment
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "change-me")  # set in Render Environment

STAFF_IDS = {
    "director": 1286115862,
    "psychologist": 987654321,
    "academic_subdirector": 555555555,
    "ethics_subdirector": 444444444
}

# ==================== LOGGING ====================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== BOT STATE ====================
user_sessions = {}
reply_map = {}
STAFF_USER_IDS = set(STAFF_IDS.values())

def get_main_menu():
    keyboard = [
        [InlineKeyboardButton("👨‍🏫 Director", callback_data="director")],
        [InlineKeyboardButton("🧠 Psychologist", callback_data="psychologist")],
        [InlineKeyboardButton("📚 Deputy Director for Academic Affairs", callback_data="academic_subdirector")],
        [InlineKeyboardButton("⚖️ Deputy Director for Spiritual and Educational Affairs", callback_data="ethics_subdirector")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context):
    await update.message.reply_text("Choose who to message:", reply_markup=get_main_menu())

async def button_handler(update: Update, context):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    await query.answer()

    if data in STAFF_IDS:
        if STAFF_IDS[data] == 0:
            await query.edit_message_text(f"{data.replace('_', ' ').title()} not configured.")
            return

        user_sessions[user_id] = {"staff": data, "staff_id": STAFF_IDS[data], "step": "ask_anon"}

        keyboard = [
            [InlineKeyboardButton("🤫 Send Anonymously", callback_data="anon_yes")],
            [InlineKeyboardButton("👤 Send with Name", callback_data="anon_no")]
        ]
        await query.edit_message_text(
            f"Send to {data.replace('_', ' ').title()}?\nChoose option:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data in ["anon_yes", "anon_no"]:
        session = user_sessions.get(user_id)
        if not session:
            return

        session["anonymous"] = (data == "anon_yes")
        session["step"] = "get_message" if data == "anon_yes" else "get_name"

        if data == "anon_no":
            await query.edit_message_text("What is your name?")
        else:
            await query.edit_message_text("Type your message:")

async def message_handler(update: Update, context):
    user_id = update.effective_user.id
    text = update.message.text

    # Staff reply-to-forwarded message => send to student
    if user_id in STAFF_USER_IDS and update.message.reply_to_message:
        staff_chat_id = update.effective_chat.id
        replied_msg_id = update.message.reply_to_message.message_id
        student_chat_id = reply_map.get((staff_chat_id, replied_msg_id))

        if not student_chat_id:
            await update.message.reply_text(
                "❌ Can't find the student for this reply.\n"
                "Please reply directly to the student's message sent by the bot."
            )
            return

        staff_name = update.effective_user.full_name
        reply_text = f"📨 Reply from administration ({staff_name}):\n\n{text}"
        await context.bot.send_message(chat_id=student_chat_id, text=reply_text)
        await update.message.reply_text("✅ Sent to student.")
        return

    if user_id not in user_sessions:
        await update.message.reply_text("Choose who to message:", reply_markup=get_main_menu())
        return

    session = user_sessions[user_id]
    step = session.get("step")

    if step == "get_name":
        session["name"] = text
        session["step"] = "get_message"
        await update.message.reply_text("Now type your message:")
        return

    if step == "get_message":
        staff_type = session["staff"]
        staff_id = session["staff_id"]
        is_anon = session.get("anonymous", True)
        name = session.get("name", "Anonymous")
        username = update.effective_user.username

        message = f"📩 NEW MESSAGE FOR {staff_type.upper().replace('_', ' ')}\n\n"
        message += f"From: {name}\n"
        if username and not is_anon:
            message += f"Username: @{username}\n"
        message += f"\nMessage:\n{text}"

        sent_msg = await context.bot.send_message(chat_id=staff_id, text=message)
        reply_map[(staff_id, sent_msg.message_id)] = update.effective_chat.id

        await update.message.reply_text(
            f"✅ Message sent to {staff_type.replace('_', ' ').title()}!\n\nSend another message to:",
            reply_markup=get_main_menu()
        )
        del user_sessions[user_id]

# ==================== WEBHOOK SERVER ====================
flask_app = Flask(__name__)
ptb_app = Application.builder().token(BOT_TOKEN).build()

ptb_app.add_handler(CommandHandler("start", start))
ptb_app.add_handler(CallbackQueryHandler(button_handler))
ptb_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

@flask_app.get("/")
def health():
    return "OK", 200

@flask_app.post(f"/webhook/{WEBHOOK_SECRET}")
def webhook():
    data = request.get_json(force=True)
    update = Update.de_json(data, ptb_app.bot)
    ptb_app.update_queue.put_nowait(update)
    return "OK", 200

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN env var not set")
    port = int(os.getenv("PORT", "10000"))

    # Start PTB (no polling)
    ptb_app.initialize()
    ptb_app.start()

    # Start Flask (Render routes traffic here)
    flask_app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
