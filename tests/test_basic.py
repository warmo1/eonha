
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from eonapi.api import EonNextAPI

@pytest.mark.asyncio
async def test_login_success():
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        # Create a Mock for the response object (not AsyncMock)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.json.return_value = {
            "data": {
                "obtainKrakenToken": {
                    "token": "fake-token",
                    "refreshToken": "fake-refresh-token",
                    "payload": {"exp": 9999999999},
                    "refreshExpiresIn": 9999999999,
                    "__typename": "ObtainJSONWebTokenPayload"
                }
            }
        }
        # The awaitable post method returns this response
        mock_post.return_value = mock_response

        api = EonNextAPI()
        result = await api.login("user@example.com", "password")
        
        assert result is True
        assert api.auth_token == "fake-token"

@pytest.mark.asyncio
async def test_login_failure():
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        # Mock failed login response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "errors": [{"message": "Invalid credentials"}]
        }
        mock_response.is_success = False
        mock_post.return_value = mock_response

        api = EonNextAPI()
        
        with pytest.raises(Exception) as excinfo:
            await api.login("user@example.com", "wrong-password")
        
        assert "Login failed" in str(excinfo.value)
