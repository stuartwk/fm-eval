package shop

import (
	"fmt"
	"net/http"
)

func (s *Server) orderRoutes(mux *http.ServeMux) {
	mux.HandleFunc("GET /orders", s.handleListOrders)
	mux.HandleFunc("POST /orders", s.handleCreateOrder)
}

type createOrderRequest struct {
	UserID string      `json:"user_id"`
	Items  []OrderItem `json:"items"`
}

func (req createOrderRequest) validate() error {
	if req.UserID == "" {
		return validationError{"user_id", "is required"}
	}
	if len(req.Items) == 0 {
		return validationError{"items", "must not be empty"}
	}
	for i, it := range req.Items {
		if it.ProductID == "" {
			return validationError{fmt.Sprintf("items[%d].product_id", i), "is required"}
		}
		if it.Quantity < 1 {
			return validationError{fmt.Sprintf("items[%d].quantity", i), "must be at least 1"}
		}
	}
	return nil
}

func (s *Server) handleListOrders(w http.ResponseWriter, r *http.Request) {
	p, err := parsePage(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, codeBadQuery, err.Error())
		return
	}
	items, info := paginate(s.orders.List(), p)
	writeList(w, items, info)
}

func (s *Server) handleCreateOrder(w http.ResponseWriter, r *http.Request) {
	var req createOrderRequest
	if err := decodeBody(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, codeBadJSON, "request body must be valid JSON")
		return
	}
	if err := req.validate(); err != nil {
		writeError(w, http.StatusUnprocessableEntity, codeValidationFailed, err.Error())
		return
	}
	if _, ok := s.users.Get(req.UserID); !ok {
		writeError(w, http.StatusUnprocessableEntity, codeValidationFailed, "user_id: unknown user")
		return
	}
	var total int64
	for i, it := range req.Items {
		p, ok := s.products.Get(it.ProductID)
		if !ok {
			writeError(w, http.StatusUnprocessableEntity, codeValidationFailed,
				fmt.Sprintf("items[%d].product_id: unknown product", i))
			return
		}
		total += p.PriceCents * int64(it.Quantity)
	}
	o := s.orders.Create(Order{UserID: req.UserID, Items: req.Items, TotalCents: total, Status: orderPending})
	writeJSON(w, http.StatusCreated, o)
}
