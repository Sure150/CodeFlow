from model.order import RawOrder


def load_orders() -> list[RawOrder]:
    return [
        (" Ada ", "keyboard", 2, 3_000),
        ("Ada", "mouse", 1, 2_000),
        ("Lin", "monitor", 1, 12_500),
        ("Sam", "cable", 0, 900),
    ]
