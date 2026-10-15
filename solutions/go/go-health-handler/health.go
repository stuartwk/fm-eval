package shop

import "net/http"

func (s *Server) healthRoutes(mux *http.ServeMux) {
	mux.HandleFunc("GET /healthz", s.handleHealth)
}

type healthResponse struct {
	Status   string `json:"status"`
	Users    int    `json:"users"`
	Products int    `json:"products"`
	Orders   int    `json:"orders"`
}

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, healthResponse{
		Status:   "ok",
		Users:    len(s.users.List()),
		Products: len(s.products.List()),
		Orders:   len(s.orders.List()),
	})
}
