"""HTTP handlers for product reviews."""

from dataclasses import dataclass
from functools import partial

from request import BadJSON, BadQuery, ValidationError, decode_body, paginate, parse_page
from respond import (CODE_BAD_JSON, CODE_BAD_QUERY, CODE_VALIDATION_FAILED, write_error, write_json, write_list,
                     write_not_found)
from review_store import Review


def review_routes(s, router):
    router.handle("GET /products/{id}/reviews", partial(handle_list_product_reviews, s))
    router.handle("POST /products/{id}/reviews", partial(handle_create_review, s))


@dataclass
class CreateReviewRequest:
    user_id: str = ""
    rating: int = 0
    body: str = ""

    def validate(self):
        if not self.user_id:
            raise ValidationError("user_id", "is required")
        if not 1 <= self.rating <= 5:
            raise ValidationError("rating", "must be from 1 to 5")
        if len(self.body) > 500:
            raise ValidationError("body", "must be at most 500 characters")


def handle_list_product_reviews(s, req):
    id = req.path_params["id"]
    if s.products.get(id) is None:
        return write_not_found("product", id)
    try:
        p = parse_page(req)
    except BadQuery as e:
        return write_error(400, CODE_BAD_QUERY, str(e))
    items, info = paginate(s.reviews.list_by_product(id), p)
    return write_list(items, info)


def handle_create_review(s, req):
    id = req.path_params["id"]
    if s.products.get(id) is None:
        return write_not_found("product", id)
    try:
        body = decode_body(req, CreateReviewRequest)
    except BadJSON:
        return write_error(400, CODE_BAD_JSON, "request body must be valid JSON")
    try:
        body.validate()
    except ValidationError as e:
        return write_error(422, CODE_VALIDATION_FAILED, str(e))
    if s.users.get(body.user_id) is None:
        return write_error(422, CODE_VALIDATION_FAILED, "user_id: unknown user")
    review = s.reviews.create(Review(id="", product_id=id, user_id=body.user_id, rating=body.rating, body=body.body))
    return write_json(201, review)
