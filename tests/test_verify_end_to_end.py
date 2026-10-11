from datetime import datetime
from zoneinfo import ZoneInfo

from noa_data.jobs import verify_end_to_end as verify


class FakeDb:
    def execute(self, sql):
        class Result:
            def fetchone(self):
                return (3, datetime(2026,10,11,15,0,tzinfo=ZoneInfo("Asia/Seoul")))
        return Result()


def test_readonly_verification_queries_include_official_and_ml():
    result = verify._counts(FakeDb())
    assert set(result) == {
        "citydata_observations", "official_hourly_forecasts",
        "hourly_ml_predictions", "verified_spot_ml",
    }


def test_api_response_source_is_not_assumed(monkeypatch):
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {"forecast": [{"time": "17시"}],
                    "source": "seoul_citydata_official"}
    monkeypatch.setattr(verify.requests, "get", lambda *a,**kw: Response())
    result = verify._api("http://127.0.0.1:8000", "POI001")
    assert result["ok"]
    assert result["source"] == "seoul_citydata_official"
    assert result["count"] == 1
