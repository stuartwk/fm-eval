package shop

import "net/http"

func (s *Server) reviewRoutes(mux *http.ServeMux) {
	mux.HandleFunc("GET /products/{id}/reviews", s.handleListProductReviews)
	mux.HandleFunc("POST /products/{id}/reviews", s.handleCreateReview)
}

type createReviewRequest struct {
	UserID string `json:"user_id"`
	Rating int    `json:"rating"`
	Body   string `json:"body"`
}

func (req createReviewRequest) validate() error {
	if req.UserID == "" {
		return validationError{"user_id", "is required"}
	}
	if req.Rating < 1 || req.Rating > 5 {
		return validationError{"rating", "must be from 1 to 5"}
	}
	if len(req.Body) > 500 {
		return validationError{"body", "must be at most 500 characters"}
	}
	return nil
}

func (s *Server) handleListProductReviews(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	if _, ok := s.products.Get(id); !ok {
		writeNotFound(w, "product", id)
		return
	}
	p, err := parsePage(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, codeBadQuery, err.Error())
		return
	}
	items, info := paginate(s.reviews.ListByProduct(id), p)
	writeList(w, items, info)
}

func (s *Server) handleCreateReview(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	if _, ok := s.products.Get(id); !ok {
		writeNotFound(w, "product", id)
		return
	}
	var req createReviewRequest
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
	rv := s.reviews.Create(Review{ProductID: id, UserID: req.UserID, Rating: req.Rating, Body: req.Body})
	writeJSON(w, http.StatusCreated, rv)
}
