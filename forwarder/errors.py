"""Turn Telegram API errors into actionable messages without exposing request data."""


def delivery_error_message(error: Exception) -> str:
    message = str(error).lower().replace("_", " ")
    if "message thread not found" in message or "topic not found" in message:
        return "Telegram не нашёл тему. Выполните /bind заново внутри существующей темы."
    if "topic closed" in message:
        return "Тема закрыта, а у бота нет права открыть её. Разрешите боту управлять темами или откройте тему вручную."
    if "not enough rights" in message or "forbidden" in message or "have no rights" in message:
        return "У бота недостаточно прав. В правах администратора включите «Управление темами» и возможность отправлять сообщения."
    if "chat not found" in message or "bot is not a member" in message:
        return "Бот больше не имеет доступа к этой группе. Добавьте его снова."
    if "message is too long" in message or "caption is too long" in message:
        return "Сообщение слишком длинное для Telegram. Сократите текст."
    return "Telegram отклонил отправку. Проверьте, что тема существует и бот может писать и управлять темами."
