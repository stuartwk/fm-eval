package shop

import (
	"net/http"
	"strings"
)

func (s *Server) productRoutes(mux *http.ServeMux) {
	mux.HandleFunc("GET /products", s.handleListProducts)
	mux.HandleFunc("GET /products/{id}", s.handleGetProduct)
	mux.HandleFunc("POST /products", s.handleCreateProduct)
}

type createProductRequest struct {
	Name       string `json:"name"`
	PriceCents int64  `json:"price_cents"`
	Stock      int    `json:"stock"`
}

func (req createProductRequest) validate() error {
	if strings.TrimSpace(req.Name) == "" {
		return validationError{"name", "is required"}
	}
	if req.PriceCents <= 0 {
		return validationError{"price_cents", "must be greater than 0"}
	}
	if req.Stock < 0 {
		return validationError{"stock", "must not be negative"}
	}
	return nil
}

func (s *Server) handleListProducts(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, s.products.List())
}

func (s *Server) handleGetProduct(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	p, ok := s.products.Get(id)
	if !ok {
		writeNotFound(w, "product", id)
		return
	}
	writeJSON(w, http.StatusOK, p)
}

func (s *Server) handleCreateProduct(w http.ResponseWriter, r *http.Request) {
	var req createProductRequest
	if err := decodeBody(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, codeBadJSON, "request body must be valid JSON")
		return
	}
	req.Name = strings.TrimSpace(req.Name)
	if err := req.validate(); err != nil {
		writeError(w, http.StatusUnprocessableEntity, codeValidationFailed, err.Error())
		return
	}
	p := s.products.Create(Product{Name: req.Name, PriceCents: req.PriceCents, Stock: req.Stock})
	writeJSON(w, http.StatusCreated, p)
}
