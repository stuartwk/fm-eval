package shop

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
)

// validationError is returned by request validate() methods. Handlers turn
// it into a 422 with code validation_failed and message "field: reason".
type validationError struct {
	Field  string
	Reason string
}

func (e validationError) Error() string {
	return e.Field + ": " + e.Reason
}

// decodeBody decodes a JSON request body and rejects unknown fields.
func decodeBody(r *http.Request, dst any) error {
	dec := json.NewDecoder(r.Body)
	dec.DisallowUnknownFields()
	return dec.Decode(dst)
}

const (
	defaultLimit = 20
	maxLimit     = 100
)

type pageParams struct {
	Limit  int
	Offset int
}

type pageInfo struct {
	Limit  int `json:"limit"`
	Offset int `json:"offset"`
	Total  int `json:"total"`
}

// parsePage reads ?limit= and ?offset=. Handlers turn an error into a 400
// with code bad_query.
func parsePage(r *http.Request) (pageParams, error) {
	p := pageParams{Limit: defaultLimit}
	q := r.URL.Query()
	if v := q.Get("limit"); v != "" {
		n, err := strconv.Atoi(v)
		if err != nil || n < 1 || n > maxLimit {
			return p, fmt.Errorf("limit must be an integer from 1 to %d", maxLimit)
		}
		p.Limit = n
	}
	if v := q.Get("offset"); v != "" {
		n, err := strconv.Atoi(v)
		if err != nil || n < 0 {
			return p, fmt.Errorf("offset must be a non-negative integer")
		}
		p.Offset = n
	}
	return p, nil
}

// paginate slices items according to p. It never returns a nil slice, so
// an empty page encodes as [] rather than null.
func paginate[T any](items []T, p pageParams) ([]T, pageInfo) {
	info := pageInfo{Limit: p.Limit, Offset: p.Offset, Total: len(items)}
	if p.Offset >= len(items) {
		return []T{}, info
	}
	end := min(p.Offset+p.Limit, len(items))
	return items[p.Offset:end], info
}
