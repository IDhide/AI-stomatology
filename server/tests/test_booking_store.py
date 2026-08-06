"""
tests/test_booking_store.py
Нормализация телефона, группировка по времени суток, запись/чтение заявок.
"""
from datetime import datetime

from server.app.booking_store import (
    BookingRequest,
    BookingStore,
    normalize_ru_phone,
    time_bucket,
)


# ── normalize_ru_phone ──────────────────────────────────────────────────
def test_normalize_ru_phone_with_leading_eight():
    phone, valid = normalize_ru_phone("89215551234")
    assert valid is True
    assert phone == "+7 921 555-12-34"


def test_normalize_ru_phone_with_leading_seven():
    phone, valid = normalize_ru_phone("79215551234")
    assert valid is True
    assert phone == "+7 921 555-12-34"


def test_normalize_ru_phone_ten_digits_without_country_code():
    phone, valid = normalize_ru_phone("9215551234")
    assert valid is True
    assert phone == "+7 921 555-12-34"


def test_normalize_ru_phone_with_spaces_and_dashes():
    phone, valid = normalize_ru_phone("+7 (921) 555-12-34")
    assert valid is True
    assert phone == "+7 921 555-12-34"


def test_normalize_ru_phone_too_short_is_flagged_invalid():
    phone, valid = normalize_ru_phone("12345")
    assert valid is False
    assert phone == "12345"


def test_normalize_ru_phone_empty_returns_none():
    phone, valid = normalize_ru_phone("")
    assert valid is False
    assert phone is None


# ── time_bucket ──────────────────────────────────────────────────────────
def test_time_bucket_morning_word():
    assert time_bucket("хочу утром") == "утро"


def test_time_bucket_evening_word():
    assert time_bucket("после работы, вечером") == "вечер"


def test_time_bucket_explicit_hour_morning():
    assert time_bucket("в 10 часов") == "утро"


def test_time_bucket_explicit_hour_evening():
    assert time_bucket("после 18") == "вечер"


def test_time_bucket_unrecognized_text():
    assert time_bucket("как получится") == "не указано"


# ── BookingRequest ────────────────────────────────────────────────────────
def test_booking_request_computes_phone_on_init():
    b = BookingRequest(name="Мария", phone_raw="8 921 555 12 34", preferred_time="вечером")
    assert b.phone == "+7 921 555-12-34"
    assert b.phone_valid is True


def test_booking_request_flags_invalid_phone_but_keeps_it():
    b = BookingRequest(name="Иван", phone_raw="плохо расслышала", preferred_time="утром")
    assert b.phone_valid is False
    assert b.phone == "плохо расслышала"


# ── BookingStore ──────────────────────────────────────────────────────────
def test_booking_store_add_and_read_roundtrip(tmp_path):
    store = BookingStore(base_dir=str(tmp_path))
    booking = BookingRequest(name="Анна", phone_raw="89215551234", preferred_time="днём")
    store.add(booking)

    loaded = store.for_day(datetime.now())
    assert len(loaded) == 1
    assert loaded[0].name == "Анна"
    assert loaded[0].phone == "+7 921 555-12-34"
    assert loaded[0].phone_valid is True


def test_booking_store_for_day_empty_when_no_file(tmp_path):
    store = BookingStore(base_dir=str(tmp_path))
    assert store.for_day(datetime.now()) == []


def test_booking_store_multiple_entries_preserve_order(tmp_path):
    store = BookingStore(base_dir=str(tmp_path))
    store.add(BookingRequest(name="Первый", phone_raw="89215551111", preferred_time="утром"))
    store.add(BookingRequest(name="Второй", phone_raw="89215552222", preferred_time="вечером"))

    loaded = store.for_day(datetime.now())
    assert [b.name for b in loaded] == ["Первый", "Второй"]
