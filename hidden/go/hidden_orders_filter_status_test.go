package shop

import (
	"net/http"
	"testing"
)

func TestHiddenListOrdersByStatus(t *testing.T) {
	tests := []struct {
		name      string
		query     string
		wantCode  int
		wantIDs   []string
		wantTotal int
	}{
		{name: "all", query: "", wantCode: http.StatusOK, wantIDs: []string{"ord_000001", "ord_000002"}, wantTotal: 2},
		{name: "paid", query: "?status=paid", wantCode: http.StatusOK, wantIDs: []string{"ord_000002"}, wantTotal: 1},
		{name: "pending", query: "?status=pending", wantCode: http.StatusOK, wantIDs: []string{"ord_000001"}, wantTotal: 1},
		{name: "cancelled none", query: "?status=cancelled", wantCode: http.StatusOK, wantIDs: []string{}, wantTotal: 0},
		{name: "with paging", query: "?status=paid&limit=1&offset=1", wantCode: http.StatusOK, wantIDs: []string{}, wantTotal: 1},
		{name: "bad status", query: "?status=shipped", wantCode: http.StatusBadRequest},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			s := newTestServer(t)
			rec := doRequest(t, s, "GET", "/orders"+tt.query, "")
			assertStatus(t, rec, tt.wantCode)
			if tt.wantCode != http.StatusOK {
				if got := errorCode(t, rec); got != codeBadQuery {
					t.Fatalf("error code = %q, want %q", got, codeBadQuery)
				}
				return
			}
			orders, page := decodeList[Order](t, rec)
			if page.Total != tt.wantTotal || len(orders) != len(tt.wantIDs) {
				t.Fatalf("got %d orders, page %+v; want %d, total %d", len(orders), page, len(tt.wantIDs), tt.wantTotal)
			}
			for i, o := range orders {
				if o.ID != tt.wantIDs[i] {
					t.Fatalf("orders[%d].ID = %q, want %q", i, o.ID, tt.wantIDs[i])
				}
			}
		})
	}
}
