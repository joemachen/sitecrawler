"""Compare what the parser saw in the raw HTML with what it sees after JavaScript ran."""

from __future__ import annotations

from sitecrawler.models import ParsedPage, RenderDiff


def diff_rendered(raw: ParsedPage, rendered: ParsedPage) -> RenderDiff:
    """Describe how ``rendered`` differs from ``raw``.

    Links are compared as sets of absolute hrefs, so a link that merely moved
    on the page is not a change. Word counts are reported but never counted
    as a change: almost every script adds or removes a few words.
    """
    raw_links = list(dict.fromkeys(raw.links))  # distinct, first-seen order
    rendered_links = list(dict.fromkeys(rendered.links))
    raw_set = set(raw_links)
    rendered_set = set(rendered_links)
    return RenderDiff(
        raw_title=raw.title,
        rendered_title=rendered.title,
        raw_meta_description=raw.meta_description,
        rendered_meta_description=rendered.meta_description,
        raw_meta_robots=raw.meta_robots,
        rendered_meta_robots=rendered.meta_robots,
        raw_canonical=raw.canonical,
        rendered_canonical=rendered.canonical,
        raw_h1=raw.h1,
        rendered_h1=rendered.h1,
        raw_word_count=raw.word_count,
        rendered_word_count=rendered.word_count,
        raw_link_count=len(raw_links),
        rendered_link_count=len(rendered_links),
        links_added=tuple(link for link in rendered_links if link not in raw_set),
        links_removed=tuple(link for link in raw_links if link not in rendered_set),
    )
