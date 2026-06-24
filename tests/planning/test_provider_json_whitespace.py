import json

from ai_electronics_lab.planning import openrouter


def test_provider_json_accepts_leading_standard_whitespace():
    payload = {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"content": "{}"},
            }
        ]
    }
    encoded = ("\n \t\r" + json.dumps(payload) + "\r\n").encode()

    decoded = openrouter._decode_json_bytes(encoded, provider=True)

    assert openrouter._extract_provider_content(decoded) == "{}"
