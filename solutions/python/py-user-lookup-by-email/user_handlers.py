"""HTTP handlers for users."""

from dataclasses import dataclass
from functools import partial

from request import BadJSON, BadQuery, ValidationError, decode_body, paginate, parse_page
from respond import (CODE_BAD_JSON, CODE_BAD_QUERY, CODE_CONFLICT, CODE_VALIDATION_FAILED, Response,
                     write_error, write_json, write_list, write_not_found)
from user_store import User


def user_routes(s, router):
    router.handle("GET /users", partial(handle_list_users, s))
    router.handle("GET /users/{id}", partial(handle_get_user, s))
    router.handle("GET /users/lookup", partial(handle_lookup_user, s))
    router.handle("POST /users", partial(handle_create_user, s))
    router.handle("DELETE /users/{id}", partial(handle_delete_user, s))


@dataclass
class CreateUserRequest:
    email: str = ""
    name: str = ""

    def validate(self):
        if not self.email.strip():
            raise ValidationError("email", "is required")
        if "@" not in self.email:
            raise ValidationError("email", "must contain @")
        if not self.name.strip():
            raise ValidationError("name", "is required")
        if len(self.name) > 80:
            raise ValidationError("name", "must be at most 80 characters")


def handle_list_users(s, req):
    try:
        p = parse_page(req)
    except BadQuery as e:
        return write_error(400, CODE_BAD_QUERY, str(e))
    items, info = paginate(s.users.list(), p)
    return write_list(items, info)


def handle_get_user(s, req):
    id = req.path_params["id"]
    user = s.users.get(id)
    if user is None:
        return write_not_found("user", id)
    return write_json(200, user)


def handle_create_user(s, req):
    try:
        body = decode_body(req, CreateUserRequest)
    except BadJSON:
        return write_error(400, CODE_BAD_JSON, "request body must be valid JSON")
    try:
        body.validate()
    except ValidationError as e:
        return write_error(422, CODE_VALIDATION_FAILED, str(e))
    if s.users.find_by_email(body.email) is not None:
        return write_error(409, CODE_CONFLICT, "email already registered")
    user = s.users.create(User(id="", email=body.email, name=body.name))
    return write_json(201, user)


def handle_delete_user(s, req):
    id = req.path_params["id"]
    if not s.users.delete(id):
        return write_not_found("user", id)
    return Response(204, "")


def handle_lookup_user(s, req):
    email = req.query.get("email", "")
    if not email:
        return write_error(400, CODE_BAD_QUERY, "email is required")
    user = s.users.find_by_email(email)
    if user is None:
        return write_not_found("user", email)
    return write_json(200, user)
