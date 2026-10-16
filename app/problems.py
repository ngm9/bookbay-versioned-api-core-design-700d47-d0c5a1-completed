from fastapi.responses import JSONResponse


def problem_response(
    *,
    status: int,
    code: str,
    title: str,
    detail: str,
    type_suffix: str,
    instance: str | None = None,
) -> JSONResponse:
    body: dict[str, object] = {
        "type": f"https://api.bookbay.example/problems/{type_suffix}",
        "title": title,
        "status": status,
        "code": code,
        "detail": detail,
    }
    if instance:
        body["instance"] = instance
    return JSONResponse(status_code=status, content=body, media_type="application/problem+json")
