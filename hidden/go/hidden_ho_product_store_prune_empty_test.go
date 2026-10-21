package shop

import "testing"

func TestHiddenProductStorePruneEmpty(t *testing.T) {
	st := NewProductStore()
	st.Create(Product{Name: "A", PriceCents: 100, Stock: 0})
	st.Create(Product{Name: "B", PriceCents: 100, Stock: 2})
	st.Create(Product{Name: "C", PriceCents: 100, Stock: 0})
	if n := st.PruneEmpty(); n != 2 {
		t.Fatalf("PruneEmpty() = %d, want 2", n)
	}
	got := st.List()
	if len(got) != 1 || got[0].ID != "prd_000002" {
		t.Fatalf("List after prune = %+v, want only prd_000002", got)
	}
	if n := st.PruneEmpty(); n != 0 {
		t.Fatalf("second PruneEmpty() = %d, want 0", n)
	}
}
