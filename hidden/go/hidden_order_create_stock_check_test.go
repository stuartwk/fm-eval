package shop

import (
	"encoding/json"
	"net/http"
	"testing"
)

func TestHiddenCreateOrderStockCheck(t *testing.T) {
	tests := []struct {
		name     string
		body     string
		wantCode int
		wantMsg  string
	}{
		{name: "exactly in stock", body: `{"user_id":"usr_000001","items":[{"product_id":"prd_000003","quantity":3}]}`, wantCode: http.StatusCreated},
		{name: "over stock", body: `{"user_id":"usr_000001","items":[{"product_id":"prd_000003","quantity":4}]}`,
			wantCode: http.StatusUnprocessableEntity, wantMsg: "items[0].quantity: exceeds stock"},
		{name: "out of stock second item", body: `{"user_id":"usr_000001","items":[{"product_id":"prd_000001","quantity":1},{"product_id":"prd_000002","quantity":1}]}`,
			wantCode: http.StatusUnprocessableEntity, wantMsg: "items[1].quantity: exceeds stock"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			s := newTestServer(t)
			rec := doRequest(t, s, "POST", "/orders", tt.body)
			assertStatus(t, rec, tt.wantCode)
			if tt.wantMsg == "" {
				return
			}
			var env errorEnvelope
			json.Unmarshal(rec.Body.Bytes(), &env)
			if env.Error.Code != codeValidationFailed || env.Error.Message != tt.wantMsg {
				t.Fatalf("error = %+v, want %q %q", env.Error, codeValidationFailed, tt.wantMsg)
			}
			if got := len(s.orders.List()); got != 2 {
				t.Fatalf("an order was stored despite the error (%d orders)", got)
			}
		})
	}
}
