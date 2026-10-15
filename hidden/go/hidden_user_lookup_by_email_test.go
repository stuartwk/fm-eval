package shop

import (
	"encoding/json"
	"net/http"
	"testing"
)

func TestHiddenLookupUserByEmail(t *testing.T) {
	tests := []struct {
		name     string
		query    string
		wantCode int
		wantID   string
		wantErr  string
		wantMsg  string
	}{
		{name: "found", query: "?email=grace@example.com", wantCode: http.StatusOK, wantID: "usr_000002"},
		{name: "case insensitive", query: "?email=ADA@example.com", wantCode: http.StatusOK, wantID: "usr_000001"},
		{name: "missing param", query: "", wantCode: http.StatusBadRequest, wantErr: codeBadQuery},
		{name: "not found", query: "?email=nobody@example.com", wantCode: http.StatusNotFound, wantErr: codeNotFound,
			wantMsg: "user nobody@example.com not found"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			s := newTestServer(t)
			rec := doRequest(t, s, "GET", "/users/lookup"+tt.query, "")
			assertStatus(t, rec, tt.wantCode)
			if tt.wantErr != "" {
				var env errorEnvelope
				json.Unmarshal(rec.Body.Bytes(), &env)
				if env.Error.Code != tt.wantErr || (tt.wantMsg != "" && env.Error.Message != tt.wantMsg) {
					t.Fatalf("error = %+v, want code %q message %q", env.Error, tt.wantErr, tt.wantMsg)
				}
				return
			}
			if u := decodeData[User](t, rec); u.ID != tt.wantID {
				t.Fatalf("ID = %q, want %q", u.ID, tt.wantID)
			}
		})
	}
}
