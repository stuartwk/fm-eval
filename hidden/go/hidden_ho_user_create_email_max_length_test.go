package shop

import (
	"encoding/json"
	"net/http"
	"strings"
	"testing"
)

func TestHiddenCreateUserEmailMaxLength(t *testing.T) {
	tests := []struct {
		name     string
		email    string
		wantCode int
	}{
		{"at limit", strings.Repeat("a", 242) + "@example.com", http.StatusCreated},
		{"over limit", strings.Repeat("a", 243) + "@example.com", http.StatusUnprocessableEntity},
		{"short", "new@example.com", http.StatusCreated},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			s := newTestServer(t)
			body, _ := json.Marshal(map[string]string{"email": tt.email, "name": "New User"})
			rec := doRequest(t, s, "POST", "/users", string(body))
			assertStatus(t, rec, tt.wantCode)
			if tt.wantCode == http.StatusUnprocessableEntity {
				if got := errorCode(t, rec); got != codeValidationFailed {
					t.Fatalf("error code = %q, want %q", got, codeValidationFailed)
				}
				if !strings.Contains(rec.Body.String(), "email: must be at most 254 characters") {
					t.Fatalf("body = %s, want the length message", rec.Body.String())
				}
			}
		})
	}
}
