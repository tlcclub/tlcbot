import logging
import pathlib
import sys
from typing import List
import aiogram.utils.markdown as md
from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.utils.exceptions import ValidationError
from bot.keyboards.keyboards import (
    BTN_PLACE_SELL,
    BTN_PLACE_BUY,
    BTN_DONE,
    SELL,
    BUY,
    HELP,
    DONE
)
from bot.messages.messages import Messages
from config import init_config

logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
formatter = logging.Formatter(('%(asctime)s %(name)s-[%(funcName)s:%(lineno)s]'
                               '%(levelname)s %(message)s'))
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

log = logger

config = init_config()

class BotInit:
    @property
    def botClient(self):
        try:
            bot = Bot(token=config.bot.token)
            return bot
        except ValidationError as err:
            log.error(f"{err}")
            sys.exit(1)
        


bot = BotInit().botClient
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)


class Form(StatesGroup):
    mtype = State()
    userid = State()
    title = State()
    description = State()
    photo = State()
    price = State()
    photo_counter = State()


msg = Messages()


@dp.message_handler(commands=['start', 'new'])
async def do_start(message: types.Message):
    await Form.mtype.set()
    await Form.userid.set()
    await message.answer(
        text=('Этот бот поможет Вам правильно оформить '
              'объявление для Барахолки TLC'),
        reply_markup=HELP)


@dp.callback_query_handler(text='sell', state=Form)
async def do_callback_sell(callback_query: types.CallbackQuery,
                           state: FSMContext):
    await bot.answer_callback_query(callback_query.id)
    await state.update_data(mtype='sell', userid=callback_query.from_user.id)
    await Form.next()

    await bot.send_message(
        callback_query.from_user.id,
        text=msg.sell(callback_query.from_user),
    )
    await bot.send_message(callback_query.from_user.id,
                           text="Введите название товара")


@dp.message_handler(state='*', commands='cancel')
@dp.message_handler(Text(equals=['cancel', 'отмена'],
                         ignore_case=True), state='*')
async def cancel_handler(message: types.Message, state: FSMContext):
    """
    Allow user to cancel any action
    """
    current_state = await state.get_state()
    if current_state is None:
        return

    logging.info('Cancelling state %r', current_state)
    # Cancel state and inform user about it
    await state.finish()
    # And remove keyboard (just in case)
    await message.reply('Создание объявлениея отменено!\nПриходите еще!',
                        reply_markup=types.ReplyKeyboardRemove())


@dp.message_handler(state=Form.title)
async def do_title(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['title'] = message.text
        log.info(data)
    await Form.next()
    await message.reply("Введите описание")


@dp.message_handler(state=Form.description)
async def do_description(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['description'] = message.text
        log.info(data)
    await Form.next()
    await message.reply("Введите картинки")


@dp.message_handler(content_types=[types.message.ContentType.PHOTO],
                    state=Form.photo)
async def do_photo(message: types.Message,
                   album: List[types.Message], state: FSMContext):
    log.info(f"DO_PHOTO {message}")
    log.info(f"DO_PHOTO {album}")

    async with state.proxy() as data:
        data['photo'] = list()
        for obj in album:
            if obj.photo:
                photo = obj.photo[-1]
                log.info(photo)
                await photo.download(destination_dir=f"{message.from_user.id}")
                file = await bot.get_file(photo.file_id)
                log.info(file.file_path)
                data['photo'].append(file.file_path)
        log.info(data)
    await message.answer(text="Ежели с картиками закончили",
                         reply_markup=DONE)


@dp.callback_query_handler(text='done', state=Form)
async def do_callback_photo_done(callback_query: types.CallbackQuery,
                                 state: FSMContext):
    async with state.proxy() as data:
        log.info(f" QUERY PHOTO DONE {data}")
    await Form.next()
    await bot.send_message(callback_query.from_user.id,
                           text="осталось ввести ценник")


@dp.message_handler(lambda message: message.text.isdigit(), state=Form)
async def do_price(message: types.Message, state: FSMContext):
    log.info("======")
    log.info(message)
    log.info("======")
    async with state.proxy() as data:

        data['price'] = message.text
        log.info(data)
        await types.ChatActions.upload_photo()
        link = md.link(f'{message.from_user.username}',
                       f'tg://user?id={message.from_user.id}')
        caption = md.text(
            md.text(md.bold(f"Наименование: {data.get('title')}"),
                    md.text(f"за {md.bold(data.get('price'))}₱")),
            md.text(f"{md.bold('Описание')}:"),
            md.text(data.get('description')),
            md.text(f"{md.bold('Локация')}"),
            md.text(f"Прдавец: {link}"),
            md.code('Никогда никому не переводите деньги без гарантий'),
            sep="\n"
        )
        media_group = types.MediaGroup()
        c = 0
        for file in data.get('photo'):
            log.info(file)
            if c == 0:
                attachment = types.InputMediaPhoto(open(
                  pathlib.Path(f"{message.from_user.id}/{file}"), 'rb'),
                  caption=caption,
                  parse_mode=types.ParseMode.MARKDOWN,
                  caption_entities=message.caption_entities)
                media_group.attach_photo(attachment)
                c = +1
            else:
                media_group.attach_photo(
                    types.InputMediaPhoto(
                        open(
                            pathlib.Path(
                              f"{message.from_user.id}/{file}"), 'rb')
                    )
                )

        await message.reply_media_group(media_group,
                                        allow_sending_without_reply=True)
        await bot.send_media_group(
            chat_id=config.bot.admin_id,
            media=media_group,
            allow_sending_without_reply=True,
        )
        # TODO:
        #  await utils.delete(f"{message.from_user.id}/{file}")

    await state.finish()
