class GymServerError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"Server returned error with status code: {status_code}")
        self.status_code = status_code


class GymRequestError(Exception):
    def __init__(self, code: int, msg: str) -> None:
        super().__init__(f"Request failed with code {code}: {msg}")
        self.msg = msg


class GymOverbookedError(GymRequestError):
    """
    Exception raised when one account has reached the maximum number of fields bookable
    for a single day -- which is 2 fields.
    """

    def __init__(self, code: int, msg: str) -> None:
        super().__init__(code, msg)  # 该项目超过每天可预约次数
        self.msg = f"Maximum number of bookable fields reached (code {code})"


class GymFieldOccupiedError(GymRequestError):
    """Exception raised when trying to book an already occupied field."""

    def __init__(self, code: int, msg: str) -> None:
        super().__init__(code, msg)  # 场地该时间段预约中 / 场地该时间段临时有安排
        self.msg = f"Field is already occupied (code {code})"


class GymRequestRateLimitedError(GymRequestError):
    """Exception raised when the request rate limit is exceeded."""

    def __init__(self, code: int, msg: str) -> None:
        super().__init__(code, msg)  # 请不要频繁提交订单
        self.msg = f"Request rate limit exceeded (code {code})"
