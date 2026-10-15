package shop

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestHiddenHealth(t *testing.T) {
	s := newTestServer(t)
	mux := http.NewServeMux()
	s.healthRoutes(mux)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, httptest.NewRequest("GET", "/healthz", nil))
	assertStatus(t, rec, http.StatusOK)
	got := decodeData[map[string]any](t, rec)
	want := map[string]any{"status": "ok", "users": 2.0, "products": 3.0, "orders": 2.0}
	for k, v := range want {
		if got[k] != v {
			t.Fatalf("data[%q] = %v, want %v (full: %v)", k, got[k], v, got)
		}
	}
}
