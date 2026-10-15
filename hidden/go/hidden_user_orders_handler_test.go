package shop

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func hiddenUserOrdersRequest(t *testing.T, s *Server, path string) *httptest.ResponseRecorder {
	t.Helper()
	mux := http.NewServeMux()
	s.userOrderRoutes(mux)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, httptest.NewRequest("GET", path, nil))
	return rec
}

func TestHiddenListUserOrders(t *testing.T) {
	s := newTestServer(t)
	s.orders.Create(Order{UserID: "usr_000001", Items: []OrderItem{{"prd_000003", 1}}, TotalCents: 18999, Status: orderPending})
	tests := []struct {
		name     string
		path     string
		wantCode int
		wantErr  string
		wantIDs  []string
		wantPage pageInfo
	}{
		{name: "two orders", path: "/users/usr_000001/orders", wantCode: http.StatusOK,
			wantIDs: []string{"ord_000001", "ord_000003"}, wantPage: pageInfo{Limit: 20, Total: 2}},
		{name: "paged", path: "/users/usr_000001/orders?limit=1&offset=1", wantCode: http.StatusOK,
			wantIDs: []string{"ord_000003"}, wantPage: pageInfo{Limit: 1, Offset: 1, Total: 2}},
		{name: "other user", path: "/users/usr_000002/orders", wantCode: http.StatusOK,
			wantIDs: []string{"ord_000002"}, wantPage: pageInfo{Limit: 20, Total: 1}},
		{name: "missing user", path: "/users/usr_000099/orders", wantCode: http.StatusNotFound, wantErr: codeNotFound},
		{name: "bad query", path: "/users/usr_000001/orders?limit=0", wantCode: http.StatusBadRequest, wantErr: codeBadQuery},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			rec := hiddenUserOrdersRequest(t, s, tt.path)
			assertStatus(t, rec, tt.wantCode)
			if tt.wantErr != "" {
				if got := errorCode(t, rec); got != tt.wantErr {
					t.Fatalf("error code = %q, want %q", got, tt.wantErr)
				}
				return
			}
			orders, page := decodeList[Order](t, rec)
			if page != tt.wantPage || len(orders) != len(tt.wantIDs) {
				t.Fatalf("got %d orders, page %+v; want %d, %+v", len(orders), page, len(tt.wantIDs), tt.wantPage)
			}
			for i, o := range orders {
				if o.ID != tt.wantIDs[i] {
					t.Fatalf("orders[%d].ID = %q, want %q", i, o.ID, tt.wantIDs[i])
				}
			}
		})
	}
}
