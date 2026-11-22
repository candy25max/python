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

BOT_TOKEN = os.getenv("BOT_TOKEN", "9184524998:AAHFBLU85WWV-3ArSduiCp9CdyERwWYjvgE")
URL_WEBAPP = os.getenv("URL_WEBAPP", "https://python-six-beige.vercel.app")
ADMIN_IDS: set[int] = {7828950337}
DATA_FILE = "bot_data.json"

DEFAULT_CASES: dict[str, dict] = {
    "dragon": {"name": "Дракон", "price": 500, "reward_min": 50, "reward_max": 1200},
    "taco": {"name": "Тако", "price": 209, "reward_min": 20, "reward_max": 500},
    "nubini": {"name": "Нубини", "price": 19, "reward_min": 5, "reward_max": 60},
    "blok": {"name": "Блок", "price": 259, "reward_min": 30, "reward_max": 700},
}

DEFAULT_PROMOS: dict[str, int] = {
    "GLIMUP100": 100,
    "START50": 50,
}


def write_json_file(
    users: dict[int, dict],
    cases: dict[str, dict],
    promos: dict[str, int] | None = None,
) -> None:
    """Атомарно записує баланси/мови/промокоди користувачів та ціни кейсів у bot_data.json."""
    payload = {
        "users": {
            str(k): {
                "balance": int(v.get("balance", 0)),
                "lang": v.get("lang") if v.get("lang") in ("ru", "en") else None,
                "used_promos": list(v.get("used_promos", [])),
            }
            for k, v in users.items()
        },
        "cases": cases,
        "promos": promos if promos is not None else DEFAULT_PROMOS,
    }
    tmp_file = f"{DATA_FILE}.tmp"
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp_file, DATA_FILE)


def load_data() -> tuple[dict[int, dict], dict[str, dict], dict[str, int]]:
    """Завантажує дані користувачів, кейси та промокоди з JSON-файлу."""
    if not os.path.exists(DATA_FILE):
        cases_copy = {k: dict(v) for k, v in DEFAULT_CASES.items()}
        promos_copy = dict(DEFAULT_PROMOS)
        write_json_file({}, cases_copy, promos_copy)
        return {}, cases_copy, promos_copy

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError):
        cases_copy = {k: dict(v) for k, v in DEFAULT_CASES.items()}
        promos_copy = dict(DEFAULT_PROMOS)
        return {}, cases_copy, promos_copy

    raw_users = raw.get("users", {})
    users: dict[int, dict] = {}
    for uid_str, val in raw_users.items():
        if str(uid_str).isdigit():
            uid = int(uid_str)
            if isinstance(val, dict):
                lang_val = val.get("lang")
                users[uid] = {
                    "balance": int(val.get("balance", 0)),
                    "lang": lang_val if lang_val in ("ru", "en") else None,
                    "used_promos": [str(p).upper() for p in val.get("used_promos", [])],
                }
            else:
                users[uid] = {
                    "balance": int(val),
                    "lang": None,
                    "used_promos": [],
                }

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

    raw_promos = raw.get("promos", DEFAULT_PROMOS)
    promos: dict[str, int] = {}
    if isinstance(raw_promos, dict):
        for code, reward in raw_promos.items():
            if str(code).strip() and int(reward) > 0:
                promos[str(code).strip().upper()] = int(reward)
    if not promos:
        promos = dict(DEFAULT_PROMOS)

    return users, cases, promos


users_db, cases_db, promos_db = load_data()


def save_data() -> None:
    write_json_file(users_db, cases_db, promos_db)


bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

pending_inputs: dict[int, dict] = {}


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def ensure_user(user_id: int) -> dict:
    if user_id not in users_db:
        users_db[user_id] = {
            "balance": 0,
            "lang": None,
            "used_promos": [],
        }
        save_data()
    return users_db[user_id]


def get_user_lang(user_id: int) -> str:
    rec = ensure_user(user_id)
    return rec["lang"] if rec["lang"] in ("ru", "en") else "ru"


def set_user_lang(user_id: int, lang: str) -> None:
    rec = ensure_user(user_id)
    rec["lang"] = "en" if lang == "en" else "ru"
    save_data()


def get_user_balance(user_id: int) -> int:
    rec = ensure_user(user_id)
    return int(rec.get("balance", 0))


def set_user_balance(user_id: int, new_balance: int) -> None:
    rec = ensure_user(user_id)
    rec["balance"] = max(0, int(new_balance))
    save_data()


def build_webapp_url(user_id: int) -> str:
    bal = get_user_balance(user_id)
    lang = get_user_lang(user_id)
    prices_map = {cid: cfg["price"] for cid, cfg in cases_db.items()}
    encoded_prices = base64.urlsafe_b64encode(
        json.dumps(prices_map, ensure_ascii=False).encode("utf-8")
    ).decode("ascii")
    sep = "&" if "?" in URL_WEBAPP else "?"
    return f"{URL_WEBAPP}{sep}balance={bal}&lang={lang}&prices={encoded_prices}"


def lang_choice_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Русский (RU)", callback_data="set_lang:ru"),
                InlineKeyboardButton(text="English (EN)", callback_data="set_lang:en"),
            ]
        ]
    )


def main_menu_kb(user_id: int) -> ReplyKeyboardMarkup:
    lang = get_user_lang(user_id)
    if lang == "en":
        open_text = "Открыть GlimUp"
        topup_text = "Пополнить"
        promo_text = "Промокод"
        lang_text = "Сменить язык"
    else:
        open_text = "Открыть GlimUp"
        topup_text = "Пополнить"
        promo_text = "Промокод"
        lang_text = "Сменить язык"

    rows = [
        [KeyboardButton(text=open_text, web_app=WebAppInfo(url=build_webapp_url(user_id)))],
        [
            KeyboardButton(text=topup_text),
            KeyboardButton(text=promo_text),
        ],
        [KeyboardButton(text=lang_text)],
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
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💰 Видати / змінити баланс", callback_data="admin_set_balance")],
            [InlineKeyboardButton(text="🎯 Змінити ціну кейсу", callback_data="admin_edit_prices")],
            [InlineKeyboardButton(text="🎟 Додати промокод", callback_data="admin_add_promo")],
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
        title="Пополнение баланса",
        description=f"Пополнение баланса на {stars_amount} ⭐",
        payload=json.dumps({"action": "topup", "stars": stars_amount}),
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=f"{stars_amount} зірок", amount=stars_amount)],
    )


async def send_language_selected_menu(chat_id: int, user_id: int) -> None:
    rec = ensure_user(user_id)
    chosen_lang = rec["lang"] if rec["lang"] in ("ru", "en") else "ru"
    bal = get_user_balance(user_id)
    lang_label = "Русский" if chosen_lang == "ru" else "English"
    await bot.send_message(
        chat_id=chat_id,
        text=f"Язык выбран: {lang_label}. Баланс: {bal} ⭐",
        reply_markup=main_menu_kb(user_id),
    )


@dp.message(Command("start"))
async def cmd_start(message: Message) -> None:
    uid = message.from_user.id
    ensure_user(uid)
    await message.answer(
        "Выберите ваш язык / Choose your language:",
        reply_markup=lang_choice_kb(),
    )


@dp.callback_query(F.data.startswith("set_lang:"))
async def cb_set_lang(callback: CallbackQuery) -> None:
    await callback.answer()
    uid = callback.from_user.id
    chosen = callback.data.split(":", 1)[1]
    set_user_lang(uid, chosen)
    await send_language_selected_menu(callback.message.chat.id, uid)


@dp.message(F.text == "Сменить язык")
async def btn_change_lang(message: Message) -> None:
    await message.answer(
        "Выберите ваш язык / Choose your language:",
        reply_markup=lang_choice_kb(),
    )


@dp.message(F.text == "Промокод")
async def btn_promo(message: Message) -> None:
    uid = message.from_user.id
    pending_inputs[uid] = {"mode": "enter_promo"}
    await message.answer("Введите промокод:")


@dp.message(F.text == "Пополнить")
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


@dp.callback_query(F.data == "admin_add_promo")
async def cb_admin_add_promo(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return
    await callback.answer()
    pending_inputs[callback.from_user.id] = {"mode": "admin_add_promo"}
    await callback.message.answer(
        "Надішліть у форматі: <code>КОД ЗІРКИ</code>\nНаприклад: <code>BONUS200 200</code>",
        parse_mode="HTML",
    )


@dp.callback_query(F.data == "admin_stats")
async def cb_admin_stats(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return
    await callback.answer()
    total_users = len(users_db)
    total_stars = sum(int(u.get("balance", 0)) for u in users_db.values())
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


# --- Текстовий ввід для промокодів, поповнення та адмін-панелі ---
@dp.message(F.text)
async def handle_pending_text(message: Message) -> None:
    uid = message.from_user.id
    state = pending_inputs.get(uid)
    if not state:
        return

    mode = state["mode"]
    raw = message.text.strip()

    if mode == "enter_promo":
        pending_inputs.pop(uid, None)
        code = raw.upper()
        reward = promos_db.get(code)
        if not reward:
            await message.answer("❌ Промокод не знайдено або недійсний.", reply_markup=main_menu_kb(uid))
            return
        rec = ensure_user(uid)
        used = rec.setdefault("used_promos", [])
        if code in used:
            await message.answer("⚠️ Ви вже активували цей промокод.", reply_markup=main_menu_kb(uid))
            return
        used.append(code)
        new_bal = get_user_balance(uid) + reward
        set_user_balance(uid, new_bal)
        await message.answer(
            f"✅ Промокод <b>{code}</b> активовано! Нараховано: <b>+{reward} ⭐</b>\n"
            f"Поточний баланс: <b>{new_bal} ⭐</b>",
            parse_mode="HTML",
            reply_markup=main_menu_kb(uid),
        )
        return

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
        return

    if mode == "admin_add_promo" and is_admin(uid):
        parts = raw.split()
        if len(parts) != 2 or not parts[1].isdigit() or int(parts[1]) < 1:
            await message.answer(
                "Формат: <code>КОД ЗІРКИ</code> (наприклад: <code>BONUS200 200</code>)",
                parse_mode="HTML",
            )
            return
        code = parts[0].upper()
        reward = int(parts[1])
        promos_db[code] = reward
        save_data()
        pending_inputs.pop(uid, None)
        await message.answer(
            f"✅ Промокод <b>{code}</b> на <b>{reward} ⭐</b> додано.",
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
