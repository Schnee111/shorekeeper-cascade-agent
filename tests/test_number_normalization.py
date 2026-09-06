from hermes_llm import clean_voice_text


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


def test_number_normalization_decimals():
    raw = "Versi rilis 2.5 telah aktif."
    cleaned = clean_voice_text(raw)
    assert "2.5" not in cleaned
    assert "dua koma lima" in cleaned or "dua" in cleaned
