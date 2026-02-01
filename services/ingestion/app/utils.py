import re
import unicodedata


def slugify(text: str, max_length: int = 200) -> str:
    if not text:
        return ""

    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")

    text = text.lower()

    text = re.sub(r"[^\w\s-]", "", text)

    text = re.sub(r"[-\s]+", "-", text)

    text = text.strip("-")

    return text[:max_length]
