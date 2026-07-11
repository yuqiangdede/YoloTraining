from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.exceptions import HTTPException


class SpaStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
        headers = {key.decode("latin-1").lower(): value.decode("latin-1") for key, value in scope.get("headers", [])}
        is_page_navigation = "text/html" in headers.get("accept", "")
        if is_page_navigation and not scope.get("path", "").startswith(("/api/", "/media/", "/docs", "/openapi.json")):
            return await super().get_response("index.html", scope)
        raise HTTPException(status_code=404)
