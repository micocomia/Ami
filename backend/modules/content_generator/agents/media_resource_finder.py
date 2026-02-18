from __future__ import annotations

import re
from typing import List
from urllib.parse import quote


def find_media_resources(
    search_runner,
    knowledge_points,
    max_videos: int = 2,
    max_images: int = 2,
) -> List[dict]:
    """Find YouTube videos and Wikipedia images for a list of knowledge points.

    Args:
        search_runner: A SearchRunner instance used to query YouTube links.
        knowledge_points: List of knowledge point dicts (with 'name' key) or strings.
        max_videos: Maximum number of YouTube videos to return.
        max_images: Maximum number of Wikipedia thumbnail images to return.

    Returns:
        List of resource dicts, each with 'type' == 'video' or 'image'.
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
        for topic in topic_names:
            video_count = sum(1 for r in results if r["type"] == "video")
            if video_count >= max_videos:
                break
            try:
                query = f"site:youtube.com {topic} tutorial education"
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
                            })
            except Exception:
                continue

    # --- Wikipedia Images ---
    if max_images > 0:
        for topic in topic_names:
            image_count = sum(1 for r in results if r["type"] == "image")
            if image_count >= max_images:
                break
            try:
                # Step 1: OpenSearch to get canonical title
                opensearch_url = (
                    f"https://en.wikipedia.org/w/api.php"
                    f"?action=opensearch&search={quote(topic)}&limit=1&format=json"
                )
                resp = requests.get(opensearch_url, timeout=5)
                data = resp.json()
                # OpenSearch response: [query, [titles], [descriptions], [urls]]
                if not data or len(data) < 2 or not data[1]:
                    continue
                title = data[1][0]

                # Step 2: REST Summary for thumbnail
                encoded_title = quote(title.replace(" ", "_"))
                summary_url = (
                    f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded_title}"
                )
                resp2 = requests.get(summary_url, timeout=5)
                summary_data = resp2.json()

                thumbnail = summary_data.get("thumbnail", {}) or {}
                image_url = thumbnail.get("source", "")
                if not image_url:
                    continue

                description = summary_data.get("description", "")
                page_url = (
                    summary_data.get("content_urls", {})
                    .get("desktop", {})
                    .get("page", "")
                )

                results.append({
                    "type": "image",
                    "title": title,
                    "url": page_url,
                    "image_url": image_url,
                    "description": description,
                })
            except Exception:
                continue

    return results
