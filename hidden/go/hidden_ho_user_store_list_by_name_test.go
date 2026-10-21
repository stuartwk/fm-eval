package shop

import "testing"

func TestHiddenUserStoreListByName(t *testing.T) {
	st := NewUserStore()
	st.Create(User{Email: "a@example.com", Name: "Sam"})
	st.Create(User{Email: "b@example.com", Name: "Alex"})
	st.Create(User{Email: "c@example.com", Name: "Sam"})
	tests := []struct {
		name    string
		query   string
		wantIDs []string
	}{
		{"two", "Sam", []string{"usr_000001", "usr_000003"}},
		{"one", "Alex", []string{"usr_000002"}},
		{"exact only", "sam", []string{}},
		{"none", "Kim", []string{}},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := st.ListByName(tt.query)
			if got == nil {
				t.Fatal("ListByName returned nil, want an empty slice")
			}
			if len(got) != len(tt.wantIDs) {
				t.Fatalf("got %d users, want %d", len(got), len(tt.wantIDs))
			}
			for i, u := range got {
				if u.ID != tt.wantIDs[i] {
					t.Fatalf("got[%d].ID = %q, want %q", i, u.ID, tt.wantIDs[i])
				}
			}
		})
	}
}
