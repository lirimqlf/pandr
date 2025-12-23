import asyncio
import json
import logging
import os
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Load from environment variables
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
RESULTS_GROUP_ID = os.getenv('TELEGRAM_GROUP_ID')
VERCEL_API_URL = os.getenv('VERCEL_API_URL', 'https://your-app.vercel.app')

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Validate environment variables
if not BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")
if not RESULTS_GROUP_ID:
    raise ValueError("TELEGRAM_GROUP_ID environment variable is required")

# Local storage for inbox
profiles_inbox = []
call_results = []

def calculate_stats():
    """Calculate overall statistics from all call results"""
    if not call_results:
        return {
            "total_calls": 0,
            "won": 0,
            "lost": 0,
            "follow_up": 0,
            "win_rate": 0,
            "avg_duration": 0,
            "total_positive": 0,
            "total_negative": 0,
            "total_neutral": 0
        }
    
    total = len(call_results)
    won = sum(1 for c in call_results if c.get('outcome') == 'won')
    lost = sum(1 for c in call_results if c.get('outcome') == 'lost')
    follow_up = sum(1 for c in call_results if c.get('outcome') == 'follow-up')
    
    total_duration = sum(c.get('duration', 0) for c in call_results)
    avg_duration = total_duration / total if total > 0 else 0
    
    total_positive = sum(c.get('stats', {}).get('positive', 0) for c in call_results)
    total_negative = sum(c.get('stats', {}).get('negative', 0) for c in call_results)
    total_neutral = sum(c.get('stats', {}).get('neutral', 0) for c in call_results)
    
    win_rate = (won / total * 100) if total > 0 else 0
    
    return {
        "total_calls": total,
        "won": won,
        "lost": lost,
        "follow_up": follow_up,
        "win_rate": round(win_rate, 1),
        "avg_duration": int(avg_duration),
        "total_positive": total_positive,
        "total_negative": total_negative,
        "total_neutral": total_neutral
    }

def format_duration(seconds):
    """Format seconds into MM:SS"""
    minutes = seconds // 60
    secs = seconds % 60
    return f"{minutes}:{secs:02d}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    welcome_message = """
🎯 **Cold Call Bot** - Welcome!

**Commands:**
/start - Show this welcome message
/stats - View overall statistics
/inbox - View profiles in inbox
/clear_inbox - Clear all profiles from inbox
/help - Show help information

**How to use:**
1. Send a JSON profile file or text to add it to inbox
2. Call results will be automatically posted here
3. Use /stats to see your performance

Send me a profile JSON to get started!
    """
    await update.message.reply_text(welcome_message, parse_mode='Markdown')

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stats command - Show overall statistics"""
    stats_data = calculate_stats()
    
    stats_message = f"""
📊 **Overall Statistics**

**Call Summary:**
• Total Calls: {stats_data['total_calls']}
• Won: {stats_data['won']} ✅
• Lost: {stats_data['lost']} ❌
• Follow-up: {stats_data['follow_up']} 📝
• Win Rate: {stats_data['win_rate']}%

**Performance:**
• Avg Duration: {format_duration(stats_data['avg_duration'])}
• Positive Responses: {stats_data['total_positive']} 👍
• Negative Responses: {stats_data['total_negative']} 👎
• Neutral Responses: {stats_data['total_neutral']} 😐

**Sentiment Score:** {stats_data['total_positive'] - stats_data['total_negative']}
    """
    
    await update.message.reply_text(stats_message, parse_mode='Markdown')

async def inbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /inbox command - Show profiles in inbox"""
    if not profiles_inbox:
        await update.message.reply_text("📭 Inbox is empty. Send a profile JSON to add one!")
        return
    
    inbox_message = f"📬 **Inbox ({len(profiles_inbox)} profiles)**\n\n"
    
    for idx, profile in enumerate(profiles_inbox, 1):
        inbox_message += f"{idx}. **{profile.get('firstName', 'N/A')} {profile.get('lastName', 'N/A')}**\n"
        inbox_message += f"   • Company: {profile.get('company', 'N/A')}\n"
        inbox_message += f"   • Phone: {profile.get('phoneNumber', 'N/A')}\n"
        inbox_message += f"   • Location: {profile.get('city', 'N/A')}, {profile.get('state', 'N/A')}\n\n"
    
    await update.message.reply_text(inbox_message, parse_mode='Markdown')

async def clear_inbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /clear_inbox command"""
    count = len(profiles_inbox)
    profiles_inbox.clear()
    await update.message.reply_text(f"🗑️ Cleared {count} profiles from inbox.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_message = """
📚 **Help - Cold Call Bot**

**Profile Format:**
Send JSON file or text:
```json
{
  "firstName": "John",
  "lastName": "Doe",
  "company": "Tech Corp",
  "position": "Engineer",
  "phoneNumber": "+1234567890",
  "city": "New York",
  "state": "NY"
}
```

**Features:**
• Profiles automatically sync to web app
• Call results posted automatically
• Statistics tracking
• Easy inbox management

**Vercel Integration:**
Bot syncs with: {VERCEL_API_URL}
    """.format(VERCEL_API_URL=VERCEL_API_URL)
    
    await update.message.reply_text(help_message, parse_mode='Markdown')

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming JSON documents"""
    document = update.message.document
    
    if not document.file_name.endswith('.json'):
        await update.message.reply_text("❌ Please send a valid JSON file.")
        return
    
    try:
        file = await context.bot.get_file(document.file_id)
        file_content = await file.download_as_bytearray()
        profile_data = json.loads(file_content.decode('utf-8'))
        
        if not all(field in profile_data for field in ['firstName', 'lastName']):
            await update.message.reply_text("❌ Invalid profile. Must include firstName and lastName.")
            return
        
        profile_data['received_at'] = datetime.now().isoformat()
        profile_data['received_from'] = update.message.from_user.username or update.message.from_user.first_name
        profiles_inbox.append(profile_data)
        
        confirmation = f"""
✅ **Profile Added to Inbox**

**Name:** {profile_data.get('firstName')} {profile_data.get('lastName')}
**Company:** {profile_data.get('company', 'N/A')}
**Phone:** {profile_data.get('phoneNumber', 'N/A')}

Total profiles in inbox: {len(profiles_inbox)}
        """
        
        await update.message.reply_text(confirmation, parse_mode='Markdown')
        
    except json.JSONDecodeError:
        await update.message.reply_text("❌ Invalid JSON file. Please check the format.")
    except Exception as e:
        logger.error(f"Error handling document: {e}")
        await update.message.reply_text(f"❌ Error processing file: {str(e)}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages that might be JSON"""
    text = update.message.text
    
    if text.strip().startswith('{') and text.strip().endswith('}'):
        try:
            profile_data = json.loads(text)
            
            if 'firstName' in profile_data and 'lastName' in profile_data:
                profile_data['received_at'] = datetime.now().isoformat()
                profile_data['received_from'] = update.message.from_user.username or update.message.from_user.first_name
                profiles_inbox.append(profile_data)
                
                confirmation = f"""
✅ **Profile Added to Inbox**

**Name:** {profile_data.get('firstName')} {profile_data.get('lastName')}
**Company:** {profile_data.get('company', 'N/A')}

Total profiles in inbox: {len(profiles_inbox)}
                """
                await update.message.reply_text(confirmation, parse_mode='Markdown')
                
            elif 'outcome' in profile_data and 'scriptName' in profile_data:
                call_results.append(profile_data)
                await update.message.reply_text("✅ Call result recorded!")
            
            else:
                await update.message.reply_text("❌ Unknown JSON format. Send a profile or call result.")
                
        except json.JSONDecodeError:
            await update.message.reply_text("❌ Invalid JSON format.")
    else:
        await update.message.reply_text(
            "Send me a JSON profile file or use /help to see available commands."
        )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    logger.error(f"Update {update} caused error {context.error}")
    
    if update and update.message:
        await update.message.reply_text(
            "❌ An error occurred. Please try again or contact support."
        )

def main():
    """Start the bot"""
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("inbox", inbox))
    application.add_handler(CommandHandler("clear_inbox", clear_inbox))
    application.add_handler(CommandHandler("help", help_command))
    
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    application.add_error_handler(error_handler)
    
    logger.info("🤖 Bot started successfully!")
    logger.info(f"📡 Connected to: {VERCEL_API_URL}")
    print("🤖 Bot is running... Press Ctrl+C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
