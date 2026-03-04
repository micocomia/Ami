import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_parser_keeps_h2_order_with_repeated_heading_text():
    from utils.document_parser import parse_document_for_section_view

    document = """# Demo

## First Topic
This paragraph mentions First Topic again but should not create a new section.

## Second Topic
This paragraph mentions Second Topic and keeps ordering stable.
"""
    parsed = parse_document_for_section_view(document)
    sections = parsed["section_documents"]
    assert len(sections) == 2
    assert sections[0].startswith("## First Topic")
    assert sections[1].startswith("## Second Topic")


def test_parser_ignores_h2_inside_code_fences():
    from utils.document_parser import parse_document_for_section_view

    document = """# Demo

## First Topic
Intro.

```python
## Not a real heading
print("hello")
```

## Second Topic
Body.
"""
    parsed = parse_document_for_section_view(document)
    assert len(parsed["section_documents"]) == 2
    assert parsed["section_documents"][0].startswith("## First Topic")
    assert parsed["section_documents"][1].startswith("## Second Topic")


def test_sidebar_order_follows_markdown_heading_order():
    from utils.document_parser import parse_document_for_section_view

    document = """# Demo

## Alpha
### Alpha Detail
Body.

## Beta
### Beta Detail
Body.
"""
    parsed = parse_document_for_section_view(document)
    sidebar = parsed["sidebar_items"]
    assert [item["title"] for item in sidebar] == [
        "1. Alpha",
        "1.1. Alpha Detail",
        "2. Beta",
        "2.1. Beta Detail",
    ]
