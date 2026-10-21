package shop

import (
	"net/http"
	"testing"
)

func TestHiddenListUsersByName(t *testing.T) {
	tests := []struct {
		name      string
		query     string
		wantIDs   []string
		wantTotal int
	}{
		{name: "all", query: "", wantIDs: []string{"usr_000001", "usr_000002"}, wantTotal: 2},
		{name: "match", query: "?name=Grace%20Hopper", wantIDs: []string{"usr_000002"}, wantTotal: 1},
		{name: "no match", query: "?name=Nobody", wantIDs: []string{}, wantTotal: 0},
		{name: "with paging", query: "?name=Ada%20Lovelace&offset=1", wantIDs: []string{}, wantTotal: 1},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			s := newTestServer(t)
			rec := doRequest(t, s, "GET", "/users"+tt.query, "")
			assertStatus(t, rec, http.StatusOK)
			users, page := decodeList[User](t, rec)
			if page.Total != tt.wantTotal || len(users) != len(tt.wantIDs) {
				t.Fatalf("got %d users, page %+v; want %d, total %d", len(users), page, len(tt.wantIDs), tt.wantTotal)
			}
			for i, u := range users {
				if u.ID != tt.wantIDs[i] {
					t.Fatalf("users[%d].ID = %q, want %q", i, u.ID, tt.wantIDs[i])
				}
			}
		})
	}
}
