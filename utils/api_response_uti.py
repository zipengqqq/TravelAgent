from starlette.responses import JSONResponse


def build_response(data) -> JSONResponse:
    return JSONResponse(status_code=200, content={'data': data, 'message': 'success'},)

def success_response():
    return JSONResponse(status_code=200, content={'message': 'success'})
