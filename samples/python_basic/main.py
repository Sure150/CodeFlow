from helpers import normalize as normalize_text


def normalize(value):
    return value.upper()


def format_message(value, callback):
    cleaned = normalize_text(value)
    display = normalize(cleaned)
    return callback(display)
