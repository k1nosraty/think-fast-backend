# T7 Word feasibility spike

**Status:** CHANGE / NO-GO for production Word support on 2026-08-26.

This is evidence for the T7 gate, not a shipped Game Type. `word` is not in the
game registry, presets, REST creation surface or production RuleSet union.

## Prototype decision

The candidate loop is Wordle-like positional feedback because it reuses the
known duplicate-safe `exact/present/absent` semantics. A character-pool loop is
deferred: it needs separate product research and would not validate the main
dictionary risk.

Canonicalization uses Unicode NFC, maps Arabic Yeh/Kaf variants to Persian,
removes diacritics/tatweel, and ignores whitespace/ZWNJ for comparison. This is
deliberately narrower than a general NLP normalizer. Unicode warns that
compatibility normalization can erase meaningful distinctions, so the spike
does not blindly apply NFKC ([Unicode UAX #15](https://unicode.org/reports/tr15/)).

The prototype uses a bounded in-memory lexicon with explicit metadata. Proper
names are excluded. Inflections are accepted only when explicitly present;
stemming does not make a Guess valid. A normalized deny-list blocks unsuitable
terms, but it is not sufficient moderation for launch. Appeals require a
versioned lexicon/moderation decision record; AI may assist review but cannot be
the authoritative validator.

## Data and license findings

- Hazm provides useful Persian normalization/tokenization under MIT, but using
  its code does not establish rights or gameplay suitability for every corpus it
  can read ([official Hazm repository](https://github.com/roshan-research/hazm),
  [package metadata](https://github.com/roshan-research/hazm/blob/master/pyproject.toml)).
- `word-list-fa` is MIT and explicitly targets Persian word games, but its small
  public description does not provide the frequency, morphology, proper-name,
  offensiveness or provenance labels required for authoritative acceptance
  ([official repository](https://github.com/mvalipour/word-list-fa)).
- Large scraped/compiled lists with absent or mixed upstream licensing are not
  acceptable for a commercial canonical dictionary.

Recommendation: create or license a curated, versioned Persian lexicon whose
source rights, surface form, lemma, part of speech, frequency band, proper-name
status and moderation status are documented per entry. Legal/product ownership
must be assigned before ingestion.

## Evidence and unresolved thresholds

`uv run pytest apps/games/tests/test_word_spike.py --no-cov` covers Arabic/Persian
variants, diacritics, spacing/ZWNJ, invalid scripts, unknown words, proper names,
blocked terms and duplicate-safe feedback. On the T7 development container,
`uv run python scripts/benchmark_word_spike.py` ran 100,000 four-letter
evaluations at 0.002013 ms median and 0.002103 ms p95 (max 0.304929 ms). Pure
feedback latency is therefore not the blocker; production dictionary lookup,
cache and moderation were not measured.

False-accept and false-reject rates are unknown because there is no licensed,
representative adjudicated Persian test set. Before a new implementation task
is approved, evaluate at least 2,000 stratified candidate words and meet agreed
targets (proposed: false accept below 0.5%, false reject below 2%, dictionary
lookup p95 below 20 ms), with disagreement and appeal outcomes reported.

## Gate to reopen Word

Production Word remains NO-GO until Product, Backend and legal/data owners
approve the loop, licensed dataset, morphology/proper-name policy, moderation
and appeal workflow, measured error thresholds and a new versioned contract.
