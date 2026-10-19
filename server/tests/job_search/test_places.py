"""Whether a job is in a place the person named: the Census gazetteer, read offline."""
import pytest

from app.matcha.services.matcha_work.job_search import places

SOCAL_NY = {"locations": ["San Diego, CA", "Orange County, CA", "Los Angeles, CA", "San Francisco, CA",
                          "New York, NY"], "remote": "any"}


def keep(location, criteria, remote=None):
    return places.judge(location, remote, criteria)


@pytest.mark.parametrize("location", [
    "Irvine, CA", "Costa Mesa, California", "El Segundo, CA and/or Burbank", "NYC HQ", "Jersey City, NJ",
    "Oakland, CA", "San Jose, CA", "Palo Alto, CA", "Stamford, CT", "Brooklyn, NY", "Hybrid (San Diego, CA)",
    "US-CA-Irvine", "Greater Los Angeles Area", "Seattle, WA; Los Angeles, CA", "Carlsbad, CA 92008",
    "San Francisco Bay Area",
])
def test_kept_near_a_place_they_named(location):
    assert keep(location, SOCAL_NY).keep, location


@pytest.mark.parametrize(("location", "why"), [
    ("Seattle, WA", "mi from"), ("Austin, TX", "mi from"), ("Sacramento, CA", "mi from"),
    ("Toronto, Ontario, Canada", "outside the US"), ("London, United Kingdom", "outside the US"),
    ("", "no location"), ("Somewhere Made Up, ZZ", "location not placed"),
])
def test_dropped_elsewhere(location, why):
    verdict = keep(location, SOCAL_NY)
    assert not verdict.keep and why in verdict.why, (location, verdict)


def test_distance_is_measured_from_the_nearest_place_named():
    assert keep("Costa Mesa, CA", SOCAL_NY).why == "8 mi from Orange County, CA"
    assert not keep("Sacramento, CA", SOCAL_NY).keep  # 75 miles from San Francisco
    assert 45 < places.miles(places.target("San Jose, CA").points[0], places.target("San Francisco, CA").points[0]) < 50


def test_remote_jobs():
    assert keep("Remote", SOCAL_NY).keep
    assert keep("United States", SOCAL_NY, remote=True).keep
    assert not keep("Remote - Canada", SOCAL_NY).keep
    assert not keep("Remote", {**SOCAL_NY, "remote": "onsite_only"}).keep
    # A remote job abroad, for someone who named a place abroad.
    assert keep("Remote - United Kingdom", {"locations": ["London, UK"]}).keep


def test_no_places_or_only_nationwide_keeps_anything():
    for criteria in ({}, {"locations": []}, {"locations": ["United States", "Remote"]}, {"locations": ["nationwide"]}):
        assert keep("Austin, TX", criteria).keep
    assert places.targets({"locations": ["Remote", "USA", 7, None]}) == []


def test_a_named_state_or_region():
    texas = {"locations": ["Texas"]}
    assert keep("Dallas, TX", texas).keep and keep("Houston", texas).keep
    assert not keep("Denver, CO", texas).keep
    assert keep("Palo Alto, CA", {"locations": ["Bay Area"]}).keep
    assert keep("Boston, MA", {"locations": ["New England"]}).keep
    # New York and Washington alone are the cities, not the states.
    assert not keep("Buffalo, NY", {"locations": ["New York"]}).keep
    assert keep("Arlington, VA", {"locations": ["Washington"]}).keep


def test_a_place_abroad_is_matched_by_name():
    london = {"locations": ["London"]}
    assert keep("London, England", london).keep
    assert not keep("Manchester, UK", london).keep
    assert not keep("London, KY", SOCAL_NY).keep


def test_how_location_text_is_read():
    assert places.named("Hybrid (San Diego, CA)") == [places.Named("san diego", "CA")]
    assert places.named("Remote - United States") == []
    assert places.named("London, United Kingdom") == [places.Named("london", None, abroad=True, country="united kingdom")]
    assert places.named("Toronto") == [places.Named("toronto", None, abroad=True, country="canada")]
    assert places.named("Salem, OR") == [places.Named("salem", "OR")]  # Oregon, not "salem or"
    assert places.named("Austin TX") == places.named("Denver Colorado")[:0] + [places.Named("austin", "TX")]
    assert places.named("Denver Colorado") == [places.Named("denver", "CO")]
    assert places.named("New York City") == [places.Named("new york city", None)]  # not a "city" state
    assert places.named("Texas") == [places.Named("", "TX")]
    assert places.named("Peru, IN") == [places.Named("peru", "IN")]  # Indiana's, not the country
    assert places.named("US-CA-Irvine") == [places.Named("irvine", "CA")]
    assert [p.name for p in places.named("El Segundo, CA and/or Burbank")] == ["el segundo", "burbank"]
    assert places.place_key("St. Louis") == places.place_key("Saint Louis") == "st louis"
    assert places.place_key("Ft. Worth") == "fort worth"


def test_a_name_without_a_state_is_the_namesake_nearest_their_places():
    la = {"locations": ["Los Angeles, CA"]}
    assert keep("Burbank", la).keep  # Burbank, CA, not Burbank, IL
    assert keep("Burbank", {"locations": ["Chicago, IL"]}).keep
    assert places.target("Springfield").points  # the largest Springfield when nothing anchors it


def test_oregon_is_a_state_not_the_word_or():
    boston = {"locations": ["Boston, MA"]}
    assert not keep("Salem, OR", boston).keep  # not Salem, MA
    assert not keep("Springfield, OR", {"locations": ["Springfield, MA"]}).keep
    assert keep("Portland, OR", {"locations": ["Salem, OR"]}).keep
    assert keep("Portland, OR", {"locations": ["OR"]}).keep and keep("Portland", {"locations": ["Oregon"]}).keep


def test_a_country_alone_keeps_the_jobs_its_postings_place_there():
    canada = {"locations": ["Canada"]}
    assert places.targets(canada)[0].country == "canada"
    assert keep("Toronto, Ontario, Canada", canada).keep and keep("Toronto", canada).keep
    assert keep("Vancouver, BC", canada).keep and keep("Remote - Canada", canada).keep
    assert not keep("Austin, TX", canada).keep and not keep("London, UK", canada).keep
    assert not keep("Remote - United States", canada).keep
    uk = {"locations": ["United Kingdom"]}
    assert keep("London, England", uk).keep and keep("Manchester", uk).keep and not keep("Dublin", uk).keep


def test_a_city_and_state_with_no_comma_and_nationwide_phrases():
    assert keep("Austin, TX", {"locations": ["Austin TX"]}).keep
    assert keep("Round Rock, TX", {"locations": ["Austin TX"]}).keep  # 18 miles: on the map, not by name
    assert keep("Denver, CO", {"locations": ["Denver Colorado"]}).keep
    assert not keep("Dallas, TX", {"locations": ["Austin TX"]}).keep
    for anywhere in ("Anywhere in the US", "US only", "Open to relocation", "Nationally"):
        assert places.targets({"locations": [anywhere]}) == [], anywhere
    assert keep("Chicago, IL", {"locations": ["Midwest"]}).keep  # a region, from its biggest city
    assert not keep("Midwest City, OK", {"locations": ["Midwest"]}).keep


def test_remote_abroad_is_dropped_outside_every_named_country():
    london_austin = {"locations": ["London", "Austin, TX"]}
    assert not keep("Remote - India", london_austin).keep
    assert keep("Remote - US", london_austin).keep and keep("Remote - UK", london_austin).keep
    assert not keep("Remote - US", {"locations": ["London"]}).keep
    assert keep("Remote", {"locations": ["London"]}).keep  # open anywhere, as far as it says
    assert not keep("New York, NY (Hybrid, not remote)", {"locations": ["Denver, CO"]}).keep


def test_the_gazetteer_carries_the_names_people_use():
    for name in ("jersey city", "nashville", "honolulu", "boise", "ventura", "orange county"):
        assert places._index().get(name), name
