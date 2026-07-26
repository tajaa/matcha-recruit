"""NAICS code → industry-title lookup for the OSHA 300A "Industry description".

OSHA Form 300A has a free-text "Industry description (e.g. Manufacture of
motor truck trailers)" field paired with the establishment's NAICS code.
Rather than leave it blank, we derive a human-readable title from the NAICS
code already stored on the company/location.

Granularity: official NAICS **sector (2-digit)** + **subsector (3-digit)**
titles (2022 NAICS). ``naics_industry_description`` does a longest-prefix
match — a 6-digit code resolves to its 3-digit subsector title, falling back
to the 2-digit sector. This is authoritative and compact; full 6-digit
national-industry titles (~1,012 codes) are intentionally not bundled.

Pure module — no DB, no I/O — so it's trivially unit-testable.
"""
from __future__ import annotations

from typing import Optional

# NAICS 2-digit sectors. The official taxonomy uses ranges for three sectors
# (31-33 Manufacturing, 44-45 Retail Trade, 48-49 Transportation); each
# constituent 2-digit prefix is mapped here so a longest-prefix lookup on the
# raw code resolves regardless of which prefix the code starts with.
SECTOR_TITLES: dict[str, str] = {
    "11": "Agriculture, Forestry, Fishing and Hunting",
    "21": "Mining, Quarrying, and Oil and Gas Extraction",
    "22": "Utilities",
    "23": "Construction",
    "31": "Manufacturing",
    "32": "Manufacturing",
    "33": "Manufacturing",
    "42": "Wholesale Trade",
    "44": "Retail Trade",
    "45": "Retail Trade",
    "48": "Transportation and Warehousing",
    "49": "Transportation and Warehousing",
    "51": "Information",
    "52": "Finance and Insurance",
    "53": "Real Estate and Rental and Leasing",
    "54": "Professional, Scientific, and Technical Services",
    "55": "Management of Companies and Enterprises",
    "56": "Administrative and Support and Waste Management and Remediation Services",
    "61": "Educational Services",
    "62": "Health Care and Social Assistance",
    "71": "Arts, Entertainment, and Recreation",
    "72": "Accommodation and Food Services",
    "81": "Other Services (except Public Administration)",
    "92": "Public Administration",
}

# NAICS 3-digit subsectors (2022). More specific than the sector title above.
SUBSECTOR_TITLES: dict[str, str] = {
    # 11 — Agriculture, Forestry, Fishing and Hunting
    "111": "Crop Production",
    "112": "Animal Production and Aquaculture",
    "113": "Forestry and Logging",
    "114": "Fishing, Hunting and Trapping",
    "115": "Support Activities for Agriculture and Forestry",
    # 21 — Mining
    "211": "Oil and Gas Extraction",
    "212": "Mining (except Oil and Gas)",
    "213": "Support Activities for Mining",
    # 22 — Utilities
    "221": "Utilities",
    # 23 — Construction
    "236": "Construction of Buildings",
    "237": "Heavy and Civil Engineering Construction",
    "238": "Specialty Trade Contractors",
    # 31-33 — Manufacturing
    "311": "Food Manufacturing",
    "312": "Beverage and Tobacco Product Manufacturing",
    "313": "Textile Mills",
    "314": "Textile Product Mills",
    "315": "Apparel Manufacturing",
    "316": "Leather and Allied Product Manufacturing",
    "321": "Wood Product Manufacturing",
    "322": "Paper Manufacturing",
    "323": "Printing and Related Support Activities",
    "324": "Petroleum and Coal Products Manufacturing",
    "325": "Chemical Manufacturing",
    "326": "Plastics and Rubber Products Manufacturing",
    "327": "Nonmetallic Mineral Product Manufacturing",
    "331": "Primary Metal Manufacturing",
    "332": "Fabricated Metal Product Manufacturing",
    "333": "Machinery Manufacturing",
    "334": "Computer and Electronic Product Manufacturing",
    "335": "Electrical Equipment, Appliance, and Component Manufacturing",
    "336": "Transportation Equipment Manufacturing",
    "337": "Furniture and Related Product Manufacturing",
    "339": "Miscellaneous Manufacturing",
    # 42 — Wholesale Trade
    "423": "Merchant Wholesalers, Durable Goods",
    "424": "Merchant Wholesalers, Nondurable Goods",
    "425": "Wholesale Trade Agents and Brokers",
    # 44-45 — Retail Trade
    "441": "Motor Vehicle and Parts Dealers",
    "444": "Building Material and Garden Equipment and Supplies Dealers",
    "445": "Food and Beverage Retailers",
    "449": "Furniture, Home Furnishings, Electronics, and Appliance Retailers",
    "455": "General Merchandise Retailers",
    "456": "Health and Personal Care Retailers",
    "457": "Gasoline Stations and Fuel Dealers",
    "458": "Clothing, Clothing Accessories, Shoe, and Jewelry Retailers",
    "459": "Sporting Goods, Hobby, Musical Instrument, Book, and Miscellaneous Retailers",
    # 48-49 — Transportation and Warehousing
    "481": "Air Transportation",
    "482": "Rail Transportation",
    "483": "Water Transportation",
    "484": "Truck Transportation",
    "485": "Transit and Ground Passenger Transportation",
    "486": "Pipeline Transportation",
    "487": "Scenic and Sightseeing Transportation",
    "488": "Support Activities for Transportation",
    "491": "Postal Service",
    "492": "Couriers and Messengers",
    "493": "Warehousing and Storage",
    # 51 — Information
    "513": "Publishing Industries",
    "516": "Broadcasting and Content Providers",
    "517": "Telecommunications",
    "518": "Computing Infrastructure Providers, Data Processing, Web Hosting, and Related Services",
    "519": "Web Search Portals, Libraries, Archives, and Other Information Services",
    # 52 — Finance and Insurance
    "521": "Monetary Authorities-Central Bank",
    "522": "Credit Intermediation and Related Activities",
    "523": "Securities, Commodity Contracts, and Other Financial Investments and Related Activities",
    "524": "Insurance Carriers and Related Activities",
    "525": "Funds, Trusts, and Other Financial Vehicles",
    # 53 — Real Estate and Rental and Leasing
    "531": "Real Estate",
    "532": "Rental and Leasing Services",
    "533": "Lessors of Nonfinancial Intangible Assets (except Copyrighted Works)",
    # 54 — Professional, Scientific, and Technical Services
    "541": "Professional, Scientific, and Technical Services",
    # 55 — Management of Companies and Enterprises
    "551": "Management of Companies and Enterprises",
    # 56 — Administrative and Support and Waste Management
    "561": "Administrative and Support Services",
    "562": "Waste Management and Remediation Services",
    # 61 — Educational Services
    "611": "Educational Services",
    # 62 — Health Care and Social Assistance
    "621": "Ambulatory Health Care Services",
    "622": "Hospitals",
    "623": "Nursing and Residential Care Facilities",
    "624": "Social Assistance",
    # 71 — Arts, Entertainment, and Recreation
    "711": "Performing Arts, Spectator Sports, and Related Industries",
    "712": "Museums, Historical Sites, and Similar Institutions",
    "713": "Amusement, Gambling, and Recreation Industries",
    # 72 — Accommodation and Food Services
    "721": "Accommodation",
    "722": "Food Services and Drinking Places",
    # 81 — Other Services
    "811": "Repair and Maintenance",
    "812": "Personal and Laundry Services",
    "813": "Religious, Grantmaking, Civic, Professional, and Similar Organizations",
    "814": "Private Households",
    # 92 — Public Administration
    "921": "Executive, Legislative, and Other General Government Support",
    "922": "Justice, Public Order, and Safety Activities",
    "923": "Administration of Human Resource Programs",
    "924": "Administration of Environmental Quality Programs",
    "925": "Administration of Housing Programs, Urban Planning, and Community Development",
    "926": "Administration of Economic Programs",
    "927": "Space Research and Technology",
    "928": "National Security and International Affairs",
}


def naics_industry_description(code: Optional[str]) -> Optional[str]:
    """Map a NAICS code (any 2–6 digit length) to an industry title.

    Longest-prefix match: 3-digit subsector first, then 2-digit sector.
    Non-digit characters are stripped (codes are sometimes stored as
    "336212" or "3362-12"). Returns None for empty/unknown codes so callers
    can leave the field blank rather than print a wrong label.
    """
    if not code:
        return None
    digits = "".join(ch for ch in str(code) if ch.isdigit())
    if len(digits) < 2:
        return None
    if len(digits) >= 3 and digits[:3] in SUBSECTOR_TITLES:
        return SUBSECTOR_TITLES[digits[:3]]
    if digits[:2] in SECTOR_TITLES:
        return SECTOR_TITLES[digits[:2]]
    return None
