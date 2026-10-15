package shop

import (
	"encoding/json"
	"net/http"
	"testing"
)

func TestHiddenGetOrder(t *testing.T) {
	tests := []struct {
		name     string
		id       string
		wantCode int
		wantMsg  string
	}{
		{name: "found pending", id: "ord_000001", wantCode: http.StatusOK},
		{name: "found paid", id: "ord_000002", wantCode: http.StatusOK},
		{name: "missing", id: "ord_000099", wantCode: http.StatusNotFound, wantMsg: "order ord_000099 not found"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			s := newTestServer(t)
			rec := doRequest(t, s, "GET", "/orders/"+tt.id, "")
			assertStatus(t, rec, tt.wantCode)
			if tt.wantMsg != "" {
				var env errorEnvelope
				json.Unmarshal(rec.Body.Bytes(), &env)
				if env.Error.Code != codeNotFound || env.Error.Message != tt.wantMsg {
					t.Fatalf("error = %+v, want code %q message %q", env.Error, codeNotFound, tt.wantMsg)
				}
				return
			}
			want, _ := s.orders.Get(tt.id)
			got := decodeData[Order](t, rec)
			if got.ID != want.ID || got.UserID != want.UserID || got.TotalCents != want.TotalCents ||
				got.Status != want.Status || len(got.Items) != len(want.Items) {
				t.Fatalf("got %+v, want %+v", got, want)
			}
		})
	}
}
