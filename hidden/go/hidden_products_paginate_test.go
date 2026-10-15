package shop

import (
	"net/http"
	"testing"
)

func TestHiddenListProductsPaginated(t *testing.T) {
	tests := []struct {
		name     string
		query    string
		wantCode int
		wantErr  string
		wantIDs  []string
		wantPage pageInfo
	}{
		{name: "default", query: "", wantCode: http.StatusOK,
			wantIDs: []string{"prd_000001", "prd_000002", "prd_000003"}, wantPage: pageInfo{Limit: 20, Offset: 0, Total: 3}},
		{name: "limit", query: "?limit=2", wantCode: http.StatusOK,
			wantIDs: []string{"prd_000001", "prd_000002"}, wantPage: pageInfo{Limit: 2, Offset: 0, Total: 3}},
		{name: "offset", query: "?limit=2&offset=2", wantCode: http.StatusOK,
			wantIDs: []string{"prd_000003"}, wantPage: pageInfo{Limit: 2, Offset: 2, Total: 3}},
		{name: "past end", query: "?offset=10", wantCode: http.StatusOK,
			wantIDs: []string{}, wantPage: pageInfo{Limit: 20, Offset: 10, Total: 3}},
		{name: "bad limit", query: "?limit=500", wantCode: http.StatusBadRequest, wantErr: codeBadQuery},
		{name: "bad offset", query: "?offset=-2", wantCode: http.StatusBadRequest, wantErr: codeBadQuery},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			s := newTestServer(t)
			rec := doRequest(t, s, "GET", "/products"+tt.query, "")
			assertStatus(t, rec, tt.wantCode)
			if tt.wantErr != "" {
				if got := errorCode(t, rec); got != tt.wantErr {
					t.Fatalf("error code = %q, want %q", got, tt.wantErr)
				}
				return
			}
			products, page := decodeList[Product](t, rec)
			if page != tt.wantPage {
				t.Fatalf("page = %+v, want %+v", page, tt.wantPage)
			}
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
