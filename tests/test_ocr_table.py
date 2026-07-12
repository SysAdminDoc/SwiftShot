"""Tests for OCR table detection (words_to_table clustering, R-09). The pure
clustering is testable without a real OCR engine."""


def _word(x, y, text, w=20, h=14):
    return {"x": x, "y": y, "w": w, "h": h, "text": text}


def test_words_to_table_empty():
    from ocr import words_to_table
    assert words_to_table([]) == ""


def test_words_to_table_rows_and_columns():
    from ocr import words_to_table
    # two rows, two columns (wide gap between columns)
    words = [
        _word(0, 0, "Name"), _word(200, 0, "Age"),
        _word(0, 30, "Alice"), _word(200, 30, "30"),
    ]
    table = words_to_table(words)
    lines = table.split("\n")
    assert len(lines) == 2
    assert lines[0] == "Name\tAge"
    assert lines[1] == "Alice\t30"


def test_words_to_table_same_column_uses_space():
    from ocr import words_to_table
    # words close together on one row → single cell, space-joined
    words = [_word(0, 0, "Hello"), _word(24, 0, "World")]
    table = words_to_table(words)
    assert table == "Hello World"


def test_words_to_table_sorts_out_of_order_input():
    from ocr import words_to_table
    words = [
        _word(200, 30, "30"), _word(0, 0, "Name"),
        _word(200, 0, "Age"), _word(0, 30, "Alice"),
    ]
    table = words_to_table(words)
    assert table.split("\n")[0] == "Name\tAge"
