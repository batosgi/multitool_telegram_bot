from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from callback_data import HashMenu
from filters import CbMagicFilters
from keyboards import InlineKeyboards
from utils import HashMenuUtils

callback_router = Router(name=__name__)


@callback_router.callback_query(CbMagicFilters.HashMenu_ENTER(F.data))
async def enter_hash_menu(callback_query: CallbackQuery):
    inline_kb = InlineKeyboards.hash_menu_keyboard()
    await callback_query.message.edit_text(text="Choose hash option", reply_markup=inline_kb)


@callback_router.callback_query(CbMagicFilters.StartMenu_ENTER(F.data))
async def return_to_start_menu_from_another_menu(callback_query: CallbackQuery):
    inline_kb = InlineKeyboards.start_menu_inline_keyboard()
    await callback_query.message.edit_text(text="Hello! I'm your friendly bot. How can I assist you today?", reply_markup=inline_kb)


@callback_router.callback_query(HashMenu.filter())
async def handle_hash_menu_selection(callback_query: CallbackQuery, state: FSMContext):
    await HashMenuUtils.extract_cb_and_set_state(callback_query, state)

    inline_kb = InlineKeyboards.return_to_hash_menu_keyboard()
    await callback_query.message.edit_text(
        text="Upload file and enter expected output in caption",
        reply_markup=inline_kb
    )
