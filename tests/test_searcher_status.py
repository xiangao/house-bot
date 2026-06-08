from code.searcher import _parse_row

BASE_ROW = {
    "SALE TYPE": "MLS Listing",
    "PROPERTY TYPE": "Single Family Residential",
    "ADDRESS": "1 Main St",
    "CITY": "Natick",
    "STATE OR PROVINCE": "MA",
    "ZIP OR POSTAL CODE": "01760",
    "PRICE": "$1,000,000",
    "BEDS": "3",
    "BATHS": "2",
    "SQUARE FEET": "2,000",
    "YEAR BUILT": "1990",
    "DAYS ON MARKET": "5",
    "MLS#": "73000001",
    "LATITUDE": "42.28",
    "LONGITUDE": "-71.35",
}


def test_parse_row_reads_status():
    row = {**BASE_ROW, "STATUS": "Pending"}
    listing = _parse_row(row, "Natick, MA")
    assert listing is not None
    assert listing.status == "Pending"


def test_parse_row_status_defaults_empty():
    row = dict(BASE_ROW)  # no STATUS key
    listing = _parse_row(row, "Natick, MA")
    assert listing.status == ""
