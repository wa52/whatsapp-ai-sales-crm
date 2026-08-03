import pytest

from whatsapp_ai_sales.messaging.language import KeywordLanguageDetector


@pytest.fixture
def detector() -> KeywordLanguageDetector:
    return KeywordLanguageDetector()


def test_detects_chinese(detector: KeywordLanguageDetector) -> None:
    assert detector.detect("你好，这个产品价格多少？") == "zh"


def test_detects_japanese_and_korean_by_script(detector: KeywordLanguageDetector) -> None:
    assert detector.detect("こんにちは、価格はいくらですか") == "ja"
    assert detector.detect("안녕하세요, 가격이 얼마인가요?") == "ko"


def test_detects_arabic_and_cyrillic_by_script(detector: KeywordLanguageDetector) -> None:
    assert detector.detect("السلام عليكم، كم سعر هذا المنتج؟") == "ar"
    assert detector.detect("Здравствуйте, сколько стоит?") == "ru"


def test_detects_german_by_keywords(detector: KeywordLanguageDetector) -> None:
    assert detector.detect("Hallo, wie ist der Preis? Was ist die Menge?") == "de"


def test_detects_french_by_keywords(detector: KeywordLanguageDetector) -> None:
    assert detector.detect("Bonjour, quel est le prix et la livraison?") == "fr"


def test_detects_spanish_by_keywords(detector: KeywordLanguageDetector) -> None:
    assert detector.detect("Hola, precio y cantidad por favor") == "es"


def test_detects_portuguese_by_keywords(detector: KeywordLanguageDetector) -> None:
    assert detector.detect("Olá, qual o preço e quantidade?") == "pt"


def test_detects_italian_by_keywords(detector: KeywordLanguageDetector) -> None:
    assert detector.detect("Ciao, quanto costa? Prezzo e consegna") == "it"


def test_latin_defaults_to_english(detector: KeywordLanguageDetector) -> None:
    assert detector.detect("What is the MOQ?") == "en"
    assert detector.detect("Please send a catalog") == "en"


def test_unrecognizable_returns_none(detector: KeywordLanguageDetector) -> None:
    assert detector.detect("") is None
    assert detector.detect("12345 !!!") is None
