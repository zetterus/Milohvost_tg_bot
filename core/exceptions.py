"""Custom domain exceptions for the application."""
class ApplicationError(Exception):
    """Base exception for all application-specific errors."""
    pass
class OrderNotFoundError(ApplicationError):
    """Raised when an order is not found in the database."""
    def __init__(self, order_id: int):
        super().__init__(f"Order with ID {order_id} not found")
        self.order_id = order_id
class UserNotFoundError(ApplicationError):
    """Raised when a user is not found in the database."""
    def __init__(self, user_id: int):
        super().__init__(f"User with ID {user_id} not found")
        self.user_id = user_id
class InvalidPhoneError(ApplicationError):
    """Raised when phone number format is invalid."""
    def __init__(self, phone_number: str):
        super().__init__(f"Invalid phone number format: {phone_number}")
        self.phone_number = phone_number
class OrderValidationError(ApplicationError):
    """Raised when order data validation fails."""
    def __init__(self, message: str, field: str | None = None):
        super().__init__(f"Order validation error: {message}")
        self.field = field
class HelpMessageNotFoundError(ApplicationError):
    """Raised when a help message is not found."""
    def __init__(self, message_id: int):
        super().__init__(f"Help message with ID {message_id} not found")
        self.message_id = message_id
