"""The site's image slots, and the built-in image each one starts with.

Every slot gets a row in page_images so the admin panel lists it with its
current picture. Rows are only ever added here, never overwritten: once a row
exists, what the admin puts in it stands.

The same pass fills the image of content rows that have none (hero slides,
service cards, astrologers, rashifal) with the built-in picture, so the admin
sees what the site is showing instead of an empty field. That is safe to repeat
on every start: an empty image field already displays the built-in picture, so
filling it in changes what the admin sees, never what a visitor sees.

The paths point into the frontend's public/images folder, and the frontend
keeps the same defaults for when the API is unreachable.
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy.orm import Session

from app.models import Astrologer, HeroSlide, PageImage, Rashifal, ServiceCard

PHOTO = "/images/photos/{}.jpg"
ZODIAC = [
    ("aries", "Mesha"), ("taurus", "Vrishabha"), ("gemini", "Mithuna"), ("cancer", "Karka"),
    ("leo", "Simha"), ("virgo", "Kanya"), ("libra", "Tula"), ("scorpio", "Vrishchika"),
    ("sagittarius", "Dhanu"), ("capricorn", "Makara"), ("aquarius", "Kumbha"), ("pisces", "Meena"),
]

# (key, where it appears, built-in image)
SLOTS: list[tuple[str, str, str]] = [
    ("banner.solar-eclipse", "Solar Eclipse page banner", PHOTO.format("solar-eclipse")),
    ("banner.lunar-eclipse", "Lunar Eclipse page banner", PHOTO.format("lunar-eclipse")),
    ("banner.vernal-equinox", "Vernal Equinox page banner", PHOTO.format("vernal-equinox")),
    ("banner.summer-solstice", "Summer Solstice page banner", PHOTO.format("summer-solstice")),
    ("banner.autumnal-equinox", "Autumnal Equinox page banner", PHOTO.format("autumnal-equinox")),
    ("banner.winter-solstice", "Winter Solstice page banner", PHOTO.format("winter-solstice")),
    ("banner.full-moon-dates", "Purnima (full moon) dates page banner", PHOTO.format("full-moon")),
    ("banner.new-moon-dates", "Amavasya (new moon) dates page banner", PHOTO.format("amavasya-diyas")),
    ("banner.rahu-kalam", "Rahu Kaal page banner", PHOTO.format("samrat-yantra")),
    ("banner.chaughadiya", "Choghadiya page banner", PHOTO.format("samrat-yantra")),
    ("banner.hora", "Hora page banner", PHOTO.format("samrat-yantra")),
    ("banner.muhurta", "Muhurta and Abhijit Muhurta page banner", PHOTO.format("samrat-yantra")),
    ("banner.planetary-positions", "Planetary Positions page banner", PHOTO.format("solar-system")),
    ("banner.graha-vakri-margi", "Planet Retrograde page banner", PHOTO.format("solar-system")),
    ("banner.graha-asta-uday", "Planet Combustion page banner", PHOTO.format("solar-system")),
    ("banner.graha-gochara", "Planet Transit page banner", PHOTO.format("navagraha")),
    ("banner.festivals", "Festivals and Festival Calendar page banner", PHOTO.format("festival-diyas")),
    ("banner.vrat", "Vrat page banner", PHOTO.format("puja-offerings")),
    ("banner.match-making", "Match-Making page banner", PHOTO.format("wedding-fire")),
    ("page.generate", "Kundali generator, beside the heading", PHOTO.format("brihajjataka")),
    ("page.auth", "Login and Signup card", PHOTO.format("night-sky")),
    ("page.coming-soon", "Coming Soon pages", PHOTO.format("night-sky")),
] + [
    (f"zodiac.{slug}", f"{slug.title()} ({sanskrit}) tile on the home page and its rashi page", f"/images/zodiac/{slug}.svg")
    for slug, sanskrit in ZODIAC
]

SERVICE_IMAGES = {
    "Generate Kundali": "kundali", "Match-Making": "match-making", "Horoscope": "horoscope",
    "Astrology": "astrology", "Occult": "occult", "Lal Kitab": "lal-kitab",
    "Western Astrology": "western-astrology", "Panchang": "panchang",
}
HERO_IMAGES = {
    "Birth Chart": "brihajjataka", "Match-Making": "wedding-fire", "Daily Horoscope": "night-sky",
    "Horoscope": "night-sky", "Lal Kitab": "puja-offerings", "Western Astrology": "prague-clock",
}
ASTROLOGER_IMAGES = {
    "Astro Rajneesh": "rajneesh", "Astro Uttam": "uttam", "Astro Vasudha": "vasudha",
    "Astro Meera": "meera", "Astro Kartik": "kartik", "Astro Sharada": "sharada",
}


def sync_defaults(db: Session) -> None:
    existing = {key for (key,) in db.query(PageImage.key)}
    for position, (key, label, url) in enumerate(SLOTS):
        if key not in existing:
            db.add(PageImage(id=uuid4().hex, key=key, label=label, image_url=url, position=position))

    for row in db.query(ServiceCard).filter(ServiceCard.image_url == ""):
        if row.title in SERVICE_IMAGES:
            row.image_url = f"/images/services/{SERVICE_IMAGES[row.title]}.svg"
    for row in db.query(HeroSlide).filter(HeroSlide.image_url == ""):
        if row.title in HERO_IMAGES:
            row.image_url = PHOTO.format(HERO_IMAGES[row.title])
    for row in db.query(Astrologer).filter(Astrologer.avatar_url == ""):
        if row.name in ASTROLOGER_IMAGES:
            row.avatar_url = f"/images/astrologers/{ASTROLOGER_IMAGES[row.name]}.svg"
    by_sanskrit = {sanskrit.lower(): slug for slug, sanskrit in ZODIAC}
    for row in db.query(Rashifal).filter(Rashifal.image_url == ""):
        slug = by_sanskrit.get((row.sign or "").strip().lower())
        if slug:
            row.image_url = f"/images/zodiac/{slug}.svg"
    db.commit()
