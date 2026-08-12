"""
tests/test_telegram_notify.py
Форматирование сводки для двух кнопок бота: «Заявки на запись» и
«Рекомендуемое расписание».
"""
from server.app.booking_store import BookingRequest
from server.app.telegram_notify import format_requests_message, format_schedule_message


def test_format_requests_message_empty_list():
    assert "не было" in format_requests_message([])


def test_format_requests_message_lists_all_entries_with_phone_and_time():
    bookings = [
        BookingRequest(name="Мария", phone_raw="89215551234", preferred_time="после 18"),
        BookingRequest(name="Иван", phone_raw="плохо расслышала", preferred_time="утром"),
    ]
    text = format_requests_message(bookings)

    assert "Мария" in text
    assert "+7 921 555-12-34" in text
    assert "после 18" in text
    assert "Иван" in text
    assert "⚠️ проверить номер" in text  # невалидный телефон должен быть помечен


def test_format_schedule_message_empty_list():
    assert "пустое" in format_schedule_message([])


def test_format_schedule_message_groups_by_time_of_day_in_order():
    bookings = [
        BookingRequest(name="Вечерний", phone_raw="89210000001", preferred_time="вечером"),
        BookingRequest(name="Утренний", phone_raw="89210000002", preferred_time="утром"),
        BookingRequest(name="Дневной", phone_raw="89210000003", preferred_time="днём"),
    ]
    text = format_schedule_message(bookings)

    # порядок в тексте должен быть утро → день → вечер, а не порядок ввода
    assert text.index("УТРО") < text.index("ДЕНЬ") < text.index("ВЕЧЕР")
    assert text.index("Утренний") < text.index("Дневной") < text.index("Вечерний")


def test_format_schedule_message_skips_empty_buckets():
    bookings = [BookingRequest(name="Только утро", phone_raw="89210000001", preferred_time="утром")]
    text = format_schedule_message(bookings)

    assert "УТРО" in text
    assert "ДЕНЬ" not in text
    assert "ВЕЧЕР" not in text
