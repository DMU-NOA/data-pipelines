from noa_data.collectors import tourapi_places


def page(items):
    return {"response": {"header": {"resultCode": "0000"}, "body": {"items": items, "totalCount": 0}}}


def test_extract_items_handles_empty_single_and_list():
    assert tourapi_places.extract_items(page("")) == []
    assert tourapi_places.extract_items(page({"item": {"contentid": "1"}})) == [{"contentid": "1"}]
    assert len(tourapi_places.extract_items(page({"item": [{"contentid": "1"}, {"contentid": "2"}]}))) == 2

