from code.html_writer import _render_card

ROW = {
    "listing_id": "73000001", "address": "1 Main St, Natick, MA",
    "price": "1000000", "beds": "3", "baths": "2", "sqft": "2000",
    "url": "https://redfin.com/x", "town": "Natick, MA",
    "property_type": "Single Family Residential", "days_on_market": "5",
    "year_built": "1990", "first_seen": "2026-06-01", "last_price": "1000000",
    "remarks": "", "builder_owned": "", "builder_match": "",
    "nearest_station": "", "station_miles": "", "station_minutes": "",
    "status": "Active",
}


def test_card_has_listing_id():
    html = _render_card(ROW, 0.0)
    assert 'data-listing-id="73000001"' in html


def test_interactive_card_has_select_and_textarea():
    html = _render_card(ROW, 0.0, interactive=True)
    assert 'class="annotate-status"' in html
    assert 'class="annotate-note"' in html
    assert "Worth visiting" in html  # option present


def test_readonly_card_shows_annotation_without_controls():
    ann = {"status_label": "Favorite", "note": "best so far"}
    html = _render_card(ROW, 0.0, annotation=ann, interactive=False)
    assert "best so far" in html
    assert "Favorite" in html
    assert 'class="annotate-status"' not in html  # no editable control


def test_label_adds_css_class_for_filtering():
    ann = {"status_label": "Worth visiting", "note": ""}
    html = _render_card(ROW, 0.0, annotation=ann, interactive=True)
    assert "label-worth-visiting" in html
    assert 'data-label="Worth visiting"' in html
