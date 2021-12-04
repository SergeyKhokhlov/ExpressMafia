import json
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils.helper import HelperMode
from data import db_session, users
import logging
from random import choice

logging.basicConfig(level=logging.INFO)
bot = Bot(token=token)
dp = Dispatcher(bot, storage=MemoryStorage())


class StatesClass(StatesGroup):  # Машина состояний
    mode = HelperMode.snake_case
    name_room = State()
    password_room = State()
    join_password_room = State()
    dead = State()
    don = State()
    policeman = State()
    doctor = State()
    end_night = State()


@dp.message_handler(commands=["start", "update"])  # Старт игры
async def cmd_start(message: types.Message):
    session = db_session.create_session()
    user_search = session.query(users.User).filter(message.chat.id == users.User.message_id).all()
    if len(user_search) == 0:  # Запись в бд
        try:
            user = users.User(nickname=(message.from_user.first_name + " " +
                                        message.from_user.last_name),
                              message_id=message.chat.id, room="")
        except Exception:
            user = users.User(nickname=(message.from_user.first_name),
                              message_id=message.chat.id, room="")
        session.add(user)
        session.commit()
    if message.text == "/start":
        await bot.send_message(message.chat.id, "Приветствуем Вас "
                                                "в онлайн-помощнике для игры в мафию")
    if not isroom(message):
        await message.answer("Список комнат:", reply_markup=take_all_rooms())
    else:
        await bot.send_message(message.chat.id, "Вы в комнате: " + str(user_search[0].room))


# Создание комнаты:

@dp.message_handler(state=None, commands=['addroom'])
async def addroom_name(message: types.Message):
    session = db_session.create_session()
    user_search = session.query(users.User).filter(message.chat.id == users.User.message_id).first()
    if user_search.room != "":
        await message.answer("Вы в комнате: " + str(user_search.room))
    else:
        await message.answer("Введите название комнаты", reply_markup=create_cancel_keyboard())
        await StatesClass.name_room.set()


@dp.message_handler(state=StatesClass.name_room)
async def addroom_take_name(message: types.Message, state: FSMContext):
    if message.text == "Отменить":
        await message.answer("Действие отменено")
        await state.finish()
    else:
        room_name = message.text
        await state.update_data(room_name=room_name)
        await message.answer('Введите пароль от комнаты', reply_markup=create_cancel_keyboard())
        await StatesClass.next()


@dp.message_handler(state=StatesClass.password_room)
async def addroom_take_password_and_create_room(message: types.Message, state: FSMContext):
    if message.text == "Отменить":
        await message.answer("Действие отменено")
    else:
        session = db_session.create_session()
        password = message.text
        await state.update_data(room_password=password)
        data = await state.get_data()
        name = data.get("room_name")
        await message.answer("Вы в комнате " + "<b>" + name + "</b>",
                             reply_markup=types.ReplyKeyboardRemove(), parse_mode="html")
        founder = session.query(users.User).filter(message.chat.id ==
                                                   users.User.message_id).first().id
        args = []
        with open("static/json/game.json", encoding="utf-8") as file:
            data = json.loads(file.readline())
            for i in data:
                args.append(i)
        with open("static/json/base.json", encoding="utf-8") as file:
            temp = json.loads(file.readline())
            temp[name] = temp.pop("0")
            temp[name]["password"] = password
            temp[name]["founder"] = founder
            temp[name]["users"] = [founder]
        with open("static/json/game.json", "w", encoding="utf-8") as file:
            data.update(temp)
            json.dump(data, file)
        user = session.query(users.User).filter(founder == users.User.id).first()
        user.room = name
        session.commit()
    await state.finish()


# Функции команд: /exit,

@dp.message_handler(commands=["exit"])  # Выход из комнаты
async def exit_room(message: types.Message):
    if isroom(message):
        session = db_session.create_session()
        user = session.query(users.User).filter(users.User.message_id == message.from_user.id).first()
        room = user.room
        with open("static/json/game.json", encoding="utf-8") as file:
            data = json.loads(file.readline())
        users_list = data[room]["users"].copy()
        if data[user.room]["mafia"][0] == 0:
            for i in users_list:
                if i != user.id:
                    take_user = session.query(users.User).filter(i == users.User.id).first()
                    await bot.send_message(take_user.message_id, "Комната была удалена"
                                                                 " администратором.")
            with open("static/json/game.json", "w", encoding="utf-8") as file:
                x = data[user.room]["users"].remove(user.id)
                if user.id == data[str(user.room)]["founder"]:
                    del data[user.room]
                json.dump(data, file)
            clearing_db(room)
            await message.answer("Вы покинули комнату")
            for i in users_list:
                take_user = session.query(users.User).filter(i == users.User.id).first()
                await bot.send_message(take_user.message_id,
                                       "Список комнат:", reply_markup=take_all_rooms())
        else:
            await message.answer("Сначала завершите игру!")
    else:
        await message.answer("Вы не в комнате!")


@dp.callback_query_handler()  # Нажатие на inline-клавиатуру для вхождения в комнату
async def process_callback(call, state: FSMContext):
    with open("static/json/game.json", encoding="utf-8") as file:
        data = json.loads(file.readline())
    if data[call.data]["mafia"][0] != 0:
        await bot.send_message(call.message.chat.id, "В комнате уже запущена игра!")
        return
    await bot.answer_callback_query(call.id, "Не забудьте выключить звук 🔕", show_alert=True)
    await state.update_data(room_name=call.data)
    await bot.send_message(call.message.chat.id, "Введите пароль от комнаты",
                           reply_markup=create_cancel_keyboard())
    await StatesClass.join_password_room.set()


@dp.message_handler(state=StatesClass.join_password_room)  # Функция для входа в комнату
async def join_room(message: types.Message, state: FSMContext):
    if message.text == "Отменить":
        await bot.send_message(message.chat.id, "Действие отменено")
    else:
        data = await state.get_data()
        room_name = data.get("room_name")
        room_password = message.text
        await state.update_data(room_name=room_password)
        session = db_session.create_session()
        with open("static/json/game.json", encoding="utf-8") as file:
            data = json.loads(file.readline())
            if data[room_name]["password"] == message.text:
                is_password = True
            else:
                is_password = False
            for i in data:
                if i == room_name:
                    user = session.query(users.User).filter(users.User.message_id ==
                                                            message.from_user.id).first()
                    user.room = room_name
                    if is_password:
                        session.commit()
        if is_password:
            with open("static/json/game.json", "w", encoding="utf-8") as file:
                data[room_name]["users"] = data[room_name]["users"] + [user.id]
                json.dump(data, file)
                line = "Вы в комнате: " + str(user.room)
        else:
            line = "Пароль не подходит."
        await message.answer(line, reply_markup=types.ReplyKeyboardRemove())
        for i in data[room_name]["users"]:
            if i != user.id and is_password:
                take_user = session.query(users.User).filter(i == users.User.id).first()
                await bot.send_message(take_user.message_id,
                                       ("<b>" + str(user.nickname) +
                                        "</b> в комнате"),
                                       reply_markup=types.ReplyKeyboardRemove(),
                                       parse_mode="html")
        if not is_password:
            await message.answer("Список комнат:", reply_markup=take_all_rooms())
    await state.finish()


@dp.message_handler(commands=["all"])  # Вывод всех игроков в комнате
async def all_players(message: types.Message):
    await message.answer(("<b>Игроки в комнате:</b>\n" + "\n".join(all_users_dropper(message))),
                         parse_mode="html")


@dp.message_handler(commands=["begin"])  # Функция для начала игры, выдачи карт
async def begin(message: types.Message):
    if not isroom(message):
        await message.answer("Вы не в комнате!")
        return
    session = db_session.create_session()
    user_search = session.query(users.User).filter(message.chat.id == users.User.message_id).first()
    with open("static/json/game.json", encoding="utf-8") as file:
        data = json.loads(file.readline())
        if len(data[user_search.room]["users"]) < 4:
            await message.answer_sticker("CAACAgIAAxkBAAID-2GKo3-Pm4kO"
                                         "2DVMcVxZmywigYbUAAJLAgACVp29CmJQRdBQ-nGcIgQ")
            await message.answer("Для игры необходимо минимум 4 игрока")
            return
        elif data[user_search.room]["mafia"][0] != 0:
            await message.answer_sticker("CAACAgQAAxkBAAIEhGGKxZPxKTlAZW5Phw"
                                         "I8ms6zqusiAAIzAAOHpawOXnZ2nFGV2LoiBA")
            await message.answer("Игра уже начата")
            return
    players = data[user_search.room]["users"].copy()
    file.close()
    mafias = []
    count_mafias = int(len(players) / 3)
    for i in range(count_mafias):  # Распределение мафий
        mafia = choice(players)
        while mafia in mafias:
            mafia = choice(players)
        mafias.append(mafia)
        players.remove(mafia)
    doctor = choice(players)  # Доктор
    players.remove(doctor)
    policeman = choice(players)  # Комиссар
    players.remove(policeman)
    poor = players  # Мирные жители
    with open("static/json/game.json", "w", encoding="utf-8") as file:
        data[user_search.room]["mafia"] = mafias
        data[user_search.room]["doctor"] = doctor
        data[user_search.room]["policeman"] = policeman
        data[user_search.room]["poor"] = poor
        data[user_search.room]["don"] = mafias[0]
        data[user_search.room]["all"] = [policeman, doctor] + mafias + poor
        json.dump(data, file)
        file.close()
    for i in mafias:
        try:
            take_user = session.query(users.User).filter(i == users.User.id).first()
            await bot.send_sticker(take_user.message_id, "CAACAgIAAxkBAAIEgmGKxVuLXIgPc3-1FpluRp"
                                                         "bhmP33AALhAANWnb0KW8GUi0D406AiBA")
            await bot.send_message(take_user.message_id, "Начинаем")
            if i == mafias[0]:
                await bot.send_message(take_user.message_id, "Вам выпала роль <b>дона мафии</b>",
                                       parse_mode="html")
            else:
                await bot.send_message(take_user.message_id, "Вам выпала роль <b>мафии</b>",
                                       parse_mode="html")
            await bot.send_message(take_user.message_id, "Первый круг. Придумайте "
                                                         "ситуацию и представьтесь.")
        except Exception:
            pass
    for i in poor:
        try:
            take_user = session.query(users.User).filter(i == users.User.id).first()
            await bot.send_sticker(take_user.message_id, "CAACAgIAAxkBAAIEgmGKxVuLXIgPc3-1FpluRp"
                                                         "bhmP33AALhAANWnb0KW8GUi0D406AiBA")
            await bot.send_message(take_user.message_id, "Начинаем")
            await bot.send_message(take_user.message_id, "Вам выпала роль <b>мирного жителя</b>",
                                   parse_mode="html")
            await bot.send_message(take_user.message_id, "Первый круг. Придумайте "
                                                         "ситуацию и представьтесь.")
        except Exception:
            pass
    try:
        take_user = session.query(users.User).filter(doctor == users.User.id).first()
        await bot.send_sticker(take_user.message_id, "CAACAgIAAxkBAAIEgmGKxVuLXIgPc3-1FpluRp"
                                                     "bhmP33AALhAANWnb0KW8GUi0D406AiBA")
        await bot.send_message(take_user.message_id, "Начинаем")
        await bot.send_message(take_user.message_id, "Вам выпала роль <b>доктора</b>",
                               parse_mode="html")
        await bot.send_message(take_user.message_id, "Первый круг. Придумайте "
                                                     "ситуацию и представьтесь.")
    except Exception:
        pass
    try:
        take_user = session.query(users.User).filter(policeman == users.User.id).first()
        await bot.send_sticker(take_user.message_id, "CAACAgIAAxkBAAIEgmGKxVuLXIgPc3-1FpluRp"
                                                     "bhmP33AALhAANWnb0KW8GUi0D406AiBA")
        await bot.send_message(take_user.message_id, "Начинаем")
        await bot.send_message(take_user.message_id, "Вам выпала роль <b>комиссара</b>",
                               parse_mode="html")
        await bot.send_message(take_user.message_id, "Первый круг. Придумайте "
                                                     "ситуацию и представьтесь.")
    except Exception:
        pass


# Ночь

@dp.message_handler(commands=["night"])  # Запуск ночи и ход мафии
async def night(message: types.Message):
    if not isroom(message):
        await message.answer("Вы не в комнате!")
        return
    if not isbegin(message):
        await message.answer("Игра не начата!")
        return
    session = db_session.create_session()
    user_search = session.query(users.User).filter(message.chat.id == users.User.message_id).first()
    with open("static/json/game.json", encoding="utf-8") as file:
        data = json.loads(file.readline())
    mafia_names = []
    if data[user_search.room]["isvote"] == 1:
        await message.answer("Дневное голосование не завершено!")
        return
    for i in data[user_search.room]["users"]:
        take_user_info = session.query(users.User).filter(i == users.User.id).first()
        stickers = ["CAACAgIAAxkBAAIBn2GjDXxUBqvyibYcau6myewqbqjXAAJ-FQAC6NbiEkjdES0Nk4maIgQ",
                    "CAACAgIAAxkBAAIBoGGjDeXG2AUO9T_LgIRFvU2ux4n8AAIOAQACVp29ChGpLWjCceBoIgQ",
                    "CAACAgIAAxkBAAIBoWGjDmLI7luroK7mAAEGylZIlPGm6AACpAYAAmMr4gk38-fCvL8kOyIE",
                    "CAACAgIAAxkBAAIBomGjDpg_7u-PsI07SxNn4w4z9js6AALAAgACVp29Cqa0tN1UgB8LIgQ"]
        await bot.send_sticker(take_user_info.message_id, choice(stickers))
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Играть", url="https://prizes.gamee.com/game/kAHVRl"))
        await bot.send_message(take_user_info.message_id, "Город засыпает", reply_markup=markup)
    for i in data[user_search.room]["mafia"]:
        take_user = session.query(users.User).filter(i == users.User.id).first()
        mafia_names.append(take_user.nickname)
    for i in data[user_search.room]["mafia"]:
        take_user = session.query(users.User).filter(i == users.User.id).first()
        if len(mafia_names) > 1:
            await bot.send_message(take_user.message_id, "Просыпатся <b>мафия</b>: " +
                                   ", ".join(mafia_names), parse_mode="html")
        else:
            await bot.send_message(take_user.message_id, "Просыпается <b>мафия</b> " +
                                   mafia_names[0], parse_mode="html")
    who_dead = []
    n = 0
    for i in data[user_search.room]["users"]:
        n += 1
        take_user_kill = session.query(users.User).filter(i == users.User.id).first()
        who_dead.append((str(n) + ". " + take_user_kill.nickname))
    for i in role_dropper(message, "mafia"):
        mafia_player = session.query(users.User).filter(users.User.id == i).first()
        await bot.send_message(mafia_player.message_id,
                               ("<b>Кого убьём сегодня?</b>\n" + "\n".join(who_dead)),
                               parse_mode="html")
    for i in role_dropper(message, "mafia"):
        mafia_player = session.query(users.User).filter(users.User.id == i).first()
        state = dp.current_state(chat=mafia_player.message_id, user=mafia_player.message_id)
        await state.set_state(StatesClass.don)


@dp.message_handler(state=StatesClass.don)  # Убийство мафии и переход к проверке Дона
async def don_check(message: types.Message, state: FSMContext):
    session = db_session.create_session()
    if len(message.text) == 2 and message.text[0].isdigit() and message.text[1] == ".":
        if int(message.text[0]) <= len(role_dropper(message, "users")):
            user = session.query(users.User).filter(
                users.User.nickname == all_users_dropper(message, numerate=False)[
                    int(message.text[:-1]) - 1]).first()
            user_don = session.query(users.User).filter(
                role_dropper(message, "don") == users.User.id).first()
            with open("static/json/game.json", encoding="utf-8") as file:
                data = json.loads(file.readline())
            with open("static/json/game.json", "w", encoding="utf-8") as file:
                data[user_don.room]["die"] = user.id
                json.dump(data, file)
                file.close()
            if data[user.room]["don"] in data[user.room]["mafia"]:
                await bot.send_message(user_don.message_id, "Просыпается <b>дон мафии</b> " +
                                       user_don.nickname,
                                       parse_mode="html")
                await bot.send_message(user_don.message_id, ("<b>Кто комиссар?</b>\n" +
                                                             "\n".join(
                                                                 all_users_dropper(message, True))),
                                       parse_mode="html")
                await state.finish()
                state = dp.current_state(chat=user_don.message_id, user=user_don.message_id)
                await state.set_state(StatesClass.policeman)
            else:
                if role_dropper(message, "policeman") != "0":
                    policeman_user = session.query(users.User).filter(
                        str(role_dropper(message, "policeman")) ==
                        users.User.id).first()
                    await bot.send_message(policeman_user.message_id, "Просыпается <b>комиссар</b> "
                                           + policeman_user.nickname,
                                           parse_mode="html")
                    await bot.send_message(policeman_user.message_id, "<b>Кто мафия?</b>\n" +
                                           "\n".join(all_users_dropper(message, True)),
                                           parse_mode="html")
                    await state.finish()
                    state = dp.current_state(chat=policeman_user.message_id,
                                             user=policeman_user.message_id)
                    await state.set_state(StatesClass.doctor)
                else:
                    if role_dropper(message, "doctor") != "0":
                        doc_user = session.query(users.User).filter(
                            str(role_dropper(message, "doctor")) ==
                            users.User.id).first()
                        await bot.send_message(doc_user.message_id, "Просыпается <b>доктор</b> " +
                                               doc_user.nickname,
                                               parse_mode="html")
                        await bot.send_message(doc_user.message_id, "<b>Кого лечим?</b>\n" +
                                               "\n".join(all_users_dropper(message)),
                                               parse_mode="html")
                        await state.finish()
                        state = dp.current_state(chat=doc_user.message_id, user=doc_user.message_id)
                        await state.set_state(StatesClass.end_night)
                    else:
                        with open("static/json/game.json", encoding="utf-8") as file:
                            data = json.loads(file.readline())
                        die_user = session.query(users.User).filter(
                            users.User.id == data[user_don.room]["die"]).first()
                        await night_result(die_user.room, False, die_user)
                        await state.finish()
        else:
            await message.answer("Игрока с таким номером не существует!")
    else:
        user_id = session.query(users.User).filter(message.chat.id == users.User.message_id).first()
        for i in role_dropper(message, "mafia"):
            if i != user_id.id:
                take_user = session.query(users.User).filter(users.User.id == i).first()
                await bot.send_message(take_user.message_id, user_id.nickname + ": " +
                                       message.text)


@dp.message_handler(state=StatesClass.policeman)  # Функция для хода дона мафии
async def don_mafia(message: types.Message, state: FSMContext):  # и начало хода комиссара
    session = db_session.create_session()
    if not str(message.text).isdigit():
        await message.answer("Такого игрока не существует!")
        return
    if int(message.text) > len(role_dropper(message, "all")):
        await message.answer("Игрока с таким номером не существует!")
        return
    don_user = session.query(users.User).filter(role_dropper(message, "mafia")[0] ==
                                                users.User.id).first()
    take_policeman = session.query(users.User).filter(str(role_dropper(message, "all")[0])
                                                      == users.User.id).first()
    if all_users_dropper(message, True)[int(message.text[0]) - 1].split(". ")[1] \
            == take_policeman.nickname:
        await bot.send_message(don_user.message_id, "Да")
    else:
        await bot.send_message(don_user.message_id, "Нет")
    if role_dropper(message, "policeman") != "0":
        policeman_user = session.query(users.User).filter(str(role_dropper(message, "policeman")) ==
                                                          users.User.id).first()
        await bot.send_message(policeman_user.message_id, "Просыпается <b>комиссар</b> " +
                               policeman_user.nickname,
                               parse_mode="html")
        await bot.send_message(policeman_user.message_id, "<b>Кто мафия?</b>\n" +
                               "\n".join(all_users_dropper(message, True)), parse_mode="html")
        await state.finish()
        state = dp.current_state(chat=policeman_user.message_id, user=policeman_user.message_id)
        await state.set_state(StatesClass.doctor)
    else:
        if role_dropper(message, "doctor") != "0":
            doc_user = session.query(users.User).filter(str(role_dropper(message, "doctor")) ==
                                                        users.User.id).first()
            await bot.send_message(doc_user.message_id, "Просыпается <b>доктор</b> "
                                   + doc_user.nickname, parse_mode="html")
            await bot.send_message(doc_user.message_id, "<b>Кого лечим?</b>\n" +
                                   "\n".join(all_users_dropper(message)),
                                   parse_mode="html")
            await state.finish()
            state = dp.current_state(chat=doc_user.message_id, user=doc_user.message_id)
            await state.set_state(StatesClass.end_night)
        else:
            with open("static/json/game.json", encoding="utf-8") as file:
                data = json.loads(file.readline())
            die_user = session.query(users.User).filter(users.User.id ==
                                                        data[don_user.room]["die"]).first()
            await night_result(die_user.room, False, die_user)
            await state.finish()


@dp.message_handler(state=StatesClass.doctor)  # Функция для хода комиссара и начало хода доктора
async def police(message: types.Message, state: FSMContext):
    session = db_session.create_session()
    if message.text.isdigit() and len(role_dropper(message, "all")) >= int(message.text) > 0:
        police_user = session.query(users.User).filter(str(role_dropper(message, "policeman")) ==
                                                       users.User.id).first()
        mafias = []
        for i in role_dropper(message, "mafia"):
            take_mafia_name = session.query(users.User).filter(i == users.User.id).first()
            mafias.append(take_mafia_name.nickname)
        if all_users_dropper(message, True)[int(message.text[0]) - 1].split(". ")[1] in mafias:
            await bot.send_message(police_user.message_id, "Да")
        else:
            await bot.send_message(police_user.message_id, "Нет")
        if role_dropper(message, "doctor") != "0":
            doc_user = session.query(users.User).filter(str(role_dropper(message, "doctor")) ==
                                                              users.User.id).first()
            await bot.send_message(doc_user.message_id, "Просыпается <b>доктор</b> " +
                                   doc_user.nickname, parse_mode="html")
            await bot.send_message(doc_user.message_id, "<b>Кого лечим?</b>\n" +
                                   "\n".join(all_users_dropper(message)),
                                   parse_mode="html")
            await state.finish()
            state = dp.current_state(chat=doc_user.message_id, user=doc_user.message_id)
            await state.set_state(StatesClass.end_night)
        else:
            with open("static/json/game.json", encoding="utf-8") as file:
                data = json.loads(file.readline())
            die_user = session.query(users.User).filter(users.User.id ==
                                                        data[police_user.room]["die"]).first()
            await night_result(police_user.room, False, die_user)
            await state.finish()
    else:
        await message.answer("Такого игрока не существует!")


@dp.message_handler(state=StatesClass.end_night)  # Функция для хода доктора и завершения ночи
async def endNight(message: types.Message, state: FSMContext):
    session = db_session.create_session()
    with open("static/json/game.json", encoding="utf-8") as file:
        data = json.loads(file.readline())
    if message.text.isdigit() and len(role_dropper(message, "users")) >= int(message.text) > 0:
        user = session.query(users.User).filter(users.User.message_id == message.chat.id).first()
        user_hill = session.query(users.User).filter(users.User.nickname == all_users_dropper(
            message, numerate=False)[int(message.text) - 1]).first()
        if user_hill.message_id != data[user.room]["help"]:
            with open("static/json/game.json", "w", encoding="utf-8") as file:
                data[user.room]["help"] = user_hill.message_id
                json.dump(data, file)
                file.close()
            result = False
            die_user = session.query(users.User).filter(users.User.id == data[user.room]["die"]).first()
            room = die_user.room
            if die_user.message_id == user_hill.message_id:
                result = True
            await night_result(room, result, die_user)
            await state.finish()
        else:
            await message.answer("Вы уже лечили этого пользователя!")
    else:
        await message.answer("Такого игрока не существует!")


async def night_result(room, result, die_user):
    session = db_session.create_session()
    isgame = True
    if not result:
        with open("static/json/game.json", encoding="utf-8") as file:
            data = json.loads(file.readline())
        with open("static/json/game.json", "w", encoding="utf-8") as file:
            x = data[room]["users"].remove(die_user.id)
            try:
                x = data[room]["mafia"].remove(die_user.id)
            except Exception:
                pass
            try:
                if data[room]["doctor"] == die_user.id:
                    data[room]["doctor"] = "0"
            except Exception:
                pass
            try:
                if data[room]["policeman"] == die_user.id:
                    data[room]["policeman"] = "0"
            except Exception:
                pass
            try:
                x = data[room]["poor"].remove(die_user.id)
            except Exception:
                pass
            json.dump(data, file)
        die_user.room = ""
        session.commit()
        file.close()
    with open("static/json/game.json", encoding="utf-8") as file:
        data = json.loads(file.readline())
    user_list = list(set(data[room]["users"] + [data[room]["die"]]))
    for i in user_list:
        take_user = session.query(users.User).filter(i == users.User.id).first()
        if result:
            stickers = ["CAACAgIAAxkBAAIJNGGPodx0DWbTFjJ-yXt665iM4q26AALaBwACRvusBDMkEAZ6"
                        "tZv0IgQ", "CAACAgIAAxkBAAIJOGGPpL1y7X4ZPMxmfLyTjQc9ZXSVAAJhAAMDQQ"
                                   "8teL9m4FCOAjYiBA", "CAACAgEAAxkBAAIJOWGPpS9-lArV3aSszS"
                                                       "C-CvZdvULUAAIHAAOhBQwNcKYXLseMHYEiBA"]
            await bot.send_sticker(take_user.message_id, choice(stickers))
            await bot.send_message(take_user.message_id, "Город просыпается. "
                                                         "Сегодня без потерь.")
        else:
            stickers = ["CAACAgEAAxkBAAIJIWGPnQABNzAxRok1GYz-5Iw3LRX6gQACBgADoQUMDUiEFCGKiN"
                        "tuIgQ", "CAACAgIAAxkBAAIJM2GPoZZtiQ8zzeMMuipp783BTpGMAAKdAgACVp29C"
                                 "kdDP2lNj5eRIgQ", "CAACAgIAAxkBAAIJNWGPo-vY7onaz5VY7Ane_lg"
                                                   "zvDZVAAKaEAACxpXRS5vXvdQx7K4cIgQ"]
            await bot.send_sticker(take_user.message_id, choice(stickers))
            await bot.send_message(take_user.message_id, "Город просыпается. "
                                                         "Игрок <b>" + die_user.nickname +
                                   "</b> найден мёртвым.", parse_mode="html")
            if die_user.message_id == take_user.message_id:
                await bot.send_message(take_user.message_id,
                                       "Подписывайтесь на создателя бота: "
                                       "https://instagram.com/khokhl0v.s")
            data_lst = [data[room]["doctor"]] + [data[room]["policeman"]] + data[room]["poor"]
            while "0" in data_lst:
                data_lst.remove("0")
            if len(data[room]["mafia"]) >= len(data_lst):
                await bot.send_sticker(take_user.message_id, "CAACAgIAAxkBAAIJ6mGP6-TG7"
                                                             "tcCOF0S9c8YusgTF7A4AALGAANWnb"
                                                             "0KbQmONokdLRciBA")
                await bot.send_message(take_user.message_id, "Игра завершена. "
                                                             "Мафия одержала победу.")
                await bot.send_message(take_user.message_id, "Подписывайтесь на создателя бота: "
                                                             "https://instagram.com/khokhl0v.s")
                isgame = False
            if len(data[room]["mafia"]) == 0:
                await bot.send_sticker(take_user.message_id, "CAACAgIAAxkBAAINSWGQNgKgmURc3m"
                                                             "5i-59EpLtlAuisAAKLAgACVp29Cve0"
                                                             "YiYNjzvzIgQ")
                await bot.send_message(take_user.message_id, "Игра завершена. "
                                                             "Мирные жители одержали победу.")
                await bot.send_message(take_user.message_id, "Подписывайтесь на создателя бота: "
                                                             "https://instagram.com/khokhl0v.s")
                isgame = False
    if not isgame:
        with open("static/json/game.json", encoding="utf-8") as file:
            data = json.loads(file.readline())
        with open("static/json/game.json", "w", encoding="utf-8") as file:
            del data[room]
            json.dump(data, file)
        clearing_db(room)


@dp.message_handler(commands=["vote"])  # Функция для голосования
async def vote_day(message: types.Message, state: FSMContext):
    if not isbegin(message):
        await message.answer("Игра не начата!")
        return
    session = db_session.create_session()
    with open("static/json/game.json", encoding="utf-8") as file:
        data = json.loads(file.readline())
    user = session.query(users.User).filter(message.chat.id == users.User.message_id).first()
    if data[user.room]["isvote"] == 1:
        await message.answer("Дневное голосование не завершено!")
        return
    send = await bot.send_poll(message.chat.id, "Кого убьём сегодня?",
                               all_users_dropper(message, numerate=False),
                               is_anonymous=False)
    with open("static/json/game.json", "w", encoding="utf-8") as file:
        data[user.room]["isvote"] = 1
        json.dump(data, file)
    for i in role_dropper(message, "users"):
        take_user = session.query(users.User).filter(i == users.User.id).first()
        if take_user.message_id != message.chat.id:
            try:
                await bot.forward_message(take_user.message_id, message.chat.id, send.message_id)
            except Exception:
                pass


@dp.poll_answer_handler()  # Функция для голосования
async def polls(message):
    session = db_session.create_session()
    user = session.query(users.User).filter(users.User.message_id == message.user.id).first()
    room = user.room
    with open("static/json/game.json", encoding="utf-8") as file:
        data = json.loads(file.readline())
    with open("static/json/game.json", "w", encoding="utf-8") as file:
        if len(message.option_ids) != 0:
            data[user.room]["vote"] = data[user.room]["vote"] + [str(user.message_id) + " " +
                                                                 str(message.option_ids[0])]
        else:
            for i in data[user.room]["vote"]:
                if str(user.message_id) in i:
                    x = data[user.room]["vote"].remove(i)
        json.dump(data, file)
        file.close()
    if len(data[user.room]["vote"]) == len(data[user.room]["users"]):
        votes = []
        for i in data[user.room]["vote"]:
            votes.append(i.split()[1])
        who_dead = 0
        who_dead_2 = 0
        counter_1 = 0
        counter_2 = 0
        for i in sorted(votes):
            if int(who_dead) < votes.count(i):
                who_dead = i
                counter_1 = votes.count(i)
        while who_dead in votes:
            votes.remove(who_dead)
        for i in sorted(votes):
            if int(who_dead_2) < votes.count(i):
                who_dead_2 = i
                counter_2 = votes.count(i)
        with open("static/json/game.json", encoding="utf-8") as file:
            data = json.loads(file.readline())
        with open("static/json/game.json", "w", encoding="utf-8") as file:
            data[user.room]["isvote"] = 0
            json.dump(data, file)
        if counter_1 == counter_2:
            for i in data[user.room]["users"]:
                take_user = session.query(users.User).filter(i == users.User.id).first()
                await bot.send_message(take_user.message_id, "Голосование окончено. Жертв нет.")
        else:
            die_user = session.query(users.User).filter(users.User.id ==
                                                        data[user.room]["users"]
                                                        [int(who_dead)]).first()
            for i in data[user.room]["users"]:
                try:
                    take_user = session.query(users.User).filter(i == users.User.id).first()
                    await bot.send_message(take_user.message_id, "Голосование окончено. Игрок <b>" +
                                           die_user.nickname + "</b> был казнён.", parse_mode="html")
                    if take_user.message_id == die_user.message_id:
                        await bot.send_message(take_user.message_id,
                                               "Подписывайтесь на создателя бота: "
                                               "https://instagram.com/khokhl0v.s")
                except Exception:
                    pass
            with open("static/json/game.json", "w", encoding="utf-8") as file:
                data[user.room]["vote"] = []
                data[user.room]["isvote"] = 0
                json.dump(data, file)
                file.close()
            with open("static/json/game.json", "w", encoding="utf-8") as file:
                x = data[room]["users"].remove(die_user.id)
                try:
                    x = data[room]["mafia"].remove(die_user.id)
                except Exception:
                    pass
                try:
                    if data[room]["doctor"] == die_user.id:
                        data[room]["doctor"] = "0"
                except Exception:
                    pass
                try:
                    if data[room]["policeman"] == die_user.id:
                        data[room]["policeman"] = "0"
                except Exception:
                    pass
                try:
                    x = data[room]["poor"].remove(die_user.id)
                except Exception:
                    pass
                json.dump(data, file)
                file.close()
            die_user.room = ""
            session.commit()

    data_lst = [data[room]["doctor"]] + [data[room]["policeman"]] + data[room]["poor"]
    while "0" in data_lst:
        data_lst.remove("0")
    isgame = True
    for i in data[room]["users"]:
        take_user = session.query(users.User).filter(users.User.id == i).first()
        if len(data[room]["mafia"]) >= len(data_lst):
            await bot.send_sticker(take_user.message_id, "CAACAgIAAxkBAAIJ6mGP6-TG7"
                                                         "tcCOF0S9c8YusgTF7A4AALGAANWnb"
                                                         "0KbQmONokdLRciBA")
            await bot.send_message(take_user.message_id, "Игра завершена. "
                                                         "Мафия одержала победу.")
            await bot.send_message(take_user.message_id, "Подписывайтесь на создателя бота: "
                                                         "https://instagram.com/khokhl0v.s")
            isgame = False
        if len(data[room]["mafia"]) == 0:
            await bot.send_sticker(take_user.message_id, "CAACAgIAAxkBAAINSWGQNgKgmURc3m"
                                                         "5i-59EpLtlAuisAAKLAgACVp29Cve0"
                                                         "YiYNjzvzIgQ")
            await bot.send_message(take_user.message_id, "Игра завершена. "
                                                         "Мирные жители одержали победу.")
            await bot.send_message(take_user.message_id, "Подписывайтесь на создателя бота: "
                                                         "https://instagram.com/khokhl0v.s")
            isgame = False
    if not isgame:
        with open("static/json/game.json", encoding="utf-8") as file:
            data = json.loads(file.readline())
        with open("static/json/game.json", "w", encoding="utf-8") as file:
            del data[room]
            json.dump(data, file)
        clearing_db(room)


@dp.message_handler(commands=["finish"])  # Функция для завершения игры
async def finish_game(message: types.Message, state: FSMContext):
    session = db_session.create_session()
    user_room = session.query(users.User).filter(users.User.message_id == message.chat.id).first()
    with open("static/json/game.json", encoding="utf-8") as file:
        data = json.loads(file.readline())
    if data[user_room.room]["mafia"][0] == 0:
        await message.answer("Игра не начата!")
        return
    if data[user_room.room]["isvote"] == 1:
        await message.answer("Дневное голосование не завершено!")
        return
    with open("static/json/game.json", "w", encoding="utf-8") as file:
        data[user_room.room]["mafia"] = [0]
        data[user_room.room]["policeman"] = 0
        data[user_room.room]["doctor"] = 0
        data[user_room.room]["poor"] = [0]
        data[user_room.room]["die"] = 0
        data[user_room.room]["help"] = 0
        data[user_room.room]["all"] = [0]
        json.dump(data, file)
        file.close()
    for i in role_dropper(message, "users"):
        user = session.query(users.User).filter(users.User.id == i).first()
        await bot.send_message(user.message_id, "Игра завершена")
        await bot.send_message(user.message_id, "Подписывайтесь на создателя бота: "
                                                "https://instagram.com/khokhl0v.s")
    await state.finish()


@dp.message_handler(commands=["help"])  # Функция команды /help, которая выводит список остальных
async def drop_commands(message):  # функций, которыми можно воспользоваться в момент вызова
    session = db_session.create_session()
    user_search = session.query(users.User).filter(message.chat.id == users.User.message_id).first()
    session = db_session.create_session()
    with open("static/json/game.json", encoding="utf-8") as file:
        data = json.loads(file.readline())
    user = session.query(users.User).filter(message.chat.id == users.User.message_id).first()
    if user_search.room == "":
        await message.answer("*Доступные Вам команды:*\n\n"
                             "/addroom - Создать Комнату\n/update - Обновить Список Комнат\n\n"
                             "_Не забудьте выключить звук 🔕_",
                             parse_mode="markdown")
        return
    if data[user.room]["isvote"] == 1:
        await message.answer("Голосуйте")
        return
    with open("static/json/game.json", encoding="utf-8") as file:
        data = json.loads(file.readline())
        if data[user_search.room]["mafia"][0] == 0:
            await message.answer("*Доступные Вам команды:*\n\n"
                                 "/begin - Начать Игру\n/exit - Покинуть Комнату\n"
                                 "/all - Список Игроков\n\n"
                                 "_Не забудьте выключить звук 🔕_",
                                 parse_mode="markdown")
            return
        else:
            await message.answer("*Доступные Вам команды:*\n\n"
                                 "/night - Ночь\n/vote - Дневное Голосование\n"
                                 "/finish - Завершить Игру\n/all - Список Игроков"
                                 "\n\n_Не забудьте выключить звук 🔕_",
                                 parse_mode="markdown")
            return


# Вспомогательные Функции:

def take_all_rooms():  # Возвращает inline-клавиатуру со всеми комнатами
    with open("static/json/game.json", encoding="utf-8") as file:
        data = json.loads(file.readline())
        markup = types.InlineKeyboardMarkup()
        for i in data:
            markup.add(types.InlineKeyboardButton(i, callback_data=i))
    return markup


@dp.message_handler(content_types=['sticker'])  # Функция для принятия стикеров
async def handle_sticker(msg):
    print(msg)


@dp.message_handler(content_types=['game'])
async def games_handler(message):
    print(message)
    # await bot.forward_message(message.chat.id, message.chat.id, message.message_id)


def create_cancel_keyboard():  # Возвращает клавиатуру с кнопкой "Отменить"
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(types.KeyboardButton("Отменить"))
    return markup


def isfounder(message):
    session = db_session.create_session()
    user = session.query(users.User).filter(message.chat.id == users.User.message_id).first()
    with open("static/json/game.json", encoding="utf-8") as file:
        data = json.loads(file.readline())
    if user.id == data[user.room]["founder"]:
        return True
    return False


def role_dropper(message, role):
    session = db_session.create_session()
    user_search = session.query(users.User).filter(message.chat.id == users.User.message_id).first()
    with open("static/json/game.json", encoding="utf-8") as file:
        data = json.loads(file.readline())
    return data[user_search.room][role]


def all_users_dropper(message, all=False, numerate=True):  # Функция возвращает пронумерованный
    session = db_session.create_session()  # список всех пользователей
    all_users = []
    all_users_lst = []
    for i in role_dropper(message, "users"):
        search_user = session.query(users.User).filter(i == users.User.id).first()
        all_users.append(search_user.nickname)
    if all:
        for i in role_dropper(message, "all"):
            search_user = session.query(users.User).filter(i == users.User.id).first()
            if search_user.nickname not in all_users:
                all_users.append(search_user.nickname)
    for i, link in enumerate(all_users, 1):
        all_users_lst.append(str(i) + ". " + str(link))
    if numerate:
        return all_users_lst
    return all_users


def clearing_db(room):  # Функция для чистки базы данных
    session = db_session.create_session()
    users_in_room = session.query(users.User).filter(room == users.User.room).all()
    for i in users_in_room:
        i.room = ""
    session.commit()


def isroom(message):  # Функция для проверки что человек находиться в комнате
    session = db_session.create_session()
    user = session.query(users.User).filter(users.User.message_id == message.chat.id).first()
    if user.room == "" or user.room is None:
        return False
    return True


def isbegin(message):
    session = db_session.create_session()
    user = session.query(users.User).filter(users.User.message_id == message.chat.id).first()
    with open("static/json/game.json", encoding="utf-8") as file:
        data = json.loads(file.readline())
    if data[user.room]["mafia"][0] == 0:
        return False
    return True


if __name__ == "__main__":
    db_session.global_init("db/database.db")
    executor.start_polling(dp, skip_updates=True)
