package shop

import (
	"net/http"
	"testing"
)

func TestHiddenCreateOrderCleansUserID(t *testing.T) {
	tests := []struct {
		name     string
		userID   string
		wantCode int
		wantID   string
	}{
		{"padded upper case", " USR_000001 ", http.StatusCreated, "usr_000001"},
		{"upper case", "USR_000002", http.StatusCreated, "usr_000002"},
		{"already clean", "usr_000001", http.StatusCreated, "usr_000001"},
		{"blank", "   ", http.StatusUnprocessableEntity, ""},
		{"unknown", " USR_000009", http.StatusUnprocessableEntity, ""},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			s := newTestServer(t)
			body := `{"user_id": "` + tt.userID + `", "items": [{"product_id": "prd_000001", "quantity": 1}]}`
			rec := doRequest(t, s, "POST", "/orders", body)
			assertStatus(t, rec, tt.wantCode)
			if tt.wantCode != http.StatusCreated {
				return
			}
			o := decodeData[Order](t, rec)
			stored, _ := s.orders.Get(o.ID)
			if o.UserID != tt.wantID || stored.UserID != tt.wantID {
				t.Fatalf("user_id = %q (stored %q), want %q", o.UserID, stored.UserID, tt.wantID)
			}
		})
	}
}
