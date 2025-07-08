from aiogram.fsm.state import StatesGroup, State

class AdminStates(StatesGroup):
    waiting_for_search_query = State()  # Пользователь вводит поисковый запрос
    waiting_for_new_order_text = State()  # Пользователь вводит новый текст для заказа
    waiting_for_help_message_text = State()  # Пользователь вводит новое сообщение помощи
    waiting_for_help_message_selection = State()  # Пользователь выбирает сообщение активным/удаляет
