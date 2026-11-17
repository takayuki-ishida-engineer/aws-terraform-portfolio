"""Minimal DEV Lambda handler behind the HTTP API.

Returns HTTP 200 with the body "ok". It reads no secret value and calls no AWS API.
"""


def handler(event, context):
    return {"statusCode": 200, "body": "ok"}
