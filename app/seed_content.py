"""Seed the CMS tables with the site's current content.

    python -m app.seed_content

Idempotent: it skips any table that already has rows, so running it twice will
not duplicate anything or overwrite edits made in the admin panel.
"""

from __future__ import annotations

from uuid import uuid4

from app.bootstrap import ensure_schema
from app.database import SessionLocal, engine
from app.models import (
    Astrologer,
    Base,
    HeroSlide,
    NavItem,
    ServiceCard,
    SiteText,
    ZodiacOverride,
)
from app.zodiac_seed_data import ZODIAC_COPY

ASTROLOGERS = [
    ("Astro Rajneesh", "Hindi, English, Punjabi", "Vedic, Numerology, Tarot, Vastu, KP, Prashna", 4.0, 5, 2045, 6, True, True),
    ("Astro Uttam", "Hindi, English", "Vedic, Numerology, Vastu, KP, Prashna", 4.0, 5, 2965, 10, True, True),
    ("Astro Vasudha", "Hindi, English", "Vedic, Numerology, Tarot, Vastu, KP, Prashna", 5.0, 4, 1452, 12, True, True),
    ("Astro Meera", "Hindi, Marathi, English", "Vedic, Lal Kitab, Prashna, Muhurat", 4.5, 9, 5310, 15, False, True),
    ("Astro Kartik", "Hindi, English, Bengali", "KP, Vedic, Vastu, Numerology", 4.2, 7, 3188, 9, False, False),
    ("Astro Sharada", "Hindi, Telugu, English", "Vedic, Tarot, Numerology, Muhurat, Prashna", 4.8, 12, 7642, 20, True, True),
]

SERVICES = [
    ("Generate Kundali", "Create an accurate North India birth chart using resolved coordinates and timezone.", "Open Generator", "/generate"),
    ("Match-Making", "A future space for compatibility, guna milan, and marriage guidance.", "Coming Soon", ""),
    ("Horoscope", "Daily, weekly, and monthly horoscope pages can be added here.", "Coming Soon", ""),
    ("Astrology", "Build detailed astrology learning, predictions, and consultation pages.", "Coming Soon", ""),
    ("Occult", "A dedicated section for numerology, tarot, and occult topics later.", "Coming Soon", ""),
    ("Lal Kitab", "Remedial astrology with its own house rules, debts, and practical upaya.", "Coming Soon", ""),
    ("Western Astrology", "Tropical charts, aspects, and western-style interpretation alongside Vedic.", "Coming Soon", ""),
    ("Panchang", "Daily tithi, nakshatra, yoga, karana, and muhurat for choosing the right moment.", "Coming Soon", ""),
]

HERO_SLIDES = [
    ("Birth Chart", "North India style kundali with precise ascendant and planetary details."),
    ("Match-Making", "Prepare for compatibility tools, guna matching, and relationship insights."),
    ("Daily Horoscope", "A dedicated horoscope experience will be connected from this homepage."),
    ("Lal Kitab", "Future remedial astrology pages can plug into this navigation."),
    ("Western Astrology", "Reserve space for tropical charts and western-style interpretations."),
]

NAV_ITEMS = [
    ("Home", "home", "", False),
    ("Generate Kundali", "generate", "", True),
    ("Match-Making", "coming-soon", "Match-Making", False),
    ("Horoscope", "coming-soon", "Horoscope", False),
    ("Astrology", "coming-soon", "Astrology", False),
    ("Occult", "coming-soon", "Occult", False),
    ("Lal Kitab", "coming-soon", "Lal Kitab", False),
    ("Western Astrology", "coming-soon", "Western Astrology", False),
    ("Astronomy", "coming-soon", "Astronomy", False),
    ("Muhurt", "coming-soon", "Muhurt", False),
    ("Panchang", "coming-soon", "Panchang", False),
    ("Others", "coming-soon", "Others", False),
    ("Contact Us", "coming-soon", "Contact Us", False),
]

# label -> children. Seeded as nav rows with parent_label set, so they are
# editable in the admin panel exactly like the top-level items.
NAV_SUBMENUS = {
    "Astronomy": ["Solar Eclipse", "Lunar Eclipse", "Vernal Equinox", "Summer Solstice",
                  "Autumnal Equinox", "Winter Solstice"],
    "Muhurt": ["Marriage Dates", "Griha Pravesh", "Buying Car", "Property Purchase",
               "Full Moon Dates", "New Moon Dates", "Planetary Positions",
               "Graha Asta & Uday", "Graha Vakri & Margi", "Graha Gochara"],
    "Panchang": ["Panchak", "Ganda Moola", "Bhadra Vichar", "Rahu Kalam", "Nakshatra",
                 "Abhijit Nakshatra"],
    "Others": ["Auspicious Yog", "Vrat", "Festivals", "Gallery", "FAQ", "Hora",
               "Chaughadiya", "Buy Now"],
}

TEXTS = [
    ("home.hero.eyebrow", "Home hero - eyebrow", "Kundali Generator"),
    ("home.hero.heading", "Home hero - heading", "Generate a precise North India birth chart."),
    ("home.hero.copy", "Home hero - supporting copy", "Global place detection, editable coordinates, 12-hour birth time input, and Swiss Ephemeris-backed kundali calculations."),
    ("home.services.eyebrow", "Services - eyebrow", "Our Services"),
    ("home.services.heading", "Services - heading", "Explore astrology services"),
    ("home.astrologers.eyebrow", "Astrologers - eyebrow", "Our Astrologers"),
    ("home.astrologers.heading", "Astrologers - heading", "Meet our astrologers"),
    ("home.horoscope.eyebrow", "Horoscope - eyebrow", "Know Your Horoscope"),
    ("home.horoscope.heading", "Horoscope - heading", "Choose your zodiac sign"),
]


def _sync_submenu(db, parent: str, children: list[str]) -> list[str]:
    """Add any declared dropdown entry the database is missing, and return the
    labels added.

    Nothing happens when they are all present, so this is safe to re-run: a
    dropdown reordered or relabelled in the admin panel is left alone. When
    there is something new, the whole dropdown is renumbered into the declared
    order, which is the only way to slot an entry into the middle of one.
    """
    existing = {
        row.label: row
        for row in db.query(NavItem).filter(NavItem.parent_label == parent)
    }
    missing = [child for child in children if child not in existing]
    if not missing:
        return []

    # One position block per parent, clear of the top-level items.
    base = len(NAV_ITEMS) + 100 + 100 * list(NAV_SUBMENUS).index(parent)
    for offset, child in enumerate(children):
        row = existing.get(child)
        if row is None:
            db.add(NavItem(
                id=uuid4().hex, position=base + offset, label=child,
                page="coming-soon", coming_soon_title=child, parent_label=parent,
            ))
        else:
            # Keeps its id and any admin edits; only the position moves.
            row.position = base + offset
    return missing


def main() -> int:
    Base.metadata.create_all(bind=engine)
    ensure_schema(engine)
    db = SessionLocal()
    added: list[str] = []
    try:
        if db.query(Astrologer).count() == 0:
            for i, (name, langs, skills, rating, years, orders, price, trending, online) in enumerate(ASTROLOGERS):
                db.add(Astrologer(
                    id=uuid4().hex, position=i, name=name, languages=langs, skills=skills,
                    rating=rating, experience_years=years, orders=orders, price_per_minute=price,
                    trending=trending, online=online,
                ))
            added.append(f"{len(ASTROLOGERS)} astrologers")

        if db.query(ServiceCard).count() == 0:
            for i, (title, text, label, route) in enumerate(SERVICES):
                db.add(ServiceCard(
                    id=uuid4().hex, position=i, title=title, text=text,
                    action_label=label, target_route=route,
                ))
            added.append(f"{len(SERVICES)} service cards")

        if db.query(HeroSlide).count() == 0:
            for i, (title, text) in enumerate(HERO_SLIDES):
                db.add(HeroSlide(id=uuid4().hex, position=i, title=title, text=text))
            added.append(f"{len(HERO_SLIDES)} hero slides")

        if db.query(NavItem).count() == 0:
            for i, (label, page, title, auth) in enumerate(NAV_ITEMS):
                db.add(NavItem(
                    id=uuid4().hex, position=i, label=label, page=page,
                    coming_soon_title=title, requires_auth=auth,
                ))
            added.append(f"{len(NAV_ITEMS)} nav items")

        # Sub-items are topped up on every run, so a newly declared dropdown
        # entry reaches an existing database without a hand-written insert.
        for parent, children in NAV_SUBMENUS.items():
            fresh = _sync_submenu(db, parent, children)
            if fresh:
                added.append(f"{parent} sub-items: {', '.join(fresh)}")

        if db.query(SiteText).count() == 0:
            for i, (key, label, value) in enumerate(TEXTS):
                db.add(SiteText(id=uuid4().hex, position=i, key=key, label=label, value=value))
            added.append(f"{len(TEXTS)} text entries")

        if db.query(ZodiacOverride).count() == 0:
            for i, copy in enumerate(ZODIAC_COPY):
                db.add(ZodiacOverride(id=uuid4().hex, position=i, **copy))
            added.append(f"{len(ZODIAC_COPY)} zodiac entries")

        db.commit()
    finally:
        db.close()

    print("Seeded: " + (", ".join(added) if added else "nothing, tables already had rows"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
