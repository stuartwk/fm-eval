package shop

import (
	"net/http"
	"strings"
)

func (s *Server) userRoutes(mux *http.ServeMux) {
	mux.HandleFunc("GET /users", s.handleListUsers)
	mux.HandleFunc("GET /users/{id}", s.handleGetUser)
	mux.HandleFunc("GET /users/lookup", s.handleLookupUser)
	mux.HandleFunc("POST /users", s.handleCreateUser)
	mux.HandleFunc("DELETE /users/{id}", s.handleDeleteUser)
}

type createUserRequest struct {
	Email string `json:"email"`
	Name  string `json:"name"`
}

func (req createUserRequest) validate() error {
	if strings.TrimSpace(req.Email) == "" {
		return validationError{"email", "is required"}
	}
	if !strings.Contains(req.Email, "@") {
		return validationError{"email", "must contain @"}
	}
	if strings.TrimSpace(req.Name) == "" {
		return validationError{"name", "is required"}
	}
	if len(req.Name) > 80 {
		return validationError{"name", "must be at most 80 characters"}
	}
	return nil
}

func (s *Server) handleListUsers(w http.ResponseWriter, r *http.Request) {
	p, err := parsePage(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, codeBadQuery, err.Error())
		return
	}
	items, info := paginate(s.users.List(), p)
	writeList(w, items, info)
}

func (s *Server) handleGetUser(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	u, ok := s.users.Get(id)
	if !ok {
		writeNotFound(w, "user", id)
		return
	}
	writeJSON(w, http.StatusOK, u)
}

func (s *Server) handleCreateUser(w http.ResponseWriter, r *http.Request) {
	var req createUserRequest
	if err := decodeBody(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, codeBadJSON, "request body must be valid JSON")
		return
	}
	if err := req.validate(); err != nil {
		writeError(w, http.StatusUnprocessableEntity, codeValidationFailed, err.Error())
		return
	}
	if _, exists := s.users.FindByEmail(req.Email); exists {
		writeError(w, http.StatusConflict, codeConflict, "email already registered")
		return
	}
	u := s.users.Create(User{Email: req.Email, Name: req.Name})
	writeJSON(w, http.StatusCreated, u)
}

func (s *Server) handleDeleteUser(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	if !s.users.Delete(id) {
		writeNotFound(w, "user", id)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (s *Server) handleLookupUser(w http.ResponseWriter, r *http.Request) {
	email := r.URL.Query().Get("email")
	if email == "" {
		writeError(w, http.StatusBadRequest, codeBadQuery, "email is required")
		return
	}
	u, ok := s.users.FindByEmail(email)
	if !ok {
		writeNotFound(w, "user", email)
		return
	}
	writeJSON(w, http.StatusOK, u)
}
