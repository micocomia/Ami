"""Tests for Audio-Visual Adaptive Content Delivery.

Unit tests — no LLM or network calls; all external dependencies mocked.

Run from backend directory:
    pytest tests/test_adaptive_content_delivery.py -v
"""

import sys
import os
import asyncio
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# TestGetFslsmInput
# ---------------------------------------------------------------------------

class TestGetFslsmInput:

    def _import(self):
        from modules.content_generator.utils.fslsm_adaptation import get_fslsm_input
        return get_fslsm_input

    def test_standard_extraction(self):
        get_fslsm_input = self._import()
        profile = {
            "learning_preferences": {
                "fslsm_dimensions": {
                    "fslsm_input": -0.8
                }
            }
        }
        assert get_fslsm_input(profile) == pytest.approx(-0.8)

    def test_missing_dims(self):
        get_fslsm_input = self._import()
        assert get_fslsm_input({}) == 0.0

    def test_nested_missing(self):
        get_fslsm_input = self._import()
        profile = {"learning_preferences": {}}
        assert get_fslsm_input(profile) == 0.0


# ---------------------------------------------------------------------------
# TestGetFslsmDim
# ---------------------------------------------------------------------------

class TestGetFslsmDim:

    def _import(self):
        from modules.content_generator.utils.fslsm_adaptation import get_fslsm_dim
        return get_fslsm_dim

    def test_extracts_processing(self):
        get_fslsm_dim = self._import()
        profile = {
            "learning_preferences": {
                "fslsm_dimensions": {
                    "fslsm_processing": -0.6
                }
            }
        }
        assert get_fslsm_dim(profile, "fslsm_processing") == pytest.approx(-0.6)

    def test_extracts_perception(self):
        get_fslsm_dim = self._import()
        profile = {
            "learning_preferences": {
                "fslsm_dimensions": {
                    "fslsm_perception": 0.5
                }
            }
        }
        assert get_fslsm_dim(profile, "fslsm_perception") == pytest.approx(0.5)

    def test_extracts_understanding(self):
        get_fslsm_dim = self._import()
        profile = {
            "learning_preferences": {
                "fslsm_dimensions": {
                    "fslsm_understanding": 0.8
                }
            }
        }
        assert get_fslsm_dim(profile, "fslsm_understanding") == pytest.approx(0.8)

    def test_missing_dim_returns_zero(self):
        get_fslsm_dim = self._import()
        profile = {"learning_preferences": {"fslsm_dimensions": {}}}
        assert get_fslsm_dim(profile, "fslsm_processing") == 0.0

    def test_empty_profile_returns_zero(self):
        get_fslsm_dim = self._import()
        assert get_fslsm_dim({}, "fslsm_understanding") == 0.0


# ---------------------------------------------------------------------------
# TestProcessingPerceptionHints
# ---------------------------------------------------------------------------

class TestProcessingPerceptionHints:

    def _import(self):
        from modules.content_generator.utils.fslsm_adaptation import processing_perception_hints
        return processing_perception_hints

    def test_active_processing_contains_try_it(self):
        processing_perception_hints = self._import()
        hint = processing_perception_hints(-0.5, 0.0)
        assert "Try It First" in hint

    def test_reflective_processing_contains_reflection(self):
        processing_perception_hints = self._import()
        hint = processing_perception_hints(0.5, 0.0)
        assert "Reflection Pause" in hint

    def test_sensing_perception_example_first(self):
        processing_perception_hints = self._import()
        hint = processing_perception_hints(0.0, -0.5)
        assert "Sensing" in hint
        assert "real-world example" in hint

    def test_intuitive_perception_theory_first(self):
        processing_perception_hints = self._import()
        hint = processing_perception_hints(0.0, 0.5)
        assert "Intuitive" in hint
        assert "theory" in hint.lower()

    def test_neutral_returns_empty(self):
        processing_perception_hints = self._import()
        assert processing_perception_hints(0.0, 0.0) == ""

    def test_within_threshold_returns_empty(self):
        processing_perception_hints = self._import()
        assert processing_perception_hints(0.2, -0.2) == ""

    def test_both_dims_combined(self):
        processing_perception_hints = self._import()
        hint = processing_perception_hints(-0.7, 0.7)
        assert "Try It First" in hint
        assert "Intuitive" in hint


# ---------------------------------------------------------------------------
# TestSessionAdaptationContract
# ---------------------------------------------------------------------------

class TestSessionAdaptationContract:

    def _import(self):
        from modules.content_generator.utils.fslsm_adaptation import build_session_adaptation_contract
        return build_session_adaptation_contract

    def test_prefers_session_fields_and_recovers_strength(self):
        build_session_adaptation_contract = self._import()
        contract = build_session_adaptation_contract(
            {
                "has_checkpoint_challenges": True,
                "thinking_time_buffer_minutes": 0,
                "session_sequence_hint": "application-first",
            },
            {
                "learning_preferences": {
                    "fslsm_dimensions": {
                        "fslsm_processing": -0.9,
                        "fslsm_perception": -0.8,
                    }
                }
            },
        )
        assert contract["processing"]["mode"] == "active"
        assert contract["processing"]["checkpoint_frequency"] == "multiple"
        assert contract["perception"]["mode"] == "application_first"
        assert contract["perception"]["section_order"] == ["application", "example", "theory"]

    def test_reflective_and_theory_first_contract(self):
        build_session_adaptation_contract = self._import()
        contract = build_session_adaptation_contract(
            {
                "has_checkpoint_challenges": False,
                "thinking_time_buffer_minutes": 5,
                "session_sequence_hint": "theory-first",
            },
            {
                "learning_preferences": {
                    "fslsm_dimensions": {
                        "fslsm_processing": 0.5,
                        "fslsm_perception": 0.6,
                    }
                }
            },
        )
        assert contract["processing"]["mode"] == "reflective"
        assert contract["processing"]["reflection_level"] == "brief"
        assert contract["perception"]["mode"] == "theory_first"
        assert contract["perception"]["section_order"] == ["theory", "pattern", "example"]


# ---------------------------------------------------------------------------
# TestUnderstandingHints
# ---------------------------------------------------------------------------

class TestUnderstandingHints:

    def _import(self):
        from modules.content_generator.utils.fslsm_adaptation import understanding_hints
        return understanding_hints

    def test_sequential_contains_linear(self):
        understanding_hints = self._import()
        hint = understanding_hints(-0.5)
        assert "Sequential" in hint
        assert "linear" in hint.lower()

    def test_global_contains_big_picture(self):
        understanding_hints = self._import()
        hint = understanding_hints(0.5)
        assert "Big Picture" in hint

    def test_neutral_returns_empty(self):
        understanding_hints = self._import()
        assert understanding_hints(0.0) == ""

    def test_within_threshold_returns_empty(self):
        understanding_hints = self._import()
        assert understanding_hints(0.2) == ""
        assert understanding_hints(-0.2) == ""


# ---------------------------------------------------------------------------
# TestVisualFormattingHints
# ---------------------------------------------------------------------------

class TestVisualFormattingHints:

    def _import(self):
        from modules.content_generator.utils.fslsm_adaptation import visual_formatting_hints
        return visual_formatting_hints

    def test_strong_visual_contains_mermaid(self):
        visual_formatting_hints = self._import()
        hint = visual_formatting_hints(-0.9)
        assert "mermaid" in hint.lower()

    def test_moderate_visual_contains_table(self):
        visual_formatting_hints = self._import()
        hint = visual_formatting_hints(-0.5)
        assert "table" in hint.lower()

    def test_balanced_empty(self):
        visual_formatting_hints = self._import()
        hint = visual_formatting_hints(0.0)
        assert hint == ""


# ---------------------------------------------------------------------------
# TestStripMarkdown
# ---------------------------------------------------------------------------

class TestStripMarkdown:

    def _import(self):
        from modules.content_generator.agents.tts_generator import _strip_markdown
        return _strip_markdown

    def test_removes_bold(self):
        _strip_markdown = self._import()
        assert _strip_markdown("**hello**") == "hello"

    def test_removes_headings(self):
        _strip_markdown = self._import()
        result = _strip_markdown("## Title\n")
        assert "##" not in result
        assert "Title" in result

    def test_removes_links(self):
        _strip_markdown = self._import()
        assert _strip_markdown("[text](url)") == "text"

    def test_removes_html_tags(self):
        _strip_markdown = self._import()
        result = _strip_markdown("<audio controls>")
        assert "<" not in result
        assert ">" not in result


# ---------------------------------------------------------------------------
# TestParseDialogueTurns
# ---------------------------------------------------------------------------

class TestParseDialogueTurns:

    def _import(self):
        from modules.content_generator.agents.tts_generator import _parse_dialogue_turns
        return _parse_dialogue_turns

    def test_two_speakers(self):
        _parse_dialogue_turns = self._import()
        doc = "**[HOST]**: Welcome to the show.\n**[EXPERT]**: Thanks for having me."
        turns = _parse_dialogue_turns(doc)
        assert len(turns) == 2
        assert turns[0][0] == "HOST"
        assert "Welcome" in turns[0][1]
        assert turns[1][0] == "EXPERT"
        assert "Thanks" in turns[1][1]

    def test_speaker_names_uppercased(self):
        _parse_dialogue_turns = self._import()
        doc = "**[host]**: Hello.\n**[expert]**: Hi there."
        turns = _parse_dialogue_turns(doc)
        assert turns[0][0] == "HOST"
        assert turns[1][0] == "EXPERT"

    def test_empty_turns_skipped(self):
        _parse_dialogue_turns = self._import()
        doc = "**[HOST]**: \n**[EXPERT]**: Real content here."
        turns = _parse_dialogue_turns(doc)
        # Empty HOST turn should be skipped
        assert all(text.strip() for _, text in turns)
        speakers = [s for s, _ in turns]
        assert "HOST" not in speakers

    def test_no_turns_returns_empty(self):
        _parse_dialogue_turns = self._import()
        doc = "This is plain prose with no speaker labels."
        turns = _parse_dialogue_turns(doc)
        assert turns == []


# ---------------------------------------------------------------------------
# TestGenerateTtsAudio
# ---------------------------------------------------------------------------

class TestGenerateTtsAudio:

    def test_generate_audio_inside_running_loop(self):
        from pathlib import Path
        import tempfile
        import shutil

        from modules.content_generator.agents import tts_generator
        from modules.content_generator.agents.tts_generator import generate_tts_audio

        async def _fake_generate_segments(turns, tmp_dir, voice_map):
            seg = tmp_dir / "turn_0000.mp3"
            seg.write_bytes(b"audio-bytes")
            return [seg]

        async def _run_in_async_context(out_dir: Path):
            with patch.object(tts_generator, "AUDIO_DIR", out_dir), \
                 patch.object(tts_generator, "_generate_segments", side_effect=_fake_generate_segments):
                return generate_tts_audio("Plain narration content")

        out_dir = Path(tempfile.mkdtemp())
        try:
            url = asyncio.run(_run_in_async_context(out_dir))
            assert url.startswith("/static/audio/")
            out_name = url.rsplit("/", 1)[-1]
            out_file = out_dir / out_name
            assert out_file.exists()
            assert out_file.read_bytes() == b"audio-bytes"
        finally:
            shutil.rmtree(out_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# TestFindMediaResources
# ---------------------------------------------------------------------------

class TestFindMediaResources:

    def _import(self):
        from modules.content_generator.agents.media_resource_finder import find_media_resources
        return find_media_resources

    def _make_search_result(self, title, link):
        result = MagicMock()
        result.title = title
        result.link = link
        return result

    def test_youtube_extraction(self):
        find_media_resources = self._import()
        mock_runner = MagicMock()
        mock_runner.invoke.return_value = [
            self._make_search_result(
                "Python Variables Tutorial",
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
            )
        ]
        results = find_media_resources(mock_runner, [{"name": "Python"}], max_videos=1, max_images=0)
        videos = [r for r in results if r["type"] == "video"]
        assert len(videos) == 1
        assert videos[0]["video_id"] == "dQw4w9WgXcQ"

    def test_thumbnail_url_format(self):
        find_media_resources = self._import()
        mock_runner = MagicMock()
        mock_runner.invoke.return_value = [
            self._make_search_result(
                "Python Tutorial",
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
            )
        ]
        results = find_media_resources(mock_runner, [{"name": "Python"}], max_videos=1, max_images=0)
        videos = [r for r in results if r["type"] == "video"]
        assert len(videos) == 1
        assert "img.youtube.com/vi/dQw4w9WgXcQ" in videos[0]["thumbnail_url"]

    def test_no_youtube_links(self):
        find_media_resources = self._import()
        mock_runner = MagicMock()
        mock_runner.invoke.return_value = [
            self._make_search_result("Some Page", "https://www.example.com/page")
        ]
        results = find_media_resources(mock_runner, [{"name": "Python"}], max_videos=2, max_images=0)
        videos = [r for r in results if r["type"] == "video"]
        assert videos == []

    def test_off_topic_video_filtered(self):
        find_media_resources = self._import()
        mock_runner = MagicMock()
        mock_runner.invoke.return_value = [
            self._make_search_result("Guitar Chords Lesson", "https://www.youtube.com/watch?v=AAAAAAAAAAA"),
        ]
        results = find_media_resources(mock_runner, [{"name": "Python"}], max_videos=1, max_images=0)
        videos = [r for r in results if r["type"] == "video"]
        assert videos == []

    def test_max_videos_respected(self):
        find_media_resources = self._import()
        mock_runner = MagicMock()
        mock_runner.invoke.return_value = [
            self._make_search_result("Vid 1", "https://www.youtube.com/watch?v=AAAAAAAAAAA"),
            self._make_search_result("Vid 2", "https://www.youtube.com/watch?v=BBBBBBBBBBB"),
            self._make_search_result("Vid 3", "https://www.youtube.com/watch?v=CCCCCCCCCCC"),
        ]
        results = find_media_resources(
            mock_runner,
            [{"name": "Topic A"}, {"name": "Topic B"}],
            max_videos=1,
            max_images=0,
        )
        videos = [r for r in results if r["type"] == "video"]
        assert len(videos) <= 1

    def test_search_failure_graceful(self):
        find_media_resources = self._import()
        mock_runner = MagicMock()
        mock_runner.invoke.side_effect = RuntimeError("Network error")
        # Should not raise; should return empty list
        results = find_media_resources(mock_runner, [{"name": "Python"}], max_videos=2, max_images=0)
        assert results == []


# ---------------------------------------------------------------------------
# TestMediaRelevanceEvaluator
# ---------------------------------------------------------------------------

class TestMediaRelevanceEvaluator:
    def _import(self):
        from modules.content_generator.agents.media_relevance_evaluator import filter_media_resources_with_llm
        return filter_media_resources_with_llm

    @patch("modules.content_generator.agents.media_relevance_evaluator.MediaRelevanceEvaluator.evaluate")
    @patch("modules.content_generator.agents.media_relevance_evaluator.LLMFactory.create")
    def test_off_topic_filtered_even_if_llm_true(self, _mock_create, mock_eval):
        filter_media_resources_with_llm = self._import()
        resources = [
            {
                "type": "video",
                "title": "Beginner Guitar Chords",
                "snippet": "Learn guitar fast",
                "url": "https://www.youtube.com/watch?v=AAAAAAAAAAA",
            }
        ]
        mock_eval.return_value = {"relevance": [True]}
        out = filter_media_resources_with_llm(
            llm=None,
            resources=resources,
            session_title="Sorting Algorithms",
            knowledge_point_names=["Merge Sort", "Quick Sort"],
        )
        assert out == []

    @patch("modules.content_generator.agents.media_relevance_evaluator.MediaRelevanceEvaluator.evaluate")
    @patch("modules.content_generator.agents.media_relevance_evaluator.LLMFactory.create")
    def test_fail_closed_fallback_keeps_only_topical_prefilter(self, _mock_create, mock_eval):
        filter_media_resources_with_llm = self._import()
        resources = [
            {
                "type": "video",
                "title": "Quick Sort explained",
                "snippet": "sorting algorithm walkthrough",
                "url": "https://www.youtube.com/watch?v=BBBBBBBBBBB",
            },
            {
                "type": "video",
                "title": "Advanced Guitar Solo",
                "snippet": "music theory",
                "url": "https://www.youtube.com/watch?v=CCCCCCCCCCC",
            },
        ]
        mock_eval.side_effect = RuntimeError("llm failed")
        out = filter_media_resources_with_llm(
            llm=None,
            resources=resources,
            session_title="Sorting Algorithms",
            knowledge_point_names=["Quick Sort"],
        )
        assert len(out) == 1
        assert "Quick Sort" in out[0]["title"]


# ---------------------------------------------------------------------------
# TestPrepareMarkdownDocumentWithMedia
# ---------------------------------------------------------------------------

class TestPrepareMarkdownDocumentWithMedia:

    def _import(self):
        from modules.content_generator.agents.learning_document_integrator import prepare_markdown_document
        return prepare_markdown_document

    def _make_doc_structure(self):
        return {"title": "My Doc", "overview": "An overview.", "summary": "A summary."}

    def test_no_media_unchanged(self):
        prepare_markdown_document = self._import()
        doc = prepare_markdown_document(self._make_doc_structure(), [], [], media_resources=None)
        assert "Supplementary Learning Resources" not in doc
        assert "Visual Learning Resources" not in doc

    def test_video_injected_inline(self):
        prepare_markdown_document = self._import()
        kps = [{"name": "Python Basics", "role": "foundational", "solo_level": "beginner"}]
        drafts = [{"title": "Variables", "content": "Intro content."}]
        media = [{
            "type": "video",
            "title": "Python Tutorial",
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "video_id": "dQw4w9WgXcQ",
            "thumbnail_url": "https://img.youtube.com/vi/dQw4w9WgXcQ/mqdefault.jpg",
            "target_section_index": 0,
        }]
        doc = prepare_markdown_document(self._make_doc_structure(), kps, drafts, media_resources=media)
        assert "## Variables" in doc
        assert "#### 🎬 Python Tutorial" in doc
        assert "youtube.com" in doc
        assert "Supplementary Learning Resources" not in doc

    def test_video_prefers_display_title_and_short_description(self):
        prepare_markdown_document = self._import()
        kps = [{"name": "Python Basics", "role": "foundational", "solo_level": "beginner"}]
        drafts = [{"title": "Variables", "content": "Intro content."}]
        media = [{
            "type": "video",
            "title": "Long Source Video Title - YouTube",
            "display_title": "Variables Explained",
            "short_description": "Concise walkthrough of variable declaration and reassignment behavior.",
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "video_id": "dQw4w9WgXcQ",
            "thumbnail_url": "https://img.youtube.com/vi/dQw4w9WgXcQ/mqdefault.jpg",
            "target_section_index": 0,
        }]
        doc = prepare_markdown_document(self._make_doc_structure(), kps, drafts, media_resources=media)
        assert "#### 🎬 Variables Explained" in doc
        assert "Concise walkthrough of variable declaration" in doc
        assert "Long Source Video Title - YouTube" not in doc

    def test_image_injected_inline(self):
        prepare_markdown_document = self._import()
        kps = [{"name": "Python Basics", "role": "foundational", "solo_level": "beginner"}]
        drafts = [{"title": "Variables", "content": "Intro content."}]
        media = [{
            "type": "image",
            "title": "Python (programming language)",
            "url": "https://en.wikipedia.org/wiki/Python_(programming_language)",
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c3/Python-logo-notext.svg/121px-Python-logo-notext.svg.png",
            "description": "High-level programming language",
            "target_section_index": 0,
        }]
        doc = prepare_markdown_document(self._make_doc_structure(), kps, drafts, media_resources=media)
        assert "#### 🖼️ Python (programming language)" in doc
        assert "wikimedia" in doc or "wikipedia" in doc

    def test_mixed_media_and_narrative_inline(self):
        prepare_markdown_document = self._import()
        kps = [{"name": "Python Basics", "role": "foundational", "solo_level": "beginner"}]
        drafts = [{"title": "Variables", "content": "Intro content."}]
        media = [
            {
                "type": "video",
                "title": "Tutorial",
                "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "video_id": "dQw4w9WgXcQ",
                "thumbnail_url": "https://img.youtube.com/vi/dQw4w9WgXcQ/mqdefault.jpg",
                "target_section_index": 0,
            },
            {
                "type": "image",
                "title": "Python Wiki",
                "url": "https://en.wikipedia.org/wiki/Python",
                "image_url": "https://upload.wikimedia.org/img.png",
                "description": "Python language",
                "target_section_index": 0,
            },
        ]
        narratives = [
            {
                "type": "short_story",
                "title": "The Variable Detective",
                "content": "A short story about tracking values.",
                "target_section_index": 0,
            }
        ]
        doc = prepare_markdown_document(
            self._make_doc_structure(),
            kps,
            drafts,
            media_resources=media,
            narrative_resources=narratives,
        )
        assert "#### 📖 Short Story: The Variable Detective" in doc
        assert "youtube.com" in doc
        assert "Supplementary Learning Resources" not in doc

    def test_integrated_content_is_canonical(self):
        prepare_markdown_document = self._import()
        doc = prepare_markdown_document(
            {
                "title": "My Doc",
                "overview": "An overview.",
                "content": "## Applied Example\n\nStart with the case.\n\n## Core Theory\n\nExplain the principle.",
                "summary": "A summary.",
            },
            [
                {"name": "Theory", "role": "foundational", "solo_level": "beginner"},
                {"name": "Example", "role": "practical", "solo_level": "intermediate"},
            ],
            [
                {"title": "Theory", "content": "Foundational body."},
                {"title": "Example", "content": "Practical body."},
            ],
            media_resources=None,
        )
        assert "## Applied Example" in doc
        assert "## Core Theory" in doc
        assert doc.index("## Applied Example") < doc.index("## Core Theory")
        assert "## Foundational Concepts" not in doc

    def test_content_without_h2_falls_back_to_sequential_sections(self):
        prepare_markdown_document = self._import()
        doc = prepare_markdown_document(
            {
                "title": "My Doc",
                "overview": "An overview.",
                "content": "Integrated body without explicit section headings.",
                "summary": "A summary.",
            },
            [{"name": "Python Basics", "role": "foundational", "solo_level": "beginner"}],
            [{"title": "Variables", "content": "Intro content."}],
            media_resources=None,
        )
        assert "## Variables" in doc
        assert "Integrated body without explicit section headings." not in doc

    def test_empty_content_uses_draft_order_not_legacy_grouping(self):
        prepare_markdown_document = self._import()
        doc = prepare_markdown_document(
            {
                "title": "My Doc",
                "overview": "An overview.",
                "content": "",
                "summary": "A summary.",
            },
            [
                {"name": "Theory", "role": "foundational", "solo_level": "beginner"},
                {"name": "Example", "role": "practical", "solo_level": "intermediate"},
            ],
            [
                {"title": "Applied Example", "content": "Start with the case."},
                {"title": "Core Theory", "content": "Explain the principle."},
            ],
            media_resources=None,
        )
        assert "## Applied Example" in doc
        assert "## Core Theory" in doc
        assert doc.index("## Applied Example") < doc.index("## Core Theory")
        assert "## Foundational Concepts" not in doc
        assert "## Practical Applications" not in doc

    def test_fallback_normalization_enforces_one_h2_per_draft(self):
        prepare_markdown_document = self._import()
        doc = prepare_markdown_document(
            {
                "title": "My Doc",
                "overview": "Overview.",
                "content": (
                    "## Applied Example\n\n"
                    "Use the concept in context.\n\n"
                    "## Extra Scaffold\n\n"
                    "This extra heading should force fallback.\n\n"
                    "## Core Theory\n\n"
                    "Explain principle."
                ),
                "summary": "Summary.",
            },
            [
                {"name": "Applied Example", "role": "practical", "solo_level": "beginner"},
                {"name": "Core Theory", "role": "foundational", "solo_level": "intermediate"},
            ],
            [
                {
                    "title": "Applied Example",
                    "content": (
                        "## Applied Example\n\n"
                        "Start from a concrete case.\n\n"
                        "## Nested Concept\n\n"
                        "Support details."
                    ),
                },
                {
                    "title": "Core Theory",
                    "content": (
                        "## Core Theory\n\n"
                        "Explain the governing rule.\n\n"
                        "## Deeper Principle\n\n"
                        "Additional reasoning."
                    ),
                },
            ],
            media_resources=None,
        )
        assert len(re.findall(r"^##\s+", doc, flags=re.MULTILINE)) >= 3  # includes Summary
        assert len(re.findall(r"^##\s+Applied Example\s*$", doc, flags=re.MULTILINE)) == 1
        assert len(re.findall(r"^##\s+Core Theory\s*$", doc, flags=re.MULTILINE)) == 1
        assert "## Extra Scaffold" not in doc
        assert "### Nested Concept" in doc
        assert "### Deeper Principle" in doc


class TestInlineAssetPlanner:
    def _import(self):
        from modules.content_generator.agents.learning_document_integrator import build_inline_assets_plan
        return build_inline_assets_plan

    def test_keyword_section_match(self):
        build_inline_assets_plan = self._import()
        kps = [
            {"name": "Python Variables", "role": "foundational", "solo_level": "beginner"},
            {"name": "Loops", "role": "practical", "solo_level": "intermediate"},
        ]
        drafts = [
            {"title": "Variables", "content": "Topic A"},
            {"title": "Loops", "content": "Topic B"},
        ]
        media = [{"type": "image", "title": "Loop flowchart", "description": "loop diagram"}]
        plan, stats = build_inline_assets_plan(kps, drafts, media_resources=media, narrative_resources=[])
        assert len(plan) == 1
        assert plan[0]["target_section_index"] == 1
        assert stats["placed_assets"] == 1

    def test_density_rollover(self):
        build_inline_assets_plan = self._import()
        kps = [
            {"name": "A", "role": "foundational", "solo_level": "beginner"},
            {"name": "B", "role": "practical", "solo_level": "intermediate"},
        ]
        drafts = [{"title": "A1", "content": ""}, {"title": "B1", "content": ""}]
        media = [
            {"type": "video", "title": "A clip 1", "target_section_index": 0},
            {"type": "image", "title": "A clip 2", "target_section_index": 0},
            {"type": "audio", "title": "A clip 3", "target_section_index": 0},
        ]
        plan, _ = build_inline_assets_plan(
            kps, drafts, media_resources=media, narrative_resources=[], max_assets_per_subsection=2
        )
        by_section = {}
        for item in plan:
            by_section[item["target_section_index"]] = by_section.get(item["target_section_index"], 0) + 1
        assert by_section.get(0, 0) <= 2
        assert by_section.get(1, 0) >= 1


# ---------------------------------------------------------------------------
# TestContentFormatRouting
# ---------------------------------------------------------------------------

class TestContentFormatRouting:
    """Test the routing logic in create_learning_content_with_llm() using mocks."""

    def _make_profile(self, fslsm_input: float):
        return {
            "learning_preferences": {
                "fslsm_dimensions": {"fslsm_input": fslsm_input}
            }
        }

    def _call(self, fslsm_input, mock_explore, mock_draft, mock_integrate,
              mock_quiz, mock_media, mock_podcast, mock_tts, mock_narrative,
              with_quiz=False):
        from modules.content_generator.orchestrators.content_generation_pipeline import (
            generate_learning_content_with_llm as create_learning_content_with_llm,
        )
        mock_explore.return_value = [{"name": "Topic A", "role": "foundational", "solo_level": "beginner"}]
        mock_draft.return_value = [{"title": "Draft A", "content": "## Draft A\n\nContent A with instructional prose."}]
        mock_integrate.return_value = "## Document\n\nContent here."
        mock_quiz.return_value = {}
        mock_media.return_value = []
        mock_narrative.return_value = []
        mock_podcast.return_value = "## Podcast Document\n\nConverted."

        mock_llm = MagicMock()
        mock_search_rag = MagicMock()
        mock_search_rag.search_runner = MagicMock()

        profile = self._make_profile(fslsm_input)
        with patch(
            "modules.content_generator.orchestrators.content_generation_pipeline.evaluate_knowledge_draft_batch_with_llm",
            return_value={
                "evaluations": [
                    {"draft_id": "draft-0", "is_acceptable": True, "issues": [], "improvement_directives": ""}
                ]
            },
        ), patch(
            "modules.content_generator.orchestrators.content_generation_pipeline.evaluate_integrated_document_with_llm",
            return_value={
                "is_acceptable": True,
                "issues": [],
                "improvement_directives": "",
                "repair_scope": "integrator_only",
                "affected_section_indices": [],
                "severity": "low",
            },
        ):
            return create_learning_content_with_llm(
                mock_llm, profile, {}, {},
                with_quiz=with_quiz,
                search_rag_manager=mock_search_rag,
            )

    @patch("modules.content_generator.orchestrators.content_generation_pipeline.generate_tts_audio")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.convert_to_podcast_with_llm")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.generate_narrative_resources_with_llm")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.find_media_resources")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.generate_document_quizzes_with_llm")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.integrate_learning_document_with_llm")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.draft_knowledge_points_with_llm")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.explore_knowledge_points_with_llm")
    def test_strong_visual(self, mock_explore, mock_draft, mock_integrate,
                           mock_quiz, mock_media, mock_narrative, mock_podcast, mock_tts):
        result = self._call(-0.9, mock_explore, mock_draft, mock_integrate,
                            mock_quiz, mock_media, mock_podcast, mock_tts, mock_narrative)
        assert result["content_format"] == "visual_enhanced"
        assert "audio_url" not in result

    @patch("modules.content_generator.orchestrators.content_generation_pipeline.generate_tts_audio")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.convert_to_podcast_with_llm")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.generate_narrative_resources_with_llm")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.find_media_resources")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.generate_document_quizzes_with_llm")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.integrate_learning_document_with_llm")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.draft_knowledge_points_with_llm")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.explore_knowledge_points_with_llm")
    def test_moderate_visual(self, mock_explore, mock_draft, mock_integrate,
                             mock_quiz, mock_media, mock_narrative, mock_podcast, mock_tts):
        result = self._call(-0.5, mock_explore, mock_draft, mock_integrate,
                            mock_quiz, mock_media, mock_podcast, mock_tts, mock_narrative)
        assert result["content_format"] == "visual_enhanced"
        assert "audio_url" not in result

    @patch("modules.content_generator.orchestrators.content_generation_pipeline.generate_tts_audio")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.convert_to_podcast_with_llm")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.generate_narrative_resources_with_llm")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.find_media_resources")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.generate_document_quizzes_with_llm")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.integrate_learning_document_with_llm")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.draft_knowledge_points_with_llm")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.explore_knowledge_points_with_llm")
    def test_standard(self, mock_explore, mock_draft, mock_integrate,
                      mock_quiz, mock_media, mock_narrative, mock_podcast, mock_tts):
        result = self._call(0.0, mock_explore, mock_draft, mock_integrate,
                            mock_quiz, mock_media, mock_podcast, mock_tts, mock_narrative)
        assert result["content_format"] == "standard"
        assert "audio_url" not in result
        mock_podcast.assert_not_called()
        mock_tts.assert_not_called()

    @patch("modules.content_generator.orchestrators.content_generation_pipeline.generate_tts_audio")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.convert_to_podcast_with_llm")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.generate_narrative_resources_with_llm")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.find_media_resources")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.generate_document_quizzes_with_llm")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.integrate_learning_document_with_llm")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.draft_knowledge_points_with_llm")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.explore_knowledge_points_with_llm")
    def test_moderate_audio(self, mock_explore, mock_draft, mock_integrate,
                            mock_quiz, mock_media, mock_narrative, mock_podcast, mock_tts):
        mock_tts.return_value = "/static/audio/host_expert.mp3"
        result = self._call(+0.5, mock_explore, mock_draft, mock_integrate,
                            mock_quiz, mock_media, mock_podcast, mock_tts, mock_narrative)
        assert result["content_format"] == "audio_enhanced"
        assert result["audio_url"] == "/static/audio/host_expert.mp3"
        assert result["audio_mode"] == "narration_optional"
        mock_podcast.assert_not_called()
        mock_tts.assert_called_once_with("## Document\n\nContent here.")

    @patch("modules.content_generator.orchestrators.content_generation_pipeline.generate_tts_audio")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.convert_to_podcast_with_llm")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.generate_narrative_resources_with_llm")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.find_media_resources")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.generate_document_quizzes_with_llm")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.integrate_learning_document_with_llm")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.draft_knowledge_points_with_llm")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.explore_knowledge_points_with_llm")
    def test_strong_audio(self, mock_explore, mock_draft, mock_integrate,
                          mock_quiz, mock_media, mock_narrative, mock_podcast, mock_tts):
        mock_tts.return_value = "/static/audio/abc123.mp3"
        result = self._call(+0.9, mock_explore, mock_draft, mock_integrate,
                            mock_quiz, mock_media, mock_podcast, mock_tts, mock_narrative)
        assert result["content_format"] == "audio_enhanced"
        assert "audio_url" in result
        assert result["audio_url"] == "/static/audio/abc123.mp3"
        assert result["audio_mode"] == "host_expert_optional"
        mock_podcast.assert_called_once()
        mock_tts.assert_called_once_with("## Podcast Document\n\nConverted.")

    @patch("modules.content_generator.orchestrators.content_generation_pipeline.generate_tts_audio")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.convert_to_podcast_with_llm")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.generate_narrative_resources_with_llm")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.find_media_resources")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.generate_document_quizzes_with_llm")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.integrate_learning_document_with_llm")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.draft_knowledge_points_with_llm")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.explore_knowledge_points_with_llm")
    def test_audio_boundary_moderate_threshold(self, mock_explore, mock_draft, mock_integrate,
                                               mock_quiz, mock_media, mock_narrative, mock_podcast, mock_tts):
        mock_tts.return_value = "/static/audio/moderate.mp3"
        result = self._call(+0.3, mock_explore, mock_draft, mock_integrate,
                            mock_quiz, mock_media, mock_podcast, mock_tts, mock_narrative)
        assert result["content_format"] == "audio_enhanced"
        assert result["audio_mode"] == "narration_optional"
        mock_podcast.assert_not_called()
        mock_tts.assert_called_once_with("## Document\n\nContent here.")

    @patch("modules.content_generator.orchestrators.content_generation_pipeline.generate_tts_audio")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.convert_to_podcast_with_llm")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.generate_narrative_resources_with_llm")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.find_media_resources")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.generate_document_quizzes_with_llm")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.integrate_learning_document_with_llm")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.draft_knowledge_points_with_llm")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.explore_knowledge_points_with_llm")
    def test_audio_boundary_strong_threshold(self, mock_explore, mock_draft, mock_integrate,
                                             mock_quiz, mock_media, mock_narrative, mock_podcast, mock_tts):
        mock_tts.return_value = "/static/audio/strong.mp3"
        result = self._call(+0.7, mock_explore, mock_draft, mock_integrate,
                            mock_quiz, mock_media, mock_podcast, mock_tts, mock_narrative)
        assert result["content_format"] == "audio_enhanced"
        assert result["audio_mode"] == "host_expert_optional"
        mock_podcast.assert_called_once()
        mock_tts.assert_called_once_with("## Podcast Document\n\nConverted.")

    @patch("modules.content_generator.orchestrators.content_generation_pipeline.generate_tts_audio")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.convert_to_podcast_with_llm")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.generate_narrative_resources_with_llm")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.find_media_resources")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.generate_document_quizzes_with_llm")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.integrate_learning_document_with_llm")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.draft_knowledge_points_with_llm")
    @patch("modules.content_generator.orchestrators.content_generation_pipeline.explore_knowledge_points_with_llm")
    def test_tts_failure_no_crash(self, mock_explore, mock_draft, mock_integrate,
                                  mock_quiz, mock_media, mock_narrative, mock_podcast, mock_tts):
        mock_tts.side_effect = RuntimeError("TTS service unavailable")
        result = self._call(+0.9, mock_explore, mock_draft, mock_integrate,
                            mock_quiz, mock_media, mock_podcast, mock_tts, mock_narrative)
        assert result["content_format"] == "audio_enhanced"
        assert "document" in result
        assert "audio_url" not in result
