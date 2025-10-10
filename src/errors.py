class Error(Exception):
    """Base class for other exceptions"""


class APIRetryError(Error):
    """
    Raised when an  API returns an error due to timeout, exceeded
    rate limit or other type of error that can be retried.
    """

    def __init__(self, message):
        super().__init__(message)
        self.message = message


class UnexpectedContentError(Error):
    """
    Raised when the downloaded content is not in the expected format.
    For example, when HTML is returned instead of CSV or JSON.
    """

    def __init__(self, message, url: str = None, content_type: str = None):
        super().__init__(message)
        self.message = message
        self.url = url
        self.content_type = content_type


class DownloaderNotInitializedError(Error):
    """
    Raised when attempting to use AsyncDownloader methods without
    entering the async context manager.
    """

    def __init__(self, message="AsyncDownloader must be used with 'async with' statement"):
        super().__init__(message)
        self.message = message


class CacheError(Error):
    """
    Raised when there are issues reading from or writing to the ETag cache.
    """

    def __init__(self, message, cache_path: str = None):
        super().__init__(message)
        self.message = message
        self.cache_path = cache_path


class OCDidNotFoundError(Error):
    """
    Raised when an OCD Id is not found. Allows the OCDid to be passed as the message.
    """

    def __init__(self, message):
        super().__init__(message)
        self.message = message


class OCDIdParsingError(Error):
    """
    Raised when an error is encountered parsing an OCDid string.
    """
    def __init__(self, message):
        super().__init__(message)
        self.message = message