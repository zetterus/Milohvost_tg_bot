from aiogram.fsm.state import StatesGroup, State

class AdminStates(StatesGroup):
    waiting_for_search_query = State()  # Пользователь вводит поисковый запрос
    waiting_for_order_text_edit = State()  # Пользователь вводит новый текст для заказа
