import os
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, filters, MessageHandler, ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, ConversationHandler
from openai import OpenAI

load_dotenv()

# Stages
CHOOSE_OPTION, APPLY_OPTION, DUMMY = range(3)
# Callback data
NEW_CHAT, CHANGE_GPT_MODEL_VERSION, CHANGE_DALLE_RESOLUTION, CHANGE_DELLE_QUALITY, \
    SET_DALLE_QUALITY_HD, SET_DALLE_QUALITY_STANDART, \
    SET_DALLE_RESOLUTION_1, SET_DALLE_RESOLUTION_2, SET_DALLE_RESOLUTION_3, \
    SET_MODEL_3_5_TURBO, SET_MODEL_4_TURBO, SET_MODEL_4, SET_MODEL_4_32K, SET_MODEL_4_VISION, \
    DUMMY = range(15)

class TelegramBot:
    def __init__(self, token, whitelist, bot_name):
        self.whitelist = whitelist
        self.bot_name = bot_name
        self.MODEL_NAME = "gpt-4-turbo-preview"
        self.DALLE_VERSION = "dall-e-3"
        self.DALLE_RESOLUTION = "1024x1792"
        self.IMAGE_QUALITY = "hd"
        self.application = ApplicationBuilder().token(os.getenv('TOKEN')).build()
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        self.application.add_handler(CommandHandler('help', self.help))
        self.application.add_handler(CommandHandler('img', self.generate_image))
        self.application.add_handler(
            ConversationHandler(
                entry_points=[CommandHandler("menu", self.show_menu)],
                states={
                    CHOOSE_OPTION: [
                        CallbackQueryHandler(self.change_gpt_version, pattern="^" + str(CHANGE_GPT_MODEL_VERSION) + "$"),
                        CallbackQueryHandler(self.change_dalle_quality, pattern="^" + str(CHANGE_DELLE_QUALITY) + "$"),
                        CallbackQueryHandler(self.change_dalle_resolution, pattern="^" + str(CHANGE_DALLE_RESOLUTION) + "$"),
                    ],
                    APPLY_OPTION: [
                        CallbackQueryHandler(self.set_dalle_quality_hd, pattern="^" + str(SET_DALLE_QUALITY_HD) + "$"),
                        CallbackQueryHandler(self.set_dalle_quality_standard, pattern="^" + str(SET_DALLE_QUALITY_STANDART) + "$"),
                        CallbackQueryHandler(self.set_dalle_resolution_1, pattern="^" + str(SET_DALLE_RESOLUTION_1) + "$"),
                        CallbackQueryHandler(self.set_dalle_resolution_2, pattern="^" + str(SET_DALLE_RESOLUTION_2) + "$"),
                        CallbackQueryHandler(self.set_dalle_resolution_3, pattern="^" + str(SET_DALLE_RESOLUTION_3) + "$"),
                        CallbackQueryHandler(self.set_model_gpt_4, pattern="^" + str(SET_MODEL_4) + "$"),
                        CallbackQueryHandler(self.set_model_gpt_4_32k, pattern="^" + str(SET_MODEL_4_32K) + "$"),
                        CallbackQueryHandler(self.set_model_gpt_4_turbo_preview, pattern="^" + str(SET_MODEL_4_TURBO) + "$"),
                        CallbackQueryHandler(self.set_model_gpt_4_vision_preview, pattern="^" + str(SET_MODEL_4_VISION) + "$"),
                        CallbackQueryHandler(self.set_model_gpt_3_5_turbo, pattern="^" + str(SET_MODEL_3_5_TURBO) + "$"),
                    ],
                    DUMMY: [
                        CallbackQueryHandler(self.dummy, pattern="^" + str(DUMMY) + "$"),
                    ],
                },
                fallbacks=[CommandHandler("menu", self.show_menu)],
            )
        )
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
        for entry in self.chat_history:
            print(entry)
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
        print(parameter)
        if len(parameter) > 0:
            self.chat_history = [{"role": "system", "content": parameter}]
        else:
            self.chat_history = []
        await context.bot.send_message(chat_id=update.effective_chat.id, text="New chat with ChatGPT started.")

    async def generate_image(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        print(update)
        if str(update.message.from_user.username) != self.whitelist:
            return
        image_url = self.imagine_gpt(update)
        await context.bot.send_photo(chat_id=update.effective_chat.id, photo=image_url)

    async def show_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        print(update)
        if str(update.message.from_user.username) != self.whitelist:
            return DUMMY
        keyboard = [
            [
                InlineKeyboardButton("GPT model", callback_data=str(CHANGE_GPT_MODEL_VERSION)),
            ],
            [
                InlineKeyboardButton("DALL-E resolution", callback_data=str(CHANGE_DALLE_RESOLUTION)),
                InlineKeyboardButton("DALL-E quality", callback_data=str(CHANGE_DELLE_QUALITY)),
            ],
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text("Please choose:", reply_markup=reply_markup)

        return CHOOSE_OPTION

    async def change_gpt_version(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()

        keyboard = [
            [
                InlineKeyboardButton("gpt-4-turbo-preview", callback_data=str(SET_MODEL_4_TURBO)),
                InlineKeyboardButton("gpt-4-vision-preview", callback_data=str(SET_MODEL_4_VISION)),
            ],
            [
                InlineKeyboardButton("gpt-4", callback_data=str(SET_MODEL_4)),
                InlineKeyboardButton("gpt-4-32k", callback_data=str(SET_MODEL_4_32K)),
                InlineKeyboardButton("gpt-3.5-turbo", callback_data=str(SET_MODEL_3_5_TURBO)),
            ],
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(text="Choose GPT model version", reply_markup=reply_markup)

        return APPLY_OPTION

    async def change_dalle_quality(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()

        keyboard = [
            [
                InlineKeyboardButton("standard", callback_data=str(SET_DALLE_QUALITY_STANDART)),
                InlineKeyboardButton("hd", callback_data=str(SET_DALLE_QUALITY_HD)),
            ]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(text="Choose DALL-E quality", reply_markup=reply_markup)

        return APPLY_OPTION

    async def change_dalle_resolution(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()

        keyboard = [
            [
                InlineKeyboardButton("1024x1024", callback_data=str(SET_DALLE_RESOLUTION_1)),
                InlineKeyboardButton("1792x1024", callback_data=str(SET_DALLE_RESOLUTION_2)),
                InlineKeyboardButton("1024x1792", callback_data=str(SET_DALLE_RESOLUTION_3)),
            ]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(text="Choose DALL-E resolution", reply_markup=reply_markup)

        return APPLY_OPTION

    #Apply options

    async def set_dalle_quality_hd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        self.IMAGE_QUALITY = "hd"
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(text="You've changed DALL-E's quality to HD!")
        return ConversationHandler.END

    async def set_dalle_quality_standard(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        self.IMAGE_QUALITY = "standard"
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(text="You've changed DALL-E's quality to standard!")
        return ConversationHandler.END

    async def set_dalle_resolution_1(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        self.DALLE_RESOLUTION = "1024x1024"
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(text="You've changed DALL-E's resolution to 1024x1024!")
        return ConversationHandler.END

    async def set_dalle_resolution_2(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        self.DALLE_RESOLUTION = "1792x1024"
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(text="You've changed DALL-E's resolution to 1792x1024!")
        return ConversationHandler.END

    async def set_dalle_resolution_3(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        self.DALLE_RESOLUTION = "1024x1792"
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(text="You've changed DALL-E's resolution to 1024x1792!")
        return ConversationHandler.END

    async def set_model_gpt_4_turbo_preview(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        self.MODEL_NAME = "gpt-4-turbo-preview"
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(text="You've changed GPT model to gpt-4-turbo-preview!")
        return ConversationHandler.END

    async def set_model_gpt_4_vision_preview(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        self.MODEL_NAME = "gpt-4-vision-preview"
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(text="You've changed GPT model to gpt-4-vision-preview!")
        return ConversationHandler.END

    async def set_model_gpt_4(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        self.MODEL_NAME = "gpt-4"
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(text="You've changed GPT model to gpt-4!")
        return ConversationHandler.END

    async def set_model_gpt_4_32k(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        self.MODEL_NAME = "gpt-4-32k"
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(text="You've changed GPT model to gpt-4-32k!")
        return ConversationHandler.END

    async def dummy(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()
        return ConversationHandler.END

    async def set_model_gpt_3_5_turbo(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        self.MODEL_NAME = "gpt-3.5-turbo"
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(text="You've changed GPT model to gpt-3.5-turbo!")
        return ConversationHandler.END

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