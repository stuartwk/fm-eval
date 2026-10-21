package shop

import (
	"net/http"
	"testing"
)

func TestHiddenSearchProductsByName(t *testing.T) {
	tests := []struct {
		name     string
		query    string
		wantCode int
		wantID   string
	}{
		{"found", "?name=Mouse", http.StatusOK, "prd_000002"},
		{"exact only", "?name=mouse", http.StatusNotFound, ""},
		{"missing param", "", http.StatusBadRequest, ""},
		{"not found", "?name=Desk", http.StatusNotFound, ""},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			s := newTestServer(t)
			rec := doRequest(t, s, "GET", "/products/search"+tt.query, "")
			assertStatus(t, rec, tt.wantCode)
			switch tt.wantCode {
			case http.StatusOK:
				if p := decodeData[Product](t, rec); p.ID != tt.wantID {
					t.Fatalf("got %q, want %q", p.ID, tt.wantID)
				}
			case http.StatusBadRequest:
				if got := errorCode(t, rec); got != codeBadQuery {
					t.Fatalf("error code = %q, want %q", got, codeBadQuery)
				}
			case http.StatusNotFound:
				if got := errorCode(t, rec); got != codeNotFound {
					t.Fatalf("error code = %q, want %q", got, codeNotFound)
				}
			}
		})
	}
}
