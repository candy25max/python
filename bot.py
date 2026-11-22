import asyncio
import base64
import json
import os
import random
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

BOT_TOKEN = "9184524998:AAHFBLU85WWV-3ArSduiCp9CdyERwWYjvgE"
URL_WEBAPP = "https://candy25max.github.io/upgrade/"  # Посилання на твій задеплоєний index.html
ADMIN_IDS: set[int] = {7828950337}
DATA_FILE = "bot_data.json"

DEFAULT_CASES: dict[str, dict] = {
    "dragon": {"name": "Дракон", "price": 500, "reward_min": 50, "reward_max": 1200},
    "taco": {"name": "Тако", "price": 209, "reward_min": 20, "reward_max": 500},
    "nubini": {"name": "Нубини", "price": 19, "reward_min": 5, "reward_max": 60},
    "blok": {"name": "Блок", "price": 259, "reward_min": 30, "reward_max": 700},
}


def write_json_file(users: dict[int, int], cases: dict[str, dict]) -> None:
    """Атомарно записує баланси користувачів та ціни кейсів у bot_data.json."""
    payload = {
        "users": {str(k): int(v) for k, v in users.items()},
        "cases": cases,
    }
    tmp_file = f"{DATA_FILE}.tmp"
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp_file, DATA_FILE)


def load_data() -> tuple[dict[int, int], dict[str, dict]]:
    """Завантажує баланси та кейси з JSON-файлу."""
    if not os.path.exists(DATA_FILE):
        cases_copy = {k: dict(v) for k, v in DEFAULT_CASES.items()}
        write_json_file({}, cases_copy)
        return {}, cases_copy

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError):
        cases_copy = {k: dict(v) for k, v in DEFAULT_CASES.items()}
        return {}, cases_copy

    raw_users = raw.get("users", {})
    users: dict[int, int] = {}
    for uid_str, bal in raw_users.items():
        if str(uid_str).isdigit():
            users[int(uid_str)] = int(bal)

    raw_cases = raw.get("cases", {})
    cases: dict[str, dict] = {}
    for cid, default_cfg in DEFAULT_CASES.items():
        saved_cfg = raw_cases.get(cid, {})
        cases[cid] = {
            "name": str(saved_cfg.get("name", default_cfg["name"])),
            "price": int(saved_cfg.get("price", default_cfg["price"])),
            "reward_min": int(saved_cfg.get("reward_min", default_cfg["reward_min"])),
            "reward_max": int(saved_cfg.get("reward_max", default_cfg["reward_max"])),
        }

    return users, cases


users_db, cases_db = load_data()


def save_data() -> None:
    write_json_file(users_db, cases_db)


bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Стани очікування текстового вводу від користувачів або адміна
pending_inputs: dict[int, dict] = {}


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def get_user_balance(user_id: int) -> int:
    if user_id not in users_db:
        users_db[user_id] = 100  # Стартовий баланс для нового користувача
        save_data()
    return users_db[user_id]


def set_user_balance(user_id: int, new_balance: int) -> None:
    users_db[user_id] = max(0, int(new_balance))
    save_data()


def build_webapp_url(user_id: int) -> str:
    bal = get_user_balance(user_id)
    prices_map = {cid: cfg["price"] for cid, cfg in cases_db.items()}
    encoded_prices = base64.urlsafe_b64encode(
        json.dumps(prices_map, ensure_ascii=False).encode("utf-8")
    ).decode("ascii")
    sep = "&" if "?" in URL_WEBAPP else "?"
    return f"{URL_WEBAPP}{sep}balance={bal}&prices={encoded_prices}"


def main_menu_kb(user_id: int) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="📦 Відкрити кейси", web_app=WebAppInfo(url=build_webapp_url(user_id)))],
        [KeyboardButton(text="⭐ Поповнити")],
    ]
    if is_admin(user_id):
        rows.append([KeyboardButton(text="🛠 Адмін-панель")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def topup_amounts_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="10 ⭐", callback_data="topup_stars:10"),
                InlineKeyboardButton(text="50 ⭐", callback_data="topup_stars:50"),
                InlineKeyboardButton(text="100 ⭐", callback_data="topup_stars:100"),
            ],
            [InlineKeyboardButton(text="✍️ Своя сума", callback_data="topup_custom")],
        ]
    )


def admin_panel_kb() -> InlineKeyboardMarkup:
    # Кнопки зміни зображення в налаштуваннях немає за умовою
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💰 Видати / змінити баланс", callback_data="admin_set_balance")],
            [InlineKeyboardButton(text="🎯 Змінити ціну кейсу", callback_data="admin_edit_prices")],
            [InlineKeyboardButton(text="📊 Статистика бота", callback_data="admin_stats")],
        ]
    )


def admin_cases_price_kb() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(
                text=f"{c['name']} — {c['price']} ⭐",
                callback_data=f"admin_case_price:{cid}",
            )
        ]
        for cid, c in cases_db.items()
    ]
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def send_stars_invoice(chat_id: int, stars_amount: int) -> None:
    await bot.send_invoice(
        chat_id=chat_id,
        title="Поповнення балансу",
        description=f"Поповнення балансу на {stars_amount} ⭐",
        payload=json.dumps({"action": "topup", "stars": stars_amount}),
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=f"{stars_amount} зірок", amount=stars_amount)],
    )


@dp.message(Command("start"))
async def cmd_start(message: Message) -> None:
    uid = message.from_user.id
    bal = get_user_balance(uid)
    await message.answer(
        f"Привіт! Твій баланс: <b>{bal} ⭐</b>\n"
        f"Натискай <b>«📦 Відкрити кейси»</b> або <b>«⭐ Поповнити»</b>:",
        parse_mode="HTML",
        reply_markup=main_menu_kb(uid),
    )


@dp.message(F.text == "⭐ Поповнити")
async def btn_topup(message: Message) -> None:
    await message.answer(
        "Оберіть, скільки зірок хочете поповнити:",
        reply_markup=topup_amounts_kb(),
    )


@dp.callback_query(F.data.startswith("topup_stars:"))
async def cb_topup_preset(callback: CallbackQuery) -> None:
    await callback.answer()
    amount = int(callback.data.split(":", 1)[1])
    await send_stars_invoice(callback.from_user.id, amount)


@dp.callback_query(F.data == "topup_custom")
async def cb_topup_custom(callback: CallbackQuery) -> None:
    await callback.answer()
    pending_inputs[callback.from_user.id] = {"mode": "custom_topup"}
    await callback.message.answer("Введіть ціле число — скільки зірок хочете поповнити:")


# --- Адмін-панель ---
@dp.message(Command("admin"))
@dp.message(F.text == "🛠 Адмін-панель")
async def open_admin_panel(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Немає доступу до адмін-панелі.")
        return
    await message.answer(
        "🛠 <b>Адмін-панель</b>\nОберіть дію:",
        parse_mode="HTML",
        reply_markup=admin_panel_kb(),
    )


@dp.callback_query(F.data == "admin_back")
async def cb_admin_back(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return
    await callback.answer()
    await callback.message.edit_text(
        "🛠 <b>Адмін-панель</b>\nОберіть дію:",
        parse_mode="HTML",
        reply_markup=admin_panel_kb(),
    )


@dp.callback_query(F.data == "admin_set_balance")
async def cb_admin_set_balance(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return
    await callback.answer()
    pending_inputs[callback.from_user.id] = {"mode": "admin_set_balance"}
    await callback.message.answer(
        "Надішліть у форматі: <code>USER_ID НОВИЙ_БАЛАНС</code>\nНаприклад: <code>7828950337 500</code>",
        parse_mode="HTML",
    )


@dp.callback_query(F.data == "admin_edit_prices")
async def cb_admin_edit_prices(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return
    await callback.answer()
    await callback.message.edit_text(
        "Оберіть кейс, щоб змінити його ціну в зірках:",
        reply_markup=admin_cases_price_kb(),
    )


@dp.callback_query(F.data.startswith("admin_case_price:"))
async def cb_admin_choose_case_price(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return
    await callback.answer()
    case_id = callback.data.split(":", 1)[1]
    if case_id not in cases_db:
        return
    pending_inputs[callback.from_user.id] = {"mode": "admin_case_price", "case_id": case_id}
    await callback.message.answer(
        f"Введіть нову ціну в зірках для кейсу <b>{cases_db[case_id]['name']}</b>:",
        parse_mode="HTML",
    )


@dp.callback_query(F.data == "admin_stats")
async def cb_admin_stats(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return
    await callback.answer()
    total_users = len(users_db)
    total_stars = sum(users_db.values())
    await callback.message.answer(
        f"📊 <b>Статистика</b>\n"
        f"Користувачів у базі: <b>{total_users}</b>\n"
        f"Сумарний баланс у боті: <b>{total_stars} ⭐</b>",
        parse_mode="HTML",
    )


# --- Дані з WebApp ---
@dp.message(F.web_app_data)
async def handle_webapp_data(message: Message) -> None:
    uid = message.from_user.id
    data = json.loads(message.web_app_data.data)
    action = data.get("action")

    if action == "open_topup":
        needed = int(data.get("needed", 0) or 0)
        text = "Оберіть кількість зірок для поповнення:"
        if needed > 0:
            text = f"Для відкриття кейсу не вистачає <b>{needed} ⭐</b>. Оберіть суму поповнення:"
        await message.answer(text, parse_mode="HTML", reply_markup=topup_amounts_kb())
        return

    if action == "open_case":
        case_id = data.get("case_id")
        case_info = cases_db.get(case_id)
        if not case_info:
            await message.answer("❌ Кейс не знайдено.", reply_markup=main_menu_kb(uid))
            return

        price = case_info["price"]
        bal = get_user_balance(uid)
        if bal < price:
            missing = price - bal
            await message.answer(
                f"❌ Не вистачає <b>{missing} ⭐</b> для відкриття кейсу «{case_info['name']}».",
                parse_mode="HTML",
                reply_markup=main_menu_kb(uid),
            )
            return

        drop = random.randint(case_info["reward_min"], case_info["reward_max"])
        new_bal = bal - price + drop
        set_user_balance(uid, new_bal)

        await message.answer(
            f"🎁 Ви відкрили кейс <b>{case_info['name']}</b> за <b>{price} ⭐</b>!\n"
            f"Випало: <b>{drop} ⭐</b>\n"
            f"Поточний баланс: <b>{new_bal} ⭐</b>",
            parse_mode="HTML",
            reply_markup=main_menu_kb(uid),
        )
        return

    if action == "upgrade":
        source_val = int(data["source"])
        target_val = int(data["target"])
        bal = get_user_balance(uid)

        if bal < source_val:
            await message.answer(
                f"❌ Не вистачає <b>{source_val - bal} ⭐</b>!",
                parse_mode="HTML",
                reply_markup=main_menu_kb(uid),
            )
            return

        win_chance = (source_val / target_val) * 0.9
        if random.random() <= win_chance:
            new_bal = bal - source_val + target_val
            set_user_balance(uid, new_bal)
            await message.answer(
                f"🎉 <b>УСПІХ!</b> Отримано <b>{target_val} ⭐</b>.\n"
                f"Баланс: <b>{new_bal} ⭐</b>",
                parse_mode="HTML",
                reply_markup=main_menu_kb(uid),
            )
        else:
            new_bal = bal - source_val
            set_user_balance(uid, new_bal)
            await message.answer(
                f"💀 <b>НЕВДАЧА!</b> Втрачено <b>{source_val} ⭐</b>.\n"
                f"Баланс: <b>{new_bal} ⭐</b>",
                parse_mode="HTML",
                reply_markup=main_menu_kb(uid),
            )


# --- Текстовий ввід для поповнення та адмін-панелі ---
@dp.message(F.text)
async def handle_pending_text(message: Message) -> None:
    uid = message.from_user.id
    state = pending_inputs.get(uid)
    if not state:
        return

    mode = state["mode"]
    raw = message.text.strip()

    if mode == "custom_topup":
        if not raw.isdigit() or int(raw) < 1:
            await message.answer("Введіть ціле додатне число, наприклад: 25")
            return
        pending_inputs.pop(uid, None)
        await send_stars_invoice(uid, int(raw))
        return

    if mode == "admin_set_balance" and is_admin(uid):
        parts = raw.split()
        if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
            await message.answer(
                "Формат: <code>USER_ID БАЛАНС</code> (наприклад: <code>7828950337 500</code>)",
                parse_mode="HTML",
            )
            return
        target_uid = int(parts[0])
        new_bal = int(parts[1])
        set_user_balance(target_uid, new_bal)
        pending_inputs.pop(uid, None)
        await message.answer(
            f"✅ Баланс користувача <code>{target_uid}</code> збережено: <b>{new_bal} ⭐</b>",
            parse_mode="HTML",
        )
        return

    if mode == "admin_case_price" and is_admin(uid):
        if not raw.isdigit() or int(raw) < 1:
            await message.answer("Введіть ціле число більше 0 для ціни кейсу.")
            return
        case_id = state["case_id"]
        new_price = int(raw)
        cases_db[case_id]["price"] = new_price
        save_data()
        pending_inputs.pop(uid, None)
        await message.answer(
            f"✅ Нова ціна кейсу <b>{cases_db[case_id]['name']}</b> збережена: <b>{new_price} ⭐</b>",
            parse_mode="HTML",
        )


# --- Оплата Telegram Stars (XTR) ---
@dp.pre_checkout_query()
async def on_pre_checkout(pre_checkout_query: PreCheckoutQuery) -> None:
    await pre_checkout_query.answer(ok=True)


@dp.message(F.successful_payment)
async def on_successful_payment(message: Message) -> None:
    uid = message.from_user.id
    paid_stars = message.successful_payment.total_amount
    new_bal = get_user_balance(uid) + paid_stars
    set_user_balance(uid, new_bal)
    await message.answer(
        f"✅ Оплату підтверджено! Нараховано <b>{paid_stars} ⭐</b>.\n"
        f"Поточний баланс: <b>{new_bal} ⭐</b>",
        parse_mode="HTML",
        reply_markup=main_menu_kb(uid),
    )


async def main() -> None:
    save_data()
    print("Бот запущений...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
