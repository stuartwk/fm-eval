## Codebase reference (Python, flat modules)

Use only these helpers. Do not redefine them in your file; import them from their modules.

Handlers are functions `handle_xxx(s, req)` returning a Response. `s` is the Server.
Stores: s.users, s.products, s.orders, s.reviews.
Each handlers module registers its routes in its own function, e.g.
`def order_routes(s, router): router.handle("GET /orders/{id}", partial(handle_get_order, s))`.
Every new handler must be registered with router.handle in its resource's routes function.

Request helpers (module request):
- `req.path_params["id"]` reads a path parameter like /orders/{id}; `req.query.get("name", "")` reads ?name=.
- `decode_body(req, SomeRequest)` returns a dataclass instance; on BadJSON respond 400 CODE_BAD_JSON "request body must be valid JSON".
- `body.validate()` raises `ValidationError("field", "reason")`; on it respond 422 CODE_VALIDATION_FAILED str(e).
- `parse_page(req)` returns PageParams; on BadQuery respond 400 CODE_BAD_QUERY str(e).
- `items, info = paginate(items, p)` then `return write_list(items, info)`.

Response helpers (module respond):
- `write_json(status, data)`
- `write_list(data, page_info)`
- `write_error(status, code, message)`
- `write_not_found(kind, id)` returns a 404 "kind id not found", e.g. write_not_found("order", id).
Error codes: CODE_BAD_JSON, CODE_BAD_QUERY, CODE_VALIDATION_FAILED, CODE_NOT_FOUND, CODE_CONFLICT.

Store methods (all return copies; get returns None when missing):
- UserStore: create(User) -> User, get(id), find_by_email(email), list(), delete(id) -> bool
- ProductStore: create(Product) -> Product, get(id), list()
- OrderStore: create(Order) -> Order, get(id), set_status(id, status) -> Order or None, list()
- ReviewStore: create(Review) -> Review, get(id), list_by_product(product_id) -> list
create assigns the ID; pass id="" when constructing.
Order statuses (module order_store): ORDER_PENDING, ORDER_PAID, ORDER_CANCELLED.

Tests: unittest.TestCase classes; table-driven with a list of dict cases and
`with self.subTest(c["name"]):`.
