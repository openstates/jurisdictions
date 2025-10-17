import io
import polars as pl

def csv_bytes_to_df(data: bytes, *, schema: dict | None = None, infer_schema_length: int | None = 1000) -> pl.DataFrame:
    return pl.read_csv(io.BytesIO(data), schema=schema, infer_schema_length=infer_schema_length)

def vstack_locals(dfs: list[pl.DataFrame]) -> pl.DataFrame:
    return pl.concat(dfs, how="vertical_relaxed") if dfs else pl.DataFrame()