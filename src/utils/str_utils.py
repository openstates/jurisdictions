import pandas as pd

def fix_zero_padding(series: pd.Series, n: int) -> pd.Series:
    """
    Zero pad all string elements in a pandas Series to n places.
    Args:
        series (pd.Series): Series of strings or numbers.
        n (int): Desired string length.
    Returns:
        pd.Series: Zero-padded string Series.
    """
    return series.astype(str).str.zfill(n)

def zero_pad_value(value, n: int) -> str:
    """
    Zero pad a single value to n places.
    Args:
        value: String or number to pad.
        n (int): Desired string length.
    Returns:
        str: Zero-padded string.
    """
    return str(value).zfill(n)