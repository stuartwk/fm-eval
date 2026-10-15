package shop

import (
	"net/http"
	"testing"
)

func TestHiddenCreateUserNormalizesEmail(t *testing.T) {
	tests := []struct {
		name      string
		body      string
		wantCode  int
		wantEmail string
	}{
		{name: "lowercased and trimmed", body: `{"email":"  Linus@Example.COM ","name":"Linus"}`,
			wantCode: http.StatusCreated, wantEmail: "linus@example.com"},
		{name: "duplicate after trim", body: `{"email":" ADA@example.com ","name":"Ada"}`, wantCode: http.StatusConflict},
		{name: "blank after trim", body: `{"email":"   ","name":"Linus"}`, wantCode: http.StatusUnprocessableEntity},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			s := newTestServer(t)
			rec := doRequest(t, s, "POST", "/users", tt.body)
			assertStatus(t, rec, tt.wantCode)
			if tt.wantEmail == "" {
				return
			}
			got := decodeData[User](t, rec)
			stored, _ := s.users.Get(got.ID)
			if got.Email != tt.wantEmail || stored.Email != tt.wantEmail {
				t.Fatalf("email = %q (stored %q), want %q", got.Email, stored.Email, tt.wantEmail)
			}
		})
	}
}
