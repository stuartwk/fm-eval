package shop

import "testing"

func TestHiddenProductStoreAdjustStock(t *testing.T) {
	tests := []struct {
		name      string
		id        string
		delta     int
		wantOK    bool
		wantStock int
	}{
		{name: "add", id: "prd_000001", delta: 5, wantOK: true, wantStock: 15},
		{name: "remove", id: "prd_000001", delta: -4, wantOK: true, wantStock: 6},
		{name: "to zero", id: "prd_000001", delta: -10, wantOK: true, wantStock: 0},
		{name: "below zero", id: "prd_000001", delta: -11, wantOK: false, wantStock: 10},
		{name: "missing", id: "prd_000099", delta: 1, wantOK: false},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			st := NewProductStore()
			st.Create(Product{Name: "Keyboard", PriceCents: 4999, Stock: 10})
			got, ok := st.AdjustStock(tt.id, tt.delta)
			if ok != tt.wantOK {
				t.Fatalf("ok = %v, want %v", ok, tt.wantOK)
			}
			if ok && got.Stock != tt.wantStock {
				t.Fatalf("returned stock = %d, want %d", got.Stock, tt.wantStock)
			}
			if tt.id == "prd_000001" {
				if stored, _ := st.Get(tt.id); stored.Stock != tt.wantStock {
					t.Fatalf("stored stock = %d, want %d", stored.Stock, tt.wantStock)
				}
			}
		})
	}
}
