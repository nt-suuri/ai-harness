# Smoke test for the /api/hello endpoint

This test verifies that the /api/hello endpoint works correctly by sending a request and checking the response structure and content.

import httpx
import pytest

@pytest.mark.asyncio
async def test_hello_endpoint():
    url = 'http://localhost:8000/api/hello?name=Test'
    expected_response = {'message': 'Hello, Test!'}  # Adjust based on actual response structure

    async with httpx.AsyncClient() as client:
        response = await client.get(url)

    assert response.status_code == 200
    assert response.json() == expected_response  # Check if response matches expected
