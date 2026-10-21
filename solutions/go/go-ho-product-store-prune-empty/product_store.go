package shop

import (
	"slices"
	"strings"
	"sync"
)

// Product prices are always integer cents, never floats.
type Product struct {
	ID         string `json:"id"`
	Name       string `json:"name"`
	PriceCents int64  `json:"price_cents"`
	Stock      int    `json:"stock"`
}

// ProductStore is an in-memory, concurrency-safe store of products.
type ProductStore struct {
	mu    sync.RWMutex
	items map[string]Product
	seq   int
}

func NewProductStore() *ProductStore {
	return &ProductStore{items: make(map[string]Product)}
}

// Create assigns the next ID, stores the product, and returns the stored copy.
func (st *ProductStore) Create(p Product) Product {
	st.mu.Lock()
	defer st.mu.Unlock()
	st.seq++
	p.ID = formatID("prd", st.seq)
	st.items[p.ID] = p
	return p
}

func (st *ProductStore) Get(id string) (Product, bool) {
	st.mu.RLock()
	defer st.mu.RUnlock()
	p, ok := st.items[id]
	return p, ok
}

// List returns all products sorted by ID.
func (st *ProductStore) List() []Product {
	st.mu.RLock()
	defer st.mu.RUnlock()
	out := make([]Product, 0, len(st.items))
	for _, p := range st.items {
		out = append(out, p)
	}
	slices.SortFunc(out, func(a, b Product) int { return strings.Compare(a.ID, b.ID) })
	return out
}

// PruneEmpty deletes every product with zero stock and reports how many it removed.
func (st *ProductStore) PruneEmpty() int {
	st.mu.Lock()
	defer st.mu.Unlock()
	n := 0
	for id, p := range st.items {
		if p.Stock == 0 {
			delete(st.items, id)
			n++
		}
	}
	return n
}
