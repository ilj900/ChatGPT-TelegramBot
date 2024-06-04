import os
from dotenv import load_dotenv
from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import Application, filters, MessageHandler, ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler
from openai import OpenAI
import sqlite3

load_dotenv()
statistics_db = "user_statistics.db"
input_price_per_token = 0.0005
output_price_per_token = 0.0015
price_per_image = 0.08

def initialize_database(database_name: str):
    connection = sqlite3.connect(database_name)
    cursor = connection.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS statistics (
                      user_name TEXT PRIMARY KEY,
                      input_token_count INTEGER,
                      output_token_count INTEGER,
                      images_generated INTEGER,
                      current_balance FLOAT)
                   ''')
    connection.commit()
    connection.close()


def get_debit(input_token_count, output_token_count, images_generated):
    return input_token_count * input_price_per_token + output_token_count * output_price_per_token + images_generated * price_per_image


def get_statistics(user_name: str, database_name: str):
    connection = sqlite3.connect(database_name)
    cursor = connection.cursor()
    input_token_count = 0
    output_token_count = 0
    images_generated = 0
    current_balance = 0

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

    cursor.execute('SELECT current_balance FROM statistics WHERE user_name = ?', (user_name,))
    result = cursor.fetchone()
    if result:
        current_balance = result[0]

    connection.close()
    return [input_token_count, output_token_count, images_generated, current_balance]


def is_active(user_name: str, database_name: str):
    statistics = get_statistics(user_name, database_name)
    usage = get_debit(statistics[0], statistics[1], statistics[2])
    if usage < statistics[3]:
        return True
    return False


def account_payment(user_name: str, paid, database_name: str):
    connection = sqlite3.connect(database_name)
    cursor = connection.cursor()
    cursor.execute("SELECT current_balance FROM statistics WHERE user_name=?", (user_name,))
    result = cursor.fetchone()
    if result:
        new_val1 = result[0] + paid
        cursor.execute('''
                            UPDATE statistics
                            SET current_balance=?
                            WHERE user_name=?
                        ''', (new_val1, user_name))
    else:
        cursor.execute('''
                            INSERT INTO statistics (user_name, input_token_count, output_token_count, images_generated, current_balance)
                            VALUES (?, ?, ?, ?, ?)
                        ''', (user_name, 0, 0, 0, paid))
    connection.commit()
    connection.close()


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
                    INSERT INTO statistics (user_name, input_token_count, output_token_count, images_generated, current_balance)
                    VALUES (?, ?, ?, ?, ?)
                ''', (user_name, input_token_count, output_token_count, images_generated, 0.1))

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


def split_code_block(text: str) -> list[str]:
    if len(text) <= 4096:
        return [text]

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


def split_text_block(text: str) -> list[str]:
    if len(text) <= 4096:
        return [text]

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
            strings_2.extend(split_code_block(string))
        else:
            strings_2.extend(split_text_block(string))

    return strings_2


class TelegramBot:
    def __init__(self, token, whitelist, admin, bot_name):
        self.whitelist = whitelist
        self.bot_name = bot_name
        self.admin = admin
        self.MODEL_NAME = "gpt-4o"
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
        self.application.add_handler(CommandHandler('pay', self.process_payment))
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


    async def process_payment(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message.from_user.username == self.admin:
            return

        splited_data = update.message.text.split()
        username = splited_data[1].rstrip(' ').lstrip(' ')
        if not username in self.whitelist:
            return

        try:
            add_to_balance = float(splited_data[2].rstrip(' ').lstrip(' '))
        except ValueError:
            return

        account_payment(username, add_to_balance, statistics_db)
        await context.bot.send_message(chat_id=update.effective_chat.id, text=str(add_to_balance) + "€ was added to " + username + " account.")


    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not str(update.message.from_user.username) in self.whitelist:
            return

        if not is_active(str(update.message.from_user.username), statistics_db):
            await context.bot.send_message(chat_id=update.effective_chat.id, text="You don't have enough € on you account.")
            return

        response = self.ask_gpt(update)
        update_token_count(str(update.message.from_user.username), response.usage.prompt_tokens, response.usage.completion_tokens, 0, statistics_db)
        messages = split_long_message(response.choices[0].message.content)
        for message in messages:
            await context.bot.send_message(chat_id=update.effective_chat.id, parse_mode='Markdown', text=message)

    async def get_usage_stat(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not str(update.message.from_user.username) in self.whitelist:
            return
        splited_text = update.message.text.split()
        if len(splited_text) == 1:
            statistics = get_statistics(str(update.message.from_user.username), statistics_db)
            debit = get_debit(statistics[0], statistics[1], statistics[2])
            await context.bot.send_message(chat_id=update.effective_chat.id, text=("Your total input, output token count and images generated are:\n" + str(statistics[0]) + "/" + str(statistics[1]) + "/" + str(statistics[2]) + "\n"
                                                                                   + "Your remaining balance is " + str(statistics[3] - debit) + "€"))
            return

        if len(splited_text) == 2:
            user_name = splited_text[1].rstrip(' ').lstrip(' ')
            if str(update.message.from_user.username) == self.admin and user_name in self.whitelist:
                statistics = get_statistics(user_name, statistics_db)
                debit = get_debit(statistics[0], statistics[1], statistics[2])
                await context.bot.send_message(chat_id=update.effective_chat.id, text=(user_name + "'s total input, output token count and images generated are:\n" + str(statistics[0]) + "/" + str(statistics[1]) + "/" + str(statistics[2]) + "\n"
                                                                                       + user_name + "'s current remaining balance is " + str(statistics[3] - debit) + "€"))
                return

            await context.bot.send_message(chat_id=update.effective_chat.id, text="User: " + user_name + " was not found.")
            return

        await context.bot.send_message(chat_id=update.effective_chat.id, text="Too much parameters for the command.")

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
                                            "/img - Ask Dall-E to generate an image with provided description. Example:\n```\n/img Draw me an iPhone but it's made of sticks and stones.```" +
                                            "/usage show you your usage statistics.")

    async def unknown(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not str(update.message.from_user.username) in self.whitelist:
            return
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Sorry, I didn't understand that command.")

    def run(self):
        self.application.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    initialize_database(statistics_db)
    bot = TelegramBot(token=os.getenv('TOKEN'), whitelist=os.getenv('ENV_TELEGRAM_WHITELIST').split(','),
                      admin=os.getenv('ENV_TELEGRAM_ADMIN'), bot_name=os.getenv('ENV_TELEGRAM_BOT_NAME'))
    bot.run()
