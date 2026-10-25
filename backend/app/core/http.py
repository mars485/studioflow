from fastapi import HTTPException, Request


async def read_limited_body(request: Request, limit: int) -> bytes:
    length = request.headers.get("content-length")
    if length is not None:
        try:
            declared = int(length)
        except ValueError:
            raise HTTPException(400, "Некорректный Content-Length")
        if declared < 0:
            raise HTTPException(400, "Некорректный Content-Length")
        if declared > limit:
            raise HTTPException(413, "Тело запроса превышает допустимый размер")
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > limit:
            raise HTTPException(413, "Тело запроса превышает допустимый размер")
        data.extend(chunk)
    return bytes(data)
