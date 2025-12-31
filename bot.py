import os
import logging
import asyncio
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from telegram.error import TimedOut, NetworkError
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from downloader import Downloader

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize Downloader
downloader = Downloader()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hello! I am an All-in-One Downloader Bot.\n"
        "Send me a link from YouTube, Instagram, Pinterest, or TikTok, and I'll download it for you."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Just send me a valid link! I support:\n"
        "- YouTube\n- Instagram\n- Pinterest\n- TikTok"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    
    # Basic URL validation
    if not (url.startswith('http://') or url.startswith('https://')):
        await update.message.reply_text("Please send a valid URL starting with http:// or https://")
        return

    status_msg = await update.message.reply_text("Fetching info...")
    
    # Get info first to confirm validity and title
    info = downloader.get_info(url)
    
    if info['status'] == 'error':
        await status_msg.edit_text(f"Error: {info['message']}")
        return

    # Store URL, title and thumbnail in user context
    context.user_data['url'] = url
    context.user_data['title'] = info.get('title', 'Media')
    context.user_data['thumbnail'] = info.get('thumbnail')
    
    # Create selection keyboard
    keyboard = [
        [
            InlineKeyboardButton("Video 🎬", callback_data="type_video"),
            InlineKeyboardButton("Audio 🎵", callback_data="type_audio")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = f"Found: {info.get('title')}\n\nSelect format:"
    
    # Send photo with caption if thumbnail exists
    if info.get('thumbnail'):
        await status_msg.delete() # Delete "Fetching info..." message
        await update.message.reply_photo(
            photo=info.get('thumbnail'),
            caption=text,
            reply_markup=reply_markup
        )
    else:
        await status_msg.edit_text(text, reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    url = context.user_data.get('url')
    
    if not url:
        if query.message.caption:
            await query.edit_message_caption("Session expired. Please send the link again.")
        else:
            await query.edit_message_text("Session expired. Please send the link again.")
        return

    if data == 'type_video':
        keyboard = [
            [InlineKeyboardButton("Best Quality", callback_data="qv_best")],
            [InlineKeyboardButton("1080p", callback_data="qv_1080"), InlineKeyboardButton("720p", callback_data="qv_720")],
            [InlineKeyboardButton("480p", callback_data="qv_480"), InlineKeyboardButton("360p", callback_data="qv_360")],
            [InlineKeyboardButton("« Back", callback_data="back_to_main")]
        ]
        if query.message.caption:
            await query.edit_message_caption("Select Video Quality:", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.edit_message_text("Select Video Quality:", reply_markup=InlineKeyboardMarkup(keyboard))
        
    elif data == 'type_audio':
        keyboard = [
            [InlineKeyboardButton("Best Audio", callback_data="qa_best")],
            [InlineKeyboardButton("320 kbps", callback_data="qa_320"), InlineKeyboardButton("192 kbps", callback_data="qa_192")],
            [InlineKeyboardButton("128 kbps", callback_data="qa_128")],
            [InlineKeyboardButton("« Back", callback_data="back_to_main")]
        ]
        if query.message.caption:
            await query.edit_message_caption("Select Audio Quality:", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.edit_message_text("Select Audio Quality:", reply_markup=InlineKeyboardMarkup(keyboard))
        
    elif data == 'back_to_main':
        keyboard = [
            [
                InlineKeyboardButton("Video 🎬", callback_data="type_video"),
                InlineKeyboardButton("Audio 🎵", callback_data="type_audio")
            ]
        ]
        text = f"Found: {context.user_data.get('title')}\n\nSelect format:"
        if query.message.caption:
            await query.edit_message_caption(text, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith('qv_') or data.startswith('qa_'):
        parts = data.split('_')
        ftype = 'video' if parts[0] == 'qv' else 'audio'
        quality = parts[1]
        
        status_text = f"Downloading {ftype} ({quality})... This might take a while."
        if query.message.caption:
            await query.edit_message_caption(status_text)
        else:
            await query.edit_message_text(status_text)
            
        await process_download(query.message, context, url, ftype, quality)

import time

async def process_download(message, context, url, ftype, quality):
    last_update_time = 0
    
    def progress_hook(d):
        nonlocal last_update_time
        if d['status'] == 'downloading':
            current_time = time.time()
            # Update progress at most every 2 seconds to avoid flooding API
            if current_time - last_update_time > 2:
                percent_str = d.get('_percent_str', '0%').replace('%','')
                try:
                    # Create a simple progress bar
                    # _percent_str might contain ANSI codes or extra spaces, strip them
                    import re
                    clean_percent = re.sub(r'\x1b\[[0-9;]*m', '', percent_str).strip()
                    
                    p = float(clean_percent)
                    filled = int(p // 10)
                    bar = '█' * filled + '░' * (10 - filled)
                    
                    status = f"Downloading {ftype} ({quality})...\n{bar} {clean_percent}%"
                    
                    # We can't use await here directly because it's a sync callback
                    # So we create a task
                    asyncio.create_task(update_progress(message, status))
                    last_update_time = current_time
                except Exception:
                    pass

    # Create a wrapper for the upload callback to include message context
    async def upload_callback_wrapper(current, total):
        nonlocal last_update_time
        current_time = time.time()
        
        # Calculate percentage
        percent = (current / total) * 100
        
        # Update if 3 seconds passed OR it's a 10% step OR complete
        if (current_time - last_update_time > 3) or (int(percent) % 10 == 0 and int(percent) != int((last_update_time if last_update_time > 100 else 0))) or percent >= 100:
             # Let's construct the bar
            filled = int(percent // 10)
            bar = '█' * filled + '░' * (10 - filled)
            status = f"Uploading...\n{bar} {percent:.1f}%"
            
            await update_progress(message, status)
            last_update_time = current_time

    try:
        # Download the content
        result = downloader.download(url, ftype, quality, progress_hook=progress_hook)
        
        if result['status'] == 'error':
            if message.caption:
                await message.edit_caption(f"Error: {result['message']}")
            else:
                await message.edit_text(f"Error: {result['message']}")
            return

        file_path = result['path']
        media_type = result['type']
        title = result.get('title', 'Media')
        
        # Check file size (Telegram limit is 50MB for bots)
        file_size = os.path.getsize(file_path)
        if file_size > 50 * 1024 * 1024:
            err_msg = f"File is too large ({file_size / (1024*1024):.2f} MB). Telegram Bot API limit is 50MB."
            if message.caption:
                await message.edit_caption(err_msg)
            else:
                await message.edit_text(err_msg)
            # Clean up immediately since we won't send it
            os.remove(file_path)
            return

        if message.caption:
            await message.edit_caption("Uploading...")
        else:
            await message.edit_text("Uploading...")
        
        try:
            with open(file_path, 'rb') as f:
                if media_type == 'image':
                    await message.reply_photo(
                        photo=f, 
                        caption=title,
                        read_timeout=60,
                        write_timeout=60,
                        connect_timeout=60
                    )
                elif media_type == 'audio':
                    # For audio, we can also try to attach the thumbnail if available
                    thumb = context.user_data.get('thumbnail')
                    await message.reply_audio(
                        audio=f,
                        caption=title,
                        title=title,
                        thumbnail=thumb if thumb else None,
                        read_timeout=300,
                        write_timeout=300,
                        connect_timeout=60,
                        # progress=upload_callback_wrapper
                    )
                else:
                    await message.reply_video(
                        video=f, 
                        caption=title, 
                        supports_streaming=True,
                        width=None, 
                        height=None, 
                        duration=result.get('duration'),
                        read_timeout=300, 
                        write_timeout=300,
                        connect_timeout=60,
                        # progress=upload_callback_wrapper
                    )
            await message.delete()
        except TimedOut:
            logger.warning("Upload timed out, but file might still be sent.")
            if message.caption:
                await message.edit_caption("Upload timed out. The file might still appear in a moment.")
            else:
                await message.edit_text("Upload timed out. The file might still appear in a moment.")
            
    except Exception as e:
        logger.error(f"Error handling message: {e}")
        if message.caption:
            await message.edit_caption(f"An error occurred while sending the file: {str(e)}")
        else:
            await message.edit_text(f"An error occurred while sending the file: {str(e)}")
        
    finally:
        # Clean up: Delete the downloaded file
        if 'file_path' in locals() and os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"Deleted {file_path}")
            except Exception as e:
                logger.error(f"Failed to delete {file_path}: {e}")

async def update_progress(message, text):
    try:
        if message.caption:
            if message.caption != text:
                await message.edit_caption(text)
        else:
            if message.text != text:
                await message.edit_text(text)
    except Exception:
        pass

async def upload_progress_callback(current, total):
    # This function is called by python-telegram-bot during upload
    # Note: python-telegram-bot 20.x doesn't support passing extra args to progress callback easily
    # in the way we implemented. For now, we disable the upload progress bar to fix the crash.
    pass

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("No TELEGRAM_BOT_TOKEN found in environment variables.")
        print("Error: Please set TELEGRAM_BOT_TOKEN in .env file.")
        return

    application = ApplicationBuilder().token(token).read_timeout(30).write_timeout(30).build()

    start_handler = CommandHandler('start', start)
    help_handler = CommandHandler('help', help_command)
    message_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message)

    application.add_handler(start_handler)
    application.add_handler(help_handler)
    application.add_handler(message_handler)
    application.add_handler(CallbackQueryHandler(button_handler))

    logger.info("Bot is polling...")
    application.run_polling()

if __name__ == '__main__':
    main()
