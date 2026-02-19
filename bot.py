import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters

# ==================== CONFIGURATION ====================
# ⚠️ EDIT THESE VALUES ONLY!

# 1. PUT YOUR BOT TOKEN HERE (from @BotFather)
BOT_TOKEN = "8360074639:AAF9slW_t0MJBrYEWDbCIHQiDYcT2tVP6m4"  # ⚠️ CHANGE THIS (revoke the one you leaked)

# 2. PUT STAFF IDs HERE (get from @userinfobot)
STAFF_IDS = {
    "director": 750181721,        # ⚠️ Director's Telegram ID
    "psychologist": 750181721,    # ⚠️ Psychologist's ID
    "academic_subdirector": 750181721,  # ⚠️ Academic Sub-Director's ID
}

# ==================== BOT CODE ====================
# DON'T EDIT BELOW UNLESS YOU KNOW WHAT YOU'RE DOING

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Store user sessions
user_sessions = {}

# ✅ REPLY FEATURE: Map staff reply targets to students
# reply_map[(staff_chat_id, staff_message_id)] = student_chat_id
reply_map = {}

# ✅ REPLY FEATURE: quick check for staff
STAFF_USER_IDS = set(STAFF_IDS.values())

def get_main_menu():
    """Return main menu keyboard"""
    keyboard = [
        [InlineKeyboardButton("👨‍🏫 Director", callback_data="director")],
        [InlineKeyboardButton("🧠 Psychologist", callback_data="psychologist")],
        [InlineKeyboardButton("📚 Deputy Director for Academic Affairs", callback_data="academic_subdirector")],
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context):
    """Handle /start command"""
    await update.message.reply_text(
        "Choose who to message:",
        reply_markup=get_main_menu()
    )

async def button_handler(update: Update, context):
    """Handle button clicks"""
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    await query.answer()

    if data in STAFF_IDS:
        # Check if staff is configured
        if STAFF_IDS[data] == 0:
            await query.edit_message_text(f"{data.replace('_', ' ').title()} not configured.")
            return

        # Store user session
        user_sessions[user_id] = {
            "staff": data,
            "staff_id": STAFF_IDS[data],
            "step": "ask_anon"
        }

        # Ask anonymous or name
        keyboard = [
            [InlineKeyboardButton("🤫 Send Anonymously", callback_data="anon_yes")],
            [InlineKeyboardButton("👤 Send with Name", callback_data="anon_no")]
        ]
        await query.edit_message_text(
            f"Send to {data.replace('_', ' ').title()}?\nChoose option:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data in ["anon_yes", "anon_no"]:
        # Handle anonymous choice
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
    """Handle text messages"""
    user_id = update.effective_user.id
    text = update.message.text

    # ✅ REPLY FEATURE: if STAFF is replying to a bot message, forward to student
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

        try:
            await context.bot.send_message(chat_id=student_chat_id, text=reply_text)
            await update.message.reply_text("✅ Sent to student.")
        except Exception as e:
            logger.error(f"Error sending reply to student: {e}")
            await update.message.reply_text("❌ Failed to send to student.")
        return

    # ---- existing student flow below ----
    if user_id not in user_sessions:
        await update.message.reply_text(
            "Choose who to message:",
            reply_markup=get_main_menu()
        )
        return

    session = user_sessions[user_id]
    step = session.get("step")

    if step == "get_name":
        # User entered their name
        session["name"] = text
        session["step"] = "get_message"
        await update.message.reply_text("Now type your message:")

    elif step == "get_message":
        # User entered their message
        staff_type = session["staff"]
        staff_id = session["staff_id"]
        is_anon = session.get("anonymous", True)
        name = session.get("name", "Anonymous")
        username = update.effective_user.username

        # Create message for staff
        message = f"📩 NEW MESSAGE FOR {staff_type.upper().replace('_', ' ')}\n\n"
        message += f"From: {name}\n"
        if username and not is_anon:
            message += f"Username: @{username}\n"
        message += f"\nMessage:\n{text}"

        try:
            # Send to staff (capture the returned message object)
            sent_msg = await context.bot.send_message(
                chat_id=staff_id,
                text=message
            )

            # ✅ REPLY FEATURE: store mapping so staff can reply
            # staff replies to sent_msg.message_id -> we forward to this student
            reply_map[(staff_id, sent_msg.message_id)] = update.effective_chat.id

            # Show success and main menu again
            await update.message.reply_text(
                f"✅ Message sent to {staff_type.replace('_', ' ').title()}!\n\n"
                "Send another message to:",
                reply_markup=get_main_menu()
            )
            logger.info(f"Message sent to {staff_type} (ID: {staff_id})")

        except Exception as e:
            # Show error and main menu again
            await update.message.reply_text(
                f"❌ Failed to send to {staff_type.replace('_', ' ').title()}.\n"
                "Staff needs to START this bot first.\n\n"
                "Choose who to message:",
                reply_markup=get_main_menu()
            )
            logger.error(f"Error sending to {staff_type}: {e}")

        # Clean up session
        del user_sessions[user_id]

def main():
    """Start the bot"""
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    print("="*60)
    print("🤖 SCHOOL MESSAGE BOT")
    print("="*60)
    print(f"\n✅ Bot token: {BOT_TOKEN[:15]}...")
    print("\n📋 STAFF IDs CONFIGURED:")
    for staff, sid in STAFF_IDS.items():
        status = "✅" if sid != 0 else "❌"
        staff_name = staff.replace('_', ' ').title()
        print(f"  {status} {staff_name}: {sid}")

    print("\n📱 HOW TO USE:")
    print("1. Staff MUST send /start to this bot first")
    print("2. Students: /start → Choose staff → Send message")
    print("3. Staff: Reply to the bot's message to respond to that student")
    print("\n⚡ Bot is now running 24/7!")
    print("Press Ctrl+C to stop")
    print("="*60)

    app.run_polling()

if __name__ == "__main__":
    main()
