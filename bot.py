import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
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

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

user_langs: dict[int, str] = {}


class DepositStates(StatesGroup):
    waiting_for_amount = State()


def lang_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Русский (RU)", callback_data="lang_ru"),
                InlineKeyboardButton(text="English (EN)", callback_data="lang_en"),
            ]
        ]
    )


def main_menu_keyboard(lang: str) -> InlineKeyboardMarkup:
    if lang == "en":
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Open GlimUp", web_app=WebAppInfo(url=WEBAPP_URL))],
                [InlineKeyboardButton(text="Top up", callback_data="topup_start")],
                [InlineKeyboardButton(text="Change language", callback_data="change_lang")],
            ]
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Открыть GlimUp", web_app=WebAppInfo(url=WEBAPP_URL))],
            [InlineKeyboardButton(text="Пополнить", callback_data="topup_start")],
            [InlineKeyboardButton(text="Сменить язык", callback_data="change_lang")],
        ]
    )


@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Выберите ваш язык / Choose your language:",
        reply_markup=lang_keyboard(),
    )


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
    user_langs[callback.from_user.id] = lang
    text = (
        "Language set to English. Choose an action:"
        if lang == "en"
        else "Язык выбран: Русский. Выберите действие:"
    )
    await callback.message.answer(text, reply_markup=main_menu_keyboard(lang))
    await callback.answer()


@dp.callback_query(F.data == "topup_start")
async def cb_topup_start(callback: CallbackQuery, state: FSMContext) -> None:
    lang = user_langs.get(callback.from_user.id, "ru")
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
    lang = user_langs.get(message.from_user.id, "ru")
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
    lang = user_langs.get(message.from_user.id, "ru")
    stars = message.successful_payment.total_amount
    done_text = (
        f"Payment completed: +{stars} Stars!"
        if lang == "en"
        else f"Оплата прошла успешно: +{stars} звёзд!"
    )
    await message.answer(done_text, reply_markup=main_menu_keyboard(lang))


async def main() -> None:
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
