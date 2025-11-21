from django import template
from urllib.parse import urlparse, parse_qs

register = template.Library()

def _extract_youtube_id(url: str) -> str | None:
    if not url:
        return None

    parsed = urlparse(url)

    # 1) ya es /embed/ID
    if "youtube.com" in parsed.netloc and "/embed/" in parsed.path:
        return parsed.path.split("/embed/")[-1]

    # 2) formato watch?v=ID
    if "youtube.com" in parsed.netloc:
        qs = parse_qs(parsed.query)
        video_id = qs.get("v", [None])[0]
        if video_id:
            return video_id

    # 3) formato youtu.be/ID  (con o sin ?si=xxxxx)
    if "youtu.be" in parsed.netloc:
        # parsed.path = "/_uQrJ0TkZlc"
        video_id = parsed.path.strip("/")
        if video_id:
            return video_id

    return None


@register.filter
def youtube_embed(url):
    """
    Acepta:
    - https://www.youtube.com/watch?v=ID
    - https://youtu.be/ID
    - https://youtu.be/ID?si=XXXX
    - https://www.youtube.com/embed/ID
    y siempre regresa:
    - https://www.youtube.com/embed/ID
    """
    video_id = _extract_youtube_id(url)
    if not video_id:
        return url or ""

    return f"https://www.youtube.com/embed/{video_id}"
