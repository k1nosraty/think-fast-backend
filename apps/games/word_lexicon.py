"""Placeholder Persian lexicon for word game.

This is a small curated set for development and testing.  Replace with a
licensed, versioned lexicon before production launch.
"""

from apps.games.word_spike import BoundedLexicon, WordEntry

_PLACEHOLDER_ENTRIES = [
    WordEntry("کتاب", "noun", 10),
    WordEntry("آرام", "adjective", 20),
    WordEntry("خانه", "noun", 30),
    WordEntry("باغچه", "noun", 40),
    WordEntry("ستاره", "noun", 50),
    WordEntry("ابریشم", "noun", 60),
    WordEntry("شیرین", "adjective", 70),
    WordEntry("سیب", "noun", 80),
    WordEntry("نوروز", "noun", 90),
    WordEntry("ایران", "proper", 100, is_proper_name=True),
    WordEntry("دانش", "noun", 110),
    WordEntry("آزاد", "adjective", 120),
    WordEntry("بزرگ", "adjective", 130),
    WordEntry("کوچک", "adjective", 140),
    WordEntry("زیبا", "adjective", 150),
    WordEntry("سبزه", "noun", 160),
    WordEntry("آسمان", "noun", 170),
    WordEntry("دریا", "noun", 180),
    WordEntry("کوه", "noun", 190),
    WordEntry("شادی", "noun", 200),
    WordEntry("غم", "noun", 210),
    WordEntry("عشق", "noun", 220),
    WordEntry("دوست", "noun", 230),
    WordEntry("دشمن", "noun", 240),
    WordEntry("جنگ", "noun", 250),
    WordEntry("صلح", "noun", 260),
    WordEntry("گذشته", "noun", 270),
    WordEntry("حال", "noun", 290),
    WordEntry("خوشبخت", "adjective", 300),
    WordEntry("بدبخت", "adjective", 310),
    WordEntry("پرنده", "noun", 320),
    WordEntry("ماهی", "noun", 330),
    WordEntry("گل", "noun", 340),
    WordEntry("درخت", "noun", 350),
    WordEntry("سنگ", "noun", 360),
    WordEntry("آهن", "noun", 370),
    WordEntry("نقره", "noun", 380),
    WordEntry("طلا", "noun", 390),
]

_BLOCKED_TERMS: set[str] = set()

_PLACEHOLDER_LEXICON: BoundedLexicon | None = None


def get_placeholder_lexicon() -> BoundedLexicon:
    global _PLACEHOLDER_LEXICON
    if _PLACEHOLDER_LEXICON is None:
        _PLACEHOLDER_LEXICON = BoundedLexicon(_PLACEHOLDER_ENTRIES, _BLOCKED_TERMS)
    return _PLACEHOLDER_LEXICON
