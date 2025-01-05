import os
import json
import asyncio
import logging
from datetime import datetime
import psutil
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# טעינת משתני הסביבה
load_dotenv()

# הגדרת לוגר
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.WARNING
)

# השתקת לוגים מיותרים
logging.getLogger('apscheduler').setLevel(logging.ERROR)
logging.getLogger('httpx').setLevel(logging.ERROR)
logging.getLogger('telegram').setLevel(logging.ERROR)

logger = logging.getLogger(__name__)

# קובפיגורציה
CHECK_INTERVAL_SECONDS = 2  # זמן בשניות בין בדיקות מצב החשמל
USERS_FILE = 'subscribed_users.json'

# טעינת רשימת המשתמשים
def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r') as f:
            return set(json.load(f))
    return set()

# שמירת רשימת המשתמשים
def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(list(users), f)

# המשתמשים הרשומים
subscribed_users = load_users()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """הוספת משתמש לרשימת המנויים"""
    user_id = update.effective_chat.id
    user_name = update.effective_user.full_name
    
    if user_id not in subscribed_users:
        subscribed_users.add(user_id)
        save_users(subscribed_users)
        logger.warning(f"New user subscribed: {user_name} (ID: {user_id})")
        await update.message.reply_text('נרשמת בהצלחה! תקבל התראות על שינויים במצב החשמל.')
    else:
        await update.message.reply_text('כבר נרשמת! אתה תקבל התראות על שינויים במצב החשמל.')

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """הסרת משתמש מרשימת המנויים"""
    user_id = update.effective_chat.id
    user_name = update.effective_user.full_name
    if user_id in subscribed_users:
        subscribed_users.remove(user_id)
        save_users(subscribed_users)
        logger.warning(f"User unsubscribed: {user_name} (ID: {user_id})")
        await update.message.reply_text('הוסרת בהצלחה מרשימת המנויים.')
    else:
        await update.message.reply_text('לא היית רשום לקבלת התראות.')

async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """הצגת עזרה והסבר על הבוט"""
    help_text = """הבוט מתריע על הפסקות חשמל והתחדשות החשמל.
שימו לב: המדידה מתבצעת בכתובת ספציפית ברחוב הקרן במעלה אדומים, ולא משקפת את מצב החשמל בכל העיר.

פקודות זמינות:
/start - הרשמה לקבלת התראות
/stop - ביטול הרשמה להתראות
/help - הצגת הודעה זו"""
    await update.message.reply_text(help_text)

async def handle_unknown_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """טיפול בהודעות לא מוכרות"""
    await update.message.reply_text("אינני מסוגל לקרוא הודעות.\n לקבלת עזרה הקש: /help")

async def check_power_status(context: ContextTypes.DEFAULT_TYPE):
    """בדיקת מצב החשמל ושליחת התראות"""
    try:
        battery = psutil.sensors_battery()
        if battery is None:
            logger.error("Failed to get battery status - No battery found")
            return
            
        current_status = battery.power_plugged
        
        # שמירת המצב הקודם בתוך context.job.data
        last_status = context.job.data.get('last_status')
        
        if last_status is not None and current_status != last_status:
            if current_status:
                logger.warning("Power restored - Connected to AC power")
                message = f"{datetime.now().strftime('%d/%m/%Y %H:%M:%S')} החשמל חזר"
            else:
                logger.warning("Power outage detected")
                message = f"{datetime.now().strftime('%d/%m/%Y %H:%M:%S')} הפסקת חשמל"
            
            # שליחת הודעה לכל המשתמשים הרשומים
            for user_id in subscribed_users:
                try:
                    await context.bot.send_message(chat_id=user_id, text=message)
                except Exception as e:
                    logger.error(f"Failed to send message to user {user_id}: {str(e)}")
        
        # עדכון המצב האחרון
        context.job.data['last_status'] = current_status
        
    except Exception as e:
        logger.error(f"Error checking power status: {str(e)}")


def run_bot():
    """הפעלת הבוט"""
    application = Application.builder().token(os.getenv('TELEGRAM_BOT_TOKEN')).build()

    # הוספת הפקודות
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('stop', stop))
    application.add_handler(CommandHandler('help', help))
    
    # הוספת handler להודעות לא מוכרות - חייב להיות אחרון!
    application.add_handler(MessageHandler(filters.ALL, handle_unknown_message))

    # הוספת משימת בדיקת מצב החשמל
    job_data = {'last_status': None}
    application.job_queue.run_repeating(check_power_status, interval=CHECK_INTERVAL_SECONDS, data=job_data)

    logger.warning("Bot is starting...")
    application.run_polling(drop_pending_updates=True)
    logger.warning("Bot stopped")

if __name__ == '__main__':
    try:
        run_bot()
    except KeyboardInterrupt:
        logger.warning("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}") 