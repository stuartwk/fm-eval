"""HTTP handler listing one user's orders."""

from functools import partial

from request import BadQuery, paginate, parse_page
from respond import CODE_BAD_QUERY, write_error, write_list, write_not_found


def user_order_routes(s, router):
    router.handle("GET /users/{id}/orders", partial(handle_list_user_orders, s))


def handle_list_user_orders(s, req):
    id = req.path_params["id"]
    if s.users.get(id) is None:
        return write_not_found("user", id)
    try:
        p = parse_page(req)
    except BadQuery as e:
        return write_error(400, CODE_BAD_QUERY, str(e))
    orders = [o for o in s.orders.list() if o.user_id == id]
    items, info = paginate(orders, p)
    return write_list(items, info)
