import os
import shutil
import time
from telegram import Update
from telegram.ext import ContextTypes
from config import ADMIN_IDS, ADMIN_USERNAMES, SIGNED_DIR, TEMP_DIR, CERTS_DIR
from bot.keyboards import get_admin_dashboard_keyboard, get_main_keyboard, get_cancel_keyboard
from bot.services.database import db


def is_admin(user) -> bool:
    if not user:
        return False
    if user.username and user.username.lstrip("@").lower() in ADMIN_USERNAMES:
        return True
    if user.id in ADMIN_IDS:
        return True
    return False


async def admin_dashboard_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user):
        await update.message.reply_text("⛔ Access denied.")
        return

    total_users = db.get_all_users_count()

    # Calculate storage
    total_size_bytes = 0
    for folder in [SIGNED_DIR, TEMP_DIR, CERTS_DIR]:
        for root, dirs, files in os.walk(folder):
            for f in files:
                fp = os.path.join(root, f)
                total_size_bytes += os.path.getsize(fp)

    total_size_mb = total_size_bytes / (1024 * 1024)

    text = (
        "👑 **Admin Control Panel**\n\n"
        f"• **Admin:** `@{user.username}`\n"
        f"• **Registered Users:** `{total_users}`\n"
        f"• **Storage Used:** `{total_size_mb:.2f} MB`\n"
        f"• **Server Status:** `🟢 Active & Running`\n"
        f"• **Unlimited Signer:** `Enabled (All Users)`\n"
        f"• **Large File Mode (>2GB):** `Enabled`\n\n"
        "Select an administrative action below:"
    )

    reply_markup = get_admin_dashboard_keyboard()
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.edit_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")


async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user = update.effective_user

    if not is_admin(user):
        await query.answer("⛔ Access denied.", show_alert=True)
        return

    await query.answer()

    if data == "admin_stats":
        total_users = db.get_all_users_count()
        signed_files_count = len(os.listdir(SIGNED_DIR))
        certs_count = len(os.listdir(CERTS_DIR))

        await query.message.reply_text(
            "📊 **Detailed System Statistics**\n\n"
            f"• **Total Users:** `{total_users}`\n"
            f"• **Signed IPAs in Storage:** `{signed_files_count}`\n"
            f"• **Stored Certificates:** `{certs_count}`\n"
            "• **Max Allowed File Size:** `Unlimited (>2GB via Direct Engine)`\n"
            "• **Sign Limit:** `Unlimited for all users`",
            parse_mode="Markdown"
        )

    elif data == "admin_users":
        # Fetch users from DB
        with db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id, sign_count, created_at FROM users ORDER BY created_at DESC LIMIT 15")
            rows = cursor.fetchall()

        if not rows:
            await query.message.reply_text("No users registered yet.")
            return

        user_lines = []
        for r in rows:
            user_lines.append(f"• ID: `{r['user_id']}` | Signs: `{r['sign_count']}`")

        msg = "👥 **Recent Registered Users (Last 15):**\n\n" + "\n".join(user_lines)
        await query.message.reply_text(msg, parse_mode="Markdown")

    elif data == "admin_clean":
        # Remove files older than 24h from TEMP_DIR and SIGNED_DIR
        now = time.time()
        cleaned = 0
        for folder in [TEMP_DIR, SIGNED_DIR]:
            for f in os.listdir(folder):
                fp = os.path.join(folder, f)
                if os.path.isfile(fp):
                    # Delete if older than 12 hours
                    if now - os.path.getmtime(fp) > 12 * 3600:
                        try:
                            os.remove(fp)
                            cleaned += 1
                        except Exception:
                            pass

        await query.message.reply_text(f"🧹 Cleaned up `{cleaned}` expired temporary/signed files.", parse_mode="Markdown")

    elif data == "admin_broadcast_prompt":
        context.user_data["waiting_for"] = "admin_broadcast_text"
        await query.message.reply_text(
            "📢 **Broadcast to All Users**\n\n"
            "Send the message you want to broadcast to all registered bot users:",
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown"
        )


async def process_admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user):
        return

    broadcast_text = update.message.text
    context.user_data.pop("waiting_for", None)

    # Get all users
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users")
        rows = cursor.fetchall()

    status_msg = await update.message.reply_text(f"⏳ Broadcasting to {len(rows)} users...")
    sent = 0
    failed = 0

    for r in rows:
        uid = r["user_id"]
        try:
            await context.bot.send_message(chat_id=uid, text=broadcast_text, parse_mode="Markdown")
            sent += 1
        except Exception:
            failed += 1

    await status_msg.edit_text(
        f"✅ **Broadcast Completed!**\n\n"
        f"• Sent: `{sent}`\n"
        f"• Failed/Blocked: `{failed}`",
        parse_mode="Markdown"
    )
