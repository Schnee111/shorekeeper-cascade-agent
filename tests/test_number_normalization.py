from hermes_llm import clean_text_for_tts, clean_voice_text


def test_number_normalization_indonesian():
    raw = "Sistem berjalan dengan 25 partikel pada tahun 2026."
    cleaned = clean_voice_text(raw)
    assert "25" not in cleaned
    assert "2026" not in cleaned
    assert "dua puluh lima" in cleaned
    assert "dua ribu dua puluh enam" in cleaned


def test_number_normalization_preserves_words_and_citations():
    raw = "Ini adalah pengujian ke-2 dengan rujukan [1]."
    cleaned = clean_voice_text(raw)
    assert "[1]" in cleaned
    assert "dua" in cleaned


def test_number_normalization_decimals_indonesian():
    raw = "Versi rilis 2.5 telah aktif."
    cleaned = clean_voice_text(raw)
    assert "2.5" not in cleaned
    assert "dua koma lima" in cleaned


def test_number_normalization_english():
    # Pure English sentences must normalize digits to English words
    raw = "Found 2 errors across 10 files in 2026."
    cleaned = clean_voice_text(raw)
    assert "2" not in cleaned
    assert "10" not in cleaned
    assert "2026" not in cleaned
    assert "two" in cleaned
    assert "ten" in cleaned
    assert "two thousand" in cleaned
    assert "dua" not in cleaned


def test_number_normalization_english_phrases():
    # Test common voice phrases like '2 weeks'
    assert "two weeks" in clean_voice_text("Check back in 2 weeks.")
    assert "two" in clean_voice_text("There are 2 items remaining.")
    assert "three" in clean_voice_text("Option 3 is recommended.")
    assert "two point five" in clean_voice_text("Version 2.5 has been deployed.")


def test_number_normalization_explicit_lang():
    # Verify lang parameter can be passed explicitly if needed
    raw = "Item 2"
    assert "two" in clean_voice_text(raw, lang="en")
    assert "dua" in clean_voice_text(raw, lang="id")


def test_strip_bullet_dashes_and_markers():
    # Fish Audio TTS vocalizes leading '-' as 'minus'.
    # All leading dashes, bullets (*, +, -), and standalone dashes must be stripped.
    raw = "- First item\n- Second item\n- Third item"
    cleaned = clean_voice_text(raw)
    assert not cleaned.startswith("-")
    assert "minus" not in cleaned
    assert "First item" in cleaned
    assert "Second item" in cleaned
    assert "Third item" in cleaned
    assert "-" not in cleaned


def test_strip_markdown_list_bullets():
    raw = "* Bullet one\n+ Bullet two\n- Bullet three"
    cleaned = clean_voice_text(raw)
    assert not any(cleaned.startswith(p) for p in ("*", "+", "-"))
    assert "Bullet one" in cleaned
    assert "Bullet two" in cleaned
    assert "Bullet three" in cleaned


def test_strip_standalone_dashes():
    # Mid-sentence standalone dashes like 'option A - option B' or ' — '
    raw = "Select option A - option B - option C"
    cleaned = clean_voice_text(raw)
    # The standalone dashes should not remain as isolated '-'
    assert " - " not in cleaned
    assert "- option" not in cleaned


def test_clean_text_for_tts_alias():
    # clean_text_for_tts should exist as an alias for clean_voice_text
    assert callable(clean_text_for_tts)
    assert clean_text_for_tts("Check 2 items") == clean_voice_text("Check 2 items")
