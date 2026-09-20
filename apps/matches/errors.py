from rest_framework.exceptions import APIException


class GameAPIError(APIException):
    status_code = 409
    default_code = "match_not_active"

    def __init__(self, code: str, message: str, *, status_code: int = 409) -> None:
        self.default_code = code
        self.status_code = status_code
        super().__init__(message, code=code)
