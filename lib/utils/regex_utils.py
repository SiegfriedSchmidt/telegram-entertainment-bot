import re
import unicodedata
from pathlib import Path

VIDEO_LINK_REGEX = re.compile(
    r'.*?'
    r'https?://(?:www\.)?'
    r'(?:youtube\.com/(?:watch\?v=|shorts/)|youtu\.be/|instagram\.com/reel/)'
    r'[^\s<>"\']+',
    re.IGNORECASE
)


def get_video_link_from_text(text: str) -> str:
    match = VIDEO_LINK_REGEX.search(text)
    return match.group() if match else ""


def is_valid_mac_address(mac: str) -> bool:
    patterns = [
        r'^[0-9A-Fa-f]{2}[:-]{1}[0-9A-Fa-f]{2}[:-]{1}[0-9A-Fa-f]{2}[:-]{1}[0-9A-Fa-f]{2}[:-]{1}[0-9A-Fa-f]{2}[:-]{1}[0-9A-Fa-f]{2}$',
        r'^[0-9A-Fa-f]{12}$',
        r'^[0-9A-Fa-f]{2}\.[0-9A-Fa-f]{2}\.[0-9A-Fa-f]{2}\.[0-9A-Fa-f]{2}\.[0-9A-Fa-f]{2}\.[0-9A-Fa-f]{2}$',
    ]
    return any(re.match(pattern, mac) for pattern in patterns)


def slugify_filename(filename: str, max_length=200) -> str:
    """
    Replaces special chars with underscores and produces lowercase output.
    """
    # Cyrillic to Latin mapping (basic)
    cyrillic_map = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
        'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
        'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
        'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch',
        'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
        'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ё': 'Yo',
        'Ж': 'Zh', 'З': 'Z', 'И': 'I', 'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M',
        'Н': 'N', 'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U',
        'Ф': 'F', 'Х': 'Kh', 'Ц': 'Ts', 'Ч': 'Ch', 'Ш': 'Sh', 'Щ': 'Shch',
        'Ъ': '', 'Ы': 'Y', 'Ь': '', 'Э': 'E', 'Ю': 'Yu', 'Я': 'Ya'
    }

    # Split into name and extension
    path = Path(filename)
    name = path.stem
    extension = path.suffix

    # Transliterate Cyrillic
    result = []
    for char in name:
        if char in cyrillic_map:
            result.append(cyrillic_map[char])
        else:
            result.append(char)

    transliterated = ''.join(result)

    # Normalize and clean remaining Unicode
    normalized = unicodedata.normalize('NFKD', transliterated)
    ascii_name = normalized.encode('ASCII', 'ignore').decode('ASCII')

    # If nothing remained, use original name
    if not ascii_name.strip():
        ascii_name = name

    # Replace unsafe characters with underscores
    safe_chars = []
    for char in ascii_name:
        if char.isalnum():
            safe_chars.append(char.lower())  # Force lowercase
        elif char in '._':
            safe_chars.append(char)  # Keep dots and underscores as-is
        elif char.isspace():
            safe_chars.append('_')  # Replace spaces with underscore
        else:
            safe_chars.append('_')  # Replace other special chars with underscore

    slug = ''.join(safe_chars)

    # Replace multiple underscores with single underscore
    slug = re.sub(r'_+', '_', slug)

    # Remove leading/trailing underscores and dots
    slug = slug.strip('_.')

    # Handle multiple dots (keep only the last one for extension later)
    # But we'll handle this carefully when adding extension

    if not slug:
        slug = 'file'

    # Clean and add extension
    if extension:
        # Clean extension: keep only alphanumeric, lowercase
        clean_ext = re.sub(r'[^a-zA-Z0-9]', '', extension.lower())
        if clean_ext:
            # Ensure no double dots
            slug = f"{slug[:max_length]}.{clean_ext}"

    # Final safety check - ensure no double dots
    slug = re.sub(r'\.+', '.', slug)

    return slug
