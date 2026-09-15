from hermes_llm import clean_text_for_tts, clean_voice_text


def test_clean_text_for_tts_indonesian():
    raw = "Sistem berjalan dengan 25 partikel pada tahun 2026."
    cleaned = clean_text_for_tts(raw)
    assert "25" not in cleaned
    assert "2026" not in cleaned
    assert "dua puluh lima" in cleaned
    assert "dua ribu dua puluh enam" in cleaned


def test_clean_text_for_tts_preserves_citations():
    raw = "Ini adalah pengujian ke-2 dengan rujukan [1]."
    cleaned = clean_text_for_tts(raw)
    assert "[1]" in cleaned
    assert "dua" in cleaned


def test_clean_text_for_tts_decimals_indonesian():
    raw = "Versi rilis 2.5 telah aktif."
    cleaned = clean_text_for_tts(raw)
    assert "2.5" not in cleaned
    assert "dua koma lima" in cleaned


def test_clean_text_for_tts_english():
    # Pure English sentences must normalize digits to English words
    raw = "Found 2 errors across 10 files in 2026."
    cleaned = clean_text_for_tts(raw)
    assert "2" not in cleaned
    assert "10" not in cleaned
    assert "2026" not in cleaned
    assert "two" in cleaned
    assert "ten" in cleaned
    assert "two thousand" in cleaned
    assert "dua" not in cleaned


def test_clean_text_for_tts_english_phrases():
    # Test common voice phrases like '2 weeks'
    assert "two weeks" in clean_text_for_tts("Check back in 2 weeks.")
    assert "two" in clean_text_for_tts("There are 2 items remaining.")
    assert "three" in clean_text_for_tts("Option 3 is recommended.")
    assert "two point five" in clean_text_for_tts("Version 2.5 has been deployed.")


def test_clean_text_for_tts_explicit_lang():
    # Verify lang parameter can be passed explicitly if needed
    raw = "Item 2"
    assert "two" in clean_text_for_tts(raw, lang="en")
    assert "dua" in clean_text_for_tts(raw, lang="id")


def test_clean_text_for_tts_strip_bullet_dashes():
    # Fish Audio TTS vocalizes leading '-' as 'minus'.
    # All leading dashes, bullets (*, +, -), and standalone dashes must be stripped for TTS.
    raw = "- First item\n- Second item\n- Third item"
    cleaned = clean_text_for_tts(raw)
    assert not cleaned.startswith("-")
    assert "minus" not in cleaned
    assert "First item" in cleaned
    assert "Second item" in cleaned
    assert "Third item" in cleaned
    assert "-" not in cleaned


def test_clean_text_for_tts_strip_markdown_list_bullets():
    raw = "* Bullet one\n+ Bullet two\n- Bullet three"
    cleaned = clean_text_for_tts(raw)
    assert not any(cleaned.startswith(p) for p in ("*", "+", "-"))
    assert "Bullet one" in cleaned
    assert "Bullet two" in cleaned
    assert "Bullet three" in cleaned


def test_clean_text_for_tts_strip_standalone_dashes():
    raw = "Select option A - option B - option C"
    cleaned = clean_text_for_tts(raw)
    assert " - " not in cleaned
    assert "- option" not in cleaned


# =========================================================================
# UI Visual Transcript Verification: digits, linebreaks & bullets preserved
# =========================================================================


def test_clean_voice_text_preserves_digits():
    raw = "3.085 MB used out of 3.659 MB, sitting at 86% capacity in 2026."
    cleaned = clean_voice_text(raw)
    assert "3.085 MB" in cleaned
    assert "3.659 MB" in cleaned
    assert "86%" in cleaned
    assert "2026" in cleaned


def test_clean_voice_text_preserves_markdown_bullets_and_linebreaks():
    raw = "Berikut laporannya:\n- Memory: 3.085 MB\n- Disk: 49 GB\n- Load: 0.12"
    cleaned = clean_voice_text(raw)
    assert "\n- Memory: 3.085 MB" in cleaned
    assert "\n- Disk: 49 GB" in cleaned
    assert "\n- Load: 0.12" in cleaned
