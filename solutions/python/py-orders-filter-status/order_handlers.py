"""HTTP handlers for orders."""

from dataclasses import dataclass, field
from functools import partial

from order_store import ORDER_CANCELLED, ORDER_PAID, ORDER_PENDING, Order, OrderItem
from request import BadJSON, BadQuery, ValidationError, decode_body, paginate, parse_page
from respond import CODE_BAD_JSON, CODE_BAD_QUERY, CODE_VALIDATION_FAILED, write_error, write_json, write_list


def order_routes(s, router):
    router.handle("GET /orders", partial(handle_list_orders, s))
    router.handle("POST /orders", partial(handle_create_order, s))


@dataclass
class CreateOrderRequest:
    user_id: str = ""
    items: list = field(default_factory=list)

    def validate(self):
        if not self.user_id:
            raise ValidationError("user_id", "is required")
        if not self.items:
            raise ValidationError("items", "must not be empty")
        for i, it in enumerate(self.items):
            if not isinstance(it, dict) or not it.get("product_id"):
                raise ValidationError(f"items[{i}].product_id", "is required")
            if not isinstance(it.get("quantity"), int) or it["quantity"] < 1:
                raise ValidationError(f"items[{i}].quantity", "must be at least 1")


def handle_list_orders(s, req):
    try:
        p = parse_page(req)
    except BadQuery as e:
        return write_error(400, CODE_BAD_QUERY, str(e))
    orders = s.orders.list()
    status = req.query.get("status", "")
    if status:
        if status not in (ORDER_PENDING, ORDER_PAID, ORDER_CANCELLED):
            return write_error(400, CODE_BAD_QUERY, "status must be one of pending, paid, cancelled")
        orders = [o for o in orders if o.status == status]
    items, info = paginate(orders, p)
    return write_list(items, info)


def handle_create_order(s, req):
    try:
        body = decode_body(req, CreateOrderRequest)
    except BadJSON:
        return write_error(400, CODE_BAD_JSON, "request body must be valid JSON")
    try:
        body.validate()
    except ValidationError as e:
        return write_error(422, CODE_VALIDATION_FAILED, str(e))
    if s.users.get(body.user_id) is None:
        return write_error(422, CODE_VALIDATION_FAILED, "user_id: unknown user")
    total = 0
    items = []
    for i, it in enumerate(body.items):
        product = s.products.get(it["product_id"])
        if product is None:
            return write_error(422, CODE_VALIDATION_FAILED, f"items[{i}].product_id: unknown product")
        total += product.price_cents * it["quantity"]
        items.append(OrderItem(product_id=it["product_id"], quantity=it["quantity"]))
    order = s.orders.create(Order(id="", user_id=body.user_id, items=items, total_cents=total, status=ORDER_PENDING))
    return write_json(201, order)
