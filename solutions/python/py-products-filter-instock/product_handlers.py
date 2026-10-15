"""HTTP handlers for products."""

from dataclasses import dataclass
from functools import partial

from product_store import Product
from request import BadJSON, ValidationError, decode_body
from respond import CODE_BAD_JSON, CODE_BAD_QUERY, CODE_VALIDATION_FAILED, write_error, write_json, write_not_found


def product_routes(s, router):
    router.handle("GET /products", partial(handle_list_products, s))
    router.handle("GET /products/{id}", partial(handle_get_product, s))
    router.handle("POST /products", partial(handle_create_product, s))


@dataclass
class CreateProductRequest:
    name: str = ""
    price_cents: int = 0
    stock: int = 0

    def validate(self):
        if not self.name.strip():
            raise ValidationError("name", "is required")
        if self.price_cents <= 0:
            raise ValidationError("price_cents", "must be greater than 0")
        if self.stock < 0:
            raise ValidationError("stock", "must not be negative")


def handle_list_products(s, req):
    products = s.products.list()
    in_stock = req.query.get("in_stock", "")
    if in_stock in ("true", "false"):
        want = in_stock == "true"
        products = [p for p in products if (p.stock > 0) == want]
    elif in_stock != "":
        return write_error(400, CODE_BAD_QUERY, "in_stock must be true or false")
    return write_json(200, products)


def handle_get_product(s, req):
    id = req.path_params["id"]
    product = s.products.get(id)
    if product is None:
        return write_not_found("product", id)
    return write_json(200, product)


def handle_create_product(s, req):
    try:
        body = decode_body(req, CreateProductRequest)
    except BadJSON:
        return write_error(400, CODE_BAD_JSON, "request body must be valid JSON")
    try:
        body.validate()
    except ValidationError as e:
        return write_error(422, CODE_VALIDATION_FAILED, str(e))
    product = s.products.create(Product(id="", name=body.name, price_cents=body.price_cents, stock=body.stock))
    return write_json(201, product)
