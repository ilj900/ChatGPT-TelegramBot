import os
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, filters, MessageHandler, ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler
from openai import OpenAI

MODEL_NAME = "gpt-4-turbo-preview"
DALLE_NAME = "dall-e-3"
IMAGE_SIZE = "1024x1024"

load_dotenv()

class TelegramBot:
    def __init__(self, token, whitelist, bot_name):
        self.whitelist = whitelist
        self.bot_name = bot_name
        self.application = ApplicationBuilder().token(os.getenv('TOKEN')).build()
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        self.application.add_handler(CommandHandler('new', self.new_chat))
        self.application.add_handler(CommandHandler('help', self.help))
        self.application.add_handler(CommandHandler('img', self.generate_image))
        self.application.add_handler(CommandHandler('menu', self.show_menu))
        self.application.add_handler(CallbackQueryHandler(self.menu_buttons))
        self.application.add_handler(CallbackQueryHandler(self.change_gpt_version))
        self.application.add_handler(MessageHandler(filters.COMMAND, self.unknown))
        self.chat_history = []
        self.gpt_client = OpenAI()
     
    def ask_gpt(self, update: Update):
        self.chat_history.append({"role": "user", "content": update.message.text})
        response = self.gpt_client.chat.completions.create(
            model=MODEL_NAME,
            messages=self.chat_history
        )
        self.chat_history.append(response.choices[0].message)
        for entry in self.chat_history:
            print(entry)
        return response

    def imagine_gpt(self, update: Update):
        response = self.gpt_client.images.generate(
            model=DALLE_NAME,
            prompt=update.message.text,
            size=IMAGE_SIZE,
            quality="standard",
            n=1,
        )

        image_url = response.data[0].url
        return image_url

    async def menu_buttons(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        await query.edit_message_text(text=f"Selected option: {query.data}")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if str(update.message.from_user.username) != self.whitelist:
            return
        response = self.ask_gpt(update)
        await context.bot.send_message(chat_id=update.effective_chat.id,  parse_mode='Markdown', text=response.choices[0].message.content)

    async def new_chat(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if str(update.message.from_user.username) != self.whitelist:
            return
        parameter = ' '.join(update.message.text.split()[1:])
        print(parameter)
        if len(parameter) > 0:
            self.chat_history = [{"role": "system", "content": parameter}]
        else:
            self.chat_history = []
        await context.bot.send_message(chat_id=update.effective_chat.id, text="New chat with ChatGPT started.")

    async def change_gpt_version(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        print(update)
        if str(update.message.from_user.username) != self.whitelist:
            return
        keyboard = [
            [
                InlineKeyboardButton("gpt-4-turbo-preview", callback_data="5"),
                InlineKeyboardButton("gpt-4-vision-preview", callback_data="6"),
                InlineKeyboardButton("gpt-3.5-turbo", callback_data="7"),
            ],
            [
                InlineKeyboardButton("gpt-4", callback_data="8"),
                InlineKeyboardButton("gpt-4-32k", callback_data="9"),
                InlineKeyboardButton("Cancel", callback_data="10"),
            ],
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.edit_message_text(text="Choose GPT model version", reply_markup=reply_markup)

    async def show_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        print(update)
        if str(update.message.from_user.username) != self.whitelist:
            return
        keyboard = [
            [
                InlineKeyboardButton("DALL-E quality", callback_data="1"),
                InlineKeyboardButton("GPT model", callback_data="2"),
            ],
            [
                InlineKeyboardButton("DALL-E resolution", callback_data="3"),
                InlineKeyboardButton("New chat", callback_data="4"),
            ],
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text("Please choose:", reply_markup=reply_markup)

    async def generate_image(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        print(update)
        if str(update.message.from_user.username) != self.whitelist:
            return
        image_url = self.imagine_gpt(update)
        await context.bot.send_photo(chat_id=update.effective_chat.id, photo=image_url)

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        print(update)
        if str(update.message.from_user.username) != self.whitelist:
            return
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Type /new to start a new chat with ChatGPT\ntype /help for help.")

    async def unknown(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        print(update)
        if str(update.message.from_user.username) != self.whitelist:
            return
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Sorry, I didn't understand that command.")

    def run(self):
        self.application.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ =='__main__':
    bot = TelegramBot(token=os.getenv('TOKEN'), whitelist=os.getenv('ENV_TELEGRAM_WHITELIST'), bot_name=os.getenv('ENV_TELEGRAM_BOT_NAME'))
    bot.run()