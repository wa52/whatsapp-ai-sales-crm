"""Customer-message language detection with a deterministic local implementation."""

from __future__ import annotations

import re
from typing import Protocol

_HIRAGANA = re.compile(r"[\u3040-\u309f]")
_KATAKANA = re.compile(r"[\u30a0-\u30ff]")
_HANGUL = re.compile(r"[\uac00-\ud7af]")
_ARABIC = re.compile(r"[\u0600-\u06ff]")
_CYRILLIC = re.compile(r"[\u0400-\u04ff]")
_HAN = re.compile(r"[\u4e00-\u9fff]")


class LanguageDetector(Protocol):
    def detect(self, text: str) -> str | None:
        """Return an ISO 639-1-ish language code, or None if unrecognized."""
        ...


_KEYWORDS: dict[str, tuple[str, ...]] = {
    "zh": ("你好", "价格", "多少", "数量", "运费", "付款", "样品", "报价", "批发", "多少钱"),
    "de": ("hallo", "guten", "preis", "menge", "stück", "stueck", "liefer",
           "zahlung", "versand", "danke", "angebot"),
    "fr": ("bonjour", "salut", "prix", "quantite", "quantité", "livraison",
           "paiement", "merci", "devis", "commander", "expedition"),
    "es": ("hola", "buenos", "precio", "cantidad", "entrega", "pago",
           "gracias", "presupuesto", "pedido", "envio"),
    "pt": ("ola", "olá", "preco", "preço", "quantidade", "entrega",
           "pagamento", "obrigado", "orcamento", "pedido"),
    "it": ("ciao", "prezzo", "quantita", "quantità", "consegna", "pagamento",
           "grazie", "preventivo", "ordine", "spedizione"),
    "en": ("price", "quantity", "shipping", "payment", "sample", "catalog",
           "order", "quote", "how much", "moq", "please", "hello"),
}


class KeywordLanguageDetector:
    """Detects language by writing script first, then keyword overlap.

    Scripts are decisive (CJK kana/hangul/han, Arabic, Cyrillic). Latin-script
    messages are scored by per-language keyword hits; ties resolve in a fixed
    priority order, and Latin with no keyword match defaults to English.
    """

    def __init__(self, *, keywords: dict[str, tuple[str, ...]] | None = None) -> None:
        self._keywords = keywords or _KEYWORDS

    def detect(self, text: str) -> str | None:
        if not any(ch.isalpha() for ch in text):
            return None
        if _HIRAGANA.search(text) or _KATAKANA.search(text):
            return "ja"
        if _HANGUL.search(text):
            return "ko"
        if _ARABIC.search(text):
            return "ar"
        if _CYRILLIC.search(text):
            return "ru"
        if _HAN.search(text):
            return "zh"

        lowered = text.lower()
        best: str | None = None
        best_hits = 0
        for lang, words in self._keywords.items():
            hits = sum(1 for word in words if word in lowered)
            if hits > best_hits:
                best, best_hits = lang, hits
        return best or "en"
