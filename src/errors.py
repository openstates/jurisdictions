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