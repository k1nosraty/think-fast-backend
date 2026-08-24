import secrets
from collections import Counter
from collections.abc import Callable

from cryptography.fernet import Fernet
from django.conf import settings

from apps.games.domain import NumberRules, validate_sequence


def generate_number_secret(
    rules: NumberRules, choice: Callable[[str], str] = secrets.choice
) -> str:
    symbols: list[str] = []
    while len(symbols) < rules.sequence_length:
        candidates = "123456789" if not symbols and not rules.allow_leading_zero else "0123456789"
        symbol = choice(candidates)
        if Counter(symbols)[symbol] < rules.max_symbol_repetition:
            symbols.append(symbol)
    value = "".join(symbols)
    return validate_sequence(value, rules)


def encrypt_secret(value: str) -> str:
    return Fernet(settings.GAME_SECRET_ENCRYPTION_KEY.encode()).encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    return Fernet(settings.GAME_SECRET_ENCRYPTION_KEY.encode()).decrypt(value.encode()).decode()
