package shop

import (
	"net/http"
	"testing"
)

func TestGetUser(t *testing.T) {
	tests := []struct {
		name     string
		id       string
		wantCode int
		wantErr  string
	}{
		{name: "found", id: "usr_000001", wantCode: http.StatusOK},
		{name: "missing", id: "usr_000099", wantCode: http.StatusNotFound, wantErr: codeNotFound},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			s := newTestServer(t)
			rec := doRequest(t, s, "GET", "/users/"+tt.id, "")
			assertStatus(t, rec, tt.wantCode)
			if tt.wantErr != "" {
				if got := errorCode(t, rec); got != tt.wantErr {
					t.Fatalf("error code = %q, want %q", got, tt.wantErr)
				}
				return
			}
			u := decodeData[User](t, rec)
			if u.ID != tt.id || u.Name != "Ada Lovelace" {
				t.Fatalf("got %+v", u)
			}
		})
	}
}

func TestListUsers(t *testing.T) {
	tests := []struct {
		name      string
		query     string
		wantCode  int
		wantIDs   []string
		wantTotal int
	}{
		{name: "default", query: "", wantCode: http.StatusOK, wantIDs: []string{"usr_000001", "usr_000002"}, wantTotal: 2},
		{name: "limit", query: "?limit=1", wantCode: http.StatusOK, wantIDs: []string{"usr_000001"}, wantTotal: 2},
		{name: "offset", query: "?offset=1", wantCode: http.StatusOK, wantIDs: []string{"usr_000002"}, wantTotal: 2},
		{name: "past end", query: "?offset=5", wantCode: http.StatusOK, wantIDs: []string{}, wantTotal: 2},
		{name: "bad limit", query: "?limit=0", wantCode: http.StatusBadRequest},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			s := newTestServer(t)
			rec := doRequest(t, s, "GET", "/users"+tt.query, "")
			assertStatus(t, rec, tt.wantCode)
			if tt.wantCode != http.StatusOK {
				return
			}
			users, page := decodeList[User](t, rec)
			if page.Total != tt.wantTotal || len(users) != len(tt.wantIDs) {
				t.Fatalf("got %d users, page %+v", len(users), page)
			}
			for i, u := range users {
				if u.ID != tt.wantIDs[i] {
					t.Fatalf("users[%d].ID = %q, want %q", i, u.ID, tt.wantIDs[i])
				}
			}
		})
	}
}

func TestCreateUser(t *testing.T) {
	tests := []struct {
		name     string
		body     string
		wantCode int
		wantErr  string
	}{
		{name: "ok", body: `{"email":"linus@example.com","name":"Linus"}`, wantCode: http.StatusCreated},
		{name: "bad json", body: `{"email":`, wantCode: http.StatusBadRequest, wantErr: codeBadJSON},
		{name: "unknown field", body: `{"email":"a@b.c","name":"A","age":3}`, wantCode: http.StatusBadRequest, wantErr: codeBadJSON},
		{name: "missing email", body: `{"name":"Linus"}`, wantCode: http.StatusUnprocessableEntity, wantErr: codeValidationFailed},
		{name: "email without at", body: `{"email":"linus","name":"Linus"}`, wantCode: http.StatusUnprocessableEntity, wantErr: codeValidationFailed},
		{name: "duplicate email", body: `{"email":"ADA@example.com","name":"Ada"}`, wantCode: http.StatusConflict, wantErr: codeConflict},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			s := newTestServer(t)
			rec := doRequest(t, s, "POST", "/users", tt.body)
			assertStatus(t, rec, tt.wantCode)
			if tt.wantErr != "" {
				if got := errorCode(t, rec); got != tt.wantErr {
					t.Fatalf("error code = %q, want %q", got, tt.wantErr)
				}
				return
			}
			if u := decodeData[User](t, rec); u.ID != "usr_000003" {
				t.Fatalf("ID = %q, want usr_000003", u.ID)
			}
		})
	}
}

func TestDeleteUser(t *testing.T) {
	s := newTestServer(t)
	assertStatus(t, doRequest(t, s, "DELETE", "/users/usr_000002", ""), http.StatusNoContent)
	assertStatus(t, doRequest(t, s, "GET", "/users/usr_000002", ""), http.StatusNotFound)
	assertStatus(t, doRequest(t, s, "DELETE", "/users/usr_000002", ""), http.StatusNotFound)
}
