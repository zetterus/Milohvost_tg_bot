from aiogram.fsm.state import State, StatesGroup

class OrderStates(StatesGroup):
    waiting_for_order_text = State()
    waiting_for_full_name = State()
    waiting_for_delivery_address = State()
    waiting_for_payment_method = State()
    waiting_for_contact_phone = State()
    waiting_for_delivery_notes = State()
    confirm_order = State()
