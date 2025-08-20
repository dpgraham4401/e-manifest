import pytest

from . import RCRAINFO_PREPROD, AsyncRcrainfoClient, new_async_client

MOCK_MTN = "100032437ELC"
MOCK_GEN_ID = "VATESTGEN001"
MOCK_API_ID = "mock_api_id"
MOCK_API_KEY = "mock_api_key"


class TestAsyncRcrainfoClient:
    """Test the async RCRAInfo client"""

    def test_client_creation(self):
        """Test that we can create an async client"""
        client = new_async_client("preprod")
        assert isinstance(client, AsyncRcrainfoClient)
        assert client.base_url == RCRAINFO_PREPROD

    def test_client_properties(self):
        """Test client properties"""
        client = new_async_client("preprod", api_id=MOCK_API_ID, api_key=MOCK_API_KEY)
        assert client.base_url == RCRAINFO_PREPROD
        assert not client.is_authenticated
        assert client.token is None
        assert client.timeout == 10

    def test_no_base_url_raises_exception(self):
        """Test that missing base URL raises an exception"""
        with pytest.raises(ValueError):
            new_async_client()

    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        """Test that the client works as an async context manager"""
        async with new_async_client("preprod") as client:
            assert isinstance(client, AsyncRcrainfoClient)
            # Session should be created
            assert client._session is not None

    @pytest.mark.asyncio
    async def test_session_management(self):
        """Test session creation and cleanup"""
        client = new_async_client("preprod")
        try:
            # Initially no session
            assert client._session is None

            # Getting session creates it
            session = await client._get_session()
            assert session is not None
            assert client._session is session

            # Getting again returns same session
            session2 = await client._get_session()
            assert session2 is session

        finally:
            await client.close()

    def test_retrieve_credentials(self):
        """Test credential retrieval methods"""
        client = new_async_client("preprod", api_id=MOCK_API_ID, api_key=MOCK_API_KEY)
        assert client.retrieve_id() == MOCK_API_ID
        assert client.retrieve_key() == MOCK_API_KEY

        # Test with explicit parameters
        assert client.retrieve_id("other_id") == "other_id"
        assert client.retrieve_key("other_key") == "other_key"


class TestAsyncNewClientConstructor:
    """Test the new_async_client factory function"""

    def test_returns_instance_of_async_client(self):
        """Test that new_async_client returns AsyncRcrainfoClient instance"""
        rcrainfo = new_async_client("prod")
        preprod = new_async_client("preprod")
        assert isinstance(rcrainfo, AsyncRcrainfoClient)
        assert isinstance(preprod, AsyncRcrainfoClient)

    def test_new_async_client_defaults_to_preprod(self):
        """Test that preprod URL is set correctly"""
        rcrainfo = new_async_client("preprod")
        assert rcrainfo.base_url == RCRAINFO_PREPROD

    def test_auto_renew_setting(self):
        """Test auto_renew parameter"""
        client_auto = new_async_client("preprod", auto_renew=True)
        client_manual = new_async_client("preprod", auto_renew=False)

        assert client_auto.auto_renew is True
        assert client_manual.auto_renew is False
