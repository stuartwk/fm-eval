package shop

import "testing"

func TestHiddenOrderStoreListByUser(t *testing.T) {
	st := NewOrderStore()
	st.Create(Order{UserID: "usr_000001", Status: orderPending})
	st.Create(Order{UserID: "usr_000002", Status: orderPending})
	st.Create(Order{UserID: "usr_000001", Status: orderPaid})
	tests := []struct {
		name    string
		user    string
		wantIDs []string
	}{
		{name: "two orders", user: "usr_000001", wantIDs: []string{"ord_000001", "ord_000003"}},
		{name: "one order", user: "usr_000002", wantIDs: []string{"ord_000002"}},
		{name: "none", user: "usr_000099", wantIDs: []string{}},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := st.ListByUser(tt.user)
			if got == nil {
				t.Fatal("ListByUser returned nil, want an empty slice")
			}
			if len(got) != len(tt.wantIDs) {
				t.Fatalf("got %d orders, want %d", len(got), len(tt.wantIDs))
			}
			for i, o := range got {
				if o.ID != tt.wantIDs[i] {
					t.Fatalf("got[%d].ID = %q, want %q", i, o.ID, tt.wantIDs[i])
				}
			}
		})
	}
}
