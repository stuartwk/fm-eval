package shop

import (
	"encoding/json"
	"fmt"
	"net/http"
)

// Error codes used in the "code" field of every error response.
const (
	codeBadJSON          = "bad_json"
	codeBadQuery         = "bad_query"
	codeValidationFailed = "validation_failed"
	codeNotFound         = "not_found"
	codeConflict         = "conflict"
)

// All success responses wrap their payload in {"data": ...}.
type dataEnvelope struct {
	Data any `json:"data"`
}

// List responses add a "page" object next to "data".
type listEnvelope struct {
	Data any      `json:"data"`
	Page pageInfo `json:"page"`
}

// All error responses look like {"error": {"code": ..., "message": ...}}.
type errorEnvelope struct {
	Error apiError `json:"error"`
}

type apiError struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

func writeJSON(w http.ResponseWriter, status int, data any) {
	writeRaw(w, status, dataEnvelope{Data: data})
}

func writeList(w http.ResponseWriter, data any, page pageInfo) {
	writeRaw(w, http.StatusOK, listEnvelope{Data: data, Page: page})
}

func writeError(w http.ResponseWriter, status int, code, message string) {
	writeRaw(w, status, errorEnvelope{Error: apiError{Code: code, Message: message}})
}

// writeNotFound writes a 404 such as "user usr_000009 not found".
func writeNotFound(w http.ResponseWriter, kind, id string) {
	writeError(w, http.StatusNotFound, codeNotFound, fmt.Sprintf("%s %s not found", kind, id))
}

func writeRaw(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(v)
}
