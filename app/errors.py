from fastapi.responses import JSONResponse


def not_found(resource: str, resource_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={
            "error": "not_found",
            "message": f"{resource} was not found",
            "resourceId": resource_id,
        },
    )


def forbidden(message: str = "You do not have permission for this operation") -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content={"error": "forbidden", "message": message},
    )


def bad_request(code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"error": code, "message": message},
    )
