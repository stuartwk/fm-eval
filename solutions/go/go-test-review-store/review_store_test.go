package shop

import "testing"

func TestReviewStoreCreate(t *testing.T) {
	st := NewReviewStore()
	tests := []struct {
		name   string
		in     Review
		wantID string
	}{
		{name: "first", in: Review{ProductID: "prd_000001", UserID: "usr_000001", Rating: 5}, wantID: "rev_000001"},
		{name: "second", in: Review{ProductID: "prd_000002", UserID: "usr_000001", Rating: 3}, wantID: "rev_000002"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := st.Create(tt.in)
			if got.ID != tt.wantID {
				t.Fatalf("ID = %q, want %q", got.ID, tt.wantID)
			}
			stored, ok := st.Get(tt.wantID)
			if !ok || stored != got {
				t.Fatalf("Get(%q) = %+v, %v", tt.wantID, stored, ok)
			}
		})
	}
}

func TestReviewStoreGetMissing(t *testing.T) {
	st := NewReviewStore()
	if _, ok := st.Get("rev_000001"); ok {
		t.Fatal("Get on empty store reported ok")
	}
}

func TestReviewStoreListByProduct(t *testing.T) {
	st := NewReviewStore()
	st.Create(Review{ProductID: "prd_000001", Rating: 5})
	st.Create(Review{ProductID: "prd_000002", Rating: 4})
	st.Create(Review{ProductID: "prd_000001", Rating: 2})
	st.Create(Review{ProductID: "prd_000001", Rating: 1})

	tests := []struct {
		name      string
		productID string
		wantIDs   []string
	}{
		{name: "filters and sorts", productID: "prd_000001", wantIDs: []string{"rev_000001", "rev_000003", "rev_000004"}},
		{name: "single", productID: "prd_000002", wantIDs: []string{"rev_000002"}},
		{name: "none", productID: "prd_000009", wantIDs: []string{}},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := st.ListByProduct(tt.productID)
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
