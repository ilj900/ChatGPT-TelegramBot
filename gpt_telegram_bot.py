import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, filters, MessageHandler, ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler
from openai import OpenAI

load_dotenv()

class TelegramBot:
    def __init__(self, token, whitelist, bot_name):
        self.whitelist = whitelist
        self.bot_name = bot_name
        self.MODEL_NAME = "gpt-4-turbo-preview"
        self.DALLE_VERSION = "dall-e-3"
        self.DALLE_RESOLUTION = "1024x1024"
        self.IMAGE_QUALITY = "hd"
        self.application = ApplicationBuilder().token(os.getenv('TOKEN')).build()
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        self.application.add_handler(CommandHandler('new', self.new_chat))
        self.application.add_handler(CommandHandler('img', self.generate_image))
        self.application.add_handler(MessageHandler(filters.COMMAND, self.unknown))
        self.chat_history = []
        self.gpt_client = OpenAI()
     
    def ask_gpt(self, update: Update):
        self.chat_history.append({"role": "user", "content": update.message.text})
        response = self.gpt_client.chat.completions.create(
            model=self.MODEL_NAME,
            messages=self.chat_history
        )
        self.chat_history.append(response.choices[0].message)
        return response

    def imagine_gpt(self, update: Update):
        response = self.gpt_client.images.generate(
            model=self.DALLE_VERSION,
            prompt=update.message.text,
            size=self.DALLE_RESOLUTION,
            quality=self.IMAGE_QUALITY,
            n=1,
        )

        image_url = response.data[0].url
        return image_url

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if str(update.message.from_user.username) != self.whitelist:
            return
        response = self.ask_gpt(update)
        await context.bot.send_message(chat_id=update.effective_chat.id,  parse_mode='Markdown', text=response.choices[0].message.content)

    async def new_chat(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if str(update.message.from_user.username) != self.whitelist:
            return
        parameter = ' '.join(update.message.text.split()[1:])
        if len(parameter) > 0:
            self.chat_history = [{"role": "system", "content": parameter}]
        else:
            self.chat_history = []
        await context.bot.send_message(chat_id=update.effective_chat.id, text="New chat with ChatGPT started.")

    async def generate_image(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if str(update.message.from_user.username) != self.whitelist:
            return
        image_url = self.imagine_gpt(update)
        await context.bot.send_photo(chat_id=update.effective_chat.id, photo=image_url)

    async def unknown(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if str(update.message.from_user.username) != self.whitelist:
            return
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Sorry, I didn't understand that command.")

    def run(self):
        self.application.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ =='__main__':
    bot = TelegramBot(token=os.getenv('TOKEN'), whitelist=os.getenv('ENV_TELEGRAM_WHITELIST'), bot_name=os.getenv('ENV_TELEGRAM_BOT_NAME'))
    bot.run()