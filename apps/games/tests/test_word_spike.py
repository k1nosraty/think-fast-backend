import pytest

from apps.games.word_spike import (
    BoundedLexicon,
    WordEntry,
    WordSpikeError,
    evaluate_word,
    normalize_persian_word,
)


def lexicon() -> BoundedLexicon:
    return BoundedLexicon(
        [
            WordEntry("کتاب", "noun", 10),
            WordEntry("آرام", "adjective", 20),
            WordEntry("امیر", "proper", 30, is_proper_name=True),
        ],
        blocked_terms={"بدواژه"},
    )


def test_normalization_maps_arabic_forms_and_removes_marks_spacing_and_zwnj() -> None:
    assert normalize_persian_word(" كِتاب\u200c ") == "کتاب"
    assert normalize_persian_word("ياد") == "یاد"


@pytest.mark.parametrize("value", ["", "book", "\u06a9\u062a\u0627\u06281", None])
def test_normalization_rejects_empty_or_non_persian_input(value: object) -> None:
    with pytest.raises(WordSpikeError):
        normalize_persian_word(value)


def test_bounded_dictionary_excludes_unknown_names_and_blocked_terms() -> None:
    assert lexicon().validate("كتاب", length=4) == "کتاب"
    for value, code, length in [
        ("پنجره", "word_not_in_dictionary", 5),
        ("امیر", "word_not_in_dictionary", 4),
        ("بدواژه", "word_blocked", 6),
    ]:
        with pytest.raises(WordSpikeError) as error:
            lexicon().validate(value, length=length)
        assert error.value.code == code


def test_candidate_wordle_feedback_is_duplicate_safe() -> None:
    feedback, solved = evaluate_word("کتاب", "کباب")
    assert feedback == ["exact", "absent", "exact", "exact"]
    assert solved is False
    assert evaluate_word("آرام", "آرام") == (["exact"] * 4, True)
