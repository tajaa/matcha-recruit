"""Titles and employer names: the words that say two postings are the same job."""
from app.matcha.services.matcha_work.job_search import normalize


def test_same_title_in_either_order():
    """Whichever side adds a little (a city, a team) may come first: a lead's
    title is compared to a board's and a board's to a lead's."""
    assert normalize.same_title("COO - Austin, TX", "Chief Operating Officer")
    assert normalize.same_title("Chief Operating Officer", "COO - Austin, TX")
    assert normalize.same_title("VP of Ops", "Vice President, Operations")
    assert not normalize.same_title("Operations Associate / Head of Operations", "Founding COO / Head of Operations")
    assert not normalize.same_title("Chief Operating Officer", "Chief of Staff")
    assert not normalize.same_title("", "COO")


def test_related_title_shares_a_work_word_not_a_level_word():
    assert normalize.related_title("Director of Operations", ["Chief Operating Officer"])
    assert normalize.related_title("HR Business Partner", ["Head of HR"])
    assert normalize.related_title("Head of People", ["Head of HR"])  # people is human resources
    assert normalize.related_title("VP, People & Culture", ["CHRO"])
    assert normalize.related_title("Nurse Manager", ["Director of Nursing"])
    assert normalize.related_title("Marketing Manager", ["Head of Market Research"])
    assert not normalize.related_title("Software Engineer", ["Chief People Officer"])
    # A five-letter stem took these for the same work.
    assert not normalize.related_title("Forklift Operator", ["COO"])
    assert not normalize.related_title("Peoplesoft Developer", ["Chief People Officer"])
    assert not normalize.related_title("Producer", ["CPO"])
    assert normalize.related_title("anything", [])


def test_a_title_of_level_words_alone_needs_the_whole_title():
    """CEO, President, General Manager have no work word: a shared level word
    is not a related job, the whole title is."""
    for other in ("Account Executive", "Police Officer", "Loan Officer", "Executive Chef"):
        assert not normalize.related_title(other, ["CEO"]), other
    assert normalize.related_title("Chief Executive Officer, North America", ["CEO"])
    assert not normalize.related_title("Store Manager", ["General Manager"])
    assert normalize.related_title("General Manager - Austin", ["General Manager"])
    assert not normalize.related_title("Vice President of Sales", ["President"])


def test_title_covers():
    assert normalize.title_covers("Senior Solutions Architect, AI", "Solutions Architect")
    assert normalize.title_covers("Engineering Manager", "Engineering Manager")
    assert not normalize.title_covers("Software Engineer", "Engineering Manager")
    assert not normalize.title_covers("Anything", "")


def test_same_employer_by_whole_names_not_one_word():
    # A board token: the whole name, its first words, or the distinctive name inside it.
    assert normalize.same_employer("Delta Dental of California", "deltadental") is True
    assert normalize.same_employer("Delta Dental of California", "delta") is False  # Delta Air Lines' board
    assert normalize.same_employer("Meta", "metabase") is False
    assert normalize.same_employer("Ro", "robinhood") is False
    assert normalize.same_employer("IBM", "ibmix") is False
    assert normalize.same_employer("Home Depot", "homeinstead") is False
    assert normalize.same_employer("Backpack Healthcare", "hellobackpack") is True
    assert normalize.same_employer("Stripe, Inc.", "stripe") is True
    # A name in words (a page's hiring organization): one side's distinctive words are the other's.
    assert normalize.same_employer("Delta Dental of California", "Delta Air Lines") is False
    assert normalize.same_employer("Beth Israel Lahey Health", "Lahey Health") is True
    assert normalize.same_employer("Meta", "Meta Platforms, Inc.") is True
    assert normalize.same_employer("Ro", "Ro Health") is True
    assert normalize.same_employer("Flex", "Headway") is False
    assert normalize.same_employer("Stealth Startup", "Acme") is None
