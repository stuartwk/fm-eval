package shop

import (
	"net/http"
	"testing"
)

func TestGetProduct(t *testing.T) {
	tests := []struct {
		name     string
		id       string
		wantCode int
		wantErr  string
	}{
		{name: "found", id: "prd_000003", wantCode: http.StatusOK},
		{name: "missing", id: "prd_000099", wantCode: http.StatusNotFound, wantErr: codeNotFound},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			s := newTestServer(t)
			rec := doRequest(t, s, "GET", "/products/"+tt.id, "")
			assertStatus(t, rec, tt.wantCode)
			if tt.wantErr != "" {
				if got := errorCode(t, rec); got != tt.wantErr {
					t.Fatalf("error code = %q, want %q", got, tt.wantErr)
				}
				return
			}
			p := decodeData[Product](t, rec)
			if p.Name != "Monitor" || p.PriceCents != 18999 {
				t.Fatalf("got %+v", p)
			}
		})
	}
}

func TestListProducts(t *testing.T) {
	s := newTestServer(t)
	rec := doRequest(t, s, "GET", "/products", "")
	assertStatus(t, rec, http.StatusOK)
	products := decodeData[[]Product](t, rec)
	if len(products) != 3 || products[0].ID != "prd_000001" {
		t.Fatalf("got %+v", products)
	}
}

func TestCreateProduct(t *testing.T) {
	tests := []struct {
		name     string
		body     string
		wantCode int
		wantErr  string
	}{
		{name: "ok", body: `{"name":"Cable","price_cents":599,"stock":40}`, wantCode: http.StatusCreated},
		{name: "bad json", body: `[]`, wantCode: http.StatusBadRequest, wantErr: codeBadJSON},
		{name: "missing name", body: `{"price_cents":599}`, wantCode: http.StatusUnprocessableEntity, wantErr: codeValidationFailed},
		{name: "zero price", body: `{"name":"Cable","price_cents":0}`, wantCode: http.StatusUnprocessableEntity, wantErr: codeValidationFailed},
		{name: "negative stock", body: `{"name":"Cable","price_cents":599,"stock":-1}`, wantCode: http.StatusUnprocessableEntity, wantErr: codeValidationFailed},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			s := newTestServer(t)
			rec := doRequest(t, s, "POST", "/products", tt.body)
			assertStatus(t, rec, tt.wantCode)
			if tt.wantErr != "" {
				if got := errorCode(t, rec); got != tt.wantErr {
					t.Fatalf("error code = %q, want %q", got, tt.wantErr)
				}
				return
			}
			if p := decodeData[Product](t, rec); p.ID != "prd_000004" {
				t.Fatalf("ID = %q, want prd_000004", p.ID)
			}
		})
	}
}
