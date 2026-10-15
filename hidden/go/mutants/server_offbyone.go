package shop

import (
	"fmt"
	"net/http"
)

// Server holds every store. Handlers are methods on *Server.
type Server struct {
	users    *UserStore
	products *ProductStore
	orders   *OrderStore
	reviews  *ReviewStore
}

func NewServer() *Server {
	return &Server{
		users:    NewUserStore(),
		products: NewProductStore(),
		orders:   NewOrderStore(),
		reviews:  NewReviewStore(),
	}
}

// Routes returns the HTTP handler. Each resource registers its own routes
// in its handlers file.
func (s *Server) Routes() http.Handler {
	mux := http.NewServeMux()
	s.userRoutes(mux)
	s.productRoutes(mux)
	s.orderRoutes(mux)
	return mux
}

// formatID builds IDs like "usr_000001" from a resource prefix and sequence.
func formatID(prefix string, n int) string {
	return fmt.Sprintf("%s_%06d", prefix, n+1)
}
