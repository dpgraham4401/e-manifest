"""
Async e-Manifest client using aiohttp for the e-Manifest API
see https://github.com/USEPA/e-manifest
"""

import json
import zipfile
from datetime import datetime, timezone
from typing import (
    Generic,
    List,
    Literal,
    Optional,
    TypeVar,
)

import aiohttp

from .types import (
    Manifest,
    ManifestExistsResponse,
    PortOfEntry,
    RcraCodeDescription,
    RcraSite,
    SiteExistsResponse,
)

RCRAINFO_PROD = "https://rcrainfo.epa.gov/rcrainfoprod/rest/api/"
RCRAINFO_PREPROD = "https://rcrainfopreprod.epa.gov/rcrainfo/rest/api/"

T = TypeVar("T")


class AsyncRcrainfoResponse(Generic[T]):
    """
    AsyncRcrainfoResponse wraps around aiohttp's ClientResponse object.
    The complete ClientResponse object can be accessed as self.response

    Attributes:
        response (aiohttp.ClientResponse) the aiohttp ClientResponse object.
    """

    def __init__(self, response: aiohttp.ClientResponse, response_data: bytes):
        self.response: aiohttp.ClientResponse = response
        self._response_data: bytes = response_data
        self._multipart_json: T | None = None
        self._multipart_zip: Optional[zipfile.ZipFile] = None

    async def json(self) -> T:
        if self._multipart_json:
            return self._multipart_json
        else:
            return json.loads(self._response_data.decode("utf-8"))

    @property
    def ok(self):
        return self.response.status < 400

    @property
    def status_code(self):
        return self.response.status

    @property
    def zip(self):
        if self._multipart_zip:
            return self._multipart_zip
        else:
            return None

    def __str__(self):
        return f"{self.__class__.__name__}: status {self.response.status}"

    def __repr__(self):
        return f"<{self.__class__.__name__} [{self.status_code}]>"

    def __bool__(self):
        """returns True if status code < 400"""
        return self.ok

    async def decode(self):
        """Decode multipart response data"""
        # For multipart responses, we would need to parse the multipart data
        # This is a simplified implementation
        content_type = self.response.headers.get("Content-Type", "")
        if "multipart" in content_type:
            # Parse multipart data (simplified - would need proper multipart parser)
            # For now, just store the raw data
            pass


class AsyncRcrainfoClient:
    """
    An async http client for using the RCRAInfo (e-Manifest) Restful web services.
    """

    # see datetime docs https://docs.python.org/3.11/library/datetime.html#strftime-strptime-behavior
    # acceptable date format(s) [yyyy-MM-dd'T'HH:mm:ssZ,yyyy-MM-dd'T'HH:mm:ss.SSSZ]
    __expiration_fmt = "%Y-%m-%dT%H:%M:%S.%f%z"
    __signature_date_fmt = "%Y-%m-%dT%H:%M:%SZ"
    __default_headers = {"Accept": "application/json"}
    __default_timeout = 10

    def __init__(
        self, base_url: str, *, api_id=None, api_key=None, timeout=10, auto_renew=True
    ) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self.__token = None
        self.__token_expiration_utc = datetime.now(timezone.utc).replace(tzinfo=timezone.utc)
        self.__api_key = api_key
        self.__api_id = api_id
        self.auto_renew = auto_renew
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def base_url(self):
        """RCRAInfo base URL, either for Production ('prod') or Preproduction ('preprod')"""
        return self.__base_url

    @base_url.setter
    def base_url(self, value):
        self.__base_url = _parse_url(value)

    @property
    def timeout(self):
        """Http request timeout"""
        return self.__timeout

    @timeout.setter
    def timeout(self, value) -> None:
        if isinstance(value, (int, float)):
            self.__timeout = value
        else:
            self.__timeout = self.__default_timeout

    @property
    def token_expiration(self) -> datetime:
        """Token expiration datetime object. Read only."""
        return self.__token_expiration_utc

    def __set_token_expiration(self, expiration: str) -> None:
        try:
            self.__token_expiration_utc = datetime.strptime(
                expiration, self.__expiration_fmt
            ).replace(tzinfo=timezone.utc)
        except ValueError:
            self.__token_expiration_utc = datetime.now(timezone.utc).replace(tzinfo=timezone.utc)

    @property
    def token(self):
        """Session token from Rcrainfo. Read Only."""
        return self.__token

    @property
    def is_authenticated(self) -> bool:
        """Returns True if the AsyncRcrainfoClient token exists and has not expired."""
        try:
            if (
                self.token_expiration > datetime.now(timezone.utc).replace(tzinfo=timezone.utc)
                and self.token is not None
            ):
                return True
            else:
                return False
        except TypeError:
            return False

    @property
    def expiration_format(self) -> str:
        """Datetime format used by RCRAInfo for token expiration. Read only."""
        return self.__expiration_fmt

    def __str__(self) -> str:
        return f"{self.__class__.__name__}"

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__}('{self.base_url}', auto_renew={self.auto_renew}, "
            f"api_id={self.__api_id}, api_key={self.__api_key})>"
        )

    async def __aenter__(self):
        """Async context manager entry"""
        await self._get_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create the aiohttp session"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout),
                headers=self.__default_headers,
            )
        return self._session

    async def close(self):
        """Close the aiohttp session"""
        if self._session and not self._session.closed:
            await self._session.close()

    async def __rcra_request(
        self, method, endpoint, *, headers=None, multipart=None, stream=False, **kwargs
    ) -> AsyncRcrainfoResponse:
        """Client internal method for making requests to RCRAInfo"""

        # If auto_renew is True, check if the token is expired and, if needed, re-authenticate.
        if self.auto_renew and not self.is_authenticated:
            await self.__get_token()

        session = await self._get_session()

        # Prepare headers
        request_headers = dict(self.__default_headers)
        if self.token:
            request_headers["Authorization"] = f"Bearer {self.token}"
        if headers:
            request_headers.update(headers)

        # decide if, and what, we need to put into the body of our request.
        if method in ("POST", "PUT", "PATCH"):
            if multipart is not None:
                data = multipart
            else:
                data = json.dumps(dict(**kwargs)) if kwargs else None
                if data:
                    request_headers["Content-Type"] = "application/json"
        else:
            data = None

        async with session.request(
            method, endpoint, data=data, headers=request_headers
        ) as response:
            response_data = await response.read()
            return AsyncRcrainfoResponse(response, response_data)

    async def __get_token(self) -> None:
        """
        used to retrieve a session token from RCRAInfo, only request that (intentionally) does
        not use __rcra_request
        """
        self.__api_id = self.retrieve_id()
        self.__api_key = self.retrieve_key()
        auth_url = f"{self.base_url}v1/auth/{self.__api_id}/{self.__api_key}"

        session = await self._get_session()
        async with session.get(auth_url) as resp:
            if resp.status < 400:
                response_data = await resp.json()
                self.__token = response_data["token"]
                self.__set_token_expiration(response_data["expiration"])

    def retrieve_id(self, api_id=None) -> str:
        """
        Getter method used internally to retrieve the desired RCRAInfo API ID. Can be overridden
        to automatically support retrieving an API ID from an external location.
        Args:
            api_id:

        Returns:
            string of the user's RCRAInfo API ID
        """
        if api_id:
            return api_id
        elif self.__api_id:
            return self.__api_id
        else:
            return ""

    def retrieve_key(self, api_key: str | None = None) -> str:
        """
        Getter method used internally to retrieve the desired RCRAInfo API key. Can be overridden
        to support retrieving an API Key from an external location.
        """
        if api_key:
            return api_key
        elif self.__api_key:
            return self.__api_key
        else:
            return ""

    # Below this line are the high level methods to request RCRAInfo/e-Manifest
    async def authenticate(self, api_id=None, api_key=None) -> None:
        """
        Authenticate user's RCRAInfo API ID and Key to generate token for use by other functions

        Args:
            api_id (str): API ID of RCRAInfo User with Site Manager level permission.
            api_key (str): User's RCRAInfo API key. Generated alongside the api_id in RCRAInfo
        """
        # if api credentials are passed, set the client's attributes
        if api_id is not None:
            self.__api_id = str(api_id)
        if api_key is not None:
            self.__api_key = str(api_key)
        await self.__get_token()

    async def get_site(self, epa_id: str) -> AsyncRcrainfoResponse[RcraSite]:
        """
        Retrieve site details for a given Site ID

        Args:
            epa_id (str): EPA site ID
        """
        endpoint = f"{self.base_url}v1/site-details/{epa_id}"
        return await self.__rcra_request("GET", endpoint)

    async def get_hazard_classes(self) -> AsyncRcrainfoResponse[List[str]]:
        """Retrieve all DOT Hazard Classes"""
        endpoint = f"{self.base_url}v1/emanifest/lookup/hazard-classes"
        return await self.__rcra_request("GET", endpoint)

    async def get_packing_groups(self) -> AsyncRcrainfoResponse[List[str]]:
        """Retrieve all DOT Packing Groups"""
        endpoint = f"{self.base_url}v1/emanifest/lookup/packing-groups"
        return await self.__rcra_request("GET", endpoint)

    async def get_haz_class_sn_id(
        self, ship_name: str, id_num: str
    ) -> AsyncRcrainfoResponse[List[str]]:
        """
        Retrieve DOT Hazard Classes by DOT Proper Shipping name and ID Number

        Args:
            ship_name (str): DOT proper shipping name. Case-sensitive (e.g. Hydrochloric acid)
            id_num (str): DOT ID number
        """
        endpoint = (
            f"{self.base_url}v1/emanifest/lookup/hazard-class-by-shipping-name-id-number/"
            f"{ship_name}/{id_num}"
        )
        return await self.__rcra_request("GET", endpoint)

    async def get_pack_groups_sn_id(
        self, ship_name: str, id_num: str
    ) -> AsyncRcrainfoResponse[List[str]]:
        """
        Retrieve DOT Packing Groups by DOT Proper Shipping name and ID Number

        Args:
            ship_name (str): DOT proper shipping name. Case-sensitive (e.g. Hydrochloric acid)
            id_num (str): DOT ID number
        """
        endpoint = (
            f"{self.base_url}v1/emanifest/lookup/packing-groups-by-shipping-name-id-number/"
            f"{ship_name}/{id_num}"
        )
        return await self.__rcra_request("GET", endpoint)

    async def get_id_by_ship_name(self, ship_name: str) -> AsyncRcrainfoResponse[List[str]]:
        """
        Retrieve DOT ID number by DOT Proper Shipping name

        Args:
            ship_name (str): DOT proper shipping name. Case-sensitive (e.g. Hydrochloric acid)
        """
        endpoint = f"{self.base_url}v1/emanifest/lookup/id-numbers-by-shipping-name/{ship_name}"
        return await self.__rcra_request("GET", endpoint)

    async def get_ship_name_by_id(self, id_num: str) -> AsyncRcrainfoResponse[List[str]]:
        """
        Retrieve DOT Proper Shipping name by DOT ID number

        Args:
            id_num (str): DOT ID number
        """
        endpoint = (
            f"{self.base_url}v1/emanifest/lookup/proper-shipping-names-by-id-number/{id_num}"
        )
        return await self.__rcra_request("GET", endpoint)

    async def get_mtn_suffix(self) -> AsyncRcrainfoResponse[List[RcraCodeDescription]]:
        """Retrieve Allowable Manifest Tracking Number (MTN) Suffixes"""
        endpoint = f"{self.base_url}v1/emanifest/lookup/printed-tracking-number-suffixes"
        return await self.__rcra_request("GET", endpoint)

    async def get_container_types(self) -> AsyncRcrainfoResponse:
        """Retrieve Container Types"""
        endpoint = f"{self.base_url}v1/emanifest/lookup/container-types"
        return await self.__rcra_request("GET", endpoint)

    async def get_quantity_uom(self) -> AsyncRcrainfoResponse[List[RcraCodeDescription]]:
        """
        Retrieve Quantity Units of Measure (UOM)
        """
        endpoint = f"{self.base_url}v1/emanifest/lookup/quantity-uom"
        return await self.__rcra_request("GET", endpoint)

    async def get_load_types(self) -> AsyncRcrainfoResponse[List[RcraCodeDescription]]:
        """Retrieve PCB Load Types"""
        endpoint = f"{self.base_url}v1/emanifest/lookup/load-types"
        return await self.__rcra_request("GET", endpoint)

    async def get_shipping_names(self) -> AsyncRcrainfoResponse[List[str]]:
        """
        Retrieve DOT Proper Shipping Names

        Returns:
            dict: object with DOT Proper Shipping names
        """
        endpoint = f"{self.base_url}v1/emanifest/lookup/proper-shipping-names"
        return await self.__rcra_request("GET", endpoint)

    async def get_id_numbers(self) -> AsyncRcrainfoResponse[List[str]]:
        """Retrieve DOT Shipping ID numbers"""
        endpoint = f"{self.base_url}v1/emanifest/lookup/id-numbers"
        return await self.__rcra_request("GET", endpoint)

    async def get_density_uom(self) -> AsyncRcrainfoResponse[List[RcraCodeDescription]]:
        """Retrieve Density Units of Measure (UOM)"""
        endpoint = f"{self.base_url}v1/lookup/density-uom"
        return await self.__rcra_request("GET", endpoint)

    async def get_form_codes(self) -> AsyncRcrainfoResponse[list[RcraCodeDescription]]:
        """Retrieve Form Codes"""
        endpoint = f"{self.base_url}v1/lookup/form-codes"
        return await self.__rcra_request("GET", endpoint)

    async def get_source_codes(self) -> AsyncRcrainfoResponse[List[RcraCodeDescription]]:
        """Retrieve Source Codes"""
        endpoint = f"{self.base_url}v1/lookup/source-codes"
        return await self.__rcra_request("GET", endpoint)

    async def get_state_waste_codes(
        self, state_code: str
    ) -> AsyncRcrainfoResponse[List[RcraCodeDescription]]:
        """
        Retrieve State Waste Codes for a given state (besides Texas)

        Args:
            state_code: (str) Two-letter state code (e.g., CA, MA)
        """
        endpoint = f"{self.base_url}v1/lookup/state-waste-codes/{state_code}"
        return await self.__rcra_request("GET", endpoint)

    async def get_fed_waste_codes(self) -> AsyncRcrainfoResponse[List[RcraCodeDescription]]:
        """Retrieve Federal Waste Codes"""
        endpoint = f"{self.base_url}v1/lookup/federal-waste-codes"
        return await self.__rcra_request("GET", endpoint)

    async def get_man_method_codes(self) -> AsyncRcrainfoResponse[List[RcraCodeDescription]]:
        """Retrieve Management Method Codes"""
        endpoint = f"{self.base_url}v1/lookup/management-method-codes"
        return await self.__rcra_request("GET", endpoint)

    async def get_waste_min_codes(self) -> AsyncRcrainfoResponse[List[RcraCodeDescription]]:
        """Retrieve Waste Minimization Codes"""
        endpoint = f"{self.base_url}v1/lookup/waste-minimization-codes"
        return await self.__rcra_request("GET", endpoint)

    async def get_entry_ports(self) -> AsyncRcrainfoResponse[List[PortOfEntry]]:
        """Retrieve Ports of Entry"""
        endpoint = f"{self.base_url}v1/lookup/ports-of-entry"
        return await self.__rcra_request("GET", endpoint)

    async def check_site_exists(self, site_id: str) -> AsyncRcrainfoResponse[SiteExistsResponse]:
        """
        Check if provided Site ID exists

        Args:
            site_id (str): EPA site ID
        """
        endpoint = f"{self.base_url}v1/site-exists/{site_id}"
        return await self.__rcra_request("GET", endpoint)

    async def check_mtn_exists(self, mtn: str) -> AsyncRcrainfoResponse[ManifestExistsResponse]:
        """Check if Manifest Tracking Number (MTN) exists and return basic details"""
        endpoint = f"{self.base_url}v1/emanifest/manifest/mtn-exists/{mtn}"
        return await self.__rcra_request("GET", endpoint)

    async def get_sites(
        self, state_code: str, site_type: str, reg: bool = False
    ) -> AsyncRcrainfoResponse[List[str]]:
        """
        Retrieve site ids for provided criteria

        Args:
            state_code (str): Two-letter US postal state code
            site_type (str): Site type (Generator, Tsdf, Transporter, Broker). Case-sensitive
            reg (bool): use endpoint for regulators, defaults to False
        """
        if reg:
            endpoint = f"{self.base_url}v1/state/emanifest/site-ids/{state_code}/{site_type}"
        else:
            endpoint = f"{self.base_url}v1/emanifest/site-ids/{state_code}/{site_type}"
        return await self.__rcra_request("GET", endpoint)

    async def get_site_mtn(
        self, site_id: str, reg: bool = False
    ) -> AsyncRcrainfoResponse[List[str]]:
        """Retrieve manifest tracking numbers for a given Site ID"""
        if reg:
            endpoint = f"{self.base_url}v1/state/emanifest/manifest-tracking-numbers/{site_id}"
        else:
            endpoint = f"{self.base_url}v1/emanifest/manifest-tracking-numbers/{site_id}"
        return await self.__rcra_request("GET", endpoint)

    async def get_manifest(self, mtn: str, reg: bool = False) -> AsyncRcrainfoResponse[Manifest]:
        """Retrieve e-Manifest details by Manifest Tracking Number (MTN)"""
        if reg:
            endpoint = f"{self.base_url}v1/state/emanifest/manifest/{mtn}"
        else:
            endpoint = f"{self.base_url}v1/emanifest/manifest/{mtn}"
        return await self.__rcra_request("GET", endpoint)


def _parse_url(base_url: str | None) -> str:
    """emanifest-py internal helper function"""
    urls = {"PROD": RCRAINFO_PROD, "PREPROD": RCRAINFO_PREPROD}
    if base_url is None:
        return urls["PREPROD"]
    if "https" not in base_url:
        if base_url.upper() in urls:
            return urls[base_url.upper()]
        else:
            return urls["PREPROD"]
    else:
        return base_url


BaseUrls = Literal["prod", "preprod"]


def new_async_client(
    base_url: BaseUrls | str | None = None,
    api_id: str | None = None,
    api_key: str | None = None,
    auto_renew: bool = False,
) -> AsyncRcrainfoClient:
    """
    Create a new async RCRAInfo client instance

    Args:
        base_url (str): Base URL of the RCRAInfo API. Defaults to 'PREPROD'
        api_id (str): RCRAInfo API ID
        api_key (str): RCRAInfo API key
        auto_renew: (bool): Automatically renew API token when expired. Defaults to False

    Returns:
        AsyncRcrainfoClient: Async RCRAInfo client instance
    """
    if base_url is None:
        raise ValueError("base_url is required")
    return AsyncRcrainfoClient(base_url, api_id=api_id, api_key=api_key, auto_renew=auto_renew)
