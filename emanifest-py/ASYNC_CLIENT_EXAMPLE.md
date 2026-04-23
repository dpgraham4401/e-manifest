# Async RCRAInfo Client Example

This repository now includes both synchronous and asynchronous RCRAInfo clients.

## Synchronous Client (existing)

```python
from emanifest import new_client

# Create a sync client
client = new_client("preprod", api_id="your_api_id", api_key="your_api_key")

# Authenticate
client.authenticate()

# Make requests
site_info = client.get_site("VATESTGEN001")
hazard_classes = client.get_hazard_classes()
```

## Asynchronous Client (new)

```python
import asyncio
from emanifest import new_async_client

async def main():
    # Create an async client (use as context manager for automatic cleanup)
    async with new_async_client("preprod", api_id="your_api_id", api_key="your_api_key") as client:
        
        # Authenticate
        await client.authenticate()
        
        # Make async requests
        site_info = await client.get_site("VATESTGEN001")
        hazard_classes = await client.get_hazard_classes()
        
        # Access response data
        site_data = await site_info.json()
        hazard_data = await hazard_classes.json()

# Run the async function
asyncio.run(main())
```

## Key Differences

- **Async client methods**: All HTTP methods are `async` and must be `await`ed
- **Session management**: Async client uses `aiohttp.ClientSession` instead of `requests.Session`
- **Context manager**: Use `async with` for automatic session cleanup
- **Response handling**: Call `await response.json()` instead of `response.json()`

## Available Methods

Both clients provide the same API methods:

- `authenticate(api_id, api_key)`
- `get_site(epa_id)`
- `get_hazard_classes()`
- `get_packing_groups()`
- `get_manifest(mtn)`
- `check_site_exists(site_id)`
- `check_mtn_exists(mtn)`
- And many more...

## Dependencies

The async client requires `aiohttp >= 3.8.0` in addition to the existing dependencies.