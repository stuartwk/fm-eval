"""Server holds every store; Router dispatches requests to handlers."""

from order_store import OrderStore
from product_store import ProductStore
from respond import Response
from review_store import ReviewStore
from user_store import UserStore


class Router:
    """Matches patterns like "GET /users/{id}". Literal path segments win
    over {param} segments. Unmatched requests get a plain 404."""

    def __init__(self):
        self.routes = []

    def handle(self, pattern, handler):
        method, path = pattern.split(" ", 1)
        self.routes.append((method, path.strip("/").split("/"), handler))

    def serve(self, req):
        parts = req.path.strip("/").split("/")
        best = None
        for method, segs, handler in self.routes:
            if method != req.method or len(segs) != len(parts):
                continue
            params, literals = {}, 0
            for seg, part in zip(segs, parts):
                if seg.startswith("{") and seg.endswith("}"):
                    params[seg[1:-1]] = part
                elif seg == part:
                    literals += 1
                else:
                    break
            else:
                if best is None or literals > best[0]:
                    best = (literals, handler, params)
        if best is None:
            return Response(404, "404 page not found")
        req.path_params = best[2]
        return best[1](req)


class Server:
    """Holds every store. Handlers are functions taking (s, req)."""

    def __init__(self):
        self.users = UserStore()
        self.products = ProductStore()
        self.orders = OrderStore()
        self.reviews = ReviewStore()

    def routes(self):
        """Each resource registers its own routes in its handlers module."""
        from order_handlers import order_routes
        from product_handlers import product_routes
        from user_handlers import user_routes

        router = Router()
        user_routes(self, router)
        product_routes(self, router)
        order_routes(self, router)
        return router
