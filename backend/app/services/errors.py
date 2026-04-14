class AppServiceError(Exception):
    def __init__(self, code: int, detail: str, message: str | None = None):
        self.code = code
        self.detail = detail
        self.message = message
        super().__init__(detail)

