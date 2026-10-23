"""Google rich-result requirements per schema.org type (ADR-0013).

Hand-kept from Google Search Central's structured data pages (checked
2026-10-22); each entry names its page. A *need* is satisfied when any one
of its paths is present; a dotted path must be present on every node the
earlier segments reach, so ``offers.price`` wants a price on every offer. A
need with ``when`` is only checked when that path is present, which is how
nested types (an Offer, an AggregateRating) get their own requirements
without making them compulsory.

FAQPage is not here: Google stopped showing FAQ rich results on 2026-05-07.
Organization's recommended list is a subset of Google's (which runs to thirty
identifiers such as ``duns`` and ``leiCode``) so that a plain company page is
not drowned in suggestions.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class Need:
    """Properties of which at least one must be present."""

    paths: tuple[str, ...]
    when: str = ""
    """Only checked when this path is present; empty means always."""

    @property
    def label(self) -> str:
        """``offers.price`` or ``offers.price or offers.lowPrice``."""
        return " or ".join(self.paths)


def _needs(*specs: str | tuple[str, ...], when: str = "") -> tuple[Need, ...]:
    return tuple(Need(s if isinstance(s, tuple) else (s,), when) for s in specs)


@dataclass(slots=True, frozen=True)
class RichResult:
    """What Google requires and recommends for one rich-result type."""

    type: str
    required: tuple[Need, ...]
    recommended: tuple[Need, ...]
    docs: str
    """The Google Search Central page the lists come from."""


_DOCS = "https://developers.google.com/search/docs/appearance/structured-data/"

_RATING_REQUIRED = (
    *_needs("aggregateRating.ratingValue", when="aggregateRating"),
    *_needs(("aggregateRating.ratingCount", "aggregateRating.reviewCount"), when="aggregateRating"),
    *_needs("review.author", "review.reviewRating.ratingValue", when="review"),
)
"""Review snippet requirements for a nested ``aggregateRating`` or ``review``."""

RICH_RESULTS: dict[str, RichResult] = {
    r.type: r
    for r in (
        RichResult(
            "Product",
            required=(
                *_needs("name", ("offers", "review", "aggregateRating")),
                *_needs(
                    ("offers.price", "offers.priceSpecification.price", "offers.lowPrice"),
                    when="offers",
                ),
                *_RATING_REQUIRED,
            ),
            recommended=(
                *_needs("aggregateRating", "review"),
                *_needs(
                    "offers.availability",
                    ("offers.priceCurrency", "offers.priceSpecification.priceCurrency"),
                    when="offers",
                ),
            ),
            docs=_DOCS + "product-snippet",
        ),
        RichResult(
            "Article",
            required=(),
            recommended=(
                *_needs("headline", "image", "datePublished", "dateModified", "author"),
                *_needs("author.name", ("author.url", "author.sameAs"), when="author"),
            ),
            docs=_DOCS + "article",
        ),
        RichResult(
            "BreadcrumbList",
            required=(
                *_needs("itemListElement"),
                *_needs(
                    "itemListElement.position",
                    ("itemListElement.name", "itemListElement.item.name"),
                    when="itemListElement",
                ),
            ),
            recommended=(),
            docs=_DOCS + "breadcrumb",
        ),
        RichResult(
            "Organization",
            required=(),
            recommended=_needs(
                "name",
                "url",
                "logo",
                "description",
                "sameAs",
                "address",
                ("contactPoint", "telephone", "email"),
            ),
            docs=_DOCS + "organization",
        ),
        RichResult(
            "LocalBusiness",
            required=(*_needs("name", "address"), *_RATING_REQUIRED),
            recommended=(
                *_needs("telephone", "url", "geo", "openingHoursSpecification", "priceRange"),
                *_needs("geo.latitude", "geo.longitude", when="geo"),
            ),
            docs=_DOCS + "local-business",
        ),
        RichResult(
            "Recipe",
            required=(*_needs("name", "image"), *_RATING_REQUIRED),
            recommended=_needs(
                "aggregateRating",
                "author",
                "cookTime",
                "datePublished",
                "description",
                "keywords",
                "nutrition.calories",
                "prepTime",
                "recipeCategory",
                "recipeCuisine",
                "recipeIngredient",
                "recipeInstructions",
                "recipeYield",
                "totalTime",
                "video",
            ),
            docs=_DOCS + "recipe",
        ),
        RichResult(
            "Event",
            required=(
                *_needs("name", "startDate", "location"),
                *_needs(("location.address", "location.url"), when="location"),
            ),
            recommended=(
                *_needs(
                    "description",
                    "endDate",
                    "eventStatus",
                    "image",
                    "offers",
                    "organizer",
                    "performer",
                ),
                *_needs("location.name", when="location"),
                *_needs(
                    "offers.price",
                    "offers.priceCurrency",
                    "offers.availability",
                    "offers.url",
                    "offers.validFrom",
                    when="offers",
                ),
                *_needs("organizer.name", "organizer.url", when="organizer"),
                *_needs("performer.name", when="performer"),
            ),
            docs=_DOCS + "event",
        ),
        RichResult(
            "VideoObject",
            required=_needs("name", "thumbnailUrl", "uploadDate"),
            recommended=_needs(("contentUrl", "embedUrl"), "description", "duration"),
            docs=_DOCS + "video",
        ),
    )
}
"""Rich-result types by schema.org name; subtypes use their nearest listed ancestor."""
