import polars as pl
import io
from typing import Optional
import asyncio
import httpx
import os
from pathlib import Path


class GetOCDIDFiles:
    """
    Fetch and handle CSV data from Open Civic Data URLs.

    This class is designed for retrieving and processing CSV data related to U.S.
    government divisions from the Open Civic Data project. It provides utilities
    to fetch CSV files asynchronously and load them into Polars DataFrames. The
    class supports retry mechanisms for network errors and configurable timeouts.

    Attributes:
    CIVIC_DATA_OCDIDS_URL: The URL for retrieving the main national divisions CSV.
    CIVIC_DATA_LOCAL_OCDIDS: The URL template for retrieving local government
        divisions CSV files, requiring a specific state USPS code.
    DEFAULT_TIMEOUT: Default timeout configuration for HTTP requests.
    DEFAULT_HEADERS: Default HTTP headers used for making requests.
    """
    CIVIC_DATA_OCDIDS_URL = "https://raw.githubusercontent.com/opencivicdata/ocd-division-ids/master/identifiers/country-us.csv"
    CIVIC_DATA_LOCAL_OCDIDS = "https://raw.githubusercontent.com/opencivicdata/ocd-division-ids/master/identifiers/country-us/state-{stusps}-local_gov.csv"
    DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=60.0)
    BASE_HEADERS = {
        "User-Agent": "openstates-jurisdictions/1.0 (+https://openstates.org/)",
        "Accept": "text/csv, */*;q=0.1",
    }

    def __init__(
        self,
        stusps: str | None = None,
        *,
        use_github_auth: bool = True,
        env_path: str | os.PathLike | None = None,
    ):
        """
        Initializes an instance with the state USPS code.

        Parameters:
        stusps: The USPS code of the state. Defaults to None.
        use_github_auth: If True (default), attempts to authenticate requests using
            a GitHub PAT from the environment/.env; falls back to unauthenticated
            requests if no token is found. If False, always make unauthenticated calls.
        env_path: Optional path to a .env file containing GITHUB_PAT or GITHUB_TOKEN.
        """
        self.stusps = stusps
        self.use_github_auth = use_github_auth
        self.github_token = None
        if use_github_auth:
            self.github_token = self._load_github_token(env_path)

    @staticmethod
    def _load_github_token(env_path: str | os.PathLike | None) -> str | None:
        """Load a GitHub token from environment or a .env file.

        1) Existing environment variable GITHUB_TOKEN
        2) A .env file (provided via env_path, current working dir, or any parent dir)
           containing GITHUB_TOKEN.
        """
        # 1/2: read from environment first
        token = os.getenv("GITHUB_TOKEN")
        if token:
            return token.strip()

        # 3: search for .env
        paths_to_try: list[Path] = []
        if env_path:
            paths_to_try.append(Path(env_path))
        else:
            # look for .env in CWD and its parents
            cwd = Path.cwd()
            for p in [cwd, *cwd.parents]:
                paths_to_try.append(p / ".env")

        for p in paths_to_try:
            try:
                if p.is_file():
                    with p.open("r", encoding="utf-8") as fh:
                        for line in fh:
                            s = line.strip()
                            if not s or s.startswith("#"):
                                continue
                            if "=" not in s:
                                continue
                            key, value = s.split("=", 1)
                            key = key.strip()
                            value = value.strip().strip('"').strip("'")
                            if key in {"GITHUB_PAT", "GITHUB_TOKEN"} and value:
                                # also export to environment for child processes
                                os.environ[key] = value
                                return value
            except OSError:
                # ignore unreadable files
                continue
        return None

    def _build_headers(self) -> dict:
        """Construct request headers, adding Authorization if a token is present."""
        headers = dict(self.BASE_HEADERS)
        if self.use_github_auth and self.github_token:
            # GitHub accepts either "token" or "Bearer" schemes; use Bearer
            headers["Authorization"] = f"Bearer {self.github_token}"
            # Be explicit about raw content type as well
            headers.setdefault("Accept", "text/csv, */*;q=0.1")
        return headers

    async def fetch_csv_bytes(
        self,
        url: str,
        *,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
        max_retries: int = 3,
        client: Optional[httpx.AsyncClient] = None,
    ) -> bytes | None:
        """
        Fetch CSV bytes from a given URL using an asynchronous HTTP client, with support for
        timeouts, retries, and backoff for error handling. The method will validate the
        response's content type to ensure it is a CSV or text format, raising an error for
        unexpected content types like HTML.

        Parameters:
        url: str
            The URL from which to fetch the CSV content.
        timeout: httpx.Timeout
            The timeout configuration for the HTTP request. Defaults to DEFAULT_TIMEOUT.
        max_retries: int
            The maximum number of retries on transient errors. Defaults to 3.
        client: Optional[httpx.AsyncClient]
            An optional custom instance of httpx.AsyncClient to use for making the HTTP request.

        Returns:
        bytes | None
            The content of the fetched CSV file as bytes, or None if not retrievable.

        Raises:
        httpx.ConnectError
            If the connection to the URL fails.
        httpx.ReadTimeout
            If the reading of the response from the server times out.
        httpx.RemoteProtocolError
            If there is a protocol error during communication.
        httpx.HTTPStatusError
            If the server returns an HTTP error status code.
        ValueError
            If the response content type is unexpected (e.g., HTML).
        """
        owns_client = client is None
        client = client or httpx.AsyncClient(
            follow_redirects=True, headers=self._build_headers(), timeout=timeout
        )

        try:
            for attempt in range(max_retries + 1):
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    ctype = resp.headers.get("Content-Type", "")
                    if "text" not in ctype and "csv" not in ctype and "html" in ctype:
                        raise ValueError(f"Unexpected content type: {ctype}")
                    return resp.content
                except (
                    httpx.ConnectError,
                    httpx.ReadTimeout,
                    httpx.RemoteProtocolError,
                ):
                    if attempt >= max_retries:
                        raise
                    # async backoff
                    delay = min(4.0, 0.5 * (2**attempt))
                    await asyncio.sleep(delay)
                except httpx.HTTPStatusError as e:
                    if 500 <= e.response.status_code < 600 and attempt < max_retries:
                        delay = min(4.0, 0.5 * (2**attempt))
                        await asyncio.sleep(delay)
                        continue
                    raise
        finally:
            if owns_client:
                await client.aclose()

    # FIXME: May want to refactor out of class into separate function.
    @staticmethod
    def read_polars_from_bytes(data: bytes) -> pl.DataFrame:
        """
        Load CSV bytes into a Polars DataFrame with sensible defaults.
        """
        return pl.read_csv(io.BytesIO(data))

    async def load_us_divisions_df(self) -> pl.DataFrame:
        """
        Loads US divisions dataframe from a remote CSV file.

        This asynchronous method fetches the CSV file containing US divisions data
        from a specified remote URL using the `fetch_csv_bytes` method. The content
        is then processed into a Polars DataFrame using the `read_polars_from_bytes`
        method.

        Returns:
            pl.DataFrame: A Polars DataFrame representing the US divisions data.
        """
        data = await self.fetch_csv_bytes(self.CIVIC_DATA_OCDIDS_URL)
        return self.read_polars_from_bytes(data)

if __name__ == "__main__":
    async def main():
        # Explicitly point to the project-level .env so auth can be used when available
        project_root = Path(__file__).resolve().parents[2]
        env_path = project_root / ".env"
        importer = GetOCDIDFiles(stusps="ak", env_path=env_path)
        master_df = await importer.load_us_divisions_df()
        print(master_df.head())

    asyncio.run(main())




