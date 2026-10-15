package shop

import (
	"encoding/json"
	"net/http"
	"testing"
)

func TestHiddenCancelOrder(t *testing.T) {
	tests := []struct {
		name       string
		id         string
		wantCode   int
		wantErr    string
		wantMsg    string
		wantStatus string
	}{
		{name: "pending", id: "ord_000001", wantCode: http.StatusOK, wantStatus: orderCancelled},
		{name: "paid", id: "ord_000002", wantCode: http.StatusConflict, wantErr: codeConflict, wantStatus: orderPaid},
		{name: "missing", id: "ord_000099", wantCode: http.StatusNotFound, wantErr: codeNotFound, wantMsg: "order ord_000099 not found"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			s := newTestServer(t)
			rec := doRequest(t, s, "POST", "/orders/"+tt.id+"/cancel", "")
			assertStatus(t, rec, tt.wantCode)
			if tt.wantErr != "" {
				var env errorEnvelope
				json.Unmarshal(rec.Body.Bytes(), &env)
				if env.Error.Code != tt.wantErr || (tt.wantMsg != "" && env.Error.Message != tt.wantMsg) {
					t.Fatalf("error = %+v, want code %q message %q", env.Error, tt.wantErr, tt.wantMsg)
				}
			} else if got := decodeData[Order](t, rec); got.ID != tt.id || got.Status != orderCancelled {
				t.Fatalf("response = %+v, want cancelled %s", got, tt.id)
			}
			if tt.wantStatus != "" {
				if stored, _ := s.orders.Get(tt.id); stored.Status != tt.wantStatus {
					t.Fatalf("stored status = %q, want %q", stored.Status, tt.wantStatus)
				}
			}
		})
	}
}

func TestHiddenCancelOrderTwice(t *testing.T) {
	s := newTestServer(t)
	assertStatus(t, doRequest(t, s, "POST", "/orders/ord_000001/cancel", ""), http.StatusOK)
	rec := doRequest(t, s, "POST", "/orders/ord_000001/cancel", "")
	assertStatus(t, rec, http.StatusConflict)
	if got := errorCode(t, rec); got != codeConflict {
		t.Fatalf("error code = %q, want %q", got, codeConflict)
	}
}
