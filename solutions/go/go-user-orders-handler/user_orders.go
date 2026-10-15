package shop

import "net/http"

func (s *Server) userOrderRoutes(mux *http.ServeMux) {
	mux.HandleFunc("GET /users/{id}/orders", s.handleListUserOrders)
}

func (s *Server) handleListUserOrders(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	if _, ok := s.users.Get(id); !ok {
		writeNotFound(w, "user", id)
		return
	}
	p, err := parsePage(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, codeBadQuery, err.Error())
		return
	}
	orders := []Order{}
	for _, o := range s.orders.List() {
		if o.UserID == id {
			orders = append(orders, o)
		}
	}
	items, info := paginate(orders, p)
	writeList(w, items, info)
}
