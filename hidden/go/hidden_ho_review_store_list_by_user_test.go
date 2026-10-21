package shop

import "testing"

func TestHiddenReviewStoreListByUser(t *testing.T) {
	st := NewReviewStore()
	st.Create(Review{ProductID: "prd_000001", UserID: "usr_000002", Rating: 4})
	st.Create(Review{ProductID: "prd_000002", UserID: "usr_000001", Rating: 5})
	st.Create(Review{ProductID: "prd_000003", UserID: "usr_000002", Rating: 2})
	tests := []struct {
		name    string
		userID  string
		wantIDs []string
	}{
		{"two reviews", "usr_000002", []string{"rev_000001", "rev_000003"}},
		{"one review", "usr_000001", []string{"rev_000002"}},
		{"none", "usr_000009", []string{}},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := st.ListByUser(tt.userID)
			if got == nil {
				t.Fatal("ListByUser returned nil, want an empty slice")
			}
			if len(got) != len(tt.wantIDs) {
				t.Fatalf("got %d reviews, want %d", len(got), len(tt.wantIDs))
			}
			for i, rv := range got {
				if rv.ID != tt.wantIDs[i] {
					t.Fatalf("got[%d].ID = %q, want %q", i, rv.ID, tt.wantIDs[i])
				}
			}
		})
	}
}
