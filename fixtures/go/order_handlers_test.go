package shop

import (
	"net/http"
	"testing"
)

func TestListOrders(t *testing.T) {
	s := newTestServer(t)
	rec := doRequest(t, s, "GET", "/orders?limit=1&offset=1", "")
	assertStatus(t, rec, http.StatusOK)
	orders, page := decodeList[Order](t, rec)
	if len(orders) != 1 || orders[0].ID != "ord_000002" || page.Total != 2 {
		t.Fatalf("got %+v, page %+v", orders, page)
	}
}

func TestCreateOrder(t *testing.T) {
	tests := []struct {
		name      string
		body      string
		wantCode  int
		wantErr   string
		wantTotal int64
	}{
		{
			name:      "ok",
			body:      `{"user_id":"usr_000002","items":[{"product_id":"prd_000001","quantity":2},{"product_id":"prd_000003","quantity":1}]}`,
			wantCode:  http.StatusCreated,
			wantTotal: 2*4999 + 18999,
		},
		{name: "bad json", body: `nope`, wantCode: http.StatusBadRequest, wantErr: codeBadJSON},
		{name: "no items", body: `{"user_id":"usr_000001","items":[]}`, wantCode: http.StatusUnprocessableEntity, wantErr: codeValidationFailed},
		{name: "zero quantity", body: `{"user_id":"usr_000001","items":[{"product_id":"prd_000001","quantity":0}]}`, wantCode: http.StatusUnprocessableEntity, wantErr: codeValidationFailed},
		{name: "unknown user", body: `{"user_id":"usr_000099","items":[{"product_id":"prd_000001","quantity":1}]}`, wantCode: http.StatusUnprocessableEntity, wantErr: codeValidationFailed},
		{name: "unknown product", body: `{"user_id":"usr_000001","items":[{"product_id":"prd_000099","quantity":1}]}`, wantCode: http.StatusUnprocessableEntity, wantErr: codeValidationFailed},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			s := newTestServer(t)
			rec := doRequest(t, s, "POST", "/orders", tt.body)
			assertStatus(t, rec, tt.wantCode)
			if tt.wantErr != "" {
				if got := errorCode(t, rec); got != tt.wantErr {
					t.Fatalf("error code = %q, want %q", got, tt.wantErr)
				}
				return
			}
			o := decodeData[Order](t, rec)
			if o.ID != "ord_000003" || o.TotalCents != tt.wantTotal || o.Status != orderPending {
				t.Fatalf("got %+v", o)
			}
		})
	}
}
