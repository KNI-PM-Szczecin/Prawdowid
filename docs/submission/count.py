"""Counts the characters of the description block in opis.md after removing draft markers."""
import re
from pathlib import Path

LIMIT = 4000
text = Path(__file__).with_name("opis.md").read_text(encoding="utf-8")
block = text.split("<!-- OPIS-START -->")[1].split("<!-- OPIS-END -->")[0].strip()
clean = re.sub(r"\[(?:WDROŻONE|ZAPLANOWANE)\]\s*", "", block)
remaining = re.findall(r"\[DO UZUPEŁNIENIA\][^.]*", clean)
print(f"znaki (bez znaczników WDROŻONE/ZAPLANOWANE): {len(clean)} / {LIMIT}")
print(f"pozostałe pola do uzupełnienia: {len(remaining)}")
