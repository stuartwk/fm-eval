package shop

import (
	"net/http"
	"testing"
)

func TestHiddenListProductsLowStock(t *testing.T) {
	tests := []struct {
		name     string
		query    string
		wantCode int
		wantIDs  []string
	}{
		{name: "all", query: "", wantCode: http.StatusOK, wantIDs: []string{"prd_000001", "prd_000002", "prd_000003"}},
		{name: "low", query: "?low_stock=true", wantCode: http.StatusOK, wantIDs: []string{"prd_000002", "prd_000003"}},
		{name: "not low", query: "?low_stock=false", wantCode: http.StatusOK, wantIDs: []string{"prd_000001"}},
		{name: "bad value", query: "?low_stock=maybe", wantCode: http.StatusBadRequest},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			s := newTestServer(t)
			rec := doRequest(t, s, "GET", "/products"+tt.query, "")
			assertStatus(t, rec, tt.wantCode)
			if tt.wantCode != http.StatusOK {
				if got := errorCode(t, rec); got != codeBadQuery {
					t.Fatalf("error code = %q, want %q", got, codeBadQuery)
				}
				return
			}
			products := decodeData[[]Product](t, rec)
			if len(products) != len(tt.wantIDs) {
				t.Fatalf("got %d products, want %d", len(products), len(tt.wantIDs))
			}
			for i, p := range products {
				if p.ID != tt.wantIDs[i] {
					t.Fatalf("products[%d].ID = %q, want %q", i, p.ID, tt.wantIDs[i])
				}
			}
		})
	}
}
