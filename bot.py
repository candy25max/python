import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
    WebAppInfo,
)

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = "9184524998:AAHFBLU85WWV-3ArSduiCp9CdyERwWYjvgE"
WEBAPP_URL = "https://glimup.netlify.app"
ADMIN_ID = 7828950337

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

conn = sqlite3.connect("glimup.db")
cur = conn.cursor()
cur.execute(
    """
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        lang TEXT DEFAULT 'ru',
        balance INTEGER DEFAULT 0
    )
    """
)
cur.execute(
    """
    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        stars INTEGER
    )
    """
)
cur.execute(
    """
    CREATE TABLE IF NOT EXISTS promocodes (
        code TEXT PRIMARY KEY,
        reward INTEGER,
        max_uses INTEGER,
        uses_count INTEGER DEFAULT 0
    )
    """
)
cur.execute(
    """
    CREATE TABLE IF NOT EXISTS promo_used (
        user_id INTEGER,
        code TEXT,
        PRIMARY KEY (user_id, code)
    )
    """
)
conn.commit()


def ensure_user(user_id: int) -> None:
    cur.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()


def get_lang(user_id: int) -> str:
    ensure_user(user_id)
    row = cur.execute("SELECT lang FROM users WHERE user_id = ?", (user_id,)).fetchone()
    return row[0] if row and row[0] else "ru"


def set_lang_db(user_id: int, lang: str) -> None:
    ensure_user(user_id)
    cur.execute("UPDATE users SET lang = ? WHERE user_id = ?", (lang, user_id))
    conn.commit()


def get_balance(user_id: int) -> int:
    ensure_user(user_id)
    row = cur.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)).fetchone()
    return int(row[0]) if row else 0


def add_balance(user_id: int, amount: int) -> None:
    ensure_user(user_id)
    cur.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()


class DepositStates(StatesGroup):
    waiting_for_amount = State()


class PromoUseStates(StatesGroup):
    waiting_for_code = State()


class AdminPromoStates(StatesGroup):
    waiting_for_code = State()
    waiting_for_reward = State()
    waiting_for_limit = State()


def lang_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Русский (RU)", callback_data="lang_ru"),
                InlineKeyboardButton(text="English (EN)", callback_data="lang_en"),
            ]
        ]
    )


def main_menu_keyboard(lang: str, user_id: int) -> InlineKeyboardMarkup:
    if lang == "en":
        rows = [
            [InlineKeyboardButton(text="Open GlimUp", web_app=WebAppInfo(url=WEBAPP_URL))],
            [
                InlineKeyboardButton(text="Top up", callback_data="topup_start"),
                InlineKeyboardButton(text="Promo code", callback_data="promo_enter"),
            ],
            [InlineKeyboardButton(text="Change language", callback_data="change_lang")],
        ]
    else:
        rows = [
            [InlineKeyboardButton(text="Открыть GlimUp", web_app=WebAppInfo(url=WEBAPP_URL))],
            [
                InlineKeyboardButton(text="Пополнить", callback_data="topup_start"),
                InlineKeyboardButton(text="Промокод", callback_data="promo_enter"),
            ],
            [InlineKeyboardButton(text="Сменить язык", callback_data="change_lang")],
        ]
    if user_id == ADMIN_ID:
        rows.append([InlineKeyboardButton(text="🛠 Admin Panel", callback_data="admin_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
            [InlineKeyboardButton(text="🎟 Создать промокод", callback_data="admin_create_promo")],
            [InlineKeyboardButton(text="📋 Список промокодів", callback_data="admin_list_promos")],
            [InlineKeyboardButton(text="⬅️ В меню", callback_data="back_to_menu")],
        ]
    )


@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    ensure_user(message.from_user.id)
    await message.answer(
        "Выберите ваш язык / Choose your language:",
        reply_markup=lang_keyboard(),
    )


@dp.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext) -> None:
    if message.from_user.id != ADMIN_ID:
        return
    await state.clear()
    await message.answer("Адмін-панель GlimUp:", reply_markup=admin_keyboard())


@dp.callback_query(F.data == "admin_menu")
async def cb_admin_menu(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Access denied", show_alert=True)
        return
    await state.clear()
    await callback.message.answer("Адмін-панель GlimUp:", reply_markup=admin_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "back_to_menu")
async def cb_back_to_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    lang = get_lang(callback.from_user.id)
    bal = get_balance(callback.from_user.id)
    txt = f"Balance: {bal} ⭐" if lang == "en" else f"Баланс: {bal} ⭐"
    await callback.message.answer(txt, reply_markup=main_menu_keyboard(lang, callback.from_user.id))
    await callback.answer()


@dp.callback_query(F.data == "admin_stats")
async def cb_admin_stats(callback: CallbackQuery) -> None:
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Access denied", show_alert=True)
        return
    total_users = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    ru_users = cur.execute("SELECT COUNT(*) FROM users WHERE lang = 'ru'").fetchone()[0]
    en_users = cur.execute("SELECT COUNT(*) FROM users WHERE lang = 'en'").fetchone()[0]
    total_payments = cur.execute("SELECT COUNT(*) FROM payments").fetchone()[0]
    total_stars = cur.execute("SELECT COALESCE(SUM(stars), 0) FROM payments").fetchone()[0]
    text = (
        f"📊 <b>Статистика GlimUp</b>\n\n"
        f"👥 Користувачів: <b>{total_users}</b> (RU: {ru_users} / EN: {en_users})\n"
        f"💳 Оплат: <b>{total_payments}</b>\n"
        f"⭐ Отримано зірок: <b>{total_stars}</b>"
    )
    await callback.message.answer(text, parse_mode="HTML", reply_markup=admin_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "admin_create_promo")
async def cb_admin_create_promo(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Access denied", show_alert=True)
        return
    await state.set_state(AdminPromoStates.waiting_for_code)
    await callback.message.answer("Введи назву промокоду (наприклад, GLIM50):")
    await callback.answer()


@dp.message(AdminPromoStates.waiting_for_code)
async def admin_promo_code(message: Message, state: FSMContext) -> None:
    if message.from_user.id != ADMIN_ID:
        return
    code = (message.text or "").strip().upper()
    if not code:
        await message.answer("Введи коректну назву промокоду:")
        return
    await state.update_data(promo_code=code)
    await state.set_state(AdminPromoStates.waiting_for_reward)
    await message.answer(f"Скільки зірок (⭐) даватиме промокод <b>{code}</b>?", parse_mode="HTML")


@dp.message(AdminPromoStates.waiting_for_reward)
async def admin_promo_reward(message: Message, state: FSMContext) -> None:
    if message.from_user.id != ADMIN_ID:
        return
    raw = (message.text or "").strip()
    if not raw.isdigit() or int(raw) <= 0:
        await message.answer("Введи додатне ціле число зірок:")
        return
    await state.update_data(reward=int(raw))
    await state.set_state(AdminPromoStates.waiting_for_limit)
    await message.answer("Скільки разів можна активувати цей промокод? (наприклад, 10):")


@dp.message(AdminPromoStates.waiting_for_limit)
async def admin_promo_limit(message: Message, state: FSMContext) -> None:
    if message.from_user.id != ADMIN_ID:
        return
    raw = (message.text or "").strip()
    if not raw.isdigit() or int(raw) <= 0:
        await message.answer("Введи додатне ціле число ліміту активацій:")
        return
    data = await state.get_data()
    code = data["promo_code"]
    reward = data["reward"]
    max_uses = int(raw)
    cur.execute(
        """
        INSERT INTO promocodes (code, reward, max_uses, uses_count)
        VALUES (?, ?, ?, 0)
        ON CONFLICT(code) DO UPDATE SET reward = excluded.reward, max_uses = excluded.max_uses, uses_count = 0
        """,
        (code, reward, max_uses),
    )
    conn.commit()
    await state.clear()
    await message.answer(
        f"✅ Промокод <b>{code}</b> створено: <b>+{reward} ⭐</b>, ліміт: <b>{max_uses}</b> активацій.",
        parse_mode="HTML",
        reply_markup=admin_keyboard(),
    )


@dp.callback_query(F.data == "admin_list_promos")
async def cb_admin_list_promos(callback: CallbackQuery) -> None:
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Access denied", show_alert=True)
        return
    rows = cur.execute("SELECT code, reward, uses_count, max_uses FROM promocodes").fetchall()
    if not rows:
        await callback.message.answer("Промокодів ще немає.", reply_markup=admin_keyboard())
    else:
        lines = [f"• <b>{c}</b>: +{r} ⭐ ({u}/{m})" for c, r, u, m in rows]
        await callback.message.answer("\n".join(lines), parse_mode="HTML", reply_markup=admin_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "promo_enter")
async def cb_promo_enter(callback: CallbackQuery, state: FSMContext) -> None:
    lang = get_lang(callback.from_user.id)
    await state.set_state(PromoUseStates.waiting_for_code)
    prompt = "Enter promo code:" if lang == "en" else "Введите промокод:"
    await callback.message.answer(prompt)
    await callback.answer()


@dp.message(PromoUseStates.waiting_for_code)
async def process_promo_code(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id
    lang = get_lang(uid)
    code = (message.text or "").strip().upper()
    await state.clear()

    row = cur.execute(
        "SELECT reward, max_uses, uses_count FROM promocodes WHERE code = ?",
        (code,),
    ).fetchone()

    if not row:
        msg = "Promo code not found." if lang == "en" else "Промокод не найден."
        await message.answer(msg, reply_markup=main_menu_keyboard(lang, uid))
        return

    reward, max_uses, uses_count = row
    if uses_count >= max_uses:
        msg = "Promo code usage limit reached." if lang == "en" else "Лимит активаций промокода исчерпан."
        await message.answer(msg, reply_markup=main_menu_keyboard(lang, uid))
        return

    already = cur.execute(
        "SELECT 1 FROM promo_used WHERE user_id = ? AND code = ?",
        (uid, code),
    ).fetchone()
    if already:
        msg = "You have already used this promo code." if lang == "en" else "Вы уже активировали этот промокод."
        await message.answer(msg, reply_markup=main_menu_keyboard(lang, uid))
        return

    cur.execute("INSERT INTO promo_used (user_id, code) VALUES (?, ?)", (uid, code))
    cur.execute("UPDATE promocodes SET uses_count = uses_count + 1 WHERE code = ?", (code,))
    conn.commit()
    add_balance(uid, int(reward))
    new_bal = get_balance(uid)

    msg = (
        f"Promo code applied: +{reward} ⭐! Balance: {new_bal} ⭐"
        if lang == "en"
        else f"Промокод активирован: +{reward} ⭐! Баланс: {new_bal} ⭐"
    )
    await message.answer(msg, reply_markup=main_menu_keyboard(lang, uid))


@dp.callback_query(F.data == "change_lang")
async def cb_change_lang(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.answer(
        "Выберите ваш язык / Choose your language:",
        reply_markup=lang_keyboard(),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("lang_"))
async def cb_set_lang(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    lang = callback.data.split("_")[1]
    set_lang_db(callback.from_user.id, lang)
    bal = get_balance(callback.from_user.id)
    text = (
        f"Language set to English. Balance: {bal} ⭐"
        if lang == "en"
        else f"Язык выбран: Русский. Баланс: {bal} ⭐"
    )
    await callback.message.answer(text, reply_markup=main_menu_keyboard(lang, callback.from_user.id))
    await callback.answer()


@dp.callback_query(F.data == "topup_start")
async def cb_topup_start(callback: CallbackQuery, state: FSMContext) -> None:
    lang = get_lang(callback.from_user.id)
    await state.set_state(DepositStates.waiting_for_amount)
    prompt = (
        "Enter the amount of Stars to top up (minimum 10):"
        if lang == "en"
        else "Введите сумму звёзд для пополнения (от 10):"
    )
    await callback.message.answer(prompt)
    await callback.answer()


@dp.message(DepositStates.waiting_for_amount)
async def process_topup_amount(message: Message, state: FSMContext) -> None:
    lang = get_lang(message.from_user.id)
    raw = (message.text or "").strip()

    if not raw.isdigit():
        err = (
            "Please enter a valid number of Stars (minimum 10):"
            if lang == "en"
            else "Введите целое число звёзд (минимум 10):"
        )
        await message.answer(err)
        return

    amount = int(raw)
    if amount < 10:
        min_err = (
            "Minimum top-up amount is 10 Stars. Enter 10 or more:"
            if lang == "en"
            else "Минимальная сумма пополнения — 10 звёзд. Введите число от 10:"
        )
        await message.answer(min_err)
        return

    await state.clear()
    title = f"GlimUp +{amount} Stars"
    desc = (
        f"Top up {amount} Telegram Stars in GlimUp"
        if lang == "en"
        else f"Пополнение баланса GlimUp на {amount} Telegram Stars"
    )
    label = f"{amount} Stars" if lang == "en" else f"{amount} звёзд"

    await message.answer_invoice(
        title=title,
        description=desc,
        payload=f"glimup_stars_{amount}",
        currency="XTR",
        prices=[LabeledPrice(label=label, amount=amount)],
    )


@dp.pre_checkout_query()
async def on_pre_checkout(pre_checkout_query: PreCheckoutQuery) -> None:
    await pre_checkout_query.answer(ok=True)


@dp.message(F.successful_payment)
async def on_successful_payment(message: Message) -> None:
    uid = message.from_user.id
    lang = get_lang(uid)
    stars = int(message.successful_payment.total_amount)
    add_balance(uid, stars)
    cur.execute("INSERT INTO payments (user_id, stars) VALUES (?, ?)", (uid, stars))
    conn.commit()
    new_bal = get_balance(uid)
    done_text = (
        f"Payment completed: +{stars} Stars! Balance: {new_bal} ⭐"
        if lang == "en"
        else f"Оплата прошла успешно: +{stars} звёзд! Баланс: {new_bal} ⭐"
    )
    await message.answer(done_text, reply_markup=main_menu_keyboard(lang, uid))


async def main() -> None:
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
