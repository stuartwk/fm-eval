package shop

import (
	"encoding/json"
	"net/http/httptest"
	"strings"
	"testing"
)

// newTestServer returns a server seeded with a fixed dataset:
//
//	usr_000001 Ada Lovelace  ada@example.com
//	usr_000002 Grace Hopper  grace@example.com
//	prd_000001 Keyboard      4999 cents, stock 10
//	prd_000002 Mouse         1999 cents, stock 0
//	prd_000003 Monitor      18999 cents, stock 3
//	ord_000001 usr_000001    2 x prd_000001, pending
//	ord_000002 usr_000002    1 x prd_000003, paid
func newTestServer(t *testing.T) *Server {
	t.Helper()
	s := NewServer()
	s.users.Create(User{Email: "ada@example.com", Name: "Ada Lovelace"})
	s.users.Create(User{Email: "grace@example.com", Name: "Grace Hopper"})
	s.products.Create(Product{Name: "Keyboard", PriceCents: 4999, Stock: 10})
	s.products.Create(Product{Name: "Mouse", PriceCents: 1999, Stock: 0})
	s.products.Create(Product{Name: "Monitor", PriceCents: 18999, Stock: 3})
	s.orders.Create(Order{UserID: "usr_000001", Items: []OrderItem{{"prd_000001", 2}}, TotalCents: 9998, Status: orderPending})
	s.orders.Create(Order{UserID: "usr_000002", Items: []OrderItem{{"prd_000003", 1}}, TotalCents: 18999, Status: orderPaid})
	return s
}

// doRequest sends a request through the server's full router.
func doRequest(t *testing.T, s *Server, method, path, body string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(method, path, strings.NewReader(body))
	rec := httptest.NewRecorder()
	s.Routes().ServeHTTP(rec, req)
	return rec
}

// decodeData decodes a {"data": ...} response into T.
func decodeData[T any](t *testing.T, rec *httptest.ResponseRecorder) T {
	t.Helper()
	var env struct {
		Data T `json:"data"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &env); err != nil {
		t.Fatalf("decode data: %v\nbody: %s", err, rec.Body.String())
	}
	return env.Data
}

// decodeList decodes a {"data": [...], "page": {...}} response.
func decodeList[T any](t *testing.T, rec *httptest.ResponseRecorder) ([]T, pageInfo) {
	t.Helper()
	var env struct {
		Data []T      `json:"data"`
		Page pageInfo `json:"page"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &env); err != nil {
		t.Fatalf("decode list: %v\nbody: %s", err, rec.Body.String())
	}
	return env.Data, env.Page
}

// errorCode returns error.code from an error response.
func errorCode(t *testing.T, rec *httptest.ResponseRecorder) string {
	t.Helper()
	var env errorEnvelope
	if err := json.Unmarshal(rec.Body.Bytes(), &env); err != nil {
		t.Fatalf("decode error: %v\nbody: %s", err, rec.Body.String())
	}
	return env.Error.Code
}

func assertStatus(t *testing.T, rec *httptest.ResponseRecorder, want int) {
	t.Helper()
	if rec.Code != want {
		t.Fatalf("status = %d, want %d\nbody: %s", rec.Code, want, rec.Body.String())
	}
}
