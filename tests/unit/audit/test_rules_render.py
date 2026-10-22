from sitecrawler.audit.rules.render import Differs, Failed
from sitecrawler.models import RenderDiff
from tests.unit.audit.helpers import flagged, page

CHANGED = RenderDiff(
    raw_title="Raw", rendered_title="Rendered", links_added=("https://site.test/x",)
)
SAME = RenderDiff(raw_title="Same", rendered_title="Same")


def test_differs_only_on_rendered_pages_with_changes() -> None:
    hits = flagged(
        Differs(),
        [
            page("/changed", render=CHANGED),
            page("/same", render=SAME),
            page("/not-rendered"),
            page("/failed", render_error="render timed out"),
            page("/gone", 404, render=CHANGED),
        ],
    )
    assert set(hits) == {"/changed"}
    assert hits["/changed"].message == "title, links +1"


def test_failed_only_on_pages_with_a_render_error() -> None:
    hits = flagged(
        Failed(),
        [
            page("/failed", render_error="render timed out after 30s waiting for networkidle"),
            page("/ok", render=SAME),
            page("/not-rendered"),
            page("/gone", 404, render_error="boom"),
        ],
    )
    assert set(hits) == {"/failed"}
    assert hits["/failed"].message == "render timed out after 30s waiting for networkidle"
