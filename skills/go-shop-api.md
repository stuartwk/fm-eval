## Codebase reference (package shop)

Use only these helpers. Do not redefine them in your file; they already exist.

Handlers are methods on *Server: `func (s *Server) handleXxx(w http.ResponseWriter, r *http.Request)`.
Stores: s.users, s.products, s.orders, s.reviews.
Each handlers file registers its routes in its own method, e.g. `func (s *Server) orderRoutes(mux *http.ServeMux)`.
Every new handler must be registered with mux.HandleFunc in its resource's routes method.

Request helpers:
- `id := r.PathValue("id")` reads a path parameter like /orders/{id}.
- `decodeBody(r, &req) error` decodes JSON; on error respond 400 codeBadJSON "request body must be valid JSON".
- `req.validate() error` returns `validationError{"field", "reason"}`; on error respond 422 codeValidationFailed err.Error().
- `parsePage(r) (pageParams, error)`; on error respond 400 codeBadQuery err.Error().
- `paginate(items, p) ([]T, pageInfo)` then `writeList(w, items, info)`.

Response helpers:
- `writeJSON(w, status, data)`
- `writeList(w, data, pageInfo)`
- `writeError(w, status, code, message)`
- `writeNotFound(w, kind, id)` writes 404 "kind id not found", e.g. writeNotFound(w, "order", id).
Error codes: codeBadJSON, codeBadQuery, codeValidationFailed, codeNotFound, codeConflict.

Store methods (all return copies; ok is false when missing):
- UserStore: Create(User) User, Get(id) (User, bool), FindByEmail(email) (User, bool), List() []User, Delete(id) bool
- ProductStore: Create(Product) Product, Get(id) (Product, bool), List() []Product
- OrderStore: Create(Order) Order, Get(id) (Order, bool), SetStatus(id, status) (Order, bool), List() []Order
- ReviewStore: Create(Review) Review, Get(id) (Review, bool), ListByProduct(productID) []Review
Create assigns the ID; never set ID yourself.
Order statuses: orderPending, orderPaid, orderCancelled.

Tests: package shop, `import "testing"` plus anything else you use; table-driven with
`tests := []struct{ name string; ... }` and `t.Run(tt.name, ...)`.
