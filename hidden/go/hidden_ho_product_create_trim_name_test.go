package shop

import (
	"net/http"
	"testing"
)

func TestHiddenCreateProductTrimsName(t *testing.T) {
	tests := []struct {
		name     string
		body     string
		wantCode int
		wantName string
	}{
		{"trimmed", `{"name": "  Desk Lamp \t", "price_cents": 2500, "stock": 4}`, http.StatusCreated, "Desk Lamp"},
		{"unchanged", `{"name": "Desk Lamp", "price_cents": 2500, "stock": 4}`, http.StatusCreated, "Desk Lamp"},
		{"blank", `{"name": "   ", "price_cents": 2500, "stock": 4}`, http.StatusUnprocessableEntity, ""},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			s := newTestServer(t)
			rec := doRequest(t, s, "POST", "/products", tt.body)
			assertStatus(t, rec, tt.wantCode)
			if tt.wantCode != http.StatusCreated {
				return
			}
			p := decodeData[Product](t, rec)
			stored, _ := s.products.Get(p.ID)
			if p.Name != tt.wantName || stored.Name != tt.wantName {
				t.Fatalf("name = %q (stored %q), want %q", p.Name, stored.Name, tt.wantName)
			}
		})
	}
}
