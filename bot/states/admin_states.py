"""FSM states for admin interactions."""
from aiogram.fsm.state import State, StatesGroup
class AdminStates(StatesGroup):
    waiting_for_search_query = State()
    waiting_for_new_order_text = State()
    waiting_for_help_message_text = State()
    waiting_for_help_message_selection = State()
