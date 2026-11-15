"""请求编排挑战判定测试。"""

from src.services.request_service import is_challenge_response


def test_json_403_is_not_challenge():
    assert not is_challenge_response({"status_code": 403, "body": '{"error":"forbidden"}'})


def test_429_rate_limit_is_not_challenge():
    assert not is_challenge_response({"status_code": 429, "body": "too many requests"})


def test_strong_interstitial_marker_is_challenge():
    assert is_challenge_response({"status_code": 403, "body": "<html><script>window._cf_chl_opt={}</script></html>"})
    assert is_challenge_response({"status_code": 200, "body": "<title>Just a moment...</title>"})
