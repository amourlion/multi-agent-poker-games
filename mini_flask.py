"""Minimal Flask-compatible interface for offline testing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple


__all__ = ["Flask", "abort", "jsonify", "request"]


class HTTPException(Exception):
    def __init__(self, status_code: int, description: str | None = None) -> None:
        super().__init__(description or "HTTP Exception")
        self.status_code = status_code
        self.description = description or ""


@dataclass
class Response:
    payload: Any
    status_code: int = 200

    def get_json(self) -> Any:
        return self.payload


@dataclass
class Request:
    method: str
    path: str
    json_data: Any

    def get_json(self, force: bool = False, silent: bool = False) -> Any:
        if self.json_data is None and not force and not silent:
            raise ValueError("No JSON body")
        return self.json_data


request: Request | None = None


class Route:
    def __init__(self, method: str, rule: str, func: Callable[..., Any]) -> None:
        self.method = method.upper()
        self.rule = rule
        self.func = func
        self.parts = [part for part in rule.strip("/").split("/") if part]

    def matches(self, method: str, path: str) -> Optional[Dict[str, str]]:
        if method.upper() != self.method:
            return None
        parts = [part for part in path.strip("/").split("/") if part]
        if len(parts) != len(self.parts):
            return None
        params: Dict[str, str] = {}
        for route_part, path_part in zip(self.parts, parts):
            if route_part.startswith("<") and route_part.endswith(">"):
                key = route_part[1:-1]
                params[key] = path_part
            elif route_part != path_part:
                return None
        return params


class Flask:
    def __init__(self, name: str) -> None:
        self.name = name
        self._routes: List[Route] = []

    # Decorators -----------------------------------------------------
    def route(self, rule: str, methods: Optional[List[str]] = None) -> Callable:
        methods = methods or ["GET"]

        def decorator(func: Callable) -> Callable:
            for method in methods:
                self._routes.append(Route(method, rule, func))
            return func

        return decorator

    def post(self, rule: str) -> Callable:
        return self.route(rule, ["POST"])

    def get(self, rule: str) -> Callable:
        return self.route(rule, ["GET"])

    # Test client ----------------------------------------------------
    def test_client(self) -> "TestClient":
        return TestClient(self)

    # Internal request handling -------------------------------------
    def _handle_request(self, method: str, path: str, json_body: Any) -> Response:
        global request
        for route in self._routes:
            params = route.matches(method, path)
            if params is None:
                continue
            request = Request(method=method, path=path, json_data=json_body)
            try:
                result = route.func(**params)
            except HTTPException as exc:  # pragma: no cover - error path
                return Response({"error": exc.description}, status_code=exc.status_code)
            finally:
                request = None
            return self._ensure_response(result)
        return Response({"error": "Not Found"}, status_code=404)

    @staticmethod
    def _ensure_response(result: Any) -> Response:
        if isinstance(result, Response):
            return result
        if isinstance(result, tuple):
            resp, status = result
            response = Flask._ensure_response(resp)
            response.status_code = status
            return response
        if isinstance(result, dict):
            return Response(result)
        if result is None:
            return Response({}, status_code=204)
        return Response({"result": result})

    def run(self, host: str = "127.0.0.1", port: int = 5000) -> None:  # pragma: no cover
        print(f"MiniFlask dev server at http://{host}:{port}")


class TestClient:
    def __init__(self, app: Flask) -> None:
        self._app = app

    def post(self, path: str, json: Any | None = None) -> Response:
        return self._app._handle_request("POST", path, json)

    def get(self, path: str) -> Response:
        return self._app._handle_request("GET", path, None)


def jsonify(payload: Any) -> Response:
    return Response(payload)


def abort(status_code: int, description: str | None = None) -> None:
    raise HTTPException(status_code, description)
