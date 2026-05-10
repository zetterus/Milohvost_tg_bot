"""Notification service - sends Telegram messages for order events."""
import logging
from aiogram import Bot
from aiogram.enums import ParseMode
from repositories.orders import OrderRepository
from repositories.users import UserRepository
from localization import get_localized_message
logger = logging.getLogger(__name__)
class NotificationService:
    """Service for sending Telegram notifications to users and admins."""
    def __init__(self, bot: Bot, order_repo: OrderRepository, user_repo: UserRepository) -> None:
        self._bot = bot
        self._order_repo = order_repo
        self._user_repo = user_repo
    async def notify_admins_new_order(self, order_id: int, admin_ids: list[int]) -> None:
        """Send new order notification to all admins."""
        order = await self._order_repo.get_by_id(order_id)
        if not order:
            logger.error(f"Order {order_id} not found for admin notification")
            return
        for admin_id in admin_ids:
            try:
                admin_lang = await self._user_repo.get_language(admin_id)
                username_text = f"@{order.username}" if order.username else get_localized_message("not_available", admin_lang)
                full_name_text = order.full_name or get_localized_message("not_provided", admin_lang)
                phone_text = order.contact_phone or get_localized_message("not_provided", admin_lang)
                status_loc = get_localized_message(f"order_status_{order.status}", admin_lang)
                title = get_localized_message("admin_new_order_notification_title", admin_lang).format(order_id=order.id)
                details = get_localized_message("admin_new_order_notification_details", admin_lang).format(
                    order_id=order.id,
                    user_id=order.user_id,
                    username=username_text,
                    full_name=full_name_text,
                    phone_number=phone_text,
                    order_text=order.order_text,
                    status=status_loc,
                    created_at=order.created_at.strftime('%d.%m.%Y %H:%M')
                )
                await self._bot.send_message(admin_id, title + "\n\n" + details, parse_mode=ParseMode.HTML)
                logger.info(f"Admin {admin_id} notified about order {order_id}")
            except Exception as e:
                logger.error(f"Failed to notify admin {admin_id} about order {order_id}: {e}", exc_info=True)
    async def notify_user_order_placed(self, user_id: int, order_id: int, lang: str) -> None:
        """Send order placement confirmation to user (if notifications enabled)."""
        is_enabled = await self._user_repo.get_notifications_enabled(user_id)
        if not is_enabled:
            logger.info(f"Notifications disabled for user {user_id}, skipping order_placed notification")
            return
        order = await self._order_repo.get_by_id(order_id)
        if not order:
            logger.error(f"Order {order_id} not found for user notification")
            return
        try:
            text = get_localized_message("order_placed_success_user_notification", lang).format(order_id=order.id)
            await self._bot.send_message(user_id, text, parse_mode=ParseMode.HTML)
            logger.info(f"User {user_id} notified about order {order_id}")
        except Exception as e:
            logger.error(f"Failed to notify user {user_id} about order {order_id}: {e}")
    async def notify_user_order_status_changed(self, user_id: int, order_id: int, new_status: str, lang: str) -> None:
        """Notify user when their order status changes."""
        is_enabled = await self._user_repo.get_notifications_enabled(user_id)
        if not is_enabled:
            return
        try:
            status_loc = get_localized_message(f"order_status_{new_status}", lang)
            text = get_localized_message("order_status_changed_notification", lang).format(
                order_id=order_id, new_status=status_loc
            )
            await self._bot.send_message(user_id, text, parse_mode=ParseMode.HTML)
            logger.info(f"User {user_id} notified about status change of order {order_id}")
        except Exception as e:
            logger.error(f"Failed to notify user {user_id} about status change: {e}")
