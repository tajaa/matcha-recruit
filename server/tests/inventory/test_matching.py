from app.matcha.services.inventory.matching import best_match, normalize_name


def _row(name):
    return {"id": name, "name": name, "normalized_name": normalize_name(name)}


def test_normalize_case_and_punctuation():
    assert normalize_name("Cherry Farms Cookies!") == normalize_name("cherry farms cookies")


def test_normalize_pluralize():
    assert normalize_name("salads") == normalize_name("salad")


def test_exact_match():
    existing = [_row("Cherry Farms Cookies")]
    assert best_match("cherry farms cookies", existing)["name"] == "Cherry Farms Cookies"


def test_containment_match():
    existing = [_row("Cherry Farms Cookies")]
    assert best_match("cookies", existing)["name"] == "Cherry Farms Cookies"


def test_typo_fuzzy_match():
    existing = [_row("Cherry Farms Cookies")]
    assert best_match("cheery farms cookies", existing)["name"] == "Cherry Farms Cookies"


def test_no_match_returns_none():
    existing = [_row("Cherry Farms Cookies")]
    assert best_match("napkins", existing) is None


def test_empty_existing_returns_none():
    assert best_match("anything", []) is None
