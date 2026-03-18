from __future__ import annotations

import concurrent.futures
import re
from typing import List
from urllib.parse import quote


def _tokens(text: str) -> set[str]:
    stop = {
        "the", "and", "for", "with", "from", "that", "this", "your", "into",
        "what", "when", "where", "how", "why", "guide", "course", "lesson",
        "video", "tutorial", "walkthrough", "lecture", "explainer", "talk",
        "podcast", "demo", "introduction", "intro", "basics",
    }
    toks = {t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(t) > 2}
    normalized = set()
    for t in toks:
        normalized.add(t)
        if t.endswith("s") and len(t) > 3:
            normalized.add(t[:-1])
    return {t for t in normalized if t not in stop}


def _is_video_on_topic(topic: str, session_context: str, title: str, snippet: str) -> bool:
    target_tokens = _tokens(f"{topic} {session_context}")
    if not target_tokens:
        return True
    candidate_tokens = _tokens(f"{title} {snippet}")
    overlap = target_tokens.intersection(candidate_tokens)
    # Require at least one concrete topic/session token overlap.
    return len(overlap) >= 1


def _topic_budget(total_topics: int, max_count: int) -> int:
    """Return the number of topics to query for a given modality."""
    return min(total_topics, max(3, 2 * max_count))


def find_media_resources(
    search_runner,
    knowledge_points,
    max_videos: int = 2,
    max_images: int = 2,
    max_audio: int = 0,
    session_context: str = "",
    video_focus: str = "visual",
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

    # Extract topic names from knowledge_points
    topic_names: List[str] = []
    for kp in knowledge_points:
        if isinstance(kp, dict):
            name = kp.get("name", "")
        else:
            name = str(kp)
        if name:
            topic_names.append(name)

    all_results: List[List[dict]] = []

    # --- YouTube Videos (per-topic parallel fetch) ---
    if max_videos > 0 and search_runner is not None:
        focus_terms = "lecture explainer talk" if video_focus == "audio" else "tutorial walkthrough visualization"
        budget = _topic_budget(len(topic_names), max_videos)
        queried_topics = topic_names[:budget]

        def _fetch_youtube(topic: str) -> List[dict]:
            context = f" {session_context}" if session_context else ""
            query = f'site:youtube.com "{topic}"{context} {focus_terms}'
            out: List[dict] = []
            try:
                search_results = search_runner.invoke(query)
                for sr in search_results:
                    link = sr.link or ""
                    title = getattr(sr, "title", "") or topic
                    snippet = getattr(sr, "snippet", "")
                    if not isinstance(snippet, str):
                        snippet = ""
                    if not _is_video_on_topic(topic, session_context, title, snippet):
                        continue
                    match = re.search(r"watch\?v=([A-Za-z0-9_-]{11})", link)
                    if match:
                        out.append({
                            "type": "video",
                            "title": title,
                            "url": link,
                            "video_id": match.group(1),
                            "thumbnail_url": f"https://img.youtube.com/vi/{match.group(1)}/mqdefault.jpg",
                            "snippet": snippet,
                            "source": "youtube",
                        })
            except Exception:
                pass
            return out

        with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(queried_topics) or 1)) as pool:
            yt_futures = [pool.submit(_fetch_youtube, t) for t in queried_topics]
            yt_raw: List[dict] = []
            for fut in yt_futures:
                try:
                    yt_raw.extend(fut.result())
                except Exception:
                    pass

        # Deduplicate by video_id, preserve topic-index order
        seen_video_ids: set = set()
        yt_deduped: List[dict] = []
        for item in yt_raw:
            vid = item.get("video_id", "")
            if vid and vid not in seen_video_ids:
                seen_video_ids.add(vid)
                yt_deduped.append(item)
                if len(yt_deduped) >= max_videos:
                    break
        all_results.append(yt_deduped)
    else:
        all_results.append([])

    # --- Wikimedia Commons Images (per-topic parallel fetch) ---
    if max_images > 0:
        _img_exts = {'.jpg', '.jpeg', '.png', '.svg', '.gif', '.tiff', '.tif', '.webp'}
        budget = _topic_budget(len(topic_names), max_images)
        queried_topics = topic_names[:budget]

        def _fetch_wiki_image(topic: str) -> List[dict]:
            out: List[dict] = []
            try:
                params = {
                    "action": "query",
                    "generator": "search",
                    "gsrsearch": f"{topic} (diagram OR chart OR illustration)",
                    "gsrnamespace": "6",
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
                    if not any(full_url.lower().endswith(e) for e in _img_exts):
                        continue
                    raw_title = page.get("title", topic)
                    display_title = re.sub(r'^File:', '', raw_title, flags=re.IGNORECASE)
                    display_title = re.sub(r'\.[a-z]+$', '', display_title).replace('_', ' ')
                    ext_meta = imageinfo.get("extmetadata", {})
                    description = (
                        ext_meta.get("ImageDescription", {}).get("value", "")
                        or ext_meta.get("ObjectName", {}).get("value", "")
                        or f"Wikimedia Commons: {display_title}"
                    )
                    description = re.sub(r'<[^>]+>', '', description).strip()
                    page_url = f"https://commons.wikimedia.org/wiki/{quote(raw_title.replace(' ', '_'))}"
                    out.append({
                        "type": "image",
                        "title": display_title,
                        "url": page_url,
                        "image_url": thumb_url,
                        "description": description,
                    })
            except Exception:
                pass
            return out

        with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(queried_topics) or 1)) as pool:
            img_futures = [pool.submit(_fetch_wiki_image, t) for t in queried_topics]
            img_raw: List[dict] = []
            for fut in img_futures:
                try:
                    img_raw.extend(fut.result())
                except Exception:
                    pass

        # Deduplicate by image_url, cap at max_images
        seen_image_urls: set = set()
        img_deduped: List[dict] = []
        for item in img_raw:
            key = item.get("image_url", "")
            if key and key not in seen_image_urls:
                seen_image_urls.add(key)
                img_deduped.append(item)
                if len(img_deduped) >= max_images:
                    break
        all_results.append(img_deduped)
    else:
        all_results.append([])

    # --- Wikimedia Commons Videos (fills remaining video slots after YouTube) ---
    yt_count = len(all_results[0]) if all_results else 0
    remaining_videos = max_videos - yt_count if max_videos > 0 else 0
    if remaining_videos > 0:
        _video_exts = {'.webm', '.ogv', '.ogg'}
        budget = _topic_budget(len(topic_names), remaining_videos)
        queried_topics = topic_names[:budget]

        def _fetch_wiki_video(topic: str) -> List[dict]:
            out: List[dict] = []
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
                    out.append({
                        "type": "video",
                        "title": display_title,
                        "url": page_url,
                        "video_id": "",
                        "thumbnail_url": thumb_url,
                        "snippet": display_title,
                        "source": "wikimedia_commons",
                    })
            except Exception:
                pass
            return out

        with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(queried_topics) or 1)) as pool:
            wv_futures = [pool.submit(_fetch_wiki_video, t) for t in queried_topics]
            wv_raw: List[dict] = []
            for fut in wv_futures:
                try:
                    wv_raw.extend(fut.result())
                except Exception:
                    pass

        seen_wv_urls: set = set()
        wv_deduped: List[dict] = []
        for item in wv_raw:
            key = item.get("url", "")
            if key and key not in seen_wv_urls:
                seen_wv_urls.add(key)
                wv_deduped.append(item)
                if len(wv_deduped) >= remaining_videos:
                    break
        all_results.append(wv_deduped)
    else:
        all_results.append([])

    # --- Wikimedia Commons Audio (for verbal learners, per-topic parallel fetch) ---
    if max_audio > 0:
        _audio_exts = {'.ogg', '.oga', '.mp3', '.flac', '.wav'}
        budget = _topic_budget(len(topic_names), max_audio)
        queried_topics = topic_names[:budget]

        def _fetch_wiki_audio(topic: str) -> List[dict]:
            out: List[dict] = []
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
                    out.append({
                        "type": "audio",
                        "title": display_title,
                        "url": page_url,
                        "audio_url": full_url,
                        "snippet": display_title,
                        "source": "wikimedia_commons",
                    })
            except Exception:
                pass
            return out

        with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(queried_topics) or 1)) as pool:
            wa_futures = [pool.submit(_fetch_wiki_audio, t) for t in queried_topics]
            wa_raw: List[dict] = []
            for fut in wa_futures:
                try:
                    wa_raw.extend(fut.result())
                except Exception:
                    pass

        seen_audio_urls: set = set()
        wa_deduped: List[dict] = []
        for item in wa_raw:
            key = item.get("audio_url", "") or item.get("url", "")
            if key and key not in seen_audio_urls:
                seen_audio_urls.add(key)
                wa_deduped.append(item)
                if len(wa_deduped) >= max_audio:
                    break
        all_results.append(wa_deduped)
    else:
        all_results.append([])

    # Flatten: YouTube videos, Wikimedia images, Wikimedia videos, Wikimedia audio
    results: List[dict] = []
    for bucket in all_results:
        results.extend(bucket)
    return results
