from telegram import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# Main User Keyboard (without VIP button)
def get_main_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    rows = [
        [
            KeyboardButton("📲 Sign IPA"),
            KeyboardButton("📦 My Certificate"),
        ],
        [
            KeyboardButton("🔍 Check P12"),
            KeyboardButton("🖼️ Change Thumbnail"),
        ],
    ]
    if is_admin:
        rows.append([
            KeyboardButton("⚙️ Settings"),
            KeyboardButton("👑 Admin Dashboard"),
        ])
    else:
        rows.append([
            KeyboardButton("⚙️ Settings"),
        ])

    return ReplyKeyboardMarkup(
        rows,
        resize_keyboard=True,
        is_persistent=True,
    )


# Certificate Management Inline Keyboard
def get_cert_menu_keyboard(has_cert: bool = False):
    keyboard = [
        [
            InlineKeyboardButton("📤 Upload P12", callback_data="cert_upload_p12"),
            InlineKeyboardButton("📤 Upload Mobileprovision", callback_data="cert_upload_prov"),
        ],
        [
            InlineKeyboardButton("🔑 Set P12 Password", callback_data="cert_set_pass"),
        ],
    ]
    if has_cert:
        keyboard.append([
            InlineKeyboardButton("🗑️ Delete My Certificate", callback_data="cert_delete"),
        ])
    keyboard.append([
        InlineKeyboardButton("🔙 Back to Menu", callback_data="menu_home"),
    ])
    return InlineKeyboardMarkup(keyboard)


# Settings Inline Keyboard
def get_settings_keyboard(current_bundle_id: str = "", current_app_name: str = ""):
    bundle_display = current_bundle_id if current_bundle_id else "Default (Original)"
    name_display = current_app_name if current_app_name else "Default (Original)"

    keyboard = [
        [
            InlineKeyboardButton(f"🆔 Bundle ID: {bundle_display}", callback_data="settings_bundle_id"),
        ],
        [
            InlineKeyboardButton(f"✏️ App Name: {name_display}", callback_data="settings_app_name"),
        ],
        [
            InlineKeyboardButton("💉 Inject Dylib / Deb", callback_data="settings_dylib"),
        ],
        [
            InlineKeyboardButton("🔄 Reset All Settings", callback_data="settings_reset"),
        ],
        [
            InlineKeyboardButton("🔙 Back to Menu", callback_data="menu_home"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


# Thumbnail Management Inline Keyboard
def get_thumbnail_keyboard(has_thumbnail: bool = False):
    keyboard = [
        [
            InlineKeyboardButton("🖼️ Upload New Thumbnail", callback_data="thumb_upload"),
        ]
    ]
    if has_thumbnail:
        keyboard.append([
            InlineKeyboardButton("🗑️ Remove Custom Thumbnail", callback_data="thumb_remove"),
        ])
    keyboard.append([
        InlineKeyboardButton("🔙 Back to Menu", callback_data="menu_home"),
    ])
    return InlineKeyboardMarkup(keyboard)


# Admin Dashboard Inline Keyboard
def get_admin_dashboard_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("📊 System Stats", callback_data="admin_stats"),
            InlineKeyboardButton("👥 User List", callback_data="admin_users"),
        ],
        [
            InlineKeyboardButton("🧹 Clean Storage", callback_data="admin_clean"),
            InlineKeyboardButton("📢 Broadcast Message", callback_data="admin_broadcast_prompt"),
        ],
        [
            InlineKeyboardButton("🔙 Back to Menu", callback_data="menu_home"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


# Cancel Inline Button
def get_cancel_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data="action_cancel")]
    ])
