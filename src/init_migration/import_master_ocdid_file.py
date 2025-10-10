import polars as pl
import io
from typing import Optional, Any, Coroutine
import asyncio
import httpx


class GetOCDIDFiles:
    CIVIC_DATA_OCDIDS_URL = "https://raw.githubusercontent.com/opencivicdata/ocd-division-ids/master/identifiers/country-us.csv"
    CIVIC_DATA_LOCAL_OCDIDS = "https://raw.githubusercontent.com/opencivicdata/ocd-division-ids/master/identifiers/country-us/state-{stusps}-local_gov.csv"
    DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=60.0)
    DEFAULT_HEADERS = {
        "User-Agent": "openstates-jurisdictions/1.0 (+https://openstates.org/)",
        "Accept": "text/csv, */*;q=0.1",
    }

    def __init__(self, stusps: str = None):
        self.stusps = stusps

    async def fetch_csv_bytes(
        self,
        url: str,
        *,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
        max_retries: int = 3,
        client: Optional[httpx.AsyncClient] = None,
    ) -> bytes | None:
        owns_client = client is None
        client = client or httpx.AsyncClient(
            follow_redirects=True, headers=self.DEFAULT_HEADERS, timeout=timeout
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
        data = await self.fetch_csv_bytes(self.CIVIC_DATA_OCDIDS_URL)
        return self.read_polars_from_bytes(data)

if __name__ == "__main__":
    async def main():
        importer = GetOCDIDFiles(stusps="ak")
        master_df = await importer.load_us_divisions_df()
        print(master_df.head())

    asyncio.run(main())




