import os
from dotenv import load_dotenv
from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import Application, filters, MessageHandler, ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler
from openai import OpenAI
import sqlite3

load_dotenv()
statistics_db = "user_statistics.db"


def initialize_database(database_name: str):
    connection = sqlite3.connect(database_name)
    cursor = connection.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS statistics (
                      user_name TEXT PRIMARY KEY,
                      input_token_count INTEGER,
                      output_token_count INTEGER,
                      images_generated INTEGER)
                   ''')
    connection.commit()
    connection.close()


def get_statistics(user_name: str, database_name: str):
    connection = sqlite3.connect(database_name)
    cursor = connection.cursor()
    input_token_count = 0
    output_token_count = 0
    images_generated = 0

    cursor.execute('SELECT input_token_count FROM statistics WHERE user_name = ?', (user_name,))
    result = cursor.fetchone()
    if result:
        input_token_count = result[0]

    cursor.execute('SELECT output_token_count FROM statistics WHERE user_name = ?', (user_name,))
    result = cursor.fetchone()
    if result:
        output_token_count = result[0]

    cursor.execute('SELECT images_generated FROM statistics WHERE user_name = ?', (user_name,))
    result = cursor.fetchone()
    if result:
        images_generated = result[0]

    connection.close()
    return [input_token_count, output_token_count, images_generated]


def update_token_count(user_name: str, input_token_count, output_token_count, images_generated, database_name: str):
    connection = sqlite3.connect(database_name)
    cursor = connection.cursor()
    cursor.execute("SELECT input_token_count, output_token_count, images_generated FROM statistics WHERE user_name=?", (user_name,))
    result = cursor.fetchone()
    if result:
        new_val1 = result[0] + input_token_count
        new_val2 = result[1] + output_token_count
        new_val3 = result[2] + images_generated
        cursor.execute('''
                    UPDATE statistics
                    SET input_token_count=?, output_token_count=?, images_generated=?
                    WHERE user_name=?
                ''', (new_val1, new_val2, new_val3, user_name))
    else:
        cursor.execute('''
                    INSERT INTO statistics (user_name, input_token_count, output_token_count, images_generated)
                    VALUES (?, ?, ?, ?)
                ''', (user_name, input_token_count, output_token_count, images_generated))

    connection.commit()
    connection.close()


def split_into_blocks(text: str):
    result = []
    in_block_of_code = False
    current_sentence = ''

    i = 0
    while i < len(text):
        if text[i:i+3] == "```":
            if in_block_of_code:
                if current_sentence != '':
                    result.append('```' + current_sentence + '```')
            else:
                if current_sentence != '':
                    result.append(current_sentence.lstrip().rstrip())
            current_sentence = ''
            in_block_of_code = not in_block_of_code
            i += 2
        else:
            current_sentence += text[i]
        i += 1

    return result


def split_code_block(text: str):
    if len(text) <= 4096:
        return text

    code_itself = text.lstrip('```').rstrip('```')

    parts = []
    current_part = str()
    current_length = 0

    for line in code_itself.splitlines(keepends=True):
        line_length = len(line)

        if current_length + line_length <= 4090:
            current_part += line
            current_length += line_length
        else:
            if current_length > 0:
                parts.append('```' + current_part + '```')

            current_part = line
            current_length = line_length

            while current_length > 4090:
                part = ''.join(current_part)[:4090]
                parts.append('```' + part + '```')
                current_part = [line[4090:]]
                current_length = len(current_part[0])

    if current_part:
        parts.append('```' + current_part + '```')

    return parts


def split_text_block(text: str):
    if len(text) <= 4096:
        return text

    parts = []
    current_part = str()
    current_length = 0

    for line in text.splitlines(keepends=True):
        line_length = len(line)

        if current_length + line_length <= 4096:
            current_part += line_length
            current_length += line_length
        else:
            if current_length > 0:
                parts.append(current_part)

            current_part = [line]
            current_length = line_length

            while current_length > 4096:
                part = ''.join(current_part)[:4096]
                parts.append(part)
                current_part = [line[4096:]]
                current_length = len(current_part[0])

    if current_part:
        parts.append(current_part)

    return parts


def split_long_message(long_message: str):
    if len(long_message) <= 4096:
        return long_message

    strings_1 = split_into_blocks(long_message)
    # If message is ill-formatted, then just split it into 4096 chunks
    if len(strings_1) % 2 != 1:
        result = []
        for i in range(0, len(long_message), 4096):
            result.append(long_message[i:i + 4096])
        return result

    strings_2 = []
    for string in strings_1:
        if string.startswith('```') and string.endswith('```'):
            strings_2.append(split_code_block(string))
        else:
            strings_2.append(split_text_block(string))

    return strings_2


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
        self.application.add_handler(CommandHandler('n', self.new_brief_chat))
        self.application.add_handler(CommandHandler('img', self.generate_image))
        self.application.add_handler(CommandHandler('help', self.display_help))
        self.application.add_handler(CommandHandler('usage', self.get_usage_stat))
        self.application.add_handler(CommandHandler('test', self.test))
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

    async def test(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not str(update.message.from_user.username) in self.whitelist:
            return

        test_message = str()
        with open('test.txt') as file:
            line = file.readline()
            while line:
                test_message += line
                line = file.readline()

        messages = split_long_message(test_message)
        for message in messages[:-1]:
            await context.bot.send_message(chat_id=update.effective_chat.id, parse_mode='Markdown', text=message)

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not str(update.message.from_user.username) in self.whitelist:
            return
        response = self.ask_gpt(update)
        update_token_count(str(update.message.from_user.username), response.usage.prompt_tokens, response.usage.completion_tokens, 0, statistics_db)
        await context.bot.send_message(chat_id=update.effective_chat.id, parse_mode='Markdown', text=response.choices[0].message.content)

    async def get_usage_stat(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not str(update.message.from_user.username) in self.whitelist:
            return
        token_count = get_statistics(str(update.message.from_user.username), statistics_db)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Your total input, output token count and images generated are: " + str(token_count[0]) + "/" + str(token_count[1]) + "/" + str(token_count[2]) + " respectively")

    async def new_brief_chat(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not str(update.message.from_user.username) in self.whitelist:
            return
        parameter = ' '.join(update.message.text.split()[1:])
        if len(parameter) > 0:
            self.chat_history = [{"role": "system", "content": "You should be extra brief."}]
        else:
            self.chat_history = []
        await context.bot.send_message(chat_id=update.effective_chat.id, text="New chat with ChatGPT started. Answers will be very brief")

    async def new_chat(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not str(update.message.from_user.username) in self.whitelist:
            return
        parameter = ' '.join(update.message.text.split()[1:])
        if len(parameter) > 0:
            self.chat_history = [{"role": "system", "content": parameter}]
        else:
            self.chat_history = []
        await context.bot.send_message(chat_id=update.effective_chat.id, text="New chat with ChatGPT started.")

    async def generate_image(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not str(update.message.from_user.username) in self.whitelist:
            return
        image_url = self.imagine_gpt(update)
        update_token_count(str(update.message.from_user.username), 0, 0, 1, statistics_db)
        await context.bot.send_photo(chat_id=update.effective_chat.id, photo=image_url)

    async def display_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not str(update.message.from_user.username) in self.whitelist:
            return
        await context.bot.send_message(chat_id=update.effective_chat.id, parse_mode='Markdown',
                                       text="/new - Starts a new chat. You can pass the \"system\" message separated by space. Example:\n```\n/new add \"Bazinga\" at the end of every reply.```\n\n" +
                                            "/n  - Starts a new chat, but the \"system\" message predefined as \"You should be extra brief.\"\n\n" +
                                            "/img - Ask Dall-E to generate an image with provided description. Example:\n```\n/img Draw me an iPhone but it's made of sticks and stones.```")

    async def unknown(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not str(update.message.from_user.username) in self.whitelist:
            return
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Sorry, I didn't understand that command.")

    def run(self):
        self.application.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    test_message = str()
    with open('test.txt') as file:
        line = file.readline()
        while line:
            test_message += line
            line = file.readline()

    messages = split_long_message(test_message)
    initialize_database(statistics_db)
    bot = TelegramBot(token=os.getenv('TOKEN'), whitelist=os.getenv('ENV_TELEGRAM_WHITELIST').split(','),
                      bot_name=os.getenv('ENV_TELEGRAM_BOT_NAME'))
    bot.run()
