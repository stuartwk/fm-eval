package shop

import "testing"

func TestOrderStoreCreateAndGet(t *testing.T) {
	st := NewOrderStore()
	tests := []struct {
		name   string
		in     Order
		wantID string
	}{
		{name: "first", in: Order{UserID: "usr_000001", Status: orderPending}, wantID: "ord_000001"},
		{name: "second", in: Order{UserID: "usr_000002", Status: orderPaid}, wantID: "ord_000002"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := st.Create(tt.in)
			if got.ID != tt.wantID {
				t.Fatalf("ID = %q, want %q", got.ID, tt.wantID)
			}
			stored, ok := st.Get(tt.wantID)
			if !ok || stored.UserID != tt.in.UserID || stored.Status != tt.in.Status {
				t.Fatalf("Get(%q) = %+v, %v", tt.wantID, stored, ok)
			}
		})
	}
}

func TestOrderStoreSetStatus(t *testing.T) {
	st := NewOrderStore()
	st.Create(Order{UserID: "usr_000001", Status: orderPending})
	tests := []struct {
		name   string
		id     string
		status string
		wantOK bool
	}{
		{name: "existing", id: "ord_000001", status: orderPaid, wantOK: true},
		{name: "missing", id: "ord_000099", status: orderPaid, wantOK: false},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, ok := st.SetStatus(tt.id, tt.status)
			if ok != tt.wantOK {
				t.Fatalf("ok = %v, want %v", ok, tt.wantOK)
			}
			if !ok {
				return
			}
			if got.Status != tt.status {
				t.Fatalf("returned status = %q, want %q", got.Status, tt.status)
			}
			if stored, _ := st.Get(tt.id); stored.Status != tt.status {
				t.Fatalf("stored status = %q, want %q", stored.Status, tt.status)
			}
		})
	}
}

func TestOrderStoreList(t *testing.T) {
	st := NewOrderStore()
	for i := 0; i < 3; i++ {
		st.Create(Order{UserID: "usr_000001", Status: orderPending})
	}
	got := st.List()
	want := []string{"ord_000001", "ord_000002", "ord_000003"}
	if len(got) != len(want) {
		t.Fatalf("got %d orders, want %d", len(got), len(want))
	}
	for i, o := range got {
		if o.ID != want[i] {
			t.Fatalf("List()[%d].ID = %q, want %q", i, o.ID, want[i])
		}
	}
}
