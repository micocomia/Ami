from __future__ import annotations

import re
from typing import List
from urllib.parse import quote


def find_media_resources(
    search_runner,
    knowledge_points,
    max_videos: int = 2,
    max_images: int = 2,
    max_audio: int = 0,
    session_context: str = "",
) -> List[dict]:
    """Find YouTube videos and Wikimedia Commons images/videos/audio for a list of knowledge points.

    Args:
        search_runner: A SearchRunner instance used to query YouTube links.
        knowledge_points: List of knowledge point dicts (with 'name' key) or strings.
        max_videos: Maximum number of videos (YouTube + Commons) to return.
        max_images: Maximum number of Wikimedia Commons educational images to return.
        max_audio: Maximum number of Wikimedia Commons audio resources to return.
        session_context: Session title string appended to YouTube queries for relevance.

    Returns:
        List of resource dicts, each with 'type' in {'video', 'image', 'audio'}.
    """
    import requests

    results: List[dict] = []

    # Extract topic names from knowledge_points
    topic_names: List[str] = []
    for kp in knowledge_points:
        if isinstance(kp, dict):
            name = kp.get("name", "")
        else:
            name = str(kp)
        if name:
            topic_names.append(name)

    # --- YouTube Videos ---
    if max_videos > 0:
        seen_video_ids: set = set()
        context = f" {session_context}" if session_context else ""
        for topic in topic_names:
            video_count = sum(1 for r in results if r["type"] == "video")
            if video_count >= max_videos:
                break
            try:
                query = f"site:youtube.com {topic}{context} tutorial"
                search_results = search_runner.invoke(query)
                for sr in search_results:
                    video_count = sum(1 for r in results if r["type"] == "video")
                    if video_count >= max_videos:
                        break
                    link = sr.link or ""
                    match = re.search(r"watch\?v=([A-Za-z0-9_-]{11})", link)
                    if match:
                        video_id = match.group(1)
                        if video_id not in seen_video_ids:
                            seen_video_ids.add(video_id)
                            results.append({
                                "type": "video",
                                "title": sr.title or topic,
                                "url": link,
                                "video_id": video_id,
                                "thumbnail_url": f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg",
                                "snippet": sr.snippet or "",
                                "source": "youtube",
                            })
            except Exception:
                continue

    # --- Wikimedia Commons Images (file namespace search for educational diagrams) ---
    if max_images > 0:
        _img_exts = {'.jpg', '.jpeg', '.png', '.svg', '.gif', '.tiff', '.tif', '.webp'}
        for topic in topic_names:
            image_count = sum(1 for r in results if r["type"] == "image")
            if image_count >= max_images:
                break
            try:
                params = {
                    "action": "query",
                    "generator": "search",
                    "gsrsearch": f"{topic} (diagram OR chart OR illustration)",
                    "gsrnamespace": "6",    # File namespace = images/media files
                    "gsrlimit": "10",
                    "prop": "imageinfo",
                    "iiprop": "url|thumburl|extmetadata",
                    "iiurlwidth": "400",
                    "format": "json",
                }
                resp = requests.get(
                    "https://commons.wikimedia.org/w/api.php",
                    params=params,
                    timeout=8,
                )
                pages = resp.json().get("query", {}).get("pages", {})
                for page_id, page in pages.items():
                    if int(page_id) < 0:
                        continue
                    imageinfo = (page.get("imageinfo") or [{}])[0]
                    thumb_url = imageinfo.get("thumburl", "")
                    full_url = imageinfo.get("url", "")
                    if not thumb_url:
                        continue
                    # Skip non-image files (audio, video OGG, etc.) that also appear in ns=6
                    if not any(full_url.lower().endswith(e) for e in _img_exts):
                        continue
                    raw_title = page.get("title", topic)
                    # Clean file title: strip "File:" prefix and extension for display
                    display_title = re.sub(r'^File:', '', raw_title, flags=re.IGNORECASE)
                    display_title = re.sub(r'\.[a-z]+$', '', display_title).replace('_', ' ')
                    # Description from extmetadata if available
                    ext_meta = imageinfo.get("extmetadata", {})
                    description = (
                        ext_meta.get("ImageDescription", {}).get("value", "")
                        or ext_meta.get("ObjectName", {}).get("value", "")
                        or f"Wikimedia Commons: {display_title}"
                    )
                    # Strip HTML tags from description
                    description = re.sub(r'<[^>]+>', '', description).strip()
                    page_url = f"https://commons.wikimedia.org/wiki/{quote(raw_title.replace(' ', '_'))}"
                    results.append({
                        "type": "image",
                        "title": display_title,
                        "url": page_url,
                        "image_url": thumb_url,
                        "description": description,
                    })
                    image_count += 1
                    if image_count >= max_images:
                        break
            except Exception:
                continue

    # --- Wikimedia Commons Videos (fills remaining slots after YouTube) ---
    if max_videos > 0:
        _video_exts = {'.webm', '.ogv', '.ogg'}
        for topic in topic_names:
            video_count = sum(1 for r in results if r["type"] == "video")
            if video_count >= max_videos:
                break
            try:
                params = {
                    "action": "query",
                    "generator": "search",
                    "gsrsearch": f"{topic} (video OR animation OR demonstration)",
                    "gsrnamespace": "6",
                    "gsrlimit": "10",
                    "prop": "imageinfo",
                    "iiprop": "url|thumburl",
                    "iiurlwidth": "480",
                    "format": "json",
                }
                resp = requests.get(
                    "https://commons.wikimedia.org/w/api.php",
                    params=params,
                    timeout=8,
                )
                pages = resp.json().get("query", {}).get("pages", {})
                for page_id, page in pages.items():
                    video_count = sum(1 for r in results if r["type"] == "video")
                    if video_count >= max_videos:
                        break
                    if int(page_id) < 0:
                        continue
                    imageinfo = (page.get("imageinfo") or [{}])[0]
                    full_url = imageinfo.get("url", "")
                    if not any(full_url.lower().endswith(e) for e in _video_exts):
                        continue
                    thumb_url = imageinfo.get("thumburl", "")
                    raw_title = page.get("title", topic)
                    display_title = re.sub(r'^File:', '', raw_title, flags=re.IGNORECASE)
                    display_title = re.sub(r'\.[a-z]+$', '', display_title).replace('_', ' ')
                    page_url = f"https://commons.wikimedia.org/wiki/{quote(raw_title.replace(' ', '_'))}"
                    results.append({
                        "type": "video",
                        "title": display_title,
                        "url": page_url,
                        "video_id": "",
                        "thumbnail_url": thumb_url,
                        "snippet": display_title,
                        "source": "wikimedia_commons",
                    })
            except Exception:
                continue

    # --- Wikimedia Commons Audio (for verbal learners) ---
    if max_audio > 0:
        _audio_exts = {'.ogg', '.oga', '.mp3', '.flac', '.wav'}
        for topic in topic_names:
            audio_count = sum(1 for r in results if r["type"] == "audio")
            if audio_count >= max_audio:
                break
            try:
                params = {
                    "action": "query",
                    "generator": "search",
                    "gsrsearch": f"{topic} (lecture OR speech OR explanation OR audio)",
                    "gsrnamespace": "6",
                    "gsrlimit": "10",
                    "prop": "imageinfo",
                    "iiprop": "url",
                    "format": "json",
                }
                resp = requests.get(
                    "https://commons.wikimedia.org/w/api.php",
                    params=params,
                    timeout=8,
                )
                pages = resp.json().get("query", {}).get("pages", {})
                for page_id, page in pages.items():
                    audio_count = sum(1 for r in results if r["type"] == "audio")
                    if audio_count >= max_audio:
                        break
                    if int(page_id) < 0:
                        continue
                    imageinfo = (page.get("imageinfo") or [{}])[0]
                    full_url = imageinfo.get("url", "")
                    if not any(full_url.lower().endswith(e) for e in _audio_exts):
                        continue
                    raw_title = page.get("title", topic)
                    display_title = re.sub(r'^File:', '', raw_title, flags=re.IGNORECASE)
                    display_title = re.sub(r'\.[a-z]+$', '', display_title).replace('_', ' ')
                    page_url = f"https://commons.wikimedia.org/wiki/{quote(raw_title.replace(' ', '_'))}"
                    results.append({
                        "type": "audio",
                        "title": display_title,
                        "url": page_url,
                        "audio_url": full_url,
                        "snippet": display_title,
                        "source": "wikimedia_commons",
                    })
            except Exception:
                continue

    return results
