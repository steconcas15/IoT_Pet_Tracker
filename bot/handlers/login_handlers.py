"""
Telegram Bot Authentication & Session Management Module
=======================================================
This module handles secure user authentication via the Telegram interface. 
It securely processes credentials, manages stateful user sessions (`LOGGED_USERS`), 
enforces privacy by aggressively deleting sensitive command messages, and 
provides an interactive selection mechanism for users managing multiple 
Digital Twin environments.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from werkzeug.security import check_password_hash

# Stateful memory structure mapping Telegram User IDs to their active Digital Twin session context.
# Structure: telegram_user_id -> {"user_id": string, "home_id": string}
LOGGED_USERS = {}

def check_auth(telegram_id: int) -> bool:
    """
    Evaluates whether a specific Telegram user currently holds an active, 
    authenticated session within the bot's memory space.
    
    Args:
        telegram_id (int): The unique identifier of the Telegram user.
        
    Returns:
        bool: True if authenticated, False otherwise.
    """
    return telegram_id in LOGGED_USERS

async def login_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Processes the /login command.
    Authenticates the user against the MongoDB database, initializes the session, 
    and handles environment (Home) selection if multiple environments are accessible.
    
    Security mechanism: Actively attempts to delete the user's invocation message 
    to prevent plaintext passwords from remaining in the chat history.
    """
    telegram_id = update.effective_user.id
    
    # 1. IMMEDIATE MESSAGE DELETION (SECURITY MEASURE)
    # The bot attempts to delete the user's message containing the plaintext password.
    try:
        if update.message:
            await update.message.delete()
    except Exception as e:
        print(f"[SECURITY WARNING] Unable to delete login message: {e}")
        # Fallback: If deletion fails (e.g., lacking administrative privileges in a group chat), alert the user.
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text="⚠️ **Security Warning:** I do not have permission to delete your message. Please delete the message containing your password manually to protect your account!",
            parse_mode='Markdown'
        )
    
    # Session state validation: Prevent redundant logins
    if check_auth(telegram_id):
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="⚠️ You are already logged in! Use /logout before logging in with another account."
        )
        return

    # Syntax and argument validation
    if len(context.args) < 2:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Invalid format. Use: /login <username> <password>"
        )
        return

    username = context.args[0]
    password = context.args[1]

    # Retrieve the injected database service dependency
    db_service = context.bot_data.get("db_service")
    if not db_service:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Internal error: Database service is not connected."
        )
        return

    try:
        user = db_service.get_user_by_username(username)

        # Authentication evaluation: Verify existence and cryptographic password hash
        if not user or not check_password_hash(user['profile']['password'], password):
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Invalid credentials. Please try again."
            )
            return

        user_id_str = str(user['_id'])
        
        # Aggregate all accessible environments (both owned and view-only)
        owned_homes = user.get("data", {}).get("owned_homes", [])
        viewable_homes = user.get("data", {}).get("viewable_homes", [])
        all_homes = owned_homes + viewable_homes

        # Edge Case: Authenticated user with no associated environments
        if not all_homes:
            LOGGED_USERS[telegram_id] = {"user_id": user_id_str, "home_id": None}
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"Login successful, {username}. However, you do not have any associated homes."
            )
            return

        # Optimization: Auto-select the environment if only one is available
        if len(all_homes) == 1:
            LOGGED_USERS[telegram_id] = {"user_id": user_id_str, "home_id": all_homes[0]}
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"Login successful! Welcome {username}. Home environment selected automatically."
            )
            return

        # Multiplexing: Generate an inline keyboard interface for environment selection
        keyboard = []
        dt_factory = context.bot_data.get("dt_factory")
        
        for home_id in all_homes:
            dt = dt_factory.get_dt(home_id) if dt_factory else None
            home_name = dt.get("name", home_id) if dt else home_id
            
            # Determine role for UI clarity
            role = "Admin" if home_id in owned_homes else "Viewer"
            
            keyboard.append([InlineKeyboardButton(f"{home_name} ({role})", callback_data=f"select_home_{home_id}")])

        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Temporarily cache the database user ID to finalize the session after callback resolution
        context.user_data['pending_login_user_id'] = user_id_str
        
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Welcome {username}! You have access to multiple environments.\nPlease select which one you want to manage during this session:",
            reply_markup=reply_markup
        )

    except Exception as e:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Error during authentication: {str(e)}"
        )


async def home_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles the asynchronous callback query triggered by the environment selection inline keyboard.
    Finalizes the session initialization by mapping the selected Home ID to the user's state.
    """
    query = update.callback_query
    await query.answer()
    
    telegram_id = update.effective_user.id
    data = query.data
    
    # Route and process the specific callback action
    if data.startswith("select_home_"):
        home_id = data.replace("select_home_", "")
        user_id_str = context.user_data.get('pending_login_user_id')
        
        # Validate that the temporary cache hasn't expired
        if not user_id_str:
            await query.edit_message_text("Login session expired or invalid state. Please execute /login again.")
            return
        
        # Finalize and register the authenticated session state
        LOGGED_USERS[telegram_id] = {"user_id": user_id_str, "home_id": home_id}
        
        # Clean up the temporary context cache
        del context.user_data['pending_login_user_id']
        
        await query.edit_message_text("Home environment selected successfully! You are now connected to the chosen Digital Twin.")


async def logout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Processes the /logout command.
    Safely terminates the user's active session and clears their state from the system's memory.
    """
    telegram_id = update.effective_user.id
    
    if telegram_id in LOGGED_USERS:
        del LOGGED_USERS[telegram_id]
        await update.message.reply_text("Successfully logged out.")
    else:
        await update.message.reply_text("You are not currently logged in.")
